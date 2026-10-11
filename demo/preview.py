"""Draw face boxes and landmarks on a preview image."""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw, ImageFont

import ix_payload


def _traits(item: dict) -> dict:
    traits = item.get("traits") if isinstance(item.get("traits"), dict) else None
    if traits is not None:
        return traits
    attrs = item.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


def _label(traits: dict) -> str:
    for key in ("deepfake", "Deepfake", "liveness2d", "Liveness2D", "kind", "Class", "ageYears", "Age", "gender", "Gender"):
        attr = traits.get(key)
        if isinstance(attr, dict):
            text = attr.get("result") or attr.get("value")
            if text not in (None, ""):
                text = str(text)
                if " · " in text:
                    text = text.split(" · ", 1)[0]
                return f"{key}: {text}"
        if attr not in (None, ""):
            return f"{key}: {attr}"
    return ""


def _color(traits: dict) -> tuple[int, int, int]:
    live = traits.get("deepfake") or traits.get("Deepfake") or traits.get("liveness2d") or traits.get("Liveness2D")
    value = ""
    if isinstance(live, dict):
        value = str(live.get("result") or live.get("value") or "")
    value = value.split(" · ", 1)[0].lower()
    if value in ("fake", "spoof"):
        return (220, 48, 48)
    if value in ("real",):
        return (36, 170, 78)
    return (48, 196, 214)


def _points(item: dict) -> list[dict]:
    pts = item.get("landmarks") if "landmarks" in item else item.get("facePoints")
    if not isinstance(pts, list):
        return []
    return [p for p in pts if isinstance(p, dict) and "x" in p and "y" in p]


def _box(item: dict) -> dict:
    region = item.get("box") if "box" in item else item.get("faceRegion")
    return region if isinstance(region, dict) else {}


def crop_region(image: Image.Image, region: Any, *, pad: float = 0.16) -> Image.Image | None:
    if image is None or not isinstance(region, dict):
        return None
    try:
        x = float(region["x"])
        y = float(region["y"])
        w = float(region["width"])
        h = float(region["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if w < 2 or h < 2:
        return None
    width, height = image.size
    px = w * pad
    py = h * pad
    left = max(0, int(x - px))
    top = max(0, int(y - py))
    right = min(width, int(x + w + px))
    bottom = min(height, int(y + h + py))
    if right - left < 2 or bottom - top < 2:
        return None
    return image.crop((left, top, right, bottom))


def jpeg_data_uri(image: Image.Image) -> str:
    from io import BytesIO
    import base64

    buf = BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def annotate(
    image: Image.Image,
    payload: dict | None,
    *,
    point_fill: tuple[int, int, int] = (255, 214, 64),
) -> Image.Image:
    if image.mode != "RGB":
        image = image.convert("RGB")
    canvas = image.copy()
    if not isinstance(payload, dict):
        return canvas
    view = ix_payload.face_view(payload)
    items = view.get("faces")
    if not isinstance(items, list) or not items:
        return canvas

    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size
    stroke = max(2, min(width, height) // 280)
    font = ImageFont.load_default()

    for item in items:
        if not isinstance(item, dict):
            continue
        traits = _traits(item)
        color = _color(traits)
        region = _box(item)
        try:
            x = float(region["x"])
            y = float(region["y"])
            w = float(region["width"])
            h = float(region["height"])
        except (KeyError, TypeError, ValueError):
            x = y = w = h = 0.0
        if w > 1 and h > 1:
            box = (x, y, x + w, y + h)
            draw.rectangle(box, outline=color, width=stroke)
            text = _label(traits)
            if text:
                tx, ty = x, max(0, y - 16)
                draw.rectangle((tx, ty, tx + 8 * len(text) + 6, ty + 14), fill=color)
                draw.text((tx + 3, ty), text, fill=(255, 255, 255), font=font)

        pts = _points(item)
        radius = max(2, stroke + 1)
        for pt in pts:
            px, py = float(pt["x"]), float(pt["y"])
            if not (0 <= px <= width and 0 <= py <= height):
                continue
            draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=point_fill, outline=point_fill)
    return canvas
