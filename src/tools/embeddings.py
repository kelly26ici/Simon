import os
from dotenv import load_dotenv
from typing import List
import httpx as httpx_mod
from src.clients.httpx_client import httpx

load_dotenv()



async def get_embeddings(text_chunks: list[str]) -> List[List[float]]:

    CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
    CLOUDFLARE_API_URL = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/qwen/qwen3-embedding-0.6b"


    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        raise ValueError("CLOUDFLARE_ACCOUNT_ID and/or CLOUDFLARE_API_TOKEN missing in environment variables")

    if not text_chunks:
        raise ValueError("get_embeddings() receives text chunks as a list of strings. Text chunks cannot be empty")

    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": text_chunks
    }

    try:
        response = await httpx.post(
            CLOUDFLARE_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

    except httpx_mod.HTTPStatusError as e:
        print(f"Cloudflare Edge Error [{e.response.status_code}]: {e.response.text}")
        return []

    except httpx_mod.RequestError as e:
        print(f"Network timeout/failure connecting to Cloudflare: {e}")
        return []
  
    return response.json()["result"]["data"]