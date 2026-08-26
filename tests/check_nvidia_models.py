#!/usr/bin/env python3

import os
import sys
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://integrate.api.nvidia.com/v1"
API_KEY = os.getenv("NVIDIA_NIM_API_KEY")

if not API_KEY:
    print("ERROR: NVIDIA_NIM_API_KEY is not set.")
    print("Fish:")
    print('  set -x NVIDIA_NIM_API_KEY "nvapi-..."')
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

def get_models():
    response = requests.get(
        f"{BASE_URL}/models",
        headers=HEADERS,
        timeout=30,
    )

    if response.status_code != 200:
        print(f"Failed to retrieve models: HTTP {response.status_code}")
        print(response.text)
        sys.exit(1)

    return response.json()["data"]


def test_model(model_id):
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": "Reply with exactly: OK",
            }
        ],
        "max_tokens": 8,
        "temperature": 0,
    }

    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=HEADERS,
            json=payload,
            timeout=60,
        )

        if response.status_code == 200:
            return model_id, "WORKS", ""

        try:
            error = response.json()
            message = error.get("detail") or error.get("message") or str(error)
        except Exception:
            message = response.text[:300]

        return model_id, f"HTTP {response.status_code}", message

    except requests.RequestException as e:
        return model_id, "ERROR", str(e)


def main():
    models = get_models()

    print(f"\nNVIDIA models visible to your API key: {len(models)}\n")
    print("=" * 90)

    model_ids = sorted(model["id"] for model in models)

    for model_id in model_ids:
        print(model_id)

    print("=" * 90)
    print("\nTesting actual inference access...")
    print("(Each successful test uses a tiny inference request.)\n")

    working = []
    failed = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(test_model, model_id): model_id
            for model_id in model_ids
        }

        for future in as_completed(futures):
            model_id, status, message = future.result()

            if status == "WORKS":
                working.append(model_id)
                print(f"  ✓ {model_id}")
            else:
                failed.append((model_id, status, message))
                print(f"  ✗ {model_id} [{status}] {message}")

    print("\n" + "=" * 90)
    print(f"WORKING MODELS: {len(working)}")
    print("=" * 90)

    for model in sorted(working):
        print(model)

    print("\n" + "=" * 90)
    print(f"FAILED / UNAVAILABLE: {len(failed)}")
    print("=" * 90)

    for model, status, message in sorted(failed):
        print(f"{model}")
        print(f"  {status}: {message}")


if __name__ == "__main__":
    main()
