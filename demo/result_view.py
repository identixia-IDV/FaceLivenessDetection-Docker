"""Format FaceRecognitionSDK process JSON for the Gradio result tables."""

from __future__ import annotations

import json
from typing import Any

import ix_payload

THUMB_SIZE = 128
GALLERY_THUMB = 180


def as_thumb(image: Any, size: int = THUMB_SIZE):
    if image is None:
        return None
    try:
        from PIL import Image
        import numpy as np

        if isinstance(image, np.ndarray):
            image = Image.fromarray(image.astype("uint8"), "RGB")
        elif not hasattr(image, "resize"):
            image = Image.open(image).convert("RGB")
        else:
            image = image.convert("RGB")
        pic = image.copy()
        pic.thumbnail((size, size))
        canvas = Image.new("RGB", (size, size), (248, 248, 248))
        canvas.paste(pic, ((size - pic.width) // 2, (size - pic.height) // 2))
        return canvas
    except Exception:  # noqa: BLE001
        return None


PERSON_KEYS = ("ageYears", "gender", "emotion", "emotions")
FACE_KEYS = (
    "medicalMask",
    "glasses",
    "sunglasses",
    "eyesLeft",
    "eyesRight",
    "deepfake",
    "liveness2d",
)
QUALITY_KEYS = (
    "faceQuality",
    "blurLevel",
    "noiseLevel",
    "sharpness",
    "noise",
    "lighting",
    "flare",
    "tooDark",
    "tooLight",
    "faceGlare",
)


def dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def attr_value(attr: Any) -> str:
    if not isinstance(attr, dict):
        return cell(attr)
    value = attr.get("value")
    if value in (None, ""):
        value = attr.get("result")
    if isinstance(value, str) and " · " in value and attr.get("confidence") is not None:
        value = value.split(" · ", 1)[0]
    if isinstance(value, str) and "\n" in value:
        return value
    return cell(value)


def attr_confidence(attr: Any) -> str:
    if not isinstance(attr, dict):
        return ""
    if "liveness_score" in attr:
        return cell(attr.get("liveness_score"))
    if "confidence" not in attr:
        return ""
    return cell(attr.get("confidence"))


def _pose_text(pose: Any) -> str:
    if not isinstance(pose, dict):
        return cell(pose)
    parts = []
    for key in ("yaw", "pitch", "roll"):
        if key in pose and pose[key] is not None:
            parts.append(f"{key} {cell(pose[key])}°")
    return " · ".join(parts)


def _region_text(region: Any) -> str:
    if not isinstance(region, dict):
        return cell(region)
    x = region.get("x")
    y = region.get("y")
    w = region.get("width")
    h = region.get("height")
    if None in (x, y, w, h):
        return cell(region)
    return f"{cell(x)}, {cell(y)} · {cell(w)}×{cell(h)}"


def _landmark_count(points: Any) -> str:
    if not isinstance(points, list):
        return ""
    return f"{len(points)} points" if points else "none"


def _view(payload: dict | None) -> dict:
    return ix_payload.face_view(payload)


def engine_error(payload: dict) -> str | None:
    view = _view(payload)
    if view.get("licenseError"):
        return str(view.get("licenseError"))
    fault = view.get("fault")
    if isinstance(fault, dict) and fault.get("code") == "LICENSE":
        return str(fault.get("message") or "not licensed")
    if view.get("success") is False:
        return str(view.get("message") or "request failed")
    status = view.get("status")
    if status in (-1, 2):
        return str(view.get("message") or f"status {status}")
    return None


def _faces(view: dict) -> list:
    faces = view.get("faces")
    return faces if isinstance(faces, list) else []


def _face_id(face: dict, index: int = 0) -> Any:
    if "id" in face:
        return face.get("id")
    return face.get("faceId", index)


def _same_id(left: Any, right: Any) -> bool:
    if left == right:
        return True
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return str(left) == str(right)


def _open_pic(image: Any):
    if image is None:
        return None
    if hasattr(image, "crop"):
        return image
    try:
        from PIL import Image

        if not hasattr(image, "convert"):
            return Image.open(image).convert("RGB")
        return image.convert("RGB")
    except Exception:  # noqa: BLE001
        return None


def _thumb_img_html(pic: Any, face: dict | None) -> str:
    if pic is None or not isinstance(face, dict):
        return ""
    try:
        from preview import crop_region, jpeg_data_uri

        crop = crop_region(pic, _box(face))
        if crop is None:
            return ""
        return (
            f'<img src="{jpeg_data_uri(as_thumb(crop))}" '
            f'width="{THUMB_SIZE}" height="{THUMB_SIZE}" alt="">'
        )
    except Exception:  # noqa: BLE001
        return ""


def _detect_faces(view: dict) -> dict[Any, list]:
    detects = view.get("detects") if isinstance(view.get("detects"), list) else []
    by_id: dict[Any, list] = {}
    for item in detects:
        if not isinstance(item, dict):
            continue
        raw = item.get("faces")
        faces = [face for face in raw if isinstance(face, dict)] if isinstance(raw, list) else []
        by_id[item.get("imageId")] = faces
    return by_id


def _face_from_list(faces: list, face_id: Any):
    for index, face in enumerate(faces):
        if isinstance(face, dict) and _same_id(_face_id(face, index), face_id):
            return face
    try:
        index = int(face_id)
    except (TypeError, ValueError):
        return None
    if 0 <= index < len(faces) and isinstance(faces[index], dict):
        return faces[index]
    return None


def _box(face: dict) -> Any:
    return face.get("box") if "box" in face else face.get("faceRegion")


def _pose(face: dict) -> Any:
    return face.get("pose") if "pose" in face else face.get("facePose")


def _landmarks(face: dict) -> Any:
    return face.get("landmarks") if "landmarks" in face else face.get("facePoints")


def _traits(face: dict) -> dict:
    traits = face.get("traits") if isinstance(face.get("traits"), dict) else None
    if traits is not None:
        return traits
    attrs = face.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


def face_cards(image: Any, payload: dict | None, headers: tuple[str, str, str] = ("Field", "Value", "Confidence")) -> str:
    """Crop each detection, then the fields for that face."""
    import html as html_lib

    view = _view(payload)
    faces = _faces(view)
    if not faces:
        return '<p class="ix-empty">No detection to show.</p>'

    pic = image
    if pic is not None and not hasattr(pic, "crop"):
        try:
            from PIL import Image

            pic = Image.open(pic).convert("RGB") if not hasattr(pic, "convert") else pic
        except Exception:  # noqa: BLE001
            pic = None

    blocks: list[str] = []
    for index, face in enumerate(faces):
        if not isinstance(face, dict):
            continue
        traits = _traits(face)
        kind = attr_value(ix_payload.trait(face, "kind", "Class")) or "Face"
        title = f"{kind} {_face_id(face, index)}"
        crop = None
        if pic is not None:
            try:
                from preview import crop_region

                crop = crop_region(pic, _box(face))
            except Exception:  # noqa: BLE001
                crop = None
        img = ""
        if crop is not None:
            from preview import jpeg_data_uri

            img = (
                '<img class="ix-crop" alt="'
                + html_lib.escape(title)
                + '" src="'
                + jpeg_data_uri(crop)
                + '">'
            )
        rows = _face_rows(face)
        body = "".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html_lib.escape(str(row[0])),
                html_lib.escape(str(row[1])).replace("\n", "<br>"),
                html_lib.escape(str(row[2])),
            )
            for row in rows
        )
        head = "".join(f"<th>{html_lib.escape(name)}</th>" for name in headers)
        blocks.append(
            '<section class="ix-face">'
            + img
            + f"<h4>{html_lib.escape(title)}</h4>"
            + f"<table class=\"ix-face-table\"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
            + "</section>"
        )
    if not blocks:
        return '<p class="ix-empty">No detection to show.</p>'
    return (
        "<style>"
        ".ix-crop{display:block;width:168px;height:auto;margin:0 0 8px;border-radius:4px}"
        ".ix-face{margin:0 0 20px}"
        ".ix-face-table{border-collapse:collapse;width:100%}"
        ".ix-face-table th,.ix-face-table td{border-bottom:1px solid #ddd;padding:4px 8px;text-align:left;vertical-align:top}"
        "</style>"
        '<div class="ix-faces">' + "".join(blocks) + "</div>"
    )


def _face_rows(face: dict) -> list[list[str]]:
    face_id = _face_id(face, "")
    traits = _traits(face)
    kind = attr_value(ix_payload.trait(face, "kind", "Class")) or "Face"
    prefix = f"{kind} {face_id}"
    rows: list[list[str]] = []
    box = _box(face)
    if box is not None:
        rows.append(["Region", _region_text(box), ""])
    pose = _pose(face)
    if pose is not None:
        pose_text = _pose_text(pose)
        pose_dict = pose if isinstance(pose, dict) else {}
        if pose_text and any(pose_dict.get(key) not in (None, 0, 0.0) for key in ("yaw", "pitch", "roll")):
            rows.append(["Pose", pose_text, ""])
    rows.extend(_attr_groups("", traits))
    cleaned = []
    for row in rows:
        label = row[0]
        if label.startswith(" · "):
            label = label[3:]
        elif label.startswith(prefix + " · "):
            label = label[len(prefix) + 3 :]
        cleaned.append([label, row[1], row[2]])
    return cleaned


def detect_rows(payload: dict) -> list[list[str]]:
    rows: list[list[str]] = []
    for face in _faces(_view(payload)):
        if not isinstance(face, dict):
            continue
        if rows:
            rows.append(["", "", ""])
        rows.extend(_face_rows(face))
    return rows


def _attr_groups(prefix: str, attrs: dict) -> list[list[str]]:
    rows: list[list[str]] = []
    used: set[str] = set()

    def add_section(title: str, keys: tuple[str, ...]) -> None:
        present = [key for key in keys if key in attrs]
        if not present:
            return
        heading = f"{prefix} · {title}" if prefix else title
        rows.append([heading, "", ""])
        for key in present:
            rows.append([key, attr_value(attrs[key]), attr_confidence(attrs[key])])
            used.add(key)
            extra = attrs[key].get("info") if isinstance(attrs[key], dict) else None
            if extra:
                rows.append(["info", cell(extra), ""])
            if key in ("liveness2d", "Liveness2D") and isinstance(attrs[key], dict):
                attack = attrs[key].get("attack_type")
                if attack not in (None, ""):
                    rows.append(["attack_type", cell(attack), ""])
                scores = attrs[key].get("attack_type_scores")
                if isinstance(scores, dict) and scores:
                    rows.append(["attack_type_scores", cell(scores), ""])

    add_section("Person", PERSON_KEYS)
    add_section("Face", FACE_KEYS)
    add_section("Quality", QUALITY_KEYS)
    leftovers = [
        key
        for key in attrs
        if key not in used and key not in ("landmarkMode", "pointCount", "LandmarkMode", "PointCount")
    ]
    if leftovers:
        heading = f"{prefix} · More" if prefix else "More"
        rows.append([heading, "", ""])
        for key in leftovers:
            rows.append([key, attr_value(attrs[key]), attr_confidence(attrs[key])])
    return rows


def deepfake_kind(attr: Any) -> str:
    """Map engine deepfake.value (bool / 0-1 / REAL|FAKE) to fake|real|''."""
    if not isinstance(attr, dict):
        return ""
    raw = attr.get("value")
    if raw is None:
        raw = attr.get("result")
    if isinstance(raw, bool):
        return "fake" if raw else "real"
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return "fake" if raw == 1 else "real"
    text = str(raw or "").strip().lower()
    if " · " in text:
        text = text.split(" · ", 1)[0]
    if text in ("fake", "true", "1", "yes"):
        return "fake"
    if text in ("real", "false", "0", "no"):
        return "real"
    return ""


def _deepfake_headline(faces: list) -> str:
    """Official deepfake print: Deepfake True/False and Confidence."""
    picked: dict | None = None
    for face in faces:
        if not isinstance(face, dict):
            continue
        attr = ix_payload.trait(face, "deepfake", "Deepfake")
        if not isinstance(attr, dict):
            continue
        kind = deepfake_kind(attr)
        if not kind:
            continue
        picked = attr
        if kind == "fake":
            break
    if picked is None:
        return ""
    raw = picked.get("value")
    if raw is None:
        raw = picked.get("result")
    if isinstance(raw, bool):
        text = "1" if raw else "0"
    elif raw in (1, 1.0, "1", "true", "True"):
        text = "1"
    elif raw in (0, 0.0, "0", "false", "False"):
        text = "0"
    else:
        text = cell(raw)
    lines = [f"Deepfake: {text}"]
    conf = picked.get("confidence")
    if isinstance(conf, (int, float)):
        lines.append(f"Confidence: {conf:.6f}")
    extra = picked.get("info")
    if extra not in (None, ""):
        lines.append(f"info {cell(extra)}")
    return "\n\n".join(lines)


def _face_facts(face: dict) -> str:
    lines: list[str] = []
    for label, value, conf in _face_rows(face):
        if not value:
            continue
        extra = f" ({conf})" if conf else ""
        lines.append(f"{label}: {value}{extra}")
    return "\n".join(lines)


def first_crop(image: Any, payload: dict | None):
    faces = [face for face in _faces(_view(payload)) if isinstance(face, dict)]
    if not faces:
        return None
    pic = image
    if pic is not None and not hasattr(pic, "crop"):
        try:
            from PIL import Image

            pic = Image.open(pic).convert("RGB") if not hasattr(pic, "convert") else pic
        except Exception:  # noqa: BLE001
            pic = None
    if pic is None:
        return None
    try:
        from preview import crop_region

        return as_thumb(crop_region(pic, _box(faces[0])))
    except Exception:  # noqa: BLE001
        return None


def face_pairs_html(image: Any, payload: dict | None) -> str:
    """Crop on the left, fields for that crop on the right. No Face 0/1 labels."""
    import html as html_lib

    faces = [face for face in _faces(_view(payload)) if isinstance(face, dict)]
    if not faces:
        return ""

    pic = image
    if pic is not None and not hasattr(pic, "crop"):
        try:
            from PIL import Image

            pic = Image.open(pic).convert("RGB") if not hasattr(pic, "convert") else pic
        except Exception:  # noqa: BLE001
            pic = None

    blocks: list[str] = []
    for face in faces:
        crop = None
        if pic is not None:
            try:
                from preview import crop_region

                crop = crop_region(pic, _box(face))
            except Exception:  # noqa: BLE001
                crop = None
        img = ""
        if crop is not None:
            from preview import jpeg_data_uri

            img = (
                f'<img src="{jpeg_data_uri(as_thumb(crop))}" '
                f'width="{THUMB_SIZE}" height="{THUMB_SIZE}" alt="">'
            )
        facts = html_lib.escape(_face_facts(face)).replace("\n", "<br>")
        blocks.append(f'<tr><td valign="top">{img}</td><td valign="top">{facts}</td></tr>')
    return "<table>" + "".join(blocks) + "</table>"


def landmark_preview_html(image: Any, payload: dict | None) -> str:
    pic = image
    if pic is not None and not hasattr(pic, "crop"):
        try:
            from PIL import Image

            pic = Image.open(pic).convert("RGB") if not hasattr(pic, "convert") else pic
        except Exception:  # noqa: BLE001
            pic = None
    if pic is None:
        return ""
    from preview import annotate, jpeg_data_uri

    marked = annotate(pic, payload, point_fill=(220, 32, 32))
    width, height = marked.size
    return (
        f'<img src="{jpeg_data_uri(marked)}" width="{width}" height="{height}" alt="">'
    )


def format_detect(payload: dict, title: str = "Detect", noun: str = "face") -> tuple[str, list[list[str]], str]:
    view = _view(payload)
    err = engine_error(payload)
    raw = dumps(payload)
    if err:
        return f"**Error:** {err}", [], raw
    faces = [face for face in _faces(view) if isinstance(face, dict)]
    kind = (title or "").strip().lower()
    if kind.startswith("deepfake"):
        label = _deepfake_headline(faces)
        heading = f"## {label}" if label else "## NO FACE"
    elif kind.startswith("landmarks"):
        heading = "" if faces else "## NO FACE"
    elif not faces:
        heading = "## NO FACE"
    elif len(faces) == 1:
        heading = "## 1 face"
    else:
        heading = f"## {len(faces)} faces"
    return heading, detect_rows(payload), raw


def match_crops(image1: Any, image2: Any, payload: dict | None):
    view = _view(payload)
    by_id = _detect_faces(view)
    left_faces = by_id.get(0) or by_id.get("0") or []
    right_faces = by_id.get(1) or by_id.get("1") or []
    pairs = [item for item in _pairs(view) if isinstance(item, dict)]
    left_id = 0
    right_id = 0
    if pairs:
        left_id = pairs[0].get("leftFaceId", pairs[0].get("firstFaceId", 0))
        right_id = pairs[0].get("rightFaceId", pairs[0].get("secondFaceId", 0))
    left = _face_from_list(left_faces, left_id)
    right = _face_from_list(right_faces, right_id)

    def _one(image, face):
        pic = _open_pic(image)
        if pic is None:
            return None
        if isinstance(face, dict):
            try:
                from preview import crop_region

                crop = crop_region(pic, _box(face))
                if crop is not None:
                    return as_thumb(crop)
            except Exception:  # noqa: BLE001
                pass
        return as_thumb(pic)

    return _one(image1, left), _one(image2, right)


def format_deepfake_overall(fake: int, real: int, scored: int) -> str:
    if fake:
        return f"## FAKE\n\n{fake} fake / {scored} scored frames."
    if real:
        return f"## REAL\n\n{real} fake / {scored} scored frames."
    return "## NO FACE\n\nNo face scored."


def _pairs(view: dict) -> list:
    pairs = view.get("pairs")
    return pairs if isinstance(pairs, list) else []


def _pair_score(item: dict) -> Any:
    if "score" in item:
        return item.get("score")
    return item.get("similarity")


def _pair_right_image(item: dict) -> Any:
    if "rightImageId" in item:
        return item.get("rightImageId")
    return item.get("secondImageId")


MATCH_THRESHOLD = 0.67


def format_match(payload: dict) -> tuple[str, list[list[str]], str]:
    view = _view(payload)
    err = engine_error(payload)
    raw = dumps(payload)
    if err:
        return f"**Error:** {err}", [], raw
    matches = _pairs(view)
    detects = view.get("detects") if isinstance(view.get("detects"), list) else []
    rows: list[list[str]] = []
    found: list[str] = []
    missing: list[str] = []
    for item in detects:
        if not isinstance(item, dict):
            continue
        faces = item.get("faces") if isinstance(item.get("faces"), list) else []
        status = item.get("status")
        image_id = item.get("imageId", "")
        label = "face found" if status == 0 and faces else "no face"
        rows.append([f"Image {image_id}", label, cell(status)])
        slot = "Image A" if image_id in (0, "0", "") else "Image B" if image_id in (1, "1") else f"Image {image_id}"
        if label == "face found":
            found.append(slot)
        else:
            missing.append(slot)
    for item in matches:
        if not isinstance(item, dict):
            continue
        left_image = item.get("leftImageId", item.get("firstImageId"))
        right_image = item.get("rightImageId", item.get("secondImageId"))
        left_face = item.get("leftFaceId", item.get("firstFaceId"))
        right_face = item.get("rightFaceId", item.get("secondFaceId"))
        pair = f"img {left_image} face {left_face} ↔ img {right_image} face {right_face}"
        rows.append(["Score", pair, cell(_pair_score(item))])
    if not matches:
        rows.append(["Score", "—", "no pair"])
    best = _best_score(matches)
    if missing:
        bits = [f"{name}: {'face found' if name in found else 'no face'}." for name in ("Image A", "Image B")]
        extra = [f"{name}: no face." for name in missing if name not in ("Image A", "Image B")]
        summary = "## NO FACE\n\n" + " ".join(bits + extra)
    elif best is None:
        summary = "## NO SCORE\n\nNo pair to compare."
    elif best >= MATCH_THRESHOLD:
        summary = (
            f"## SAME PERSON\n\nScore {cell(best)} — at or above 0.67, treated as the same person."
        )
    else:
        summary = (
            f"## DIFFERENT PEOPLE\n\nScore {cell(best)} — below 0.67, treated as different people."
        )
    if len(matches) > 1 and not missing and best is not None:
        summary += f"\n\nBest of {len(matches)} pairs."
    return summary, rows, raw


def match_pairs_html(image1: Any, image2: Any, payload: dict | None) -> str:
    """Crop A, crop B, and the score for every compared pair."""
    import html as html_lib

    view = _view(payload)
    by_id = _detect_faces(view)
    left_faces = by_id.get(0) or by_id.get("0") or []
    right_faces = by_id.get(1) or by_id.get("1") or []
    pic1 = _open_pic(image1)
    pic2 = _open_pic(image2)
    blocks: list[str] = []
    for item in _pairs(view):
        if not isinstance(item, dict):
            continue
        left = _face_from_list(left_faces, item.get("leftFaceId", item.get("firstFaceId")))
        right = _face_from_list(right_faces, item.get("rightFaceId", item.get("secondFaceId")))
        score = _pair_score(item)
        if isinstance(score, (int, float)):
            if score >= MATCH_THRESHOLD:
                title = "SAME PERSON"
                line = f"Score {cell(score)} — at or above 0.67, treated as the same person."
            else:
                title = "DIFFERENT PEOPLE"
                line = f"Score {cell(score)} — below 0.67, treated as different people."
        else:
            title = "NO SCORE"
            line = "No pair to compare."
        facts = html_lib.escape(f"{title}\n{line}").replace("\n", "<br>")
        blocks.append(
            f'<tr><td valign="top">{_thumb_img_html(pic1, left)}</td>'
            f'<td valign="top">{_thumb_img_html(pic2, right)}</td>'
            f'<td valign="top">{facts}</td></tr>'
        )
    return "<table>" + "".join(blocks) + "</table>" if blocks else ""


def _liveness_decision(face: dict, view: dict | None = None) -> tuple[str, str]:
    live = ix_payload.trait(face, "liveness2d", "Liveness2D")
    if not isinstance(live, dict) and isinstance(view, dict):
        live = view.get("liveness") if isinstance(view.get("liveness"), dict) else None
    if not isinstance(live, dict):
        return "NO FACE", "No liveness result"
    verdict = live.get("value") or live.get("result") or ""
    heading = str(verdict).strip() or "NO FACE"
    if heading.lower() == "real":
        heading = "REAL"
    elif heading.lower() == "fake":
        heading = "FAKE"
    lines: list[str] = []
    score = live.get("liveness_score")
    if isinstance(score, (int, float)):
        lines.append(f"liveness_score {score:.6f}")
    conf = live.get("confidence")
    if isinstance(conf, (int, float)):
        lines.append(f"confidence {conf:.6f}")
    if not lines:
        fallback = live.get("confidence")
        if fallback is None:
            fallback = live.get("liveness_score")
        if isinstance(fallback, (int, float)):
            lines.append(f"{fallback:.6f}")
    scores = live.get("attack_type_scores")
    if isinstance(scores, dict) and scores:
        lines.append(f"attack_type_scores {cell(scores)}")
    return heading, "\n".join(lines)


def _deepfake_decision(face: dict, view: dict | None = None) -> tuple[str, str]:
    attr = ix_payload.trait(face, "deepfake", "Deepfake")
    if not isinstance(attr, dict) and isinstance(view, dict):
        attr = view.get("deepfake") if isinstance(view.get("deepfake"), dict) else None
    kind = deepfake_kind(attr)
    if not kind:
        return "NO FACE", "No deepfake result"
    heading = "FAKE" if kind == "fake" else "REAL"
    lines: list[str] = []
    if isinstance(attr, dict):
        score = attr.get("confidence")
        if isinstance(score, (int, float)):
            lines.append(f"confidence {score:.6f}")
    return heading, "\n".join(lines)


def _combined_heading(live_heading: str, df_heading: str) -> str:
    if live_heading == "REAL" and df_heading == "REAL":
        return "REAL"
    if live_heading == "NO FACE" and df_heading == "NO FACE":
        return "NO FACE"
    return "FAKE"


def _engine_block(name: str, heading: str, line: str) -> str:
    if line:
        return f"{name} {heading}\n{line}"
    return f"{name} {heading}"


def _face_has_deepfake(face: dict) -> bool:
    return isinstance(ix_payload.trait(face, "deepfake", "Deepfake"), dict)


def _combined_decisions(payload: dict):
    view = _view(payload)
    faces = [face for face in _faces(view) if isinstance(face, dict)]
    rows = []
    for index, face in enumerate(faces):
        live_heading, live_line = _liveness_decision(face, view if index == 0 else None)
        df_heading, df_line = _deepfake_decision(face)
        rows.append(
            (
                _combined_heading(live_heading, df_heading),
                live_heading,
                live_line,
                df_heading,
                df_line,
                face,
            )
        )
    return rows


def _trait_score(attr: Any) -> str:
    if not isinstance(attr, dict):
        return ""
    score = attr.get("liveness_score")
    if not isinstance(score, (int, float)):
        score = attr.get("confidence")
    if isinstance(score, (int, float)):
        return f"{score:.6f}"
    return ""


def _face_liveness_rows(face: dict, view: dict | None) -> list[list[str]]:
    live = ix_payload.trait(face, "liveness2d", "Liveness2D")
    if not isinstance(live, dict) and isinstance(view, dict):
        live = view.get("liveness") if isinstance(view.get("liveness"), dict) else None
    live_heading, _line = _liveness_decision(face, view)
    rows = [["Liveness", live_heading, _trait_score(live)]]
    if _face_has_deepfake(face):
        df = ix_payload.trait(face, "deepfake", "Deepfake")
        df_heading, _df_line = _deepfake_decision(face)
        rows.append(["Deepfake", df_heading, _trait_score(df)])
    if isinstance(live, dict):
        attack = live.get("attack_type")
        if attack not in (None, ""):
            rows.append(["attack_type", cell(attack), ""])
    return rows


def format_liveness(payload: dict) -> tuple[str, list[list[str]], str]:
    view = _view(payload)
    raw = dumps(payload)
    err = engine_error(payload)
    if err:
        return f"**Error:** {err}", [], raw
    faces = [face for face in _faces(view) if isinstance(face, dict)]
    if not faces:
        return "**Error:** No face", [], raw
    rows: list[list[str]] = []
    for index, face in enumerate(faces):
        rows.extend(_face_liveness_rows(face, view if index == 0 else None))
    if not rows or all(row[1] == "NO FACE" for row in rows):
        return "**Error:** No liveness result", [], raw
    return "", rows, raw


def liveness_pairs_html(image: Any, payload: dict | None) -> str:
    """One table: cropped face on the left, check rows on the right."""
    import html as html_lib

    view = _view(payload)
    faces = [face for face in _faces(view) if isinstance(face, dict)]
    if not faces:
        return ""
    pic = _open_pic(image)
    body_rows: list[str] = []
    for index, face in enumerate(faces):
        img = ""
        if pic is not None:
            try:
                from preview import crop_region, jpeg_data_uri

                crop = crop_region(pic, _box(face))
                if crop is not None:
                    img = (
                        '<img class="ix-crop" alt="" src="'
                        + jpeg_data_uri(crop)
                        + '">'
                    )
            except Exception:  # noqa: BLE001
                img = ""
        rows = _face_liveness_rows(face, view if index == 0 else None)
        if not rows:
            continue
        span = len(rows)
        for row_index, row in enumerate(rows):
            face_cell = (
                f'<td class="ix-face-cell" rowspan="{span}">{img}</td>'
                if row_index == 0
                else ""
            )
            body_rows.append(
                "<tr>{}<td>{}</td><td>{}</td><td>{}</td></tr>".format(
                    face_cell,
                    html_lib.escape(str(row[0])),
                    html_lib.escape(str(row[1])),
                    html_lib.escape(str(row[2])),
                )
            )
    if not body_rows:
        return ""
    return (
        "<style>"
        ".ix-live-table{border-collapse:collapse;width:100%}"
        ".ix-live-table th,.ix-live-table td{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}"
        ".ix-face-cell{width:176px}"
        ".ix-crop{display:block;width:168px;height:auto;border-radius:4px}"
        "</style>"
        '<table class="ix-live-table"><thead><tr>'
        "<th>Face</th><th>Check</th><th>Decision</th><th>Confidence</th>"
        "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table>"
    )


def _best_score(matches: list) -> float | None:
    best = None
    for item in matches:
        if not isinstance(item, dict):
            continue
        score = _pair_score(item)
        if isinstance(score, (int, float)) and (best is None or score > best):
            best = float(score)
    return best


def format_identify(
    payload: dict, names: dict[int, str], threshold: float = MATCH_THRESHOLD
) -> tuple[str, list[list[str]], str, int | None]:
    """Return summary, table rows, raw JSON, and the best gallery index (or None)."""
    view = _view(payload)
    raw = dumps(payload)
    err = engine_error(payload)
    if err:
        return f"**Error:** {err}", [], raw, None
    matches = _pairs(view)
    rows: list[list[str]] = []
    best_index = None
    best_score = None
    for item in matches:
        if not isinstance(item, dict):
            continue
        index = _pair_right_image(item)
        score = _pair_score(item)
        name = names.get(index, f"#{index}") if isinstance(index, int) else cell(index)
        rows.append([name, cell(index), cell(score)])
        if isinstance(score, (int, float)) and isinstance(index, int):
            if best_score is None or score > best_score:
                best_score = float(score)
                best_index = index
    limit = cell(threshold)
    if best_index is None:
        return (
            f"## NO MATCH\n\nNo enrolled face is at or above {limit}.",
            rows,
            raw,
            None,
        )
    name = names.get(best_index, f"#{best_index}")
    return (
        f"## FOUND  {name}\n\nScore {cell(best_score)} — at or above the {limit} threshold.",
        rows,
        raw,
        best_index,
    )


def format_enroll(payload: dict, name: str) -> tuple[str, list[list[str]], str]:
    view = _view(payload)
    raw = dumps(payload)
    err = engine_error(payload)
    if err:
        return f"**Error:** {err}", [], raw
    results = view.get("features") if isinstance(view.get("features"), list) else []
    entry = results[0] if results and isinstance(results[0], dict) else {}
    index = entry.get("index")
    features = entry.get("features") if isinstance(entry.get("features"), list) else []
    feature = features[0] if features and isinstance(features[0], dict) else {}
    box = feature.get("box") if "box" in feature else feature.get("faceRegion")
    size = feature.get("size") if "size" in feature else feature.get("featureSize")
    rows = [
        ["Name", name, ""],
        ["Index", cell(index), ""],
        ["Region", _region_text(box), ""],
        ["Feature size", cell(size), ""],
    ]
    if not isinstance(index, int):
        return f"**Error:** enroll failed", rows, raw
    return f"## ENROLLED  {name}\n\nSaved as person {index}.", rows, raw
