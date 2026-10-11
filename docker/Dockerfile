# FaceLiveness-Linux — Linux SDK + Docker (same repo)
# Native libs are linux/amd64; image runs on any Docker host (Win/Mac/Linux).
# Before build: python scripts/get_runtime.py  (fills ./lib/cpu from GitHub Release)
FROM --platform=linux/amd64 python:3.12-slim-trixie


RUN apt-get update -y && apt-get install -y --no-install-recommends \
        psmisc curl util-linux e2fsprogs libgomp1 libstdc++6 libgcc-s1 libuuid1 zlib1g libssl3 \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /root/facesdk


COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt


COPY sdk ./sdk
COPY server ./server
COPY run_server.py ./
COPY lib ./lib/


ENV LD_LIBRARY_PATH=/root/facesdk/lib/cpu
ENV LD_PRELOAD=/root/facesdk/lib/cpu/libFaceLivenessSDK.so
# Listen on product API port 14105 (same as host publish)
ENV PORT=14105
RUN test -f ./lib/cpu/libFaceLivenessSDK.so \
    && test -f ./lib/cpu/libFaceLivenessEngine.so \
    && test -f ./lib/cpu/recognition-common.xdb \
    && test -f ./lib/cpu/recognition-liveness.xdb \
    && test -f ./lib/cpu/recognition-deepfake.xdb \
    && test -e ./lib/cpu/libusb-0.1.so.4


CMD ["python3", "run_server.py"]
EXPOSE 14105
