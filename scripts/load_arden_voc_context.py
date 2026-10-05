"""
Loads the Arden Actuation Systems customer context -- the worked example in
voice_of_customer_input_spec.md Part 6 -- into a tenant via the Agent 1
(Voice of Customer) API: segments, channels, attribution policy and the
three known pain points.

Modelled on scripts/load_arden_tech_reg_scope.py: same HTTP helpers, same
step-by-step printing, same "stops once the inputs are loaded" scope. It
does not start a run; that's a separate, deliberate step.

NO EVIDENCE IS UPLOADED, deliberately (Part 6: "Evidence supplied: none at
demo time"). The Tier 2 run is the point: it shows what the agent produces
from public evidence alone, titled an external customer-context analysis,
and reports each of the three beliefs below as not found because no
evidence was supplied that could test it -- naming exactly what a document
upload or a CRM connection would settle. The script warns if the tenant is
not at Tier 2 when it finishes, which means evidence is already uploaded.

Every PUT replaces its section wholesale, so this script is idempotent --
running it twice leaves the same context, not a doubled one.

Usage:
    python -m scripts.load_arden_voc_context --base-url https://api.example.com --api-key sk_live_...

Or via environment variables (no credentials are hardcoded in this file):
    AGENT1_BASE_URL, AGENT1_API_KEY

Agent 1's context, Agent 3's envelope and Agent 5's decision brief are
normally loaded into the SAME Arden tenant, so AGENT3_* and then AGENT5_*
are accepted as fallbacks and the script says which it used.

PRODUCT CATEGORIES ARE NOT LOADED HERE. Part 6 says "the five categories
from the Tech & Regulation envelope", and this agent reads those through
rather than asking for them twice. Load scripts/load_arden_tech_reg_scope.py
first; this script reports what it reads through and warns if it finds none.

PROVENANCE OF THE DATA BELOW. Transcribed from the input spec, with three
interpretations flagged inline:

  * Segment names and descriptions come from Part 1.1's example table;
    Part 6 gives only the names in prose and the counts. The counts agree.
  * Channel directions: "inbound and outbound" (Part 1.3, direct sales) is
    stored as `both`, the API's single value for it.
  * Known pain point segment keys are mapped from each belief's subject
    (primes -> OEM-PRIME, integrators -> OEM-TIER1, MRO organisations ->
    MRO). `category_key` is left empty: Part 6 does not tie any belief to a
    product category, and a guessed one would narrow what the agent tests.

No named customers are loaded -- Part 6 names none, and attribution is
segment_only regardless.
"""
from __future__ import annotations

import argparse
import os
import sys

import httpx

# ---------------------------------------------------------------------------
# 1. Customer segments  (Part 6 counts; names and descriptions from Part 1.1)
#
# End operators' count is None, not 0: "unknown" is the spec's own answer,
# and the agent states when a finding rests on a segment of unstated size.
# ---------------------------------------------------------------------------

SEGMENTS = [
    {
        "segment_key": "OEM-PRIME",
        "segment_name": "Prime contractors",
        "description": "Airframe and missile primes buying at shipset level",
        "approximate_count": 6,
    },
    {
        "segment_key": "OEM-TIER1",
        "segment_name": "Tier 1 integrators",
        "description": "System integrators specifying actuation",
        "approximate_count": 14,
    },
    {
        "segment_key": "MRO",
        "segment_name": "MRO and sustainment",
        "description": "Depot and field maintenance organisations",
        "approximate_count": 30,
    },
    {
        "segment_key": "OPERATOR",
        "segment_name": "End operators",
        "description": "Fleet operators with direct influence on spec",
        "approximate_count": None,
    },
]

# ---------------------------------------------------------------------------
# 2. Channels  (Part 1.3 table, which Part 6 restates in prose)
#
# Field service is the declared inbound channel for failure reports. With no
# evidence uploaded, the agent will report it as unrepresented -- feedback
# absent from a channel is not the same as a channel with no complaints.
# ---------------------------------------------------------------------------

CHANNELS = [
    {"channel": "Direct sales", "direction": "both", "note": "Primes and Tier 1"},
    {"channel": "Distributor", "direction": "outbound", "note": "Utility actuation aftermarket"},
    {"channel": "Field service", "direction": "inbound", "note": "Primary source of failure reports"},
    {"channel": "Programme reviews", "direction": "both", "note": "Quarterly with primes"},
]

# ---------------------------------------------------------------------------
# 3. Attribution policy  (Part 6)
# ---------------------------------------------------------------------------

CONFIG = {"attribution_policy": "segment_only"}

# ---------------------------------------------------------------------------
# 4. Known pain points  (Part 6, verbatim)
#
# The input to belief testing -- the highest-value analysis this agent
# performs. `their_assessment` is the function Part 6 attaches to each.
# ---------------------------------------------------------------------------

KNOWN_PAIN_POINTS = [
    {
        "pain_point": "Primes say our lead times are the longest in the qualified set",
        "segment_key": "OEM-PRIME",
        "category_key": "",
        "their_assessment": "procurement",
    },
    {
        "pain_point": "Integrators find our control interface harder to integrate than Moog's",
        "segment_key": "OEM-TIER1",
        "category_key": "",
        "their_assessment": "engineering",
    },
    {
        "pain_point": "MRO organisations say field diagnosis takes too long without a service tool",
        "segment_key": "MRO",
        "category_key": "",
        "their_assessment": "sustainment",
    },
]

# Loaded in the spec's own order. `section` is the API path segment.
SECTIONS = [
    ("segments", "Customer segments", SEGMENTS),
    ("channels", "Channels", CHANNELS),
    ("config", "Attribution policy", CONFIG),
    ("known-pain-points", "Known pain points", KNOWN_PAIN_POINTS),
]


# ---------------------------------------------------------------------------
# HTTP helpers -- same shape as scripts/load_arden_tech_reg_scope.py
# ---------------------------------------------------------------------------


class LoadFailure(RuntimeError):
    pass


def _print_step(title: str) -> None:
    print(f"\n=== {title} ===")


def _request(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
    resp = client.request(method, path, **kwargs)
    print(f"{method} {path} -> {resp.status_code}")
    return resp


def _require_ok(resp: httpx.Response, step: str) -> None:
    if resp.status_code >= 400:
        raise LoadFailure(f"{step} failed: {resp.status_code} {resp.text}")


def put_context(client: httpx.Client, section: str, body, step: str):
    resp = _request(client, "PUT", f"/agents/voice-of-customer/context/{section}", json=body)
    _require_ok(resp, step)
    stored = resp.json()
    if isinstance(stored, list):
        print(f"  {len(stored)} row(s) stored")
    else:
        print(f"  stored: {stored}")
    return stored


def _resolve(url_flag: str | None, key_flag: str | None) -> tuple[str | None, str | None, str | None]:
    """(base_url, api_key, env prefix used) -- flags first, then AGENT1_*,
    AGENT3_*, AGENT5_*, taking the URL and key from the SAME prefix.

    Resolving them independently would pair one agent's key with another's
    URL whenever only half of a prefix is set -- e.g. AGENT3_API_KEY alone
    plus AGENT5_BASE_URL sends the Agent 3 key to the Agent 5 host. A prefix
    only counts if it supplies everything the flags do not."""
    if url_flag and key_flag:
        return url_flag, key_flag, None
    for prefix in ("AGENT1", "AGENT3", "AGENT5"):
        url = url_flag or os.environ.get(f"{prefix}_BASE_URL")
        key = key_flag or os.environ.get(f"{prefix}_API_KEY")
        if url and key:
            return url, key, prefix
    return url_flag, key_flag, None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=None,
                        help="Deployed backend base URL (or set AGENT1_BASE_URL / AGENT3_BASE_URL / AGENT5_BASE_URL)")
    parser.add_argument("--api-key", default=None,
                        help="Tenant API key (or set AGENT1_API_KEY / AGENT3_API_KEY / AGENT5_API_KEY) -- never hardcode this")
    args = parser.parse_args()

    base_url, api_key, source = _resolve(args.base_url, args.api_key)

    if source and source != "AGENT1":
        print(f"Note: using {source}_BASE_URL / {source}_API_KEY -- the agents' inputs normally "
              "share the Arden tenant.")

    if not base_url:
        print("ERROR: --base-url or AGENT1_BASE_URL is required.", file=sys.stderr)
        return 2
    if not api_key:
        print("ERROR: --api-key or AGENT1_API_KEY is required.", file=sys.stderr)
        return 2

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        with httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=60.0) as client:
            for i, (section, title, body) in enumerate(SECTIONS, start=1):
                _print_step(f"{i}. {title}")
                put_context(client, section, body, f"PUT context/{section}")

            _print_step("5. Product categories (read through from Technology & Regulation)")
            resp = _request(client, "GET", "/agents/voice-of-customer/context/categories")
            _require_ok(resp, "GET context/categories")
            categories = resp.json()
            for c in categories:
                print(f"  - {c['category_key']}: {c['category_name']} [{c['source']}]")
            if not categories:
                print("\nWARNING: no product categories found. Part 6 reads the five from the Tech & "
                      "Regulation envelope -- run scripts/load_arden_tech_reg_scope.py against this "
                      "tenant first, or feedback cannot be attached to a product line.", file=sys.stderr)

            _print_step("6. Operating tier")
            resp = _request(client, "GET", "/agents/voice-of-customer/context/state")
            _require_ok(resp, "GET context/state")
            state = resp.json()
            print(f"  operating_tier: {state['operating_tier']} ({state['run_label']})")
            for item in state["items"]:
                suffix = f" ({item['consequence']})" if item["consequence"] else ""
                print(f"  - {item['label']}: {item['status']}, {item['count']} row(s){suffix}")

            if state["operating_tier"] != "tier_2":
                # Not a failure, but not the demo: evidence is already
                # uploaded to this tenant, so the run will not be the Tier 2
                # external customer-context analysis Part 6 describes.
                print("\nWARNING: expected tier_2 -- this tenant already has evidence uploaded. "
                      "Delete it via DELETE /agents/voice-of-customer/evidence/{id} for the Part 6 demo.",
                      file=sys.stderr)

            print(
                "\nContext loaded. No evidence uploaded and no run started.\n\n"
                "A run now is a Tier 2 external customer-context analysis, and the three beliefs\n"
                "above are what make it land (input spec Part 6): each is reported as not found\n"
                "because no customer evidence was supplied that could test it, naming what a\n"
                "document upload or a CRM connection would settle. A belief the customer holds that\n"
                "the system cannot yet test is a sharper argument for connecting data than any\n"
                "feature list."
            )
            return 0

    except LoadFailure as e:
        print(f"\nLOAD FAILED: {e}", file=sys.stderr)
        return 1
    except httpx.HTTPError as e:
        print(f"\nLOAD FAILED (network error): {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
