#!/usr/bin/env bash
# Build linux/amd64 image (runs on Linux / Windows / macOS Docker hosts).
set -euo pipefail
cd "$(dirname "$0")/.."
TAG="${1:-identixia/face-liveness:local}"

REPO="identixia-IDV/FaceLivenessDetection-Docker"
ASSET="faceliveness-linux.zip"
LIB_RELEASE_LATEST="https://github.com/${REPO}/releases/latest/download/${ASSET}"

need_runtime() {
  [[ ! -f lib/cpu/libFaceLivenessSDK.so ]] \
    || [[ ! -f lib/cpu/recognition-common.xdb ]] \
    || [[ ! -f lib/cpu/recognition-liveness.xdb ]] \
    || [[ ! -f lib/cpu/recognition-deepfake.xdb ]] \
    || [[ ! -f lib/cpu/libFaceLivenessEngine.so ]]
}

if need_runtime; then
  if [[ -f scripts/get_runtime.py ]]; then
    echo "lib/cpu incomplete — fetching GitHub Release runtime…"
    python3 scripts/get_runtime.py
  fi
fi

if need_runtime; then
  echo "ERROR: ./lib/cpu/ is incomplete."
  echo "Need: libFaceLivenessSDK.so, recognition-common.xdb, recognition-liveness.xdb, recognition-deepfake.xdb, libFaceLivenessEngine.so."
  echo "Download the Identixia Linux runtime into ./lib/cpu/:"
  echo "  python3 scripts/get_runtime.py"
  echo "  # $LIB_RELEASE_LATEST"
  exit 1
fi

docker build --platform linux/amd64 -f docker/Dockerfile -t "$TAG" .
echo "Built $TAG (linux/amd64)"
