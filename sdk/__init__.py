"""ctypes bindings to libFaceLivenessSDK.so (Face Liveness, Linux — Windows uses FaceLivenessSDK.dll).

Native libs live in lib/cpu/.
"""

from __future__ import annotations

import atexit
import base64
import ctypes
import io
import json
import os
import sys
from pathlib import Path

_SDK_DIR = Path(__file__).resolve().parent
if str(_SDK_DIR) not in sys.path:
    sys.path.insert(0, str(_SDK_DIR))

import ix_payload

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "lib" / "cpu"
# Windows Face Liveness ships FaceLivenessSDK.dll; Linux uses the same basename.
SO = LIB / "libFaceLivenessSDK.so"
ENGINE = LIB / "libFaceLivenessEngine.so"

os.chdir(ROOT)

if not SO.is_file():
    print(
        f"ERROR: missing {SO.relative_to(ROOT)}\n"
        "Download the Linux runtime into ./lib/cpu/.",
        file=sys.stderr,
    )
    raise SystemExit(1)

os.environ["LD_LIBRARY_PATH"] = str(LIB) + (
    (":" + os.environ["LD_LIBRARY_PATH"]) if os.environ.get("LD_LIBRARY_PATH") else ""
)

# Engine + onnx first so wrapper dlopen resolves under RTLD_GLOBAL.
for _dep in (
    LIB / "libonnxruntime.so",
    LIB / "libonnxruntime_providers_shared.so",
    ENGINE,
):
    if _dep.is_file():
        ctypes.CDLL(str(_dep), mode=os.RTLD_GLOBAL)
_dll = ctypes.CDLL(str(SO), mode=os.RTLD_GLOBAL)

_dll.FaceSDK_initSDK.restype = ctypes.c_int
_dll.FaceSDK_initSDK.argtypes = []
_dll.FaceSDK_activate.restype = ctypes.c_int
_dll.FaceSDK_activate.argtypes = [ctypes.c_char_p]
if hasattr(_dll, "FaceSDK_release"):
    _dll.FaceSDK_release.restype = None
    _dll.FaceSDK_release.argtypes = []
_dll.FaceSDK_getMachineCode.restype = ctypes.c_int
_dll.FaceSDK_getMachineCode.argtypes = [ctypes.c_char_p]


def _bind(name, restype, argtypes, *aliases):
    fn = getattr(_dll, name, None)
    if fn is None:
        for alt in aliases:
            fn = getattr(_dll, alt, None)
            if fn is not None:
                break
    if fn is None:
        return None
    fn.restype = restype
    fn.argtypes = argtypes
    return fn


_dll.FaceSDK_detect = _bind("FaceSDK_detect", ctypes.c_int, [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_bool])
_dll.FaceSDK_face_detect = _bind(
    "FaceSDK_face_detect",
    ctypes.c_int,
    [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_bool],
    "FaceSDK_detect",
)
_dll.FaceSDK_face_attribute = _bind(
    "FaceSDK_face_attribute", ctypes.c_int, [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_bool]
)
_dll.FaceSDK_image_quality = _bind(
    "FaceSDK_image_quality", ctypes.c_int, [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_bool]
)
_dll.FaceSDK_quality = _bind("FaceSDK_quality", ctypes.c_int, [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_bool])
_dll.FaceSDK_deepfake = _bind("FaceSDK_deepfake", ctypes.c_int, [ctypes.c_char_p, ctypes.c_char_p])
_dll.FaceSDK_landmarks = _bind("FaceSDK_landmarks", ctypes.c_int, [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p])
_dll.FaceSDK_match = _bind(
    "FaceSDK_match",
    ctypes.c_int,
    [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_bool],
)
_dll.FaceSDK_getFeature = _bind("FaceSDK_getFeature", ctypes.c_int, [ctypes.c_char_p, ctypes.c_char_p])
_dll.FaceSDK_getSimilarity = _bind(
    "FaceSDK_getSimilarity", ctypes.c_float, [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
)
_dll.FaceSDK_liveness_all = _bind(
    "FaceSDK_liveness_all", ctypes.c_int, [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p]
)
if _dll.FaceSDK_liveness_all is None:
    raise AttributeError(f"{SO.name}: missing required FaceSDK_liveness_all")
if _dll.FaceSDK_deepfake is None:
    raise AttributeError(
        f"{SO.name}: missing FaceSDK_deepfake — rebuild FaceLivenessDetection-Docker-SDK "
        "with the face331 wrapper (same API surface as FaceRecognition-LivenessDetection)."
    )


def _opt_sym(name, restype, argtypes):
    fn = getattr(_dll, name, None)
    if fn is None:
        return None
    fn.restype = restype
    fn.argtypes = argtypes
    return fn


_get_license_status = _opt_sym(
    "FaceSDK_getLicenseStatus", ctypes.c_int, [ctypes.c_char_p]
)
_missing_databases = _opt_sym(
    "FaceSDK_missingDatabases", ctypes.c_int, [ctypes.c_char_p, ctypes.c_size_t]
)

_MC_BUF = 768
_STATUS_BUF = 512
# The DLL writes up to 16MB (landmarks + quality). A smaller buffer overflows.
_OUT_MIN = 16 * 1024 * 1024
_OUT_MAX = 16 * 1024 * 1024
_MAX_IMG = 8 * 1024 * 1024


def _b(v) -> bytes:
    if v is None:
        raise ValueError("required")
    if isinstance(v, bytes):
        return v
    return str(v).encode("utf-8")


def _out(*parts: bytes):
    n = min(max(_OUT_MIN, sum(len(p) for p in parts) * 2 + 262144), _OUT_MAX)
    return ctypes.create_string_buffer(n)


def _strip(raw: bytes) -> bytes:
    text = raw.decode("utf-8", errors="ignore").strip()
    if text.startswith("data:") and "base64," in text:
        text = text.split("base64,", 1)[1]
    return text.encode("utf-8")


def _fit_b64(image_b64: str, max_bytes: int = _MAX_IMG) -> bytes:
    """RGB JPEG for the engine. Existing JPEGs pass through; other types are converted."""
    raw = _strip(_b(image_b64))
    data = base64.b64decode(raw, validate=False)
    if data[:3] == b"\xff\xd8\xff" and len(raw) <= max_bytes:
        return raw
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.load()
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
    img = img.convert("RGB")
    quality = 90
    while True:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        jpeg = buf.getvalue()
        encoded = base64.b64encode(jpeg)
        if len(encoded) <= max_bytes or quality <= 40 or img.width <= 64:
            return encoded
        quality = 70
        img = img.resize((max(1, img.width * 3 // 4), max(1, img.height * 3 // 4)))


def _fit_encoded_b64(image_b64: str, max_bytes: int = _MAX_IMG) -> bytes:
    """Pass through JPEG/PNG/BMP for createContextFromEncodedImage; else JPEG-convert."""
    raw = _strip(_b(image_b64))
    data = base64.b64decode(raw, validate=False)
    if len(raw) <= max_bytes and (
        data[:3] == b"\xff\xd8\xff"
        or data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:2] == b"BM"
    ):
        return raw
    return _fit_b64(image_b64, max_bytes)


def backend() -> str:
    return "cpu"


def get_machine_code() -> str:
    buf = ctypes.create_string_buffer(_MC_BUF)
    _dll.FaceSDK_getMachineCode(buf)
    return buf.value.decode("utf-8", errors="replace")


def get_license_status() -> dict:
    fallback = {
        "licensed": False,
        "level": -1,
        "levelName": "None",
        "recognition": False,
        "liveness": False,
        "label": "No license",
    }
    if _get_license_status is None:
        return fallback
    buf = ctypes.create_string_buffer(_STATUS_BUF)
    if int(_get_license_status(buf)) != 0:
        return fallback
    try:
        data = json.loads(buf.value.decode("utf-8", errors="replace") or "{}")
        return data if isinstance(data, dict) else fallback
    except Exception:  # noqa: BLE001
        return fallback


def activate(license_path: str) -> int:
    return int(_dll.FaceSDK_activate(_b(license_path)))


def release() -> None:
    fn = getattr(_dll, "FaceSDK_release", None)
    if fn is not None:
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass


atexit.register(release)


def init_sdk() -> int:
    rc = int(_dll.FaceSDK_initSDK())
    if rc == 0:
        missing = missing_databases()
        if missing:
            print(
                "WARN: missing databases (features skipped): " + ", ".join(missing),
                flush=True,
            )
    return rc


def missing_databases() -> list[str]:
    """Licensed packs that were not found at init (soft-skipped)."""
    if _missing_databases is None:
        return []
    buf = ctypes.create_string_buffer(1024)
    if int(_missing_databases(buf, ctypes.sizeof(buf))) != 0:
        return []
    text = buf.value.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    return [p.strip() for p in text.split(",") if p.strip()]


def detect(image: str, crop_image: bool = False) -> str:
    image_b = _fit_b64(image)
    out = _out(image_b)
    _dll.FaceSDK_detect(image_b, out, bool(crop_image))
    return out.value.decode("utf-8", errors="replace")


def quality(image: str, crop_image: bool = False) -> str:
    image_b = _fit_b64(image)
    out = _out(image_b)
    _dll.FaceSDK_quality(image_b, out, bool(crop_image))
    return out.value.decode("utf-8", errors="replace")


def _image_flags(fn, image: str, crop_image: bool = False) -> str:
    if fn is None:
        return json.dumps(ix_payload.wrap_process({"status": -1, "message": "operation is not available in this build"}))
    image_b = _fit_b64(image)
    out = _out(image_b)
    fn(image_b, out, bool(crop_image))
    return out.value.decode("utf-8", errors="replace")


def face_detect(image: str, crop_image: bool = False) -> str:
    return _image_flags(_dll.FaceSDK_face_detect, image, crop_image)


def face_attribute(image: str, crop_image: bool = False) -> str:
    return _image_flags(_dll.FaceSDK_face_attribute, image, crop_image)


def image_quality(image: str, crop_image: bool = False) -> str:
    return _image_flags(_dll.FaceSDK_image_quality, image, crop_image)


def deepfake(image: str) -> str:
    image_b = _fit_encoded_b64(image)
    out = _out(image_b)
    _dll.FaceSDK_deepfake(image_b, out)
    return out.value.decode("utf-8", errors="replace")


def landmarks(image: str, mode: int = 14) -> str:
    use_mode = 14 if int(mode) in (14, 18, 0) else int(mode)
    if use_mode not in (14, 68):
        return json.dumps({"status": -1, "message": "landmark mode must be 14 or 68"})
    image_b = _fit_b64(image)
    out = _out(image_b)
    _dll.FaceSDK_landmarks(image_b, use_mode, out)
    return out.value.decode("utf-8", errors="replace")


def match(image1: str, image2: str, crop_image: bool = False) -> str:
    a = _fit_b64(image1, _MAX_IMG // 2)
    b = _fit_b64(image2, _MAX_IMG // 2)
    out = _out(a, b)
    _dll.FaceSDK_match(a, b, out, bool(crop_image))
    return out.value.decode("utf-8", errors="replace")


def feature(image: str) -> str:
    image_b = _fit_b64(image)
    out = _out(image_b)
    _dll.FaceSDK_getFeature(image_b, out)
    return out.value.decode("utf-8", errors="replace")


def similarity_score(feature1: str, feature2: str) -> float:
    try:
        import identity

        raw1 = identity.feature_bytes(feature1)
        raw2 = identity.feature_bytes(feature2)
    except Exception:  # noqa: BLE001
        return -1.0
    if not raw1 or len(raw1) != len(raw2):
        return -1.0
    return float(_dll.FaceSDK_getSimilarity(raw1, raw2, len(raw1)))


def similarity(feature1: str, feature2: str) -> str:
    value = similarity_score(feature1, feature2)
    if value < 0:
        raise ValueError("feature length mismatch")
    return json.dumps(ix_payload.wrap_process({"status": 0, "message": "COMPLETED", "score": value}))


def _jpeg_bytes(image_b64: str) -> bytes:
    text = image_b64.strip()
    if text.startswith("data:") and "base64," in text:
        text = text.split("base64,", 1)[1]
    data = base64.b64decode(text, validate=False)
    if len(data) <= _MAX_IMG and data[:2] == b"\xff\xd8":
        return data
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.load()
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    out = buf.getvalue()
    while len(out) > _MAX_IMG and img.width > 32:
        img = img.resize((max(1, int(img.width * 0.75)), max(1, int(img.height * 0.75))))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        out = buf.getvalue()
    return out


def _liveness_once(image_b: bytes) -> str:
    out = _out(image_b)
    _dll.FaceSDK_liveness_all(image_b, 0, out)
    return out.value.decode("utf-8", errors="replace")


def _liveness_faces(raw: str) -> list:
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return []
    view = ix_payload.face_view(doc)
    faces = view.get("faces")
    return faces if isinstance(faces, list) else []


def _has_liveness_score(face: dict) -> bool:
    attr = ix_payload.trait(face, "liveness2d", "Liveness2D")
    if not isinstance(attr, dict):
        return False
    return isinstance(attr.get("liveness_score"), (int, float)) or isinstance(
        attr.get("confidence"), (int, float)
    )


def _rgb_from_b64(image: str):
    from PIL import Image

    data = base64.b64decode(_strip(_b(image)), validate=False)
    img = Image.open(io.BytesIO(data))
    img.load()
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
    return img.convert("RGB")


def _face_jpeg_b64(pic, box: dict | None) -> str | None:
    if pic is None or not isinstance(box, dict):
        return None
    try:
        x = float(box.get("x") or 0)
        y = float(box.get("y") or 0)
        w = float(box.get("width") or 0)
        h = float(box.get("height") or 0)
    except (TypeError, ValueError):
        return None
    if w < 2 or h < 2:
        return None
    pad_x, pad_y = w * 0.16, h * 0.16
    left = max(0, int(x - pad_x))
    top = max(0, int(y - pad_y))
    right = min(pic.width, int(x + w + pad_x))
    bottom = min(pic.height, int(y + h + pad_y))
    if right - left < 2 or bottom - top < 2:
        return None
    buf = io.BytesIO()
    pic.crop((left, top, right, bottom)).save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _liveness_each_face(image: str, raw: str, faces: list) -> str:
    """The native liveness PB only scores a single object; crop and score each face."""
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    try:
        pic = _rgb_from_b64(image)
    except Exception:  # noqa: BLE001
        return raw
    updated: list = []
    for face in faces:
        if not isinstance(face, dict):
            updated.append(face)
            continue
        item = dict(face)
        if not _has_liveness_score(item):
            crop_b64 = _face_jpeg_b64(pic, item.get("box"))
            if crop_b64:
                one_faces = _liveness_faces(_liveness_once(_fit_encoded_b64(crop_b64)))
                src = one_faces[0] if one_faces and isinstance(one_faces[0], dict) else {}
                traits = item.get("traits") if isinstance(item.get("traits"), dict) else {}
                src_traits = src.get("traits") if isinstance(src.get("traits"), dict) else {}
                merged = dict(traits)
                for key in ("liveness2d", "deepfake"):
                    if key in src_traits:
                        merged[key] = src_traits[key]
                if merged:
                    item["traits"] = merged
        updated.append(item)
    if isinstance(doc.get("faces"), list):
        doc["faces"] = updated
    result = doc.get("result")
    if isinstance(result, dict) and isinstance(result.get("faces"), list):
        result["faces"] = updated
    return json.dumps(doc)


def liveness(image: str) -> str:
    image_b = _fit_encoded_b64(image)
    raw = _liveness_once(image_b)
    faces = _liveness_faces(raw)
    if len(faces) <= 1 or all(
        not isinstance(face, dict) or _has_liveness_score(face) for face in faces
    ):
        return raw
    return _liveness_each_face(image, raw, faces)


_vw_start = _opt_sym("FaceSDK_vw_start", ctypes.c_int, [ctypes.c_float])
_vw_stop = _opt_sym("FaceSDK_vw_stop", ctypes.c_int, [])
_vw_set_database = _opt_sym("FaceSDK_vw_set_database", ctypes.c_int, [ctypes.c_char_p])
_vw_add_frame = _opt_sym("FaceSDK_vw_add_frame", ctypes.c_int, [ctypes.c_char_p, ctypes.c_char_p])
_vw_poll_events = _opt_sym("FaceSDK_vw_poll_events", ctypes.c_int, [ctypes.c_char_p])

_vw_on = False
_vw_threshold = 0.67


def vw_running() -> bool:
    return _vw_on


def vw_threshold() -> float:
    return _vw_threshold


def vw_start(threshold: float = 0.67) -> int:
    global _vw_on, _vw_threshold
    if _vw_start is None:
        return 1
    _vw_threshold = float(threshold)
    rc = int(_vw_start(ctypes.c_float(_vw_threshold)))
    _vw_on = rc == 0
    return rc


def vw_stop() -> int:
    global _vw_on
    _vw_on = False
    if _vw_stop is None:
        return 0
    return int(_vw_stop())


def vw_set_database(payload: dict) -> str:
    if _vw_set_database is None:
        return json.dumps({"status": -1, "message": "video worker is not available"})
    raw = json.dumps(payload).encode("utf-8")
    rc = int(_vw_set_database(raw))
    if rc != 0:
        return json.dumps({"status": -1, "message": "gallery sync failed"})
    return json.dumps({"status": 0, "message": "COMPLETED"})


def vw_add_frame(image: str) -> str:
    if _vw_add_frame is None:
        return json.dumps({"status": -1, "message": "video worker is not available"})
    image_b = _fit_b64(image)
    out = _out(image_b)
    _vw_add_frame(image_b, out)
    return out.value.decode("utf-8", errors="replace")


def vw_poll_events() -> str:
    if _vw_poll_events is None:
        return json.dumps({"status": 0, "message": "COMPLETED", "data": []})
    out = ctypes.create_string_buffer(_OUT_MIN)
    _vw_poll_events(out)
    return out.value.decode("utf-8", errors="replace")
