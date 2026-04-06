import httpx
import base64
import os


def test_inference():
    url = "http://localhost:8000/v1/chat/completions"

    # 1. 테스트용 샘플 이미지 다운로드 (M4 Mac Mini 환경 가정)
    img_path = "test_image.jpg"
    if not os.path.exists(img_path):
        print("[*] Downloading sample image...")
        with open(img_path, "wb") as f:
            resp = httpx.get(
                "https://raw.githubusercontent.com/gradio-app/gradio/main/test/test_files/bus.png"
            )
            f.write(resp.content)

    # 2. 이미지를 Base64로 인코딩
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    # 3. API 요청 구성 (OpenAI Multimodal 규격)
    payload = {
        "model": "vlm-fast",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "이미지에 무엇이 보이나요? 구체적으로 분석해 주세요.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                ],
            }
        ],
    }

    print(f"[*] Sending inference request to {url}...")
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, json=payload)
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                print("\n[+] AI Analysis Result:")
                print("-" * 30)
                print(content)
                print("-" * 30)
            else:
                print(f"[!] Error: {response.status_code}")
                print(response.text)
    except Exception as e:
        print(f"[!] Request failed: {e}")


if __name__ == "__main__":
    test_inference()
