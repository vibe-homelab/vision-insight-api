# [기획조사] M4 Mac Mini 기반 로컬 Vision AI Insight 파이프라인 구축 및 API화

## 1. 개요
본 문서는 M4 Mac Mini 환경에서 SOTA(State-of-the-Art) Vision 모델을 활용하여 이미지를 분석하고 Insight를 추출하는 Self-hosted API 시스템 구축을 위한 기획 조사 보고서입니다. LLM Agent가 이 API를 호출하여 이미지 이해(Vision-to-Text) 및 생성(Text-to-Image) 작업을 자동화할 수 있는 기반을 마련합니다.

---

## 2. SOTA 모델 조사 결과 (Apple Silicon 최적화)

### A. Vision-to-Text (이미지 분석 및 설명)
*   **Florence-2 (Microsoft)**: OCR, 캡셔닝, 객체 검출에 최적화된 올인원 모델. MLX 환경에서 매우 빠른 속도를 보임.
*   **Qwen2-VL (7B/72B)**: 비디오 및 이미지 이해 능력이 현존 오픈소스 모델 중 최상위권. 복잡한 Insight 추출에 적합.
*   **Moondream2**: 초경량(1.6B) 모델로, 실시간에 가까운 응답 속도가 필요한 단순 VQA 작업에 적합.

### B. Text-to-Image (이미지 생성 및 편집)
*   **FLUX.1 [schnell]**: 12B 파라미터의 고성능 생성 모델. MLX 4-bit 양자화를 통해 M4에서 고품질 이미지 생성 가능.
*   **SDXL (Stable Diffusion XL)**: Apple의 DiffusionKit을 활용하여 CoreML 가속을 최대로 활용 가능.

---

## 3. 시스템 아키텍처 설계

### 핵심 구성 요소
1.  **OpenAI-Compatible Gateway (FastAPI)**:
    *   `/v1/chat/completions`: VLM 모델 호출용.
    *   `/v1/images/generations`: 이미지 생성용.
    *   기존 Clawdbot/PageLM 등과의 쉬운 통합을 지원.
2.  **Worker-Process 모델**:
    *   각 모델군(VLM, Caption, Diffusion)을 별도의 프로세스로 실행하여 Unified Memory를 효율적으로 해제 및 관리.
3.  **Hotset Manager**:
    *   사용 빈도에 따라 메모리에 유지할 모델을 결정(LRU 방식).
    *   M4의 VRAM 한계를 넘지 않도록 동적 모델 로딩/언로딩 관리.

---

## 4. 단계별 구현 로드맵

| 단계 | 주요 작업 | 기대 결과 |
| :--- | :--- | :--- |
| **Phase 1** | MLX 환경 구축 및 FastAPI 게이트웨이 프로토타입 | API 통신 기반 마련 |
| **Phase 2** | Florence-2 및 Qwen2-VL 통합 (Vision-to-Text) | 이미지 Insight 추출 기능 확보 |
| **Phase 3** | FLUX.1 및 SDXL 통합 (Text-to-Image) | 이미지 생성 기능 확보 |
| **Phase 4** | Clawdbot/PageLM 에이전트 연동 및 최적화 | 완전한 로컬 Vision AI 워크플로우 완성 |

---

## 5. 결론 및 제언
M4 Mac Mini는 하드웨어 가속 성능이 뛰어나 로컬 SOTA 모델 구동에 최적의 환경입니다. 특히 **MLX 프레임워크**를 최우선으로 활용할 때 가장 낮은 지연 시간과 높은 처리량을 얻을 수 있습니다. 

**향후 과제**:
*   모델 양자화(Quantization) 수준에 따른 성능/정확도 트레이드오프 검증.
*   에이전트가 이미지에서 추출한 Insight를 바탕으로 복합적인 업무(예: UI 자동 테스트, 문서 요약 등)를 수행하도록 프롬프트 엔지니어링 고도화.
