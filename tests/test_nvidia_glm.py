"""Test the NVIDIA NIM API connection with the z-ai/glm-5.2 model.

Run with:
    uv run python tests/test_nvidia_glm.py
"""

from openai import OpenAI

MODEL = "z-ai/glm-5.2"
BASE_URL = "https://integrate.api.nvidia.com/v1"
API_KEY = "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"


def main() -> None:
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

    print(f"Testing model: {MODEL}")
    print(f"Base URL: {BASE_URL}")
    print("-" * 60)

    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "Reply with exactly: NVIDIA GLM test successful",
                }
            ],
            temperature=0.1,
            max_tokens=100,
        )

        message = completion.choices[0].message.content
        print("Response received:")
        print(message)
        print("-" * 60)
        print("Model:", completion.model)
        print("Usage:", completion.usage)
        print("\nSUCCESS: Connection to NVIDIA API works.")
    except Exception as exc:  # noqa: BLE001
        print(f"\nFAILURE: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
