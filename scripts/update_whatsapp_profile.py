"""
Script to update WhatsApp Business Profile and Meta settings for Realtors Round Tables (Simon).

Usage:
    python scripts/update_whatsapp_profile.py
    python scripts/update_whatsapp_profile.py --test-phone 254706716616
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import httpx

# Load environment variables
env_path = Path(__file__).resolve().parent.parent / "Samantha.env"
if env_path.exists():
    load_dotenv(env_path, override=True)
else:
    load_dotenv(override=True)

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "").strip()
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "1229045376955799").strip()
META_WABA_ID = os.getenv("META_WABA_ID", "988741520452943").strip()
META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v21.0").strip()
META_GRAPH_BASE_URL = os.getenv("META_GRAPH_BASE_URL", "https://graph.facebook.com").strip()

HEADERS = {
    "Authorization": f"Bearer {META_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

PROFILE_DATA = {
    "messaging_product": "whatsapp",
    "about": "Simon | Customer Service at Realtors Round Tables",
    "description": (
        "Realtors Round Tables — Kenya's trusted real estate concierge. "
        "Discover homes, apartments, villas & land in Nairobi & coast. "
        "Contact Executive Simon on 0701454854 | Website: realtorsroundtables.co.ke"
    ),
    "websites": [
        "https://realtorsroundtables.co.ke",
    ],
    "email": "info@realtorsroundtables.co.ke",
    "address": "Nairobi, Kenya",
    "vertical": "PROF_SERVICES",
}


def request_display_name_change(new_name: str = "Simon") -> dict:
    """Attempts to update or request display name change via Meta Graph API."""
    url = f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}"
    print(f"\n[*] Requesting Display Name Change to '{new_name}' on Meta...")
    print(f"URL: {url}")
    with httpx.Client(timeout=15.0) as client:
        # Meta Graph API parameter for display name is 'verified_name' or 'name'
        resp = client.post(url, headers=HEADERS, json={"verified_name": new_name})
        print(f"Status Code: {resp.status_code}")
        try:
            data = resp.json()
            print("Response:", json.dumps(data, indent=2))
            return data
        except Exception:
            print("Raw Response:", resp.text)
            return {"error": resp.text}



def get_phone_number_details() -> dict:
    """Fetches details about the phone number and current verified display name."""
    url = f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}?fields=display_phone_number,verified_name,name_status,code_verification_status,quality_rating"
    print(f"\n[1] Fetching Phone Number & Display Name Info from Meta...")
    print(f"URL: {url}")
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=HEADERS)
        print(f"Status Code: {resp.status_code}")
        try:
            data = resp.json()
            print("Response:", json.dumps(data, indent=2))
            return data
        except Exception:
            print("Raw Response:", resp.text)
            return {"error": resp.text}


def get_current_profile() -> dict:
    """Fetches the current WhatsApp Business Profile from Meta."""
    url = (
        f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}/whatsapp_business_profile"
        f"?fields=about,address,description,email,profile_picture_url,websites,vertical"
    )
    print(f"\n[2] Fetching Current WhatsApp Business Profile...")
    print(f"URL: {url}")
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=HEADERS)
        print(f"Status Code: {resp.status_code}")
        try:
            data = resp.json()
            print("Current Profile:", json.dumps(data, indent=2))
            return data
        except Exception:
            print("Raw Response:", resp.text)
            return {"error": resp.text}


def update_business_profile(custom_about: str | None = None, custom_desc: str | None = None) -> dict:
    """Updates the WhatsApp Business Profile on Meta."""
    url = f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}/whatsapp_business_profile"
    payload = dict(PROFILE_DATA)
    if custom_about:
        payload["about"] = custom_about
    if custom_desc:
        payload["description"] = custom_desc

    print(f"\n[3] Sending POST Request to Update WhatsApp Business Profile...")
    print(f"URL: {url}")
    print("Payload:", json.dumps(payload, indent=2))

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(url, headers=HEADERS, json=payload)
        print(f"Status Code: {resp.status_code}")
        try:
            data = resp.json()
            print("Update Result:", json.dumps(data, indent=2))
            return data
        except Exception:
            print("Raw Response:", resp.text)
            return {"error": resp.text}


def send_test_interactive_button(recipient_phone: str) -> dict:
    """Sends a sample interactive CTA button connecting to Simon on WhatsApp."""
    url = f"{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_phone,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "header": {
                "type": "text",
                "text": "Realtors Round Tables",
            },
            "body": {
                "text": (
                    "Hello! You can speak directly with our Customer Service Executive *Simon* on *0701454854* "
                    "or explore our listings at *realtorsroundtables.co.ke*.\n\n"
                    "Tap below to open a direct WhatsApp conversation with Simon."
                ),
            },
            "footer": {
                "text": "Realtors Round Tables Concierge",
            },
            "action": {
                "name": "cta_url",
                "parameters": {
                    "display_text": "Chat with Simon",
                    "url": "https://wa.me/254701454854?text=Hello%20Simon,%20I%20would%20like%20to%20inquire%20about%20real%20estate%20listings.",
                },
            },
        },
    }

    print(f"\n[4] Sending Test Interactive CTA URL Button to {recipient_phone}...")
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(url, headers=HEADERS, json=payload)
        print(f"Status Code: {resp.status_code}")
        try:
            data = resp.json()
            print("Message Response:", json.dumps(data, indent=2))
            return data
        except Exception:
            print("Raw Response:", resp.text)
            return {"error": resp.text}


def main():
    parser = argparse.ArgumentParser(description="Update WhatsApp Business Profile for Simon / Realtors Round Tables")
    parser.add_argument("--test-phone", type=str, help="Recipient phone to send a test interactive button (e.g. 254706716616)")
    parser.add_argument("--about", type=str, help="Custom 'about' status text")
    parser.add_argument("--description", type=str, help="Custom business profile description")
    args = parser.parse_args()

    if not META_ACCESS_TOKEN:
        print("ERROR: META_ACCESS_TOKEN is not set in Samantha.env or environment.")
        sys.exit(1)

    print("=" * 60)
    print(" WHATSAPP BUSINESS PROFILE UPDATE UTILITY")
    print(f" Phone Number ID: {META_PHONE_NUMBER_ID}")
    print(f" WABA ID:         {META_WABA_ID}")
    print(f" Graph Version:   {META_GRAPH_API_VERSION}")
    print("=" * 60)

    # 1. Check Phone Number info
    get_phone_number_details()

    # 2. Get current profile
    get_current_profile()

    # 3. Update profile description, about, websites, vertical
    res = update_business_profile(args.about, args.description)
    if res.get("success"):
        print("\n✅ WhatsApp Business Profile successfully updated on Meta!")
    else:
        print("\n⚠️ Profile update response:", res)

    # 4. Attempt display name change
    name_res = request_display_name_change("Simon")
    if name_res.get("success"):
        print("\n✅ Display Name update submitted to Meta!")
    else:
        print("\nℹ️ Display name response:", name_res)

    # 5. Fetch profile again to confirm
    get_current_profile()

    # 6. Optional test message
    if args.test_phone:
        send_test_interactive_button(args.test_phone)


if __name__ == "__main__":
    main()
