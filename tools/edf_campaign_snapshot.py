#!/usr/bin/env python3
"""Snapshot EDF/Kraken campaign + loyalty state for an account.

Run once before an in-app sign-up and once after, then diff the two JSON files
to see exactly what the mobile app changed server-side.

Usage:
    EDF_API_KEY=sk_live_xxx python3 edf_campaign_snapshot.py [label]

If EDF_API_KEY is unset and the script is running on the Home Assistant host,
it reads the key straight out of the edf_energy config entry. The key is used
in-process only and is never printed or written to the output file.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

URL = "https://api.edfgb-kraken.energy/v1/graphql/"
CONFIG_ENTRIES = "/config/.storage/core.config_entries"


def api_key_from_config_entry():
    """Read the api_key from the local HA config entry, if we're on the host."""
    try:
        with open(CONFIG_ENTRIES) as fh:
            entries = json.load(fh)["data"]["entries"]
    except (OSError, KeyError, ValueError):
        return None
    for entry in entries:
        if entry.get("domain") == "edf_energy":
            key = entry.get("data", {}).get("api_key")
            if key:
                return key
    return None


def gql(query, variables=None, token=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"JWT {token}"
    req = urllib.request.Request(URL, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main():
    api_key = os.environ.get("EDF_API_KEY") or api_key_from_config_entry()
    if not api_key:
        sys.exit(
            "No API key. Set EDF_API_KEY, or run this on the Home Assistant "
            "host where the edf_energy config entry can be read."
        )
    label = sys.argv[1] if len(sys.argv) > 1 else "snapshot"

    token = gql(
        "mutation ObtainTokenFromAPIKey($apiKey: String!) {"
        "  obtainKrakenToken(input: { APIKey: $apiKey }) { token } }",
        {"apiKey": api_key},
    )["data"]["obtainKrakenToken"]["token"]

    accounts = gql("{ viewer { accounts { number } } }", token=token)
    numbers = [a["number"] for a in accounts["data"]["viewer"]["accounts"]]

    out = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "accounts": {},
    }

    for number in numbers:
        acc = {}
        acc["activeCampaignOffers"] = gql(
            "query($a: String!) { activeCampaignOffers(accountNumber: $a)"
            " { name slug expiryDate } }",
            {"a": number}, token=token,
        )
        acc["campaigns"] = gql(
            "query($a: String!) { campaigns(accountNumber: $a, first: 100)"
            " { totalCount edges { node {"
            "   name slug startDate expiryDate campaignExpiryDate } } } }",
            {"a": number}, token=token,
        )
        for status in ("ACTIVE", "SCHEDULED", "EXPIRED"):
            acc[f"campaigns_{status}"] = gql(
                "query($a: String!, $s: CampaignAccountStatus!) {"
                " campaigns(accountNumber: $a, status: $s, first: 100)"
                " { totalCount edges { node {"
                "   name slug startDate expiryDate campaignExpiryDate } } } }",
                {"a": number, "s": status}, token=token,
            )
        out["accounts"][number] = acc

    path = f"edf_{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)

    print(f"Wrote {path}")
    for number, acc in out["accounts"].items():
        print(f"\nAccount {number}")
        offers = (acc["activeCampaignOffers"].get("data") or {}).get("activeCampaignOffers")
        print(f"  activeCampaignOffers: {offers}")
        for key in ("campaigns_ACTIVE", "campaigns_SCHEDULED", "campaigns_EXPIRED"):
            data = (acc[key].get("data") or {}).get("campaigns") or {}
            nodes = [e["node"] for e in data.get("edges", [])]
            print(f"  {key}: {data.get('totalCount', '?')}")
            for n in nodes:
                print(f"    - {n['slug']} ({n['name']}) {n['startDate']} -> {n['expiryDate']}")
        for key in ("activeCampaignOffers", "campaigns"):
            if acc[key].get("errors"):
                print(f"  !! {key} errors: {acc[key]['errors']}")


if __name__ == "__main__":
    main()
