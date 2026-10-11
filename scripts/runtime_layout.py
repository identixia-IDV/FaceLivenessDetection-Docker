#!/usr/bin/env python3
"""Canonical GitHub Release runtime assets ↔ local install paths.

Used by:
  - ``scripts/get_runtime.py`` (download into an app / product clone)
  - ``repositories/APPs/github_manage.py update_runtime`` (package + publish Release assets)

Private ``*-SDK`` build kits are never published. Public product repositories
host the Release; apps download from that same repo (or from the paired
Android / iOS product for cross-platform kits).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_ORG = "identixia-IDV"


@dataclass(frozen=True)
class AssetRule:
    """One Release asset and where its contents land in a product clone."""

    # Asset file name on the GitHub Release
    asset: str
    # Local paths that must exist after install (relative to repo root).
    # For zips: directory that receives the extract (or files listed in members).
    dest: str
    # Optional: only these archive members (posix) are extracted; empty = all.
    members: tuple[str, ...] = ()
    # When set, download this asset from another product repo instead of self.
    source_repo: str = ""
    # How to place the download: "zip" (extract), "file" (copy as dest file).
    kind: str = "zip"


@dataclass(frozen=True)
class RepoRuntime:
    """Runtime install plan for one public product repository."""

    name: str
    assets: tuple[AssetRule, ...]
    # Local sources used when *publishing* a Release (relative to repo root).
    # Each entry: (asset_name, local_path_or_dir, zip_root_name_or_empty)
    publish: tuple[tuple[str, str, str], ...] = ()


def face_artifact_stem(name: str) -> str:
    """Android / iOS Release artifact stem. Distinct for recognition, liveness, and both."""
    if "Recognition" in name and "Liveness" in name:
        return "facefullsdk"
    if name.startswith("FaceLiveness"):
        return "facelivenesssdk"
    return "facerecognitionsdk"


def face_android_module(name: str) -> str:
    """Gradle module directory that holds the Face AAR (``libfacefullsdk``, …)."""
    return "lib" + face_artifact_stem(name)


def document_android_module(name: str) -> str:
    """Gradle module directory that holds the Document AAR."""
    return "lib" + Path(document_aar_name(name)).stem


def face_ios_zip_name(name: str) -> str:
    """iOS Release zip name (``{stem}-ios.zip``)."""
    return f"{face_artifact_stem(name)}-ios.zip"


def document_aar_name(name: str) -> str:
    """Android AAR file name. Distinct for recognition, liveness, and both."""
    if "Recognition" in name and "Liveness" in name:
        return "documentfullsdk.aar"
    if "Liveness" in name:
        return "documentlivenesssdk.aar"
    return "documentrecognitionsdk.aar"


def windows_dll_name(name: str) -> str:
    """Windows wrapper DLL name matching ``repositories/SDKs/*-Windows-SDK`` builds.

    - Document recognition → ``DocumentRecognitionSDK.dll``
    - Document liveness → ``DocumentLivenessSDK.dll``
    - Document recognition+liveness → ``DocumentFullSDK.dll``
    - Face recognition / liveness / both → ``FaceRecognitionSDK`` /
      ``FaceLivenessSDK`` / ``FaceFullSDK``
    """
    if "Document" in name:
        if "Recognition" in name and "Liveness" in name:
            return "DocumentFullSDK.dll"
        if "Liveness" in name:
            return "DocumentLivenessSDK.dll"
        return "DocumentRecognitionSDK.dll"
    if "Recognition" in name and "Liveness" in name:
        return "FaceFullSDK.dll"
    if name.startswith("FaceLiveness"):
        return "FaceLivenessSDK.dll"
    return "FaceRecognitionSDK.dll"


def _face_android_zip(aar_name: str = "facerecognitionsdk.aar") -> tuple[tuple[str, str, str], ...]:
    stem = Path(aar_name).stem
    return ((f"{stem}-android.zip", f"lib{stem}", ""),)


# ---------------------------------------------------------------------------
# Product → Release assets
# ---------------------------------------------------------------------------

REPOS: dict[str, RepoRuntime] = {}


def _reg(rt: RepoRuntime) -> None:
    REPOS[rt.name] = rt


# --- Face Android (recognition, liveness, and both use different AAR names) ---
for _name in (
    "FaceRecognition-LivenessDetection-Android",
    "FaceRecognition-Android",
    "FaceLivenessDetection-Android",
):
    # Thin FaceRecognition-Android Release is not published yet — pull the
    # combined host zip (still contains the recognition packs get_runtime verifies).
    if _name == "FaceRecognition-Android":
        _zip = "facefullsdk-android.zip"
        _src = "FaceRecognition-LivenessDetection-Android"
        _publish_zip = "facerecognitionsdk-android.zip"
    else:
        _zip = f"{face_artifact_stem(_name)}-android.zip"
        _src = ""
        _publish_zip = _zip
    _reg(
        RepoRuntime(
            name=_name,
            assets=(
                AssetRule(
                    asset=_zip,
                    dest=face_android_module(_name),
                    kind="zip",
                    source_repo=_src,
                ),
            ),
            publish=((_publish_zip, face_android_module(_name), ""),),
        )
    )

# --- Document Android ---
for _name in (
    "ID-Document-Recognition-Liveness-Detection-Android",
    "ID-Document-Recognition-Android",
    "ID-Document-Liveness-Detection-Android",
):
    _aar = document_aar_name(_name)
    # Thin Document Android hosts are not published yet — pull combined AAR
    # into the product-specific local filename.
    if _name in (
        "ID-Document-Recognition-Android",
        "ID-Document-Liveness-Detection-Android",
    ):
        _asset = "documentfullsdk.aar"
        _src = "ID-Document-Recognition-Liveness-Detection-Android"
    else:
        _asset = _aar
        _src = ""
    _reg(
        RepoRuntime(
            name=_name,
            assets=(
                AssetRule(
                    asset=_asset,
                    dest=f"{document_android_module(_name)}/{_aar}",
                    kind="file",
                    source_repo=_src,
                ),
            ),
            publish=((_aar, f"{document_android_module(_name)}/{_aar}", ""),),
        )
    )

# --- Face / Document Windows (lib/cpu zip) ---
_WINDOWS_FACE = (
    ("FaceRecognition-LivenessDetection-Windows", "facerecognition-liveness-windows.zip"),
    ("FaceRecognition-Windows", "facerecognition-windows.zip"),
    ("FaceLivenessDetection-Windows", "faceliveness-windows.zip"),
)
for _name, _asset in _WINDOWS_FACE:
    _reg(
        RepoRuntime(
            name=_name,
            assets=(AssetRule(asset=_asset, dest="lib/cpu", kind="zip"),),
            publish=((_asset, "lib/cpu", ""),),
        )
    )

for _name, _asset in (
    (
        "ID-Document-Recognition-Liveness-Detection-Windows",
        "documentrecognition-windows.zip",
    ),
    ("ID-Document-Recognition-Windows", "documentrecognition-windows.zip"),
    ("ID-Document-Liveness-Detection-Windows", "documentliveness-windows.zip"),
):
    # Thin Document Windows Releases are not published yet — pull the combined
    # host zip into lib/cpu (still contains document.xdb).
    if _name in (
        "ID-Document-Recognition-Windows",
        "ID-Document-Liveness-Detection-Windows",
    ):
        _get_asset = "documentrecognition-windows.zip"
        _src = "ID-Document-Recognition-Liveness-Detection-Windows"
    else:
        _get_asset = _asset
        _src = ""
    _reg(
        RepoRuntime(
            name=_name,
            assets=(
                AssetRule(
                    asset=_get_asset,
                    dest="lib/cpu",
                    kind="zip",
                    source_repo=_src,
                ),
            ),
            publish=((_asset, "lib/cpu", ""),),
        )
    )

# --- Face / Document Linux (Docker app repos) ---
_LINUX_FACE = (
    ("FaceRecognition-LivenessDetection-Docker", "facerecognition-liveness-linux.zip"),
    ("FaceRecognition-Docker", "facerecognition-linux.zip"),
    ("FaceLivenessDetection-Docker", "faceliveness-linux.zip"),
)
for _name, _asset in _LINUX_FACE:
    _reg(
        RepoRuntime(
            name=_name,
            assets=(AssetRule(asset=_asset, dest="lib/cpu", kind="zip"),),
            publish=((_asset, "lib/cpu", ""),),
        )
    )

for _name, _asset in (
    (
        "ID-Document-Recognition-Liveness-Detection-Docker",
        "documentrecognition-linux.zip",
    ),
    ("ID-Document-Recognition-Docker", "documentrecognition-linux.zip"),
    ("ID-Document-Liveness-Detection-Docker", "documentliveness-linux.zip"),
):
    _reg(
        RepoRuntime(
            name=_name,
            assets=(AssetRule(asset=_asset, dest="lib/cpu", kind="zip"),),
            publish=((_asset, "lib/cpu", ""),),
        )
    )

# --- Face / Document iOS ---
for _name in (
    "FaceRecognition-LivenessDetection-iOS",
    "FaceRecognition-iOS",
    "FaceLivenessDetection-iOS",
):
    _zip = face_ios_zip_name(_name)
    # Thin FaceRecognition-iOS Release is not published yet — get_runtime falls
    # back to the combined host zip (still contains recognition packs).
    if _name == "FaceRecognition-iOS":
        _get = "facefullsdk-ios.zip"
        _src = "FaceRecognition-LivenessDetection-iOS"
    else:
        _get = _zip
        _src = ""
    _reg(
        RepoRuntime(
            name=_name,
            assets=(
                AssetRule(
                    asset=_get,
                    dest=".",
                    kind="zip",
                    source_repo=_src,
                ),
            ),
            publish=((_zip, ".", "ios-bundle"),),
        )
    )

for _name in (
    "ID-Document-Recognition-Liveness-Detection-iOS",
    "ID-Document-Recognition-iOS",
    "ID-Document-Liveness-Detection-iOS",
):
    _src = (
        "ID-Document-Recognition-Liveness-Detection-iOS"
        if _name
        in (
            "ID-Document-Recognition-iOS",
            "ID-Document-Liveness-Detection-iOS",
        )
        else ""
    )
    _reg(
        RepoRuntime(
            name=_name,
            assets=(
                AssetRule(
                    asset="documentfullsdk.xcframework.zip",
                    dest=".",
                    kind="zip",
                    source_repo=_src,
                ),
            ),
            publish=(("documentfullsdk.xcframework.zip", "documentfullsdk.xcframework", "documentfullsdk.xcframework"),),
        )
    )


def _xplat_face(
    name: str,
    android_repo: str,
    ios_repo: str,
    *,
    android_asset: str | None = None,
    ios_asset: str | None = None,
) -> RepoRuntime:
    """Cross-platform Face kits pull Android + iOS product Releases."""
    _mod = face_android_module(name)
    android_dest = {
        "Flutter": f"example/android/{_mod}",
        "React-Native": f"example/android/{_mod}",
        "Ionic-Capacitor": f"example/android/{_mod}",
        "Ionic-Cordova": "Identixia/src/android",
    }
    ios_dest = {
        "Flutter": "ios/Frameworks",
        "React-Native": "ios/Frameworks",
        "Ionic-Capacitor": "ios/Frameworks",
        "Ionic-Cordova": "Identixia/src/ios/Frameworks",
    }
    kind = (
        "Flutter"
        if name.endswith("-Flutter")
        else "React-Native"
        if name.endswith("-React-Native")
        else "Ionic-Cordova"
        if name.endswith("-Ionic-Cordova")
        else "Ionic-Capacitor"
    )
    zip_name = android_asset or f"{face_artifact_stem(name)}-android.zip"
    ios_zip = ios_asset or face_ios_zip_name(name)
    return RepoRuntime(
        name=name,
        assets=(
            AssetRule(
                asset=zip_name,
                dest=android_dest[kind],
                kind="zip",
                source_repo=android_repo,
            ),
            AssetRule(
                asset=ios_zip,
                dest=ios_dest[kind],
                kind="zip",
                source_repo=ios_repo,
            ),
        ),
        publish=(),  # xplat does not host the engine Release; native apps do
    )


def _xplat_doc(
    name: str,
    android_repo: str,
    ios_repo: str,
    *,
    android_asset: str | None = None,
) -> RepoRuntime:
    _aar = document_aar_name(name)
    # Release asset may be the combined AAR while the local dest keeps the
    # product-specific filename (thin Document hosts are not published yet).
    _asset = android_asset or _aar
    _mod = document_android_module(name)
    android_dest = {
        "Flutter": f"example/android/{_mod}/{_aar}",
        "React-Native": f"example/android/{_mod}/{_aar}",
        "Ionic-Capacitor": f"example/android/{_mod}/{_aar}",
        "Ionic-Cordova": f"DocumentRecognitionPlugin/src/android/{_aar}",
    }
    ios_dest = {
        "Flutter": "ios/Frameworks",
        "React-Native": "ios/Frameworks",
        "Ionic-Capacitor": "ios/Frameworks",
        "Ionic-Cordova": "DocumentRecognitionPlugin/src/ios/Frameworks",
    }
    kind = (
        "Flutter"
        if name.endswith("-Flutter")
        else "React-Native"
        if name.endswith("-React-Native")
        else "Ionic-Cordova"
        if name.endswith("-Ionic-Cordova")
        else "Ionic-Capacitor"
    )
    return RepoRuntime(
        name=name,
        assets=(
            AssetRule(
                asset=_asset,
                dest=android_dest[kind],
                kind="file",
                source_repo=android_repo,
            ),
            AssetRule(
                asset="documentfullsdk.xcframework.zip",
                dest=ios_dest[kind],
                kind="zip",
                source_repo=ios_repo,
            ),
        ),
        publish=(),
    )


# Cross-platform Face
for _suffix in ("Flutter", "React-Native", "Ionic-Capacitor", "Ionic-Cordova"):
    _reg(
        _xplat_face(
            f"FaceRecognition-LivenessDetection-{_suffix}",
            "FaceRecognition-LivenessDetection-Android",
            "FaceRecognition-LivenessDetection-iOS",
        )
    )
    # Thin FaceRecognition xplat: thin Android/iOS host Releases are not
    # published yet — pull the combined FaceRecognition-LivenessDetection
    # assets (includes the recognition packs get_runtime verifies).
    _reg(
        _xplat_face(
            f"FaceRecognition-{_suffix}",
            "FaceRecognition-LivenessDetection-Android",
            "FaceRecognition-LivenessDetection-iOS",
            android_asset="facefullsdk-android.zip",
            ios_asset="facefullsdk-ios.zip",
        )
    )
    _reg(
        _xplat_face(
            f"FaceLivenessDetection-{_suffix}",
            "FaceLivenessDetection-Android",
            "FaceLivenessDetection-iOS",
        )
    )

# Cross-platform Document
for _suffix in ("Flutter", "React-Native", "Ionic-Capacitor", "Ionic-Cordova"):
    _reg(
        _xplat_doc(
            f"ID-Document-Recognition-Liveness-Detection-{_suffix}",
            "ID-Document-Recognition-Liveness-Detection-Android",
            "ID-Document-Recognition-Liveness-Detection-iOS",
        )
    )
    # Thin Document xplat: same fallback to the published combined hosts.
    _reg(
        _xplat_doc(
            f"ID-Document-Recognition-{_suffix}",
            "ID-Document-Recognition-Liveness-Detection-Android",
            "ID-Document-Recognition-Liveness-Detection-iOS",
            android_asset="documentfullsdk.aar",
        )
    )
    _reg(
        _xplat_doc(
            f"ID-Document-Liveness-Detection-{_suffix}",
            "ID-Document-Recognition-Liveness-Detection-Android",
            "ID-Document-Recognition-Liveness-Detection-iOS",
            android_asset="documentfullsdk.aar",
        )
    )


def lookup(name: str) -> RepoRuntime | None:
    return REPOS.get(name)


def is_sdk_repo(name: str) -> bool:
    return name.endswith("-SDK")


def paired_sdk_name(name: str) -> str | None:
    """Public product repo → private ``*-SDK`` kit that stages the same runtime."""
    if not name or is_sdk_repo(name):
        return None
    return f"{name}-SDK"


# Feature-pack databases that must ship with the Release (not optional extras).
# Recognition-only kits omit PAD / deepfake packs; combined FaceRecognition-
# LivenessDetection-* hosts ship the full set.
FACE_RECOGNITION_ONLY_DBS: tuple[str, ...] = (
    "recognition.xdb",
    "recognition-common.xdb",
    "recognition-attr.xdb",
    "recognition-quality.xdb",
)
FACE_RECOGNITION_DBS: tuple[str, ...] = FACE_RECOGNITION_ONLY_DBS + (
    "recognition-liveness.xdb",
    "recognition-deepfake.xdb",
)
FACE_LIVENESS_ANDROID_DBS: tuple[str, ...] = (
    "liveness.xdb",
    "recognition-deepfake.xdb",
)
FACE_LIVENESS_DESKTOP_DBS: tuple[str, ...] = (
    "recognition-common.xdb",
    "recognition-liveness.xdb",
    "recognition-deepfake.xdb",
)
DOCUMENT_DBS: tuple[str, ...] = ("document.xdb",)


def expected_databases(name: str) -> tuple[str, ...]:
    """Separate ``*.xdb`` files that must appear in the Release / after get_runtime.

    Document Android embeds ``document.xdb`` inside the AAR — empty here.
    Document iOS embeds it inside the framework bundle when built — empty here
    (packaging still injects the pack if the bundle is missing it).
    Cross-platform Face kits pull the Android zip, so they need the same packs
    under their Android ``libfacefullsdk`` / ``libfacerecognitionsdk`` / ``libfacelivenesssdk`` install path.
    """
    if is_sdk_repo(name) or not name:
        return ()
    if "Document" in name:
        if name.endswith("-Windows") or name.endswith("-Docker"):
            return DOCUMENT_DBS
        return ()
    if name.startswith("FaceLiveness") and "Recognition" not in name:
        if name.endswith(("-Android", "-iOS")):
            return FACE_LIVENESS_ANDROID_DBS
        if name.endswith(("-Windows", "-Docker")):
            return FACE_LIVENESS_DESKTOP_DBS
        if name.endswith(
            ("-Flutter", "-React-Native", "-Ionic-Capacitor", "-Ionic-Cordova")
        ):
            return FACE_LIVENESS_ANDROID_DBS
        return ()
    # Face recognition-only ships matcher packs. Combined also ships liveness packs.
    face_dbs = (
        FACE_RECOGNITION_DBS
        if "Recognition" in name and "Liveness" in name
        else FACE_RECOGNITION_ONLY_DBS
    )
    if name.endswith(("-Android", "-Windows", "-Docker", "-iOS")):
        return face_dbs
    if name.endswith(
        ("-Flutter", "-React-Native", "-Ionic-Capacitor", "-Ionic-Cordova")
    ):
        return face_dbs
    return ()


def database_search_dirs(name: str, product_root: Path, sdk_root: Path | None) -> list[Path]:
    """Ordered dirs to scan for ``*.xdb`` (later entries fill gaps only)."""
    dirs: list[Path] = []
    if "Document" in name:
        if name.endswith(("-Windows", "-Docker")):
            dirs.extend(
                [
                    product_root / "lib" / "cpu",
                    *( [sdk_root / "lib" / "cpu"] if sdk_root else []),
                ]
            )
        elif name.endswith("-iOS"):
            dirs.extend(
                [
                    product_root / "libdocumentfullsdk",
                    product_root / "Frameworks",
                    *(
                        [sdk_root / "libdocumentfullsdk", sdk_root / "lib"]
                        if sdk_root
                        else []
                    ),
                ]
            )
        return [d for d in dirs if d.is_dir()]

    if name.endswith("-Android"):
        asset = (
            "facelivenesssdk"
            if name.startswith("FaceLiveness") and "Recognition" not in name
            else "facerecognitionsdk"
        )
        mod = face_android_module(name)
        dirs.extend(
            [
                product_root / mod / "databases",
                product_root / "libfacesdk" / "databases",
                product_root / "app" / "src" / "main" / "assets" / asset,
                *( [sdk_root / "lib" / "databases"] if sdk_root else []),
            ]
        )
    elif name.endswith(("-Windows", "-Docker")):
        dirs.extend(
            [
                product_root / "lib" / "cpu",
                *( [sdk_root / "lib" / "cpu"] if sdk_root else []),
            ]
        )
    elif name.endswith("-iOS"):
        dirs.extend(
            [
                product_root / "assets",
                product_root / "databases",
                product_root / "FaceRecognitionSDK" / "databases",
                product_root / "FaceLivenessSDK" / "databases",
                product_root / "libfacelivenesssdk",
                product_root / "libfacefullsdk" / "databases",
                product_root / "libfacerecognitionsdk" / "databases",
                product_root / "libfacesdk" / "databases",
                product_root / "Frameworks",
                *(
                    [
                        sdk_root / "lib" / "databases",
                        sdk_root / "libfacelivenesssdk",
                        sdk_root / "libfacerecognitionsdk",
                        sdk_root / "lib",
                        sdk_root / "assets",
                    ]
                    if sdk_root
                    else []
                ),
            ]
        )
    return [d for d in dirs if d.is_dir()]


def product_repo_dir(repos_dir: Path, name: str) -> Path:
    """Local checkout under repositories/APPs or repositories/SDKs."""
    if not name:
        return repos_dir
    if name.endswith("-SDK"):
        return repos_dir / "SDKs" / name
    if name == "identixia-assets" or name.startswith("_"):
        return repos_dir / name
    return repos_dir / "APPs" / name


def collect_databases(
    name: str, product_root: Path, repos_dir: Path
) -> dict[str, Path]:
    """Map ``basename.xdb`` → source path. Product wins over SDK on name clash."""
    sdk_name = paired_sdk_name(name)
    sdk_root = product_repo_dir(repos_dir, sdk_name) if sdk_name else None
    if sdk_root is not None and not sdk_root.is_dir():
        sdk_root = None
    found: dict[str, Path] = {}
    for folder in database_search_dirs(name, product_root, sdk_root):
        for path in sorted(folder.glob("*.xdb")):
            if path.is_file() and path.stat().st_size > 0:
                # First hit wins so product dirs (listed first) keep priority.
                found.setdefault(path.name, path)
        # One level of nested bundles (e.g. framework Resources)
        for path in sorted(folder.rglob("*.xdb")):
            if path.is_file() and path.stat().st_size > 0:
                found.setdefault(path.name, path)
    return found


def missing_databases(name: str, present: dict[str, Path] | set[str]) -> list[str]:
    keys = set(present) if isinstance(present, dict) else set(present)
    return [n for n in expected_databases(name) if n not in keys]


def release_url(org: str, repo: str, asset: str, tag: str | None) -> str:
    """Build download URL. ``tag`` None / 'latest' → releases/latest/download."""
    if not tag or tag == "latest":
        return f"https://github.com/{org}/{repo}/releases/latest/download/{asset}"
    return f"https://github.com/{org}/{repo}/releases/download/{tag}/{asset}"
