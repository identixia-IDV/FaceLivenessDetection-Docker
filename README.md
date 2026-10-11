<div align="center">
<img alt="Identixia" src="https://raw.githubusercontent.com/identixia-IDV/identixia-assets/main/brand/logo.png" width="320"/>

<a href="https://identixia.com"><img src="https://img.shields.io/badge/Website-0F766E?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Website" /></a>
<a href="https://docs.identixia.com"><img src="https://img.shields.io/badge/Docs-0F766E?style=for-the-badge&logo=gitbook&logoColor=white" alt="Docs" /></a>
<a href="https://huggingface.co/Identixia"><img src="https://img.shields.io/badge/HuggingFace-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black" alt="Hugging Face" /></a>
<a href="https://hub.docker.com/u/identixia"><img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker Hub" /></a>
<a href="https://playground.identixia.com/"><img src="https://img.shields.io/badge/Playground-0F766E?style=for-the-badge&logo=cloudplayground&logoColor=white" alt="Playground" /></a>
</div>

<div align="center">

# <img src="https://cdn.simpleicons.org/docker/2496ED" width="32" height="32" alt="" /> Face Liveness Detection SDK for Linux / Docker — HTTP API Demo | Identixia

</div>

Integrate **face liveness detection and anti-spoofing** with the **Identixia Linux / Docker SDK**. This repository provides a self-hosted Linux / Docker HTTP API for passive face liveness detection and deepfake detection. Use presentation attack detection (PAD) to check for face spoofing and deepfake detection to check for manipulated face images. The combined authenticity result is REAL only when both checks pass. Face recognition and matching are not included.

Use the sample to add selfie liveness checks to remote onboarding and biometric identity verification alongside a separate face matching service. Processing runs on your own server; images are not sent to the Identixia cloud.

> For setup, integration, and API guides, see the [Face Liveness Detection SDK documentation for Linux / Docker](https://docs.identixia.com/developers/face-sdk/liveness-linux-docker). This page covers the sample repository.

## <img src="https://api.iconify.design/lucide/clipboard-list.svg?color=%230F766E" width="24" height="24" alt="" /> SDK overview

Start the server and request its machine code using `GET /api/machinecode`. Send that code to [contact@identixia.com](mailto:contact@identixia.com) to request a license for this machine. Apply the returned key using the activation instructions below.

| Topic | Basic information |
| --- | --- |
| **Product** | On-premise **face liveness** for Linux / Docker |
| **What you run** | HTTP API on port **14105** |
| **Gradio demo** | Port **14205** |
| **Docker image** | `identixia/face-liveness` |
| **Models included** | `recognition-common.xdb`, `recognition-liveness.xdb`, `recognition-deepfake.xdb` |
| **Models left out** | `recognition.xdb`, `recognition-attr.xdb`, `recognition-quality.xdb` |
| **Privacy** | Biometrics stay in your cluster — no Identixia cloud |

---

## <img src="https://api.iconify.design/lucide/package.svg?color=%230F766E" width="24" height="24" alt="" /> SDK installation

Run the following script to download the native SDK libraries and model files from this repository’s GitHub Releases. The script places each file in the folder used by the sample.

```bash
python scripts/get_runtime.py
```

To select a release explicitly, pass its tag with `--tag`. For example:

```bash
python scripts/get_runtime.py --tag 1.0.0
```

Docker Hub images already include the runtime. For a host install, unpack the GitHub Release into `./lib/cpu/`.

---

## <img src="https://api.iconify.design/lucide/terminal.svg?color=%230F766E" width="24" height="24" alt="" /> Quick start

### <img src="https://img.shields.io/badge/-1-0F766E?style=for-the-badge" alt="" /> Run the server

```bash
docker pull identixia/face-liveness:latest
docker run -d --name identixia-face-liveness \
  --shm-size=1gb --privileged \
  -p 14105:14105 \
  -v /etc/machine-id:/etc/machine-id:ro \
  identixia/face-liveness:latest
```

Copy `.env.example` to `.env` and edit the settings for your installation: `PORT`, `LICENSE`, `API_BASE`, and `DEMO_PORT`. Environment variables already set in the shell take precedence over values in `.env`.

### <img src="https://img.shields.io/badge/-2-0F766E?style=for-the-badge" alt="" /> Get a license

```bash
curl -s http://127.0.0.1:14105/api/machinecode
```

The JSON response contains your machine code in `data.machinecode`. This value identifies the machine for licensing.

Email the machine code and the product you want to use to [contact@identixia.com](mailto:contact@identixia.com) to request a license key.

### <img src="https://img.shields.io/badge/-3-0F766E?style=for-the-badge" alt="" /> Activate / license

Replace `YOUR_KEY` in the request below with the license key issued for this machine. The activation endpoint saves the key to the server’s `.env` file and attempts to initialize the SDK. For a local installation, you can also set `LICENSE=YOUR_KEY` in the repository’s `.env` file and restart the server.

```bash
curl -s -X POST http://127.0.0.1:14105/api/activate -H "Content-Type: application/json" -d "{\"license\":\"YOUR_KEY\"}"
```

### <img src="https://img.shields.io/badge/-4-0F766E?style=for-the-badge" alt="" /> Check that it is running

```bash
curl -s http://127.0.0.1:14105/api/health
```

### <img src="https://img.shields.io/badge/-5-0F766E?style=for-the-badge" alt="" /> Try the API

Liveness calls:

- `POST /api/face/liveness` — Combined authenticity result from presentation attack detection and deepfake checks
- `POST /api/face/deepfake` — deepfake-only check

---

## <img src="https://api.iconify.design/lucide/list-checks.svg?color=%230F766E" width="24" height="24" alt="" /> Features

| Capability | What it does |
| --- | --- |
| **Passive liveness** | Run presentation attack detection when licensed |
| **Deepfake** | Check for manipulated face images; report REAL only when both liveness and deepfake checks pass |
| **Docker image** | Prebuilt runtime for Linux hosts |

---

## <img src="https://api.iconify.design/lucide/pc-case.svg?color=%230F766E" width="24" height="24" alt="" /> System requirements

| | |
| --- | --- |
| API port | **14105** |
| Gradio demo port | **14205** |
| Runtime download | `python scripts/get_runtime.py` |

## <img src="https://api.iconify.design/lucide/braces.svg?color=%230F766E" width="24" height="24" alt="" /> API

HTTP API on port **14105**. For image-processing requests, encode the JPEG image as base64 and include it in the JSON request body. Control routes return `{success, code, message, request_id, data}`.

| Call | Route |
| --- | --- |
| Health | `GET /api/health` |
| Machine code | `GET /api/machinecode` |
| Activate | `POST /api/activate` with a JSON body containing your license key: `{"license":"YOUR_KEY"}` |
| License status | `GET /api/licenseStatus` |
| Liveness | `POST /api/face/liveness` — REAL only if PAD and deepfake both pass |
| Recognition / 1:N | Not in this build. Use a Face Recognition repository. |

```bash
curl -s http://127.0.0.1:14105/api/health
```

---

## <img src="https://api.iconify.design/lucide/layers.svg?color=%230F766E" width="24" height="24" alt="" /> SDKs for other platforms

| | Platform | Repo |
| --- | --- | --- |
| <img src="https://cdn.simpleicons.org/android/3DDC84" width="18" height="18" alt="" /> | Android | [FaceLivenessDetection-Android](https://github.com/identixia-IDV/FaceLivenessDetection-Android) |
| <img src="https://cdn.simpleicons.org/apple/000000" width="18" height="18" alt="" /> | iOS | [FaceLivenessDetection-iOS](https://github.com/identixia-IDV/FaceLivenessDetection-iOS) |
| <img src="https://cdn.simpleicons.org/flutter/02569B" width="18" height="18" alt="" /> | Flutter | [FaceLivenessDetection-Flutter](https://github.com/identixia-IDV/FaceLivenessDetection-Flutter) |
| <img src="https://cdn.simpleicons.org/react/61DAFB" width="18" height="18" alt="" /> | React Native | [FaceLivenessDetection-React-Native](https://github.com/identixia-IDV/FaceLivenessDetection-React-Native) |
| <img src="https://cdn.simpleicons.org/ionic/3880FF" width="18" height="18" alt="" /> | Ionic Capacitor | [FaceLivenessDetection-Ionic-Capacitor](https://github.com/identixia-IDV/FaceLivenessDetection-Ionic-Capacitor) |
| <img src="https://cdn.simpleicons.org/apachecordova/E8E8E8" width="18" height="18" alt="" /> | Ionic Cordova | [FaceLivenessDetection-Ionic-Cordova](https://github.com/identixia-IDV/FaceLivenessDetection-Ionic-Cordova) |
| <img src="https://cdn.simpleicons.org/windows/0078D4" width="18" height="18" alt="" /> | Windows | [FaceLivenessDetection-Windows](https://github.com/identixia-IDV/FaceLivenessDetection-Windows) |
| <img src="https://cdn.simpleicons.org/docker/2496ED" width="18" height="18" alt="" /> | Linux / Docker ← this repo | [FaceLivenessDetection-Docker](https://github.com/identixia-IDV/FaceLivenessDetection-Docker) |

---

## <img src="https://api.iconify.design/lucide/mail.svg?color=%230F766E" width="24" height="24" alt="" /> Contact

<div align="center">

<a href="mailto:contact@identixia.com"><img alt="Email contact@identixia.com" src="https://img.shields.io/badge/Email-contact%40identixia.com-0F766E?style=for-the-badge&logo=gmail&logoColor=white" /></a>
<a href="https://wa.me/17018854218"><img alt="WhatsApp +1 (701) 885-4218" src="https://img.shields.io/badge/WhatsApp-%2B1_(701)_885--4218-25D366?style=for-the-badge&logo=whatsapp&logoColor=white" /></a>
<a href="https://t.me/identixia"><img alt="Telegram @identixia" src="https://img.shields.io/badge/Telegram-%40identixia-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" /></a>

</div>

---
