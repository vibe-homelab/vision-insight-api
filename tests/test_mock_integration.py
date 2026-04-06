import subprocess
import time
import httpx
import os
import signal
import sys


def run_test():
    print("[*] Starting Integration Test (Mock Flow)...")

    # 1. Start Gateway in background
    # Note: We assume PYTHONPATH includes current directory
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()

    gateway_proc = subprocess.Popen(
        [sys.executable, "-m", "src.gateway.main"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    print("[*] Waiting for Gateway to start...")
    time.sleep(5)  # Give it time to start

    if gateway_proc.poll() is not None:
        print("[!] Gateway failed to start. Output:")
        print(gateway_proc.stdout.read())
        return

    try:
        # 2. Send request to Gateway for the mock model
        print("[*] Sending request to Gateway (this will trigger mock worker spawn)...")
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "http://localhost:8000/v1/chat/completions",
                json={
                    "model": "mock-test",
                    "messages": [{"role": "user", "content": "Hello mock!"}],
                },
            )

            print(f"[*] Response Status: {resp.status_code}")
            print(f"[*] Response Body: {resp.text}")

            if resp.status_code == 200:
                print("[+] Integration Test PASSED!")
            else:
                print("[-] Integration Test FAILED!")

    except Exception as e:
        print(f"[!] Test Error: {e}")
    finally:
        print("[*] Cleaning up...")
        gateway_proc.terminate()
        try:
            gateway_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            gateway_proc.kill()

        # Clean up sockets
        if os.path.exists("/tmp/vision_worker_mock-test.sock"):
            os.remove("/tmp/vision_worker_mock-test.sock")


if __name__ == "__main__":
    # This test requires fastapi, uvicorn, httpx, pydantic to be installed.
    run_test()
