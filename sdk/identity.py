"""Gallery identify document. Matching stays a match document; names stay in SQLite."""

from __future__ import annotations

import base64
from typing import Callable

import ix_payload


def feature_bytes(value) -> bytes:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="ignore")
    else:
        text = str(value or "")
    text = "".join(text.split())
    if text.startswith("data:") and "base64," in text:
        text = text.split("base64,", 1)[1]
    return base64.b64decode(text, validate=False)


def identify_document(probe: dict, people, threshold: float, score_fn: Callable, entitlement: dict | None = None) -> dict:
    """Build the identify match document as metadata plus result keys.

    ``people`` are gallery rows with ``id`` and ``feature``. ``score_fn`` returns
    a similarity, or a negative value when the templates cannot be compared.
    Hits use the gallery row id as ``rightImageId``, not the list position.
    """
    matches = []
    compared = 0
    for person in people:
        raw = score_fn(probe.get("feature"), person.feature)
        if raw is None or raw < 0:
            continue
        compared += 1
        score = round(float(raw), 4)
        if score < threshold:
            continue
        matches.append(
            {
                "leftFaceId": 0,
                "rightFaceId": 0,
                "leftImageId": 0,
                "rightImageId": person.id,
                "score": score,
            }
        )
    if people and compared == 0:
        return ix_payload.wrap_process({"status": -1, "message": "feature compare failed"}, entitlement)
    matches.sort(key=lambda row: row["score"], reverse=True)
    face = {
        "id": 0,
        "box": probe.get("box") or probe.get("faceRegion") or {},
        "landmarks": probe.get("landmarks") or probe.get("facePoints") or [],
    }
    return ix_payload.wrap_process(
        {
            "status": 0,
            "detects": [{"imageId": 0, "status": 0, "faces": [face]}],
            "pairs": matches,
        },
        entitlement,
    )
