"""Identixia Face process documents: metadata plus result keys."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any


CODE_OK = 0
CODE_NO_FACE = 2


def _as_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _metadata(status: int, message: str) -> dict[str, Any]:
    return {
        "status": int(status),
        "transactionId": "ix_" + secrets.token_hex(16),
        "message": str(message or ""),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def is_ixdoc(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("api") == "doc/1"


def is_ixface(payload: Any) -> bool:
    """True for the current process JSON or a legacy face/1 envelope."""
    if not isinstance(payload, dict):
        return False
    if payload.get("api") == "face/1":
        return True
    meta = payload.get("metadata")
    return isinstance(meta, dict) and "status" in meta and "transactionId" in meta


def process_meta(payload: dict | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"status": -1, "transactionId": "", "message": "", "timestamp": ""}
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    status = meta.get("status", payload.get("statusCode", payload.get("status", payload.get("code"))))
    try:
        status = int(status)
    except (TypeError, ValueError):
        status = -1
    message = meta.get("message")
    if not isinstance(message, str) or not message:
        result = _as_dict(payload.get("result"))
        message = result.get("message") or payload.get("message") or ""
    fault = payload.get("fault")
    if isinstance(fault, dict) and fault.get("message"):
        message = str(fault.get("message"))
    return {
        "status": status,
        "transactionId": str(meta.get("transactionId") or ""),
        "message": str(message or ""),
        "timestamp": str(meta.get("timestamp") or ""),
    }


def _trait_key(key: str) -> str:
    known = {
        "Age": "ageYears",
        "Gender": "gender",
        "Emotion": "emotion",
        "Emotions": "emotions",
        "Smile": "smile",
        "Glasses": "glasses",
        "Sunglasses": "sunglasses",
        "EyeRight": "eyeRight",
        "EyeLeft": "eyeLeft",
        "EyesLeft": "eyesLeft",
        "EyesRight": "eyesRight",
        "HeadCovering": "headCovering",
        "ForeheadCovering": "foreheadCovering",
        "Mouth": "mouth",
        "MedicalMask": "medicalMask",
        "Occlusion": "occlusion",
        "StrongMakeup": "strongMakeup",
        "Headphones": "headphones",
        "FaceQuality": "faceQuality",
        "BlurLevel": "blurLevel",
        "NoiseLevel": "noiseLevel",
        "Sharpness": "sharpness",
        "Noise": "noise",
        "Lighting": "lighting",
        "Flare": "flare",
        "TooDark": "tooDark",
        "TooLight": "tooLight",
        "FaceGlare": "faceGlare",
        "Liveness2D": "liveness2d",
        "Deepfake": "deepfake",
        "Class": "kind",
        "LandmarkMode": "landmarkMode",
        "Yaw": "yaw",
        "Pitch": "pitch",
        "Roll": "roll",
        "ImageWidth": "imageWidth",
        "ImageHeight": "imageHeight",
    }
    if key in known:
        return known[key]
    if key and key[0].isupper():
        return key[0].lower() + key[1:]
    return key


def _remap_face(face: dict) -> dict:
    out: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    for key, value in face.items():
        if key in ("faceId", "id"):
            out["id"] = value
        elif key in ("faceRegion", "box"):
            out["box"] = value
        elif key in ("facePoints", "landmarks"):
            out["landmarks"] = value
        elif key in ("facePose", "pose"):
            out["pose"] = value
        elif key in ("attributes", "traits"):
            traits = {}
            if isinstance(value, dict):
                for attr_key, attr in value.items():
                    traits[_trait_key(str(attr_key))] = attr
            out["traits"] = traits
        elif key in ("features", "crop", "status", "index"):
            out[key] = value
        else:
            extras[key] = value
    if extras:
        out["extras"] = extras
    return out


def _remap_template(item: dict) -> dict:
    out: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    for key, value in item.items():
        if key in ("faceRegion", "box"):
            out["box"] = value
        elif key in ("facePoints", "landmarks"):
            out["landmarks"] = value
        elif key in ("featureSize", "size"):
            out["size"] = value
        elif key == "feature":
            out["feature"] = value
        else:
            extras[key] = value
    if extras:
        out["extras"] = extras
    return out


def _remap_pair(item: dict) -> dict:
    pair: dict[str, Any] = {}
    if "similarity" in item:
        pair["score"] = item["similarity"]
    elif "score" in item:
        pair["score"] = item["score"]
    if "firstFaceId" in item:
        pair["leftFaceId"] = item["firstFaceId"]
    elif "leftFaceId" in item:
        pair["leftFaceId"] = item["leftFaceId"]
    if "secondFaceId" in item:
        pair["rightFaceId"] = item["secondFaceId"]
    elif "rightFaceId" in item:
        pair["rightFaceId"] = item["rightFaceId"]
    if "firstImageId" in item:
        pair["leftImageId"] = item["firstImageId"]
    elif "leftImageId" in item:
        pair["leftImageId"] = item["leftImageId"]
    if "secondImageId" in item:
        pair["rightImageId"] = item["secondImageId"]
    elif "rightImageId" in item:
        pair["rightImageId"] = item["rightImageId"]
    skip = {
        "similarity",
        "score",
        "firstFaceId",
        "secondFaceId",
        "firstImageId",
        "secondImageId",
        "leftFaceId",
        "rightFaceId",
        "leftImageId",
        "rightImageId",
    }
    for key, value in item.items():
        if key not in skip:
            pair[key] = value
    return pair


def _flatten_ixface(doc: dict) -> dict:
    result = _as_dict(doc.get("result"))
    out: dict[str, Any] = {}
    for key, value in result.items():
        if key in ("message", "scale"):
            continue
        out[key] = value
    meta = process_meta(doc)
    out["metadata"] = _metadata(meta["status"], meta["message"])
    if meta.get("transactionId"):
        out["metadata"]["transactionId"] = meta["transactionId"]
    if meta.get("timestamp"):
        out["metadata"]["timestamp"] = meta["timestamp"]
    return out


def wrap_process(doc: Any, entitlement: dict | None = None) -> dict:
    """Wrap engine JSON as metadata plus result keys. Idempotent."""
    del entitlement  # not part of the customer process JSON
    if not isinstance(doc, dict):
        doc = {"status": -1, "message": "invalid engine response"}
    if isinstance(doc.get("metadata"), dict) and "transactionId" in doc["metadata"] and doc.get("api") != "face/1":
        return doc
    if doc.get("api") == "face/1":
        return _flatten_ixface(doc)

    status_code = doc.get("status", doc.get("code", -1))
    try:
        status_code = int(status_code)
    except (TypeError, ValueError):
        status_code = -1
    license_error = doc.get("licenseError")
    has_lic = isinstance(license_error, str) and bool(license_error)
    message = license_error if has_lic else (doc.get("message") or "")
    if not message:
        message = "COMPLETED" if status_code == CODE_OK else "failed"

    out: dict[str, Any] = {}
    if "score" in doc:
        out["score"] = doc["score"]
    elif "similarity" in doc:
        out["score"] = doc["similarity"]

    data = doc.get("data")
    if isinstance(data, list):
        faces = []
        events = []
        for item in data:
            if isinstance(item, dict) and ("event" in item or "track_id" in item):
                ev = dict(item)
                inner = ev.get("faces")
                if isinstance(inner, list):
                    ev["faces"] = [
                        _remap_face(face) if isinstance(face, dict) else face for face in inner
                    ]
                events.append(ev)
            elif isinstance(item, dict):
                faces.append(_remap_face(item))
            else:
                faces.append(item)
        if events:
            out["events"] = events
            if faces:
                out["faces"] = faces
        else:
            out["faces"] = faces
    elif isinstance(data, dict):
        live = dict(data)
        if "score" in live and "confidence" not in live:
            live["confidence"] = live.pop("score")
        elif "score" in live:
            live["confidence"] = live["score"]
            live.pop("score", None)
        if "result" in live and "decision" not in live:
            live["decision"] = live.pop("result")
        out["liveness"] = live

    raw_pairs = doc.get("match") if isinstance(doc.get("match"), list) else doc.get("pairs")
    if isinstance(raw_pairs, list):
        out["pairs"] = [_remap_pair(item) if isinstance(item, dict) else item for item in raw_pairs]

    if isinstance(doc.get("detects"), list):
        detects = []
        for det in doc["detects"]:
            if not isinstance(det, dict):
                detects.append(det)
                continue
            entry = {key: value for key, value in det.items() if key not in ("faces",)}
            faces = det.get("faces")
            if isinstance(faces, list):
                entry["faces"] = [_remap_face(face) if isinstance(face, dict) else face for face in faces]
            detects.append(entry)
        out["detects"] = detects

    if isinstance(doc.get("results"), list):
        features = []
        for entry in doc["results"]:
            if not isinstance(entry, dict):
                features.append(entry)
                continue
            mapped = {key: value for key, value in entry.items() if key != "features"}
            items = entry.get("features")
            if isinstance(items, list):
                mapped["features"] = [
                    _remap_template(item) if isinstance(item, dict) else item for item in items
                ]
            features.append(mapped)
        out["features"] = features
    elif "features" in doc:
        out["features"] = doc["features"]

    out["metadata"] = _metadata(status_code, message)
    return out


def doc_view(payload: dict | None) -> dict:
    """Flatten doc/1 into keys demos historically used, plus new names."""
    if not isinstance(payload, dict):
        return {}
    if not is_ixdoc(payload):
        out = dict(payload)
        if "security" in out and "authenticity" not in out:
            out["authenticity"] = out["security"]
        return out

    result = _as_dict(payload.get("result"))
    document = _as_dict(result.get("document"))
    fields = _as_dict(result.get("fields"))
    media = _as_dict(result.get("media"))
    geometry = _as_dict(result.get("geometry"))
    fault = payload.get("fault")

    out: dict[str, Any] = {
        "api": payload.get("api"),
        "ok": payload.get("ok"),
        "statusCode": payload.get("statusCode"),
        "statusText": payload.get("status"),
        "elapsedMs": payload.get("elapsedMs"),
        "entitlement": payload.get("entitlement"),
        "fault": fault,
        "result": result,
        "documentName": document.get("type"),
        "countryName": document.get("country"),
        "score": document.get("confidence"),
        "errorCode": payload.get("statusCode", 0),
        "processingFinished": result.get("processingFinished"),
        "ocr": fields.get("ocr"),
        "mrz": fields.get("mrz"),
        "barcode": fields.get("barcode"),
        "rfid": fields.get("rfid"),
        "nation": fields.get("nation"),
        "imageQuality": result.get("quality"),
        "quality": result.get("quality"),
        "images": media.get("surfaces"),
        "security": result.get("authenticity"),
        "authenticity": result.get("authenticity"),
        "verification": result.get("verification"),
        "status": result.get("engineStatus"),
        "engineStatus": result.get("engineStatus"),
        "position": geometry.get("document"),
        "portrait_rect": geometry.get("portrait"),
        "barcodePosition": geometry.get("barcode"),
        "geometry": geometry,
        "extras": result.get("extras"),
    }
    if isinstance(fault, dict) and fault.get("code") == "LICENSE":
        out["licenseError"] = fault.get("message")
    return out


def face_view(payload: dict | None) -> dict:
    """Flatten process JSON for detect / quality / match / liveness demos."""
    if not isinstance(payload, dict):
        return {}
    if payload.get("api") == "face/1":
        payload = wrap_process(payload)
    elif not (isinstance(payload.get("metadata"), dict) and "status" in payload["metadata"]):
        payload = wrap_process(payload)

    meta = process_meta(payload)
    status = meta["status"]
    message = meta["message"]
    ok = status in (CODE_OK, CODE_NO_FACE)
    out: dict[str, Any] = {
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else meta,
        "ok": ok,
        "status": status,
        "statusCode": status,
        "message": message,
        "faces": payload.get("faces"),
        "pairs": payload.get("pairs"),
        "detects": payload.get("detects"),
        "features": payload.get("features"),
        "events": payload.get("events"),
        "liveness": payload.get("liveness"),
        "score": payload.get("score"),
        "success": ok,
        "result": {key: value for key, value in payload.items() if key != "metadata"},
    }
    live = _as_dict(payload.get("liveness"))
    if live:
        data = dict(live)
        if "confidence" in data and "score" not in data:
            data["score"] = data["confidence"]
        if "decision" in data and "result" not in data:
            data["result"] = data["decision"]
        out["data"] = data
        out["liveness"] = live
    lowered = message.lower()
    if "not licensed" in lowered or "license" in lowered:
        out["licenseError"] = message
    return out


def trait(face: dict | None, *names: str) -> Any:
    if not isinstance(face, dict):
        return None
    traits = face.get("traits") if isinstance(face.get("traits"), dict) else {}
    for name in names:
        if name in traits:
            return traits[name]
        mapped = _trait_key(name)
        if mapped in traits:
            return traits[mapped]
    return None
