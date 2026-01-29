# Vision Insight API

[![Part of Vibe Homelab](https://img.shields.io/badge/Vibe%20Homelab-Vision%20Insight-blue)](https://vibe-homelab.github.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> MLX-accelerated Computer Vision API for Apple Silicon Homelab

Mac Mini M4 (Apple Silicon)에서 MLX 가속을 활용한 로컬 AI API 서버입니다. OpenAI 호환 REST API로 이미지 생성 및 비전 분석을 제공합니다.

## 기능

| 태스크 | 엔드포인트 | 설명 |
|--------|-----------|------|
| Text → Image | `POST /v1/images/generations` | 텍스트로 이미지 생성 (FLUX) |
| (Text, Image) → Image | `POST /v1/images/edits` | 이미지 편집/변형 |
| (Text, Image) → Text | `POST /v1/chat/completions` | 이미지 분석 (OpenAI 호환) |
| Image → Text | `POST /v1/vision/analyze` | 구조화된 이미지 분석 |

## 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│  Docker                                                  │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Gateway (:8000) - FastAPI                       │    │
│  └──────────────────────┬──────────────────────────┘    │
└─────────────────────────┼───────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────┐
│  Host (macOS)           │                               │
│  ┌──────────────────────▼──────────────────────────┐    │
│  │  Worker Manager (:8100)                          │    │
│  │  - 워커 자동 스폰/종료                            │    │
│  │  - 메모리 관리                                   │    │
│  │  - Idle timeout (5분) 후 자동 offload            │    │
│  └──────────────────────┬──────────────────────────┘    │
│           ┌─────────────┼─────────────┐                 │
│           ▼             ▼             ▼                 │
│     ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│     │ vlm-fast │  │ vlm-best │  │image-gen │           │
│     │ :8001    │  │ :8002    │  │ :8003    │           │
│     │Moondream │  │Qwen2.5-VL│  │  FLUX    │           │
│     └──────────┘  └──────────┘  └──────────┘           │
│              MLX / Metal Acceleration                   │
└─────────────────────────────────────────────────────────┘
```

## 빠른 시작

### 설치

```bash
# 전체 설치 (서비스 등록 + Docker 시작)
make install
```

### 사용

```bash
# 이미지 생성
curl -X POST http://localhost:8000/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a cat in space", "size": "512x512"}'

# 시스템 상태
curl http://localhost:8000/v1/system/status
```

---

## API Reference

### 1. 이미지 생성 (Text → Image)

**`POST /v1/images/generations`**

텍스트 프롬프트로 이미지를 생성합니다.

#### Request

```json
{
  "prompt": "a cute cat sitting on a chair",
  "size": "1024x1024",
  "model": "schnell",
  "steps": 4,
  "seed": 42,
  "guidance": 3.5
}
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `prompt` | string | (필수) | 이미지 설명 |
| `size` | string | "1024x1024" | 이미지 크기 |
| `model` | string | "schnell" | 모델 (`schnell`=빠름, `dev`=고품질) |
| `steps` | int | 4 | 추론 단계 (schnell: 4, dev: 20) |
| `seed` | int | random | 랜덤 시드 |
| `guidance` | float | 3.5 | Guidance scale |

#### Response

```json
{
  "created": 1706300000,
  "data": [
    {
      "b64_json": "iVBORw0KGgo...",
      "revised_prompt": "a cute cat sitting on a chair"
    }
  ],
  "usage": {
    "latency": 44.5,
    "seed": 42
  }
}
```

---

### 2. 이미지 편집 (Image → Image)

**`POST /v1/images/edits`**

기존 이미지를 텍스트 지시에 따라 변형합니다.

#### Request

```json
{
  "prompt": "make it sunset",
  "image": "<base64 encoded image>",
  "strength": 0.7,
  "steps": 4
}
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `prompt` | string | (필수) | 변경 지시 |
| `image` | string | (필수) | Base64 인코딩된 입력 이미지 |
| `strength` | float | 0.7 | 변형 강도 (0.0=원본 유지, 1.0=완전 재생성) |
| `steps` | int | 4 | 추론 단계 |

---

### 3. 채팅 (Vision) - OpenAI 호환

**`POST /v1/chat/completions`**

이미지와 텍스트를 함께 처리하는 멀티모달 채팅입니다.

#### Request

```json
{
  "model": "vlm-best",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "이 이미지에 뭐가 있어?"},
        {
          "type": "image_url",
          "image_url": {"url": "data:image/png;base64,..."}
        }
      ]
    }
  ],
  "max_tokens": 512
}
```

---

### 4. 이미지 분석 (구조화)

**`POST /v1/vision/analyze`**

미리 정의된 태스크로 이미지를 분석합니다.

#### Request

```json
{
  "image": "<base64 encoded image>",
  "task": "caption",
  "max_tokens": 512
}
```

#### 태스크 종류

| Task | 설명 |
|------|------|
| `caption` | 한 줄 요약 |
| `ocr` | 텍스트 추출 |
| `describe` | 상세 설명 |
| `analyze` | 종합 분석 |
| `objects` | 객체 목록 |
| `custom` | 사용자 정의 프롬프트 |

---

### 5. 시스템 관리

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /v1/models` | 모델 목록 |
| `GET /v1/system/status` | 시스템 상태 (메모리, 워커) |
| `POST /v1/system/evict/{alias}` | 워커 수동 종료 |
| `GET /v1/vision/tasks` | 분석 태스크 목록 |
| `GET /healthz` | 헬스체크 |

---

## 모델 정보

| 별칭 | 모델 | 용도 | 메모리 |
|------|------|------|--------|
| `vlm-fast` | Moondream2 | 빠른 이미지 분석 | ~1.5GB |
| `vlm-best` | Qwen2.5-VL-7B-4bit | 고품질 이미지 분석 | ~4.5GB |
| `image-gen` | FLUX.1-schnell-4bit | 이미지 생성 | ~6GB |

---

## 관리 명령어

```bash
make install      # 전체 설치
make start        # Gateway 시작
make stop         # Gateway 중지
make status       # 상태 확인
make logs         # Gateway 로그
make logs-manager # Worker Manager 로그
make uninstall    # 전체 제거
```

---

## 설정

`config.yaml`에서 모델과 메모리 설정을 변경할 수 있습니다.

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `IDLE_TIMEOUT` | 300 | 워커 자동 종료 시간 (초) |
| `MANAGER_PORT` | 8100 | Worker Manager 포트 |

---

## 라이선스

MIT

---

## Vibe Homelab

This project is part of [Vibe Homelab](https://vibe-homelab.github.io) - AI-Powered Home Services with Vibe Coding.
