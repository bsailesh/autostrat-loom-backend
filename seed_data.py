"""
Seed script — creates a demo tenant and some sample data by calling the
running API (not by touching the database directly), so it doubles as a
smoke test that the API itself works end to end.

Usage:
    1. Start the server: uvicorn app.main:app --reload
    2. In another terminal: python seed_data.py
"""
import requests

BASE_URL = "http://127.0.0.1:8000"
ADMIN_KEY = "admin-dev-key-change-me"  # must match LOOM_ADMIN_KEYS in your .env


def main():
    # 1. Create a demo tenant
    resp = requests.post(
        f"{BASE_URL}/admin/tenants",
        json={"name": "Acme Industrial Co."},
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    resp.raise_for_status()
    tenant = resp.json()
    api_key = tenant["api_key"]
    print(f"Created tenant '{tenant['name']}' (id={tenant['id']})")
    print(f"API key: {api_key}")
    print("Save this key — it's the only time it's returned.\n")

    headers = {"Authorization": f"Bearer {api_key}"}

    # 2. Create a few sample initiatives
    sample_initiatives = [
        {
            "title": "Self-serve onboarding flow",
            "description": "New customers currently need a sales call to get set up. A self-serve flow could cut time-to-value from 2 weeks to under a day.",
            "category": "growth",
        },
        {
            "title": "Migrate legacy auth module",
            "description": "Current auth library is unmaintained upstream and flagged in the last security review.",
            "category": "sustainment",
        },
        {
            "title": "Replace EOL barcode scanner firmware",
            "description": "Vendor has announced end-of-support for the firmware used across our warehouse scanner fleet.",
            "category": "obsolescence",
        },
    ]
    initiative_ids = []
    for payload in sample_initiatives:
        r = requests.post(f"{BASE_URL}/initiatives", json=payload, headers=headers)
        r.raise_for_status()
        created = r.json()
        initiative_ids.append(created["id"])
        print(f"Created initiative: {created['title']} (id={created['id']})")

    # 3. Create a sample tracked asset
    r = requests.post(
        f"{BASE_URL}/assets",
        json={
            "name": "Zebra DS2208 barcode scanner firmware",
            "asset_type": "dependency",
            "eol_date": "2027-03-01",
            "criticality": "high",
        },
        headers=headers,
    )
    r.raise_for_status()
    asset = r.json()
    print(f"Created asset: {asset['name']} (id={asset['id']})")

    print("\nSeed complete. Next steps (require ANTHROPIC_API_KEY to be set):")
    print(f"  curl -X POST {BASE_URL}/initiatives/{initiative_ids[0]}/prioritize -H 'Authorization: Bearer {api_key}'")
    print(f"  curl -X POST {BASE_URL}/assets/{asset['id']}/assess -H 'Authorization: Bearer {api_key}'")


if __name__ == "__main__":
    main()
