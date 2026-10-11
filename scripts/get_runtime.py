#!/usr/bin/env python3
"""Download Identixia engine runtime from GitHub Releases into this repository.

Run from a product repository root (Android / iOS / Windows / Docker / Flutter /
React Native / Ionic). Detects the product from the folder name (or git remote)
and places each Release asset in the path that product expects.

Examples
--------
  python scripts/get_runtime.py
  python scripts/get_runtime.py --tag 1.0.0
  python scripts/get_runtime.py --tag latest
  python scripts/get_runtime.py --org identixia-IDV --force

Environment
-----------
  IDENTIXIA_RUNTIME_TAG   Default tag when ``--tag`` is omitted (default: latest)
  IDENTIXIA_GITHUB_ORG    Override org (default: identixia-IDV)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# Allow running as scripts/get_runtime.py from a product clone that vendors
# only this file (layout table is inlined below when runtime_layout is absent).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    import runtime_layout as layout  # type: ignore
except ImportError:  # vendored into a product repo without runtime_layout.py
    layout = None  # type: ignore


VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+$")


def die(msg: str, code: int = 1) -> None:
    print("ERROR:", msg, file=sys.stderr)
    raise SystemExit(code)


def detect_repo_name(cwd: Path) -> str:
    # Prefer directory name (customer clones match GitHub repo name).
    name = cwd.name
    if layout and layout.lookup(name):
        return name
    # Fall back to git remote
    git = cwd / ".git"
    if git.exists():
        try:
            import subprocess

            r = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
            url = (r.stdout or "").strip().rstrip("/")
            if url:
                base = url.split(":")[-1]
                base = base.split("/")[-1]
                if base.endswith(".git"):
                    base = base[:-4]
                if layout and layout.lookup(base):
                    return base
                return base
        except Exception:
            pass
    return name


def _fmt_bytes(n: float) -> str:
    units = ("B", "KB", "MB", "GB")
    v = float(max(0, n))
    for unit in units:
        if v < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(v)} {unit}"
            return f"{v:.1f} {unit}"
        v /= 1024.0
    return f"{v:.1f} GB"


def _progress_line(prefix: str, done: int, total: int | None, started: float) -> str:
    elapsed = max(time.monotonic() - started, 0.001)
    speed = done / elapsed
    if total and total > 0:
        pct = min(100.0, 100.0 * done / total)
        bar_w = 24
        filled = min(bar_w, int(bar_w * done / total))
        bar = "#" * filled + "-" * (bar_w - filled)
        eta = ""
        if speed > 0 and done < total:
            remain = (total - done) / speed
            eta = f" ETA {int(remain // 60)}m{int(remain % 60):02d}s"
        return (
            f"\r{prefix} [{bar}] {pct:5.1f}% "
            f"{_fmt_bytes(done)}/{_fmt_bytes(total)} "
            f"{_fmt_bytes(speed)}/s{eta}"
        )
    return f"\r{prefix} {_fmt_bytes(done)} downloaded ({_fmt_bytes(speed)}/s)"


def download(url: str, dest: Path, *, attempts: int = 4) -> None:
    """Stream ``url`` to ``dest`` with a live progress line and retries."""
    print(f"GET {url}", flush=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    chunk = 1024 * 256
    last_err: BaseException | None = None

    for attempt in range(1, attempts + 1):
        existing = dest.stat().st_size if dest.is_file() else 0
        headers = {
            "User-Agent": "identixia-get-runtime/1.0 (+https://github.com/identixia-IDV)",
            "Accept": "*/*",
        }
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
                if status == 200:
                    mode = "wb"
                    done = 0
                    total_hdr = resp.headers.get("Content-Length")
                    total = int(total_hdr) if total_hdr and total_hdr.isdigit() else None
                elif status == 206:
                    mode = "ab"
                    done = existing
                    cr = resp.headers.get("Content-Range") or ""
                    total = None
                    if "/" in cr:
                        try:
                            total = int(cr.rsplit("/", 1)[-1])
                        except ValueError:
                            total = None
                    if total is None:
                        cl = resp.headers.get("Content-Length")
                        if cl and cl.isdigit():
                            total = existing + int(cl)
                else:
                    die(f"download failed ({status}): {url}")

                started = time.monotonic()
                last_draw = 0.0
                with open(dest, mode) as out:
                    while True:
                        block = resp.read(chunk)
                        if not block:
                            break
                        out.write(block)
                        done += len(block)
                        now = time.monotonic()
                        if now - last_draw >= 0.2 or (total and done >= total):
                            sys.stdout.write(
                                _progress_line("  downloading", done, total, started)
                            )
                            sys.stdout.flush()
                            last_draw = now
                sys.stdout.write(
                    _progress_line("  downloading", done, total or done, started) + "\n"
                )
                sys.stdout.flush()

            size = dest.stat().st_size if dest.is_file() else 0
            if size < 1024:
                die(f"download too small ({size} bytes): {url}")
            print(f"  -> {dest} ({_fmt_bytes(size)})", flush=True)
            return
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 416:
                size = dest.stat().st_size if dest.is_file() else 0
                if size >= 1024:
                    print(
                        f"  -> {dest} ({_fmt_bytes(size)}) [already complete]",
                        flush=True,
                    )
                    return
            if isinstance(exc, urllib.error.HTTPError) and exc.code in {401, 403, 404}:
                die(f"download failed ({exc.code}): {url}")
            if dest.is_file() and dest.stat().st_size < 1024:
                dest.unlink(missing_ok=True)
            wait = min(2 ** (attempt - 1), 8)
            print(
                f"\n  WARN attempt {attempt}/{attempts} failed: {exc}; "
                f"retry in {wait}s...",
                flush=True,
            )
            time.sleep(wait)

    die(f"download failed after {attempts} attempts: {url} ({last_err})")


def extract_zip(zip_path: Path, dest_dir: Path, members: tuple[str, ...] = ()) -> None:
    """Extract ``zip_path`` into ``dest_dir`` (creates dest).

    If every member shares one top-level folder whose name equals ``dest_dir.name``
    (e.g. zip rooted at ``cpu/...`` into ``lib/cpu``), that folder is stripped.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if members:
            allow = set(members)
            infos = [
                i
                for i in infos
                if i.filename in allow
                or any(i.filename.startswith(m.rstrip("/") + "/") for m in members)
            ]
        tops = {i.filename.split("/", 1)[0] for i in infos if "/" in i.filename}
        strip_prefix = ""
        if len(tops) == 1:
            only = next(iter(tops))
            if only == dest_dir.name or only in {
                "cpu",
                "libfacesdk",
                "libfacefullsdk",
                "libfacerecognitionsdk",
                "libfacelivenesssdk",
                "libdocsdk",
                "libdocumentfullsdk",
                "libdocumentrecognitionsdk",
                "libdocumentlivenesssdk",
                "Frameworks",
            }:
                strip_prefix = only + "/"
        total_files = len(infos)
        started = time.monotonic()
        for idx, info in enumerate(infos, 1):
            name = info.filename
            rel = (
                name[len(strip_prefix) :]
                if strip_prefix and name.startswith(strip_prefix)
                else name
            )
            if not rel or rel.endswith("/"):
                continue
            target = (dest_dir / rel).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                die(f"zip slip blocked: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 256)
            if total_files >= 8 and (
                idx == total_files or idx % max(1, total_files // 20) == 0
            ):
                sys.stdout.write(
                    _progress_line("  extracting", idx, total_files, started)
                )
                sys.stdout.flush()
        if total_files >= 8:
            sys.stdout.write(
                _progress_line("  extracting", total_files, total_files, started) + "\n"
            )
            sys.stdout.flush()
    print(f"  extracted -> {dest_dir}", flush=True)


def _present_databases(root: Path, name: str) -> set[str]:
    """Basenames of ``*.xdb`` found where this product keeps runtime packs."""
    found: set[str] = set()
    # Scan install destinations + common runtime folders (product may already
    # have packs from a prior export).
    candidates: list[Path] = [root]
    rt = layout.lookup(name) if layout else None
    if rt:
        for rule in rt.assets:
            candidates.append(root / rule.dest)
    for extra in (
        root / "lib" / "cpu",
        root / "libfacesdk" / "databases",
        root / "databases",
        root / "libdocsdk",
    ):
        candidates.append(extra)
    seen: set[Path] = set()
    for base in candidates:
        try:
            base = base.resolve()
        except OSError:
            continue
        if base in seen or not base.exists():
            continue
        seen.add(base)
        if base.is_file() and base.suffix.lower() == ".xdb":
            found.add(base.name)
            continue
        if not base.is_dir():
            continue
        # Prefer shallow globs; also cover AAR-embedded document.xdb.
        for path in base.rglob("*.xdb"):
            if path.is_file():
                found.add(path.name)
        if base.suffix.lower() == ".aar" or any(base.glob("*.aar")):
            for aar in [base] if base.suffix.lower() == ".aar" else base.glob("*.aar"):
                try:
                    with zipfile.ZipFile(aar, "r") as zf:
                        for n in zf.namelist():
                            if n.endswith(".xdb"):
                                found.add(Path(n).name)
                except zipfile.BadZipFile:
                    pass
    return found


def verify_databases(name: str, root: Path) -> None:
    """Fail if required feature-pack databases did not land after download."""
    if layout is None:
        return
    expected = layout.expected_databases(name)
    if not expected:
        # Document Android / iOS: pack lives inside AAR or framework.
        if "Document" in name and name.endswith("-Android"):
            aar_name = layout.document_aar_name(name)
            aar = root / "libdocsdk" / aar_name
            # xplat may place the AAR elsewhere — scan install dests.
            rt = layout.lookup(name)
            aars = [aar]
            if rt:
                for rule in rt.assets:
                    if rule.asset.endswith(".aar"):
                        aars.append(root / rule.dest)
            ok = False
            for path in aars:
                if path.is_file():
                    try:
                        with zipfile.ZipFile(path, "r") as zf:
                            if any(n.endswith("document.xdb") for n in zf.namelist()):
                                ok = True
                                break
                    except zipfile.BadZipFile:
                        pass
            if not ok and any(p.is_file() for p in aars):
                die(
                    f"{name}: document.xdb missing inside {aar_name} — "
                    f"re-run get_runtime.py --force after the Release is fixed"
                )
        return
    present = _present_databases(root, name)
    missing = [n for n in expected if n not in present]
    if missing:
        die(
            f"{name}: missing database pack(s) after download: {', '.join(missing)}. "
            f"The GitHub Release was published without them — re-run "
            f"repositories/APPs/github_manage.py update_runtime for this product."
        )
    print(f"databases ok: {', '.join(expected)}", flush=True)


def align_runtime_names(root: Path, name: str) -> None:
    """Rename combined-host artifacts to the product-specific SDK names.

    Thin Document Windows apps download the combined zip (``DocumentFullSDK.dll``).
    Thin Face Android apps may download ``facefullsdk.aar``. Apps and SDK builds
    use product-specific names (``DocumentRecognitionSDK.dll``, ``facerecognitionsdk.aar``,
    …) — same rename document_split_prepare applies when building thin SDKs.
    """
    if layout is None:
        return

    if "Document" in name and name.endswith("-Windows"):
        cpu = root / "lib" / "cpu"
        wanted = layout.windows_dll_name(name)
        wanted_path = cpu / wanted
        if cpu.is_dir() and not wanted_path.is_file():
            for alt in (
                "DocumentFullSDK.dll",
                "DocumentRecognitionSDK.dll",
                "DocumentLivenessSDK.dll",
            ):
                alt_path = cpu / alt
                if alt_path.is_file() and alt != wanted:
                    alt_path.replace(wanted_path)
                    print(f"renamed {alt} -> {wanted}", flush=True)
                    break

    if name.startswith("Face"):
        wanted = f"{layout.face_artifact_stem(name)}.aar"
        module = f"lib{layout.face_artifact_stem(name)}"
        for lib in (
            root / module,
            root / "example" / "android" / module,
            root / "libfacesdk",
            root / "example" / "android" / "libfacesdk",
            root / "Identixia" / "src" / "android",
            root / "android" / "libs",
        ):
            wanted_path = lib / wanted
            if not lib.is_dir() or wanted_path.is_file():
                continue
            for alt in (
                "facefullsdk.aar",
                "facerecognitionsdk.aar",
                "facelivenesssdk.aar",
            ):
                alt_path = lib / alt
                if alt_path.is_file() and alt != wanted:
                    alt_path.replace(wanted_path)
                    print(f"renamed {alt} -> {wanted}", flush=True)
                    break

    if name.endswith("-Ionic-Cordova"):
        plugin = "DocumentRecognitionPlugin" if "Document" in name else "Identixia"
        android = root / plugin / "src" / "android"
        if android.is_dir():
            libs = android / "libs"
            if libs.is_dir():
                for aar in libs.glob("*.aar"):
                    target = android / aar.name
                    if target.is_file():
                        aar.unlink()
                        print(f"removed {aar}", flush=True)
                    else:
                        aar.replace(target)
                        print(f"moved {aar.name} -> {target}", flush=True)
            loose_db = android / "databases"
            if loose_db.is_dir():
                db_out = libs / "databases"
                db_out.mkdir(parents=True, exist_ok=True)
                for src in loose_db.glob("*.xdb"):
                    target = db_out / src.name
                    if not target.is_file():
                        src.replace(target)
                        print(f"moved {src.name} -> {target}", flush=True)
                if not any(loose_db.iterdir()):
                    loose_db.rmdir()


def install_asset(
    *,
    org: str,
    repo: str,
    rule,  # layout.AssetRule
    tag: str | None,
    root: Path,
    force: bool,
) -> None:
    source_repo = rule.source_repo or repo
    url = layout.release_url(org, source_repo, rule.asset, tag)
    dest = root / rule.dest
    if rule.kind == "file":
        if dest.is_file() and not force and dest.stat().st_size > 1024:
            print(f"SKIP exists: {dest} (use --force to replace)", flush=True)
            return
        with tempfile.TemporaryDirectory(prefix="ix-rt-") as tmp:
            part = Path(tmp) / rule.asset
            download(url, part)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(part, dest)
            print(f"OK file: {dest}", flush=True)
        return

    # zip
    marker_ok = False
    if dest.is_dir() and not force:
        # Heuristic: skip if any engine binary already present
        for pat in (
            "*.aar",
            "*.dll",
            "*.so",
            "*.xcframework",
            "*.framework",
            "*.xdb",
        ):
            if any(dest.rglob(pat)):
                marker_ok = True
                break
        if marker_ok:
            print(f"SKIP exists: {dest} (use --force to replace)", flush=True)
            return

    with tempfile.TemporaryDirectory(prefix="ix-rt-") as tmp:
        part = Path(tmp) / rule.asset
        download(url, part)
        extract_zip(part, dest, rule.members)
        print(f"OK zip: {dest}", flush=True)


def main(argv: list[str] | None = None) -> int:
    if layout is None:
        die(
            "runtime_layout.py is missing next to get_runtime.py — "
            "copy both files into scripts/ from the Identixia workspace"
        )

    ap = argparse.ArgumentParser(
        description="Download Identixia runtime from GitHub Releases into this repository.",
    )
    ap.add_argument(
        "--tag",
        default=os.environ.get("IDENTIXIA_RUNTIME_TAG", "latest"),
        help="Release tag (1.0.0 / v1.0.0) or 'latest' (default)",
    )
    ap.add_argument(
        "--org",
        default=os.environ.get("IDENTIXIA_GITHUB_ORG", layout.DEFAULT_ORG),
        help=f"GitHub org (default: {layout.DEFAULT_ORG})",
    )
    ap.add_argument(
        "--repo-dir",
        default=".",
        help="Product repository root (default: cwd)",
    )
    ap.add_argument(
        "--name",
        default="",
        help="Override product repo name (default: detect from folder / git remote)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Replace existing runtime files",
    )
    args = ap.parse_args(argv)

    root = Path(args.repo_dir).resolve()
    name = (args.name or detect_repo_name(root)).strip()
    if layout.is_sdk_repo(name):
        die(f"{name} is a private SDK kit — run get_runtime.py from a product / app repository")

    rt = layout.lookup(name)
    if not rt:
        die(
            f"no runtime layout for {name!r}. "
            "Run this from an Identixia product repository root."
        )

    tag = (args.tag or "latest").strip()
    if tag != "latest" and not VERSION_RE.match(tag):
        die(f"tag must look like 1.0.0, v1.0.0, or latest (got {tag!r})")
    # Normalize preferred form without forcing v-prefix (Release tags are bare 1.0.0).
    if tag.startswith("v") and VERSION_RE.match(tag):
        # Keep as-is; publish accepts both. Prefer bare for download if latest not used.
        pass

    print(f"Repository: {name}", flush=True)
    print(f"Org: {args.org}  tag: {tag}", flush=True)
    for rule in rt.assets:
        src = rule.source_repo or name
        print(f"- {rule.asset}  <=  {src}  ->  {rule.dest}", flush=True)
        install_asset(
            org=args.org,
            repo=name,
            rule=rule,
            tag=None if tag == "latest" else tag,
            root=root,
            force=bool(args.force),
        )
    align_runtime_names(root, name)
    verify_databases(name, root)
    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
