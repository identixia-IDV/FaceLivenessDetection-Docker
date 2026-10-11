#!/usr/bin/env python3
"""Face Recognition HTTP API — Flask + the sdk package."""

from __future__ import annotations

import sys
from pathlib import Path as _BootPath

_APP_ROOT = _BootPath(__file__).resolve().parent.parent
_PKG_DIR = _BootPath(__file__).resolve().parent
for _p in (_APP_ROOT, _APP_ROOT / "sdk", _PKG_DIR):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.append(_s)

import base64
import json
import os
from pathlib import Path

def _load_env() -> None:
    """Load repo-root ``.env`` without overriding real process env.

    Prefers python-dotenv when installed; otherwise parses KEY=VALUE lines so
    LICENSE is always available at bootstrap even in minimal venvs.
    """
    env_path = _APP_ROOT / ".env"
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore[assignment]
    if load_dotenv is not None:
        load_dotenv(env_path, override=False)
        return
    if not env_path.is_file():
        return
    import os
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        os.environ[key] = val



_load_env()

import traceback

from flask import Flask, Response, request
from werkzeug.exceptions import HTTPException

import gallery
import http_body
import identity
import ix_payload
import license_ux
import sdk

ROOT = _APP_ROOT
app = Flask(__name__)


def envelope(success: bool, code: int, message: str, data=None, status: int = 200):
    return Response(
        json.dumps(
            {
                "success": success,
                "code": code,
                "message": message,
                "request_id": None,
                "data": data,
            }
        ),
        status=status,
        mimetype="application/json",
    )


def sdk_json(result):
    raw = result if isinstance(result, (bytes, bytearray)) else str(result).encode()
    return Response(raw, mimetype="application/json")


@app.errorhandler(Exception)
def unhandled(ex):
    if isinstance(ex, HTTPException):
        return ex
    traceback.print_exc()
    return sdk_json(json.dumps(ix_payload.wrap_process({"status": -1, "message": str(ex)})))


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.route("/api/<path:_unused>", methods=["OPTIONS"])
def options(_unused):
    return Response(status=204)


@app.get("/api/health")
def health():
    return envelope(True, 0, "OK", {"status": "ok"})


@app.get("/api/machinecode")
def machinecode():
    return envelope(True, 0, "OK", {"machinecode": sdk.get_machine_code()})


@app.get("/api/licenseStatus")
def license_status():
    return envelope(True, 0, "OK", sdk.get_license_status())


@app.get("/api/backend")
def backend():
    name = sdk.backend()
    return envelope(
        True,
        0,
        "OK",
        {
            "product": "FaceLiveness",
            "sdk_version": "1.0.0",
            "backend": name or "cpu",
            "lib_dir": f"lib/{name}",
        },
    )


@app.post("/api/activate")
def activate():
    raw = http_body.activate_license_bytes()
    if not raw:
        return envelope(False, -1, "Empty license", None)
    path = license_ux.save_license(ROOT, raw)
    res = sdk.activate(str(path))
    if hasattr(license_ux, "remember_loaded"):
        license_ux.remember_loaded(ROOT)
    if hasattr(license_ux, "mark_sdk_ready"):
        license_ux.mark_sdk_ready(False)
    mc = sdk.get_machine_code()
    if hasattr(license_ux, "ACTIVATION_ENGINE_FAILED") and res == license_ux.ACTIVATION_ENGINE_FAILED:
        return envelope(
            False,
            -2,
            "License accepted but engine failed to start",
            {"activated": True, "initialized": False, "machinecode": mc},
        )
    if res != 0:
        return envelope(
            False,
            -1,
            "Invalid license",
            {"activated": False, "initialized": False, "machinecode": mc},
        )
    if sdk.init_sdk() != 0:
        return envelope(
            False,
            -2,
            "License accepted but engine failed to start",
            {"activated": True, "initialized": False, "machinecode": mc},
        )
    if hasattr(license_ux, "mark_sdk_ready"):
        license_ux.mark_sdk_ready(True)
    return envelope(
        True,
        0,
        "Successfully activated",
        {"activated": True, "initialized": True, "machinecode": mc},
    )



def _image_only(fn):
    try:
        data = http_body.parse_body()
        image = data.get("image")
        if not image:
            return sdk_json(_process_json({"status": -1, "message": "image required"}))
        return sdk_json(fn(image))
    except Exception as ex:
        traceback.print_exc()
        return sdk_json(_process_json({"status": -1, "message": f"{type(ex).__name__}: {ex}"}))


@app.before_request
def _ensure_sdk_for_face():
    if request.path.startswith("/api/face"):
        license_ux.ensure_ready(ROOT, sdk.activate, sdk.init_sdk)


@app.post("/api/face/deepfake")
def deepfake():
    return _image_only(sdk.deepfake)


@app.post("/api/face/liveness")
def liveness():
    data = http_body.parse_body()
    image = data.get("image")
    if not image:
        return envelope(False, -1, "image required", None)
    return sdk_json(sdk.liveness(image))


def _entitlement() -> dict:
    try:
        status = sdk.get_license_status()
    except Exception:  # noqa: BLE001
        return {"recognition": None, "liveness": None}
    return {
        "recognition": bool(status.get("recognition")),
        "liveness": bool(status.get("liveness")),
    }


def _process_json(doc: dict) -> str:
    return json.dumps(ix_payload.wrap_process(doc, _entitlement()))


def _engine(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ix_payload.wrap_process({"status": -1, "message": "invalid engine response"}, _entitlement())
    if isinstance(data, dict):
        return data
    return ix_payload.wrap_process({"status": -1, "message": "invalid engine response"}, _entitlement())


def _view(doc: dict) -> dict:
    return ix_payload.face_view(doc)


@app.errorhandler(HTTPException)
def http_error(ex: HTTPException):
    if ex.code == 404:
        return envelope(False, -10, "Not found", None, 404)
    return envelope(False, -19, ex.description or str(ex), None, ex.code or 500)


@app.errorhandler(Exception)
def fail(ex: Exception):
    if isinstance(ex, HTTPException):
        return http_error(ex)
    return envelope(False, -19, str(ex), None, 500)


def main() -> None:
    gallery.open_db(ROOT)
    license_ux.bootstrap(
        ROOT,
        get_machine_code=sdk.get_machine_code,
        activate=sdk.activate,
        init_sdk=sdk.init_sdk,
    )
    port = int(os.environ.get("PORT", os.environ.get("FACESDK_PORT", "14105")))
    host = os.environ.get("HOST") or os.environ.get("FACESDK_BIND_HOST", "0.0.0.0")
    print("API listening on http://{0}:{1}".format(host, port))
    import port_guard

    port_guard.free_port(port)
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
