"""Gradio demo — Face Recognition API (local only; not shipped in Docker)."""


from __future__ import annotations

import sys
from pathlib import Path as _BootPath

_APP_ROOT = _BootPath(__file__).resolve().parent.parent
_PKG_DIR = _BootPath(__file__).resolve().parent
for _p in (_APP_ROOT, _APP_ROOT / "sdk", _PKG_DIR):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.append(_s)


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_APP_ROOT / ".env", override=False)


_load_env()

import base64
import json
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Any

import cv2
import gradio as gr
import numpy as np
import requests
from PIL import Image

import demo_ui
import server.gallery as gallery_db
import ix_payload
import preview
import result_view


ROOT = _APP_ROOT
SAMPLES = ROOT / "assets" / "examples" / "samples"


def _env_port(primary: str, legacy: str, default: str) -> str:
    return os.environ.get(primary) or os.environ.get(legacy) or default


API = os.environ.get("API_BASE") or (
    f"http://127.0.0.1:{_env_port('PORT', 'FACESDK_PORT', '14105')}"
)
API = API.rstrip("/")
DEMO_HOST = os.environ.get("DEMO_HOST") or os.environ.get("HOST") or "0.0.0.0"
DEMO_PORT = int(os.environ.get("DEMO_PORT", "14205"))


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}




def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")




def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)




def _list_images() -> list[Path]:
    if not SAMPLES.is_dir():
        return []
    return sorted(
        p for p in SAMPLES.iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES
    )




def _sample_index(path: Path) -> int | None:
    m = re.match(r"(?:odd|even)\((\d+)\)", path.stem, re.I)
    if m:
        return int(m.group(1))
    m = re.match(r"^(\d+)$", path.stem)
    if m:
        return int(m.group(1))
    return None




def _sorted_sample_paths() -> list[Path]:
    indexed = [(idx, p) for p in _list_images() if (idx := _sample_index(p)) is not None]
    indexed.sort(key=lambda item: item[0])
    return [p for _, p in indexed]




def _face_examples() -> list[str]:
    numbered = [str(p) for p in _sorted_sample_paths()]
    return numbered or [str(p) for p in _list_images()]




def _odd_examples() -> list[str]:
    return [str(p) for p in _sorted_sample_paths() if (_sample_index(p) or 0) % 2 == 1]




def _even_examples() -> list[str]:
    return [str(p) for p in _sorted_sample_paths() if (_sample_index(p) or 0) % 2 == 0]




def _error(msg: str):
    return f"**Error:** {msg}", [], ""


def _pad(out, n: int = 4):
    if isinstance(out, tuple):
        return out + (None,) * (n - len(out))
    return (out, [], "", None)[:n]


def _load_image(image) -> Image.Image | None:
    if image is None:
        return None
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, np.ndarray):
        arr = image
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr], axis=-1)
        return Image.fromarray(arr.astype("uint8"), "RGB")
    if isinstance(image, (str, Path)) and Path(image).is_file():
        return Image.open(image).convert("RGB")
    return None


def _jpeg_b64(image) -> str:
    pic = _load_image(image)
    if pic is None:
        raise ValueError("image required")
    buf = BytesIO()
    pic.convert("RGB").save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _encoded_b64(image) -> str:
    """Prefer original JPEG/PNG/BMP bytes for deepfake (matches vendor processing-block demos)."""
    if isinstance(image, (str, Path)) and Path(image).is_file():
        data = Path(image).read_bytes()
        if (
            data[:3] == b"\xff\xd8\xff"
            or data[:8] == b"\x89PNG\r\n\x1a\n"
            or data[:2] == b"BM"
        ):
            return base64.b64encode(data).decode("ascii")
    return _jpeg_b64(image)


def _overlay(image, payload) -> Image.Image | None:
    pic = _load_image(image)
    if pic is None:
        return None
    return preview.annotate(pic, payload if isinstance(payload, dict) else None)




def _fetch_license_status() -> dict:
    try:
        r = requests.get(f"{API}/api/licenseStatus", timeout=5)
        body = r.json() if r.ok else {}
        data = body.get("data") if isinstance(body, dict) else None
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}




def _license_banner_md(status: dict | None = None) -> str:
    st = status if status is not None else _fetch_license_status()
    label = str(st.get("label") or "").strip()
    if not label:
        if st.get("licensed"):
            label = str(st.get("levelName") or "Licensed")
        else:
            label = "No license"
    return f"**License:** {label}"




def _capability_notes(status: dict) -> list[str]:
    notes: list[str] = []
    if not status.get("liveness"):
        notes.append("Liveness is **not available** on this license.")
    if not status.get("recognition"):
        notes.append("Recognition is **not available** on this license.")
    return notes




def _capability_notes_md(status: dict | None = None) -> str:
    st = status if status is not None else _fetch_license_status()
    notes = _capability_notes(st)
    return "\n\n".join(f"**Note:** {n}" for n in notes)




def _license_header() -> tuple[str, str]:
    st = _fetch_license_status()
    return _license_banner_md(st), _capability_notes_md(st)




def _notes_md(status: dict, *, need_recognition: bool = False, need_liveness: bool = False) -> str | None:
    if not status.get("licensed"):
        return "**Note:** No license — activate with a license key first."
    if need_recognition and not status.get("recognition"):
        return "**Note:** This license does not include recognition."
    if need_liveness and not status.get("liveness"):
        return "**Note:** This license does not include liveness."
    return None




def _post(path: str, body: dict) -> dict | tuple:
    try:
        r = requests.post(f"{API}{path}", json=body, timeout=120)
        payload = r.json()
    except Exception as ex:  # noqa: BLE001
        return _error(str(ex))
    if not isinstance(payload, dict):
        return "**Unexpected response.**", [], json.dumps(payload, indent=2)
    return payload




def _attr_value(attr: Any) -> str:
    if not isinstance(attr, dict):
        return _cell(attr)
    return _cell(attr.get("value"))




def _attr_extra(attr: Any, *, kind: str) -> str:
    if not isinstance(attr, dict):
        return ""
    if kind == "detect":
        if "confidence" in attr:
            return _cell(attr["confidence"])
        return ""
    # quality
    parts = []
    if "status" in attr:
        parts.append(f"status={_cell(attr['status'])}")
    if "range" in attr:
        parts.append(f"range={_cell(attr['range'])}")
    return ", ".join(parts)




def format_detect(payload: dict) -> tuple[str, list[list[str]], str]:
    return result_view.format_detect(payload)


def format_match(payload: dict) -> tuple[str, list[list[str]], str]:
    return result_view.format_match(payload)




def detect(image):
    return _engine_image(image, "/api/face/boxes", "Face detect", "face")


def face_attribute(image):
    return _engine_image(image, "/api/face/traits", "Face attribute", "face")


def image_quality(image):
    return _engine_image(image, "/api/face/image-quality", "Image quality", "face")


def landmarks(image, mode):
    note = _notes_md(_fetch_license_status(), need_recognition=True)
    if note:
        return note, "", ""
    if not image:
        return _pad(_error("Image required"))[0], "", ""
    if str(mode) in ("14", "18"):
        use_mode = 14
    elif str(mode) == "68":
        use_mode = 68
    else:
        return _pad(_error("landmark mode must be 14 or 68"))[0], "", ""
    out = _post("/api/face/landmarks", {"image": _jpeg_b64(image), "mode": use_mode})
    if isinstance(out, tuple):
        return out[0], "", out[2] if len(out) > 2 else ""
    summary, _rows, raw = result_view.format_detect(out, title=f"Landmarks {use_mode}", noun="face")
    return summary, result_view.landmark_preview_html(image, out), raw


def _engine_image(image, path: str, title: str, noun: str):
    note = _notes_md(_fetch_license_status(), need_recognition=True)
    if note:
        return note, "", ""
    if not image:
        return _pad(_error("Image required"))[0], "", ""
    out = _post(path, {"image": _jpeg_b64(image), "cropImage": False})
    if isinstance(out, tuple):
        return out[0], "", out[2] if len(out) > 2 else ""
    summary, _rows, raw = result_view.format_detect(out, title=title, noun=noun)
    return summary, result_view.face_pairs_html(image, out), raw


def deepfake(image):
    note = _notes_md(_fetch_license_status(), need_recognition=True)
    if note:
        return note, "", ""
    if not image:
        return _pad(_error("Image required"))[0], "", ""
    out = _post("/api/face/deepfake", {"image": _encoded_b64(image)})
    if isinstance(out, tuple):
        return out[0], "", out[2] if len(out) > 2 else ""
    summary, _rows, raw = result_view.format_detect(out, title="Deepfake", noun="face")
    return summary, result_view.face_pairs_html(image, out), raw


def match(image1, image2):
    note = _notes_md(_fetch_license_status(), need_recognition=True)
    if note:
        return note, "", ""
    if not image1 or not image2:
        return _error("Both images required")[0], "", ""
    out = _post(
        "/api/face/compare",
        {"image1": _b64(image1), "image2": _b64(image2), "cropImage": False},
    )
    if isinstance(out, tuple):
        return out[0], "", out[2] if len(out) > 2 else ""
    summary, _rows, raw = format_match(out)
    return summary, result_view.match_pairs_html(image1, image2, out), raw




def _liveness_examples() -> list[str]:
    names = []
    for p in _list_images():
        stem = p.stem.lower()
        if stem.startswith("real") or stem.startswith("fake"):
            names.append(str(p))
    return names or _face_examples()




def _face_image(path: str, image_b64: str):
    try:
        r = requests.post(f"{API}{path}", json={"image": image_b64}, timeout=180)
        payload = r.json()
    except Exception as ex:  # noqa: BLE001
        return None, f"**Error:** {ex}", ""
    if not isinstance(payload, dict):
        return None, f"**Error:** {payload}", json.dumps(payload, indent=2, ensure_ascii=False)
    return payload, None, ""


def check_liveness(path):
    note = _notes_md(_fetch_license_status(), need_liveness=True)
    if note:
        return note, "", ""
    if not path:
        return "**Error:** Image required", "", ""
    image = _encoded_b64(path)
    live, err, raw = _face_image("/api/face/liveness", image)
    if err:
        return err, "", raw
    summary, _rows, formatted = result_view.format_liveness(live)
    if summary:
        return summary, "", formatted
    return "", result_view.liveness_pairs_html(path, live), formatted




def _live_attr(payload: dict) -> dict | None:
    view = ix_payload.face_view(payload)
    faces = view.get("faces") if isinstance(view.get("faces"), list) else []
    if not faces or not isinstance(faces[0], dict):
        return None
    live = ix_payload.trait(faces[0], "liveness2d", "Liveness2D")
    return live if isinstance(live, dict) else None


def _image_from_bytes(blob: bytes | None):
    if not blob:
        return None
    try:
        from io import BytesIO

        import numpy as np
        from PIL import Image

        img = Image.open(BytesIO(blob)).convert("RGB")
        return np.asarray(img)
    except Exception:  # noqa: BLE001
        return None


def _placeholder_thumb(label: str):
    import numpy as np
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (160, 160), (32, 40, 48))
    draw = ImageDraw.Draw(img)
    draw.text((12, 70), (label or "?")[:16], fill=(220, 230, 240))
    return np.asarray(img)


def _crop_region(path, region):
    if not path or not isinstance(region, dict):
        return path
    try:
        from PIL import Image

        img = Image.open(path).convert("RGB")
        x = max(0, int(float(region.get("x") or 0)))
        y = max(0, int(float(region.get("y") or 0)))
        w = int(float(region.get("width") or 0))
        h = int(float(region.get("height") or 0))
        if w <= 1 or h <= 1:
            return path
        x2 = min(img.width, x + w)
        y2 = min(img.height, y + h)
        if x2 <= x or y2 <= y:
            return path
        return img.crop((x, y, x2, y2))
    except Exception:  # noqa: BLE001
        return path


def _probe_face_region(payload: dict):
    view = ix_payload.face_view(payload)
    detects = view.get("detects") if isinstance(view.get("detects"), list) else []
    if not detects or not isinstance(detects[0], dict):
        return None
    faces = detects[0].get("faces")
    if not isinstance(faces, list) or not faces or not isinstance(faces[0], dict):
        return None
    region = faces[0].get("box") if isinstance(faces[0].get("box"), dict) else faces[0].get("faceRegion")
    return region if isinstance(region, dict) else None


def _enrolled_gallery():
    import html as html_lib

    from preview import jpeg_data_uri

    gallery_db.open_db(ROOT)
    cells = []
    choices = []
    size = result_view.GALLERY_THUMB
    for person in gallery_db.list_people():
        label = f"{person.id} · {person.name}"
        choices.append(label)
        thumb = _image_from_bytes(person.thumbnail)
        if thumb is None:
            thumb = _placeholder_thumb(person.name)
        pic = result_view.as_thumb(thumb, size)
        img = ""
        if pic is not None:
            img = f'<img src="{jpeg_data_uri(pic)}" width="{size}" height="{size}" alt="">'
        cells.append(
            f"<td valign=\"top\" width=\"{size}\">{img}<br>{html_lib.escape(label)}</td>"
        )
    rows = []
    for i in range(0, len(cells), 5):
        rows.append("<tr>" + "".join(cells[i : i + 5]) + "</tr>")
    return f"<table>{''.join(rows)}</table>", choices


def _identity_pack(summary: str, rows: list, raw: str, query=None, enrolled=None):
    images, choices = _enrolled_gallery()
    return (
        summary,
        rows,
        raw,
        result_view.as_thumb(query),
        result_view.as_thumb(enrolled),
        images,
        gr.update(choices=choices, value=None),
    )


def _identity_names() -> dict[int, str]:
    gallery_db.open_db(ROOT)
    return {person.id: person.name for person in gallery_db.list_people()}


def enroll_person(name, image):
    note = _notes_md(_fetch_license_status(), need_recognition=True)
    if note:
        return _identity_pack(note, [], "")
    label = str(name or "").strip()
    if not label:
        return _identity_pack("**Error:** Name required", [], "")
    if not image:
        return _identity_pack("**Error:** Enroll image required", [], "")
    out = _post("/api/face/enroll", {"image": _b64(image), "name": label})
    if isinstance(out, tuple):
        return _identity_pack(out[0], out[1], out[2])
    summary, rows, raw = result_view.format_enroll(out, label)
    thumb = None
    view = ix_payload.face_view(out)
    results = view.get("features") if isinstance(view.get("features"), list) else []
    index = results[0].get("index") if results and isinstance(results[0], dict) else None
    if isinstance(index, int):
        person = gallery_db.get(index)
        thumb = _image_from_bytes(person.thumbnail) if person else None
    return _identity_pack(summary, rows, raw, _crop_region(image, _enroll_region(out)), thumb)


def _enroll_region(payload: dict):
    view = ix_payload.face_view(payload)
    results = view.get("features") if isinstance(view.get("features"), list) else []
    if not results or not isinstance(results[0], dict):
        return None
    features = results[0].get("features")
    if not isinstance(features, list) or not features or not isinstance(features[0], dict):
        return None
    region = features[0].get("box") if isinstance(features[0].get("box"), dict) else features[0].get("faceRegion")
    return region if isinstance(region, dict) else None


def identify_person(image, threshold):
    note = _notes_md(_fetch_license_status(), need_recognition=True)
    if note:
        return _identity_pack(note, [], "")
    if not image:
        return _identity_pack("**Error:** Identify image required", [], "")
    try:
        limit = float(threshold if threshold is not None else 0.67)
    except (TypeError, ValueError):
        limit = 0.67
    out = _post("/api/face/search", {"image": _b64(image), "threshold": limit})
    if isinstance(out, tuple):
        return _identity_pack(out[0], out[1], out[2])
    summary, rows, raw, best = result_view.format_identify(out, _identity_names(), limit)
    query = _crop_region(image, _probe_face_region(out))
    enrolled = None
    if isinstance(best, int):
        person = gallery_db.get(best)
        enrolled = _image_from_bytes(person.thumbnail) if person else None
        if enrolled is None and person is not None:
            enrolled = _placeholder_thumb(person.name)
    return _identity_pack(summary, rows, raw, query, enrolled)


def delete_person(choice):
    if not choice:
        return _identity_pack("*Select a person to delete.*", [], "")
    index = str(choice).split("·", 1)[0].strip()
    if not index.isdigit():
        return _identity_pack("**Error:** Invalid person", [], "")
    out = _request("DELETE", f"/api/face/gallery/{index}")
    if isinstance(out, tuple):
        return _identity_pack(out[0], [], "")
    raw = json.dumps(out, indent=2, ensure_ascii=False)
    err = result_view.engine_error(out) if isinstance(out, dict) else "delete failed"
    if err:
        return _identity_pack(f"**Error:** {err}", [], raw)
    return _identity_pack(f"Deleted index {index}.", [], raw)


def refresh_identity():
    images, choices = _enrolled_gallery()
    return images, gr.update(choices=choices)


def _request(method: str, path: str):
    try:
        r = requests.request(method, f"{API}{path}", timeout=180)
        return r.json()
    except Exception as ex:  # noqa: BLE001
        return f"**Error:** {ex}", [], ""


def _result_image(label: str):
    return gr.Image(
        label=label,
        interactive=False,
        height=result_view.THUMB_SIZE,
        width=result_view.THUMB_SIZE,
    )


def _result_panel(*, headers: list[str], label: str, preview: bool = False):
    summary = gr.Markdown(value="*Run an action to see the result.*")
    table = gr.HTML() if preview else demo_ui.result_dataframe(headers=headers, label=label)
    with gr.Accordion("Response", open=False):
        raw = gr.Code(language="json", label="API response")
    return summary, table, raw




_DETECT_EX = _face_examples()
_ODD_EX = _odd_examples()
_EVEN_EX = _even_examples()
_LIVENESS_EX = _liveness_examples()


with gr.Blocks(title="Identixia Face Liveness") as demo:
    gr.Markdown("# Identixia Face Liveness\nAPI `" + API + "` — start with `python3 run_server.py` first.")
    license_md = gr.Markdown(value=_license_banner_md())
    notes_md = gr.Markdown(value=_capability_notes_md())

    gr.Markdown("Still image. REAL only when both the liveness and deepfake engines say real.")
    with gr.Row():
        with gr.Column(scale=1, min_width=200):
            liv_in = gr.Image(type="filepath", label="Face")
            liv_btn = gr.Button("Check liveness", variant="primary")
            if _LIVENESS_EX:
                gr.Examples(_LIVENESS_EX, inputs=liv_in, label="Examples")
        with gr.Column(scale=3, min_width=360):
            liv_summary, liv_table, liv_raw = _result_panel(
                headers=["Face", "Check", "Decision", "Confidence"],
                label="Liveness",
                preview=True,
            )
    liv_btn.click(check_liveness, inputs=liv_in, outputs=[liv_summary, liv_table, liv_raw])
    liv_btn.click(_license_header, outputs=[license_md, notes_md])
    demo.load(_license_header, outputs=[license_md, notes_md])



def main() -> None:
    from server.port_guard import free_port

    free_port(DEMO_PORT)
    print(f"Gradio demo -> http://{DEMO_HOST}:{DEMO_PORT}  (API {API})")
    demo.launch(server_name=DEMO_HOST, server_port=DEMO_PORT)

if __name__ == "__main__":
    main()
