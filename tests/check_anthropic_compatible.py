#!/usr/bin/env python3

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_URL = "https://integrate.api.nvidia.com/v1"
API_KEY = os.getenv("NVIDIA_NIM_API_KEY")

if not API_KEY:
    print("ERROR: NVIDIA_NIM_API_KEY is not set.")
    sys.exit(1)

HEADERS = {
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

OPENAI_HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

TIMEOUT = 60


def get_models():
    response = requests.get(
        f"{BASE_URL}/models",
        headers=OPENAI_HEADERS,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    return sorted(model["id"] for model in response.json()["data"])


def test_anthropic_endpoint():
    """
    Test whether the hosted endpoint exposes Anthropic Messages at all.

    We deliberately use a known callable model first. If this returns 404,
    there is no point testing 100 models individually.
    """

    model = "deepseek-ai/deepseek-v4-flash-0731"

    payload = {
        "model": model,
        "max_tokens": 64,
        "messages": [
            {
                "role": "user",
                "content": "Reply with exactly: ANTHROPIC_OK",
            }
        ],
    }

    try:
        response = requests.post(
            f"{BASE_URL}/messages",
            headers=HEADERS,
            json=payload,
            timeout=TIMEOUT,
        )

        return response

    except requests.RequestException as exc:
        print(f"Endpoint test failed: {exc}")
        sys.exit(1)


def test_model(model_id):
    """
    Test one model using Anthropic Messages API.

    This is only meaningful if /v1/messages exists on the endpoint.
    """

    payload = {
        "model": model_id,
        "max_tokens": 128,
        "messages": [
            {
                "role": "user",
                "content": "Reply with exactly: ANTHROPIC_OK",
            }
        ],
    }

    start = time.monotonic()

    try:
        response = requests.post(
            f"{BASE_URL}/messages",
            headers=HEADERS,
            json=payload,
            timeout=TIMEOUT,
        )

        elapsed = time.monotonic() - start

        try:
            body = response.json()
        except ValueError:
            body = response.text[:500]

        return {
            "model": model_id,
            "status_code": response.status_code,
            "elapsed": elapsed,
            "body": body,
        }

    except requests.RequestException as exc:
        return {
            "model": model_id,
            "status_code": None,
            "elapsed": time.monotonic() - start,
            "body": str(exc),
        }


def print_result(result):
    model = result["model"]
    status = result["status_code"]
    elapsed = result["elapsed"]
    body = result["body"]

    if status == 200:
        print(f"  ✓ {model} [{elapsed:.2f}s]")

    elif status == 429:
        print(f"  ~ {model} [429 RATE LIMITED]")

    elif status == 404:
        print(f"  ✗ {model} [404]")

    elif status == 400:
        print(f"  ✗ {model} [400] {body}")

    else:
        print(f"  ✗ {model} [{status}] {body}")


def main():
    print("=" * 90)
    print("NVIDIA HOSTED API - ANTHROPIC MESSAGES COMPATIBILITY TEST")
    print("=" * 90)
    print()

    print("Checking /v1/messages endpoint...")

    endpoint_response = test_anthropic_endpoint()

    print(
        f"Endpoint status: "
        f"{endpoint_response.status_code}"
    )

    try:
        endpoint_body = endpoint_response.json()
    except ValueError:
        endpoint_body = endpoint_response.text

    print(f"Response: {endpoint_body}")
    print()

    if endpoint_response.status_code == 404:
        print("=" * 90)
        print("RESULT")
        print("=" * 90)
        print()
        print("NVIDIA's hosted integrate.api.nvidia.com endpoint does")
        print("NOT expose the Anthropic /v1/messages API.")
        print()
        print("Therefore individual model testing cannot establish")
        print("Anthropic compatibility. The endpoint itself is missing.")
        print()
        print("Use:")
        print("  https://integrate.api.nvidia.com/v1/chat/completions")
        print()
        print("for the hosted NVIDIA API, or use a self-hosted NIM")
        print("deployment exposing /v1/messages.")
        print()
        return

    if endpoint_response.status_code >= 500:
        print("The Anthropic endpoint appears to exist but is")
        print("currently failing. Aborting model scan.")
        return

    print("Anthropic endpoint exists.")
    print()

    models = get_models()

    print(f"NVIDIA models visible to your key: {len(models)}")
    print()

    print("=" * 90)
    print("TESTING ALL MODELS THROUGH /v1/messages")
    print("=" * 90)

    results = []

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(test_model, model): model
            for model in models
        }

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print_result(result)

    working = [
        r for r in results
        if r["status_code"] == 200
    ]

    rate_limited = [
        r for r in results
        if r["status_code"] == 429
    ]

    failed = [
        r for r in results
        if r["status_code"] not in (200, 429)
    ]

    print()
    print("=" * 90)
    print("SUMMARY")
    print("=" * 90)

    print(f"Anthropic-compatible models: {len(working)}")
    print(f"Rate limited:               {len(rate_limited)}")
    print(f"Failed/unsupported:         {len(failed)}")

    if working:
        print()
        print("WORKING:")
        for result in sorted(working, key=lambda x: x["model"]):
            print(f"  ✓ {result['model']}")

    if rate_limited:
        print()
        print("RATE LIMITED:")
        for result in sorted(rate_limited, key=lambda x: x["model"]):
            print(f"  ~ {result['model']}")

    if failed:
        print()
        print("FAILED:")
        for result in sorted(failed, key=lambda x: x["model"]):
            print(
                f"  ✗ {result['model']} "
                f"[{result['status_code']}]"
            )


if __name__ == "__main__":
    main()
