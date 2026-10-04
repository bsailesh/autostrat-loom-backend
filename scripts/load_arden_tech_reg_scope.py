"""
Loads the Arden Actuation Systems applicability envelope -- the worked
example in tech_regulation_scoping_input_spec.md Part 6 -- into a tenant via
the Agent 3 (Technology & Regulatory Intelligence) API. All eight scoping
sections, in the order the spec presents them.

Modelled on scripts/load_arden_brief.py: same HTTP helpers, same
step-by-step printing, same "stops once the inputs are loaded" scope. It
does not start a run; that's a separate, deliberate step.

Every PUT replaces its dimension wholesale, so this script is idempotent --
running it twice leaves the same envelope, not a doubled one.

Usage:
    python -m scripts.load_arden_tech_reg_scope --base-url https://api.example.com --api-key sk_live_...

Or via environment variables (no credentials are hardcoded in this file):
    AGENT3_BASE_URL, AGENT3_API_KEY

Agent 3's envelope and Agent 5's decision brief are normally loaded into the
SAME Arden tenant, so AGENT5_BASE_URL / AGENT5_API_KEY are accepted as a
fallback and the script says when it used them. The two agents share a
tenant API key; nothing about them is otherwise connected at load time.

PROVENANCE OF THE DATA BELOW. Everything is transcribed from the scoping
spec, with three authored details flagged inline:

  * `category_key` values for the two categories Part 6 names only in prose
    (ground-based air defence actuation, hydraulic-replacement retrofit).
    Part 1.1's example establishes the EMA-* convention for the other three,
    so these follow it.
  * `platform_class` values, taken from the products/fleet table in
    arden_actuation_demo_brief.md Section 2 rather than from the scoping
    spec, which only names the platforms.
  * Supplier names are the spec's own "Vendor A/B/C" placeholders, kept
    verbatim rather than invented into real companies.

Nothing numeric or categorical is invented beyond those three. Where the
spec gives no value -- a `held_since` for MIL-STD-461G, for instance -- the
field is left empty rather than filled with a guess, which is also what the
agent's own rules require of it.
"""
from __future__ import annotations

import argparse
import os
import sys

import httpx

# ---------------------------------------------------------------------------
# 1. Product categories  (spec Part 6; keys per Part 1.1's EMA-* convention)
# ---------------------------------------------------------------------------

CATEGORIES = [
    {
        "category_key": "EMA-FIN",
        "category_name": "Missile fin actuation",
        "description": "Electromechanical fin actuators for tactical missiles",
    },
    {
        "category_key": "EMA-TVC",
        "category_name": "Thrust vector control",
        "description": "Launch vehicle and upper stage TVC actuators",
    },
    {
        "category_key": "EMA-UTIL",
        "category_name": "Utility actuation",
        "description": "Door, hatch and secondary system actuators",
    },
    # The two Part 6 names only in prose. Keys authored to match the
    # convention above; names and scope are the spec's own words.
    {
        "category_key": "EMA-GBAD",
        "category_name": "Ground-based air defence actuation",
        "description": "Actuation for mobile ground-based air defence launchers",
    },
    {
        "category_key": "EMA-HYDX",
        "category_name": "Hydraulic-replacement retrofit",
        "description": "Retrofit kits replacing hydraulic actuation on in-service platforms",
    },
]

# ---------------------------------------------------------------------------
# 2. Jurisdictions  (spec Part 6)
#
# Part 1.2's example also lists Japan as export-only; Part 6 names three, so
# three is what loads here.
# ---------------------------------------------------------------------------

JURISDICTIONS = [
    {"jurisdiction": "United States", "role": "primary"},
    {"jurisdiction": "European Union", "role": "primary"},
    {"jurisdiction": "United Kingdom", "role": "secondary"},
]

# ---------------------------------------------------------------------------
# 3. Certification basis  (spec Part 6, with statuses and years from Part 1.3)
#
# "MIL-STD-810H and MIL-STD-461G for defence lines" -- the defence lines are
# the missile fin and ground-based air defence categories, so both bases
# attach to both. Status/held_since are carried from Part 1.3's example where
# it gives them and left empty where it does not.
#
# Note EMA-HYDX has no basis here: Part 6 names none for it. That is a real
# gap in the envelope rather than an omission in this script, and the agent
# will report findings against that category without an applicability
# assessment.
# ---------------------------------------------------------------------------

CERTIFICATION_BASIS = [
    {
        "category_key": "EMA-FIN", "basis_type": "MIL-STD",
        "basis_identifier": "MIL-STD-810H", "status": "qualified", "held_since": "2021",
    },
    {
        "category_key": "EMA-FIN", "basis_type": "MIL-STD",
        "basis_identifier": "MIL-STD-461G", "status": "qualified", "held_since": "",
    },
    {
        "category_key": "EMA-GBAD", "basis_type": "MIL-STD",
        "basis_identifier": "MIL-STD-810H", "status": "qualified", "held_since": "",
    },
    {
        "category_key": "EMA-GBAD", "basis_type": "MIL-STD",
        "basis_identifier": "MIL-STD-461G", "status": "qualified", "held_since": "",
    },
    {
        "category_key": "EMA-UTIL", "basis_type": "TSO",
        "basis_identifier": "TSO-C196b", "status": "approved", "held_since": "2019",
    },
    {
        "category_key": "EMA-UTIL", "basis_type": "Part",
        "basis_identifier": "14 CFR Part 25", "status": "installed on", "held_since": "2019",
    },
    {
        "category_key": "EMA-TVC", "basis_type": "Standard",
        "basis_identifier": "AIAA S-120A", "status": "qualified", "held_since": "2022",
    },
]

# ---------------------------------------------------------------------------
# 4. Platforms  (spec Part 6; platform_class from the demo brief Section 2)
#
# Part 6's list is explicit and does NOT include the two sunsetting
# hydraulic-replacement platforms (military transport, legacy rotorcraft)
# that appear in the demo brief's fleet table. They are left out rather than
# added, since Part 6 is the named source -- but `relationship: sunsetting`
# exists for exactly that case, so they are the obvious first addition if
# the demo wants EMA-HYDX connected to a programme.
# ---------------------------------------------------------------------------

PLATFORMS = [
    {
        "platform": "Tactical missile — surface launched",
        "platform_class": "Defence, guided weapons",
        "relationship": "shipping",
        "programme_status": "active production",
    },
    {
        "platform": "Tactical missile — air launched",
        "platform_class": "Defence, guided weapons",
        "relationship": "shipping",
        "programme_status": "active production",
    },
    {
        "platform": "Small launch vehicle",
        "platform_class": "Space, launch",
        "relationship": "shipping",
        "programme_status": "active production",
    },
    {
        "platform": "Upper stage",
        "platform_class": "Space, launch",
        "relationship": "shipping",
        "programme_status": "active production",
    },
    {
        "platform": "Rotorcraft — medium",
        "platform_class": "Part 29 rotorcraft",
        "relationship": "shipping",
        "programme_status": "in service",
    },
    {
        "platform": "Business jet",
        "platform_class": "Part 25 business",
        "relationship": "shipping",
        "programme_status": "in service",
    },
    {
        "platform": "Mobile launcher",
        "platform_class": "Defence, ground",
        "relationship": "shipping",
        "programme_status": "active production",
    },
    # The one pursued position, and the reason `relationship` is load-bearing:
    # a regulatory change here is an entry condition on a closing design-in
    # window, not a cost against existing revenue.
    {
        "platform": "Narrowbody commercial",
        "platform_class": "Part 25 transport",
        "relationship": "pursuing",
        "programme_status": "design-in window",
    },
]

# ---------------------------------------------------------------------------
# 5. Standards held  (spec Part 1.5, confirmed by Part 6)
#
# DO-254 is deliberately "in_progress" with no revision: Part 1.5 shows a
# dash for its revision, and Part 6 notes this row matches committed project
# P-01 in the Agent 5 brief.
# ---------------------------------------------------------------------------

STANDARDS_HELD = [
    {"standard_id": "DO-160", "revision": "G", "scope": "Environmental qualification", "status": "compliant"},
    {"standard_id": "DO-254", "revision": "", "scope": "Airborne electronic hardware", "status": "in_progress"},
    {"standard_id": "AS9100", "revision": "D", "scope": "Quality management", "status": "certified"},
    {"standard_id": "MIL-STD-461", "revision": "G", "scope": "EMI/EMC", "status": "compliant"},
]

# ---------------------------------------------------------------------------
# 6. Supplier watch list  (spec Part 1.6, confirmed by Part 6)
#
# "Vendor A/B/C" are the spec's own placeholders and are kept verbatim.
# Part 6 notes the GaN row matches committed project P-03 and objective SO-2.
# ---------------------------------------------------------------------------

SUPPLIERS = [
    {"supplier": "Vendor A", "what_they_supply": "GaN power devices", "criticality": "single_source"},
    {"supplier": "Vendor B", "what_they_supply": "Roller screws", "criticality": "dual_sourced"},
    {"supplier": "Vendor C", "what_they_supply": "Position sensors — resolver", "criticality": "single_source"},
]

# ---------------------------------------------------------------------------
# 7. Technology domains  (spec Part 6)
# ---------------------------------------------------------------------------

DOMAINS = [
    {"domain": "Electrification"},
    {"domain": "Advanced air mobility"},
    {"domain": "UAV/UAS"},
    {"domain": "Space systems"},
    {"domain": "Cybersecurity"},
]

# ---------------------------------------------------------------------------
# 8. Exclusions  (spec Part 6: "Part 23 general aviation; China; rail and
# marine")
#
# "Rail and marine" loads as two platform_class rows rather than one, so each
# can be lifted independently if the scope changes. Reasons follow Part 2's
# own example wording.
# ---------------------------------------------------------------------------

EXCLUSIONS = [
    {"exclusion_type": "platform_class", "value": "Part 23 general aviation", "reason": "not a market we serve"},
    {"exclusion_type": "jurisdiction", "value": "China", "reason": "no sales or certification intent"},
    {"exclusion_type": "platform_class", "value": "Rail", "reason": "not a market we serve"},
    {"exclusion_type": "platform_class", "value": "Marine", "reason": "not a market we serve"},
]

# Loaded in the spec's own order. The dimension names are the API path
# segments, which differ from the section titles in two cases
# (certification-basis, standards).
SECTIONS = [
    ("categories", "Product categories", CATEGORIES),
    ("jurisdictions", "Jurisdictions", JURISDICTIONS),
    ("certification-basis", "Certification basis", CERTIFICATION_BASIS),
    ("platforms", "Platforms and applications", PLATFORMS),
    ("standards", "Standards held", STANDARDS_HELD),
    ("suppliers", "Supplier watch list", SUPPLIERS),
    ("domains", "Technology domains", DOMAINS),
    ("exclusions", "Exclusions", EXCLUSIONS),
]


# ---------------------------------------------------------------------------
# HTTP helpers -- same shape as scripts/load_arden_brief.py
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


def put_scope(client: httpx.Client, dimension: str, rows: list[dict], step: str) -> list[dict]:
    resp = _request(client, "PUT", f"/agents/tech-regulation/scope/{dimension}", json=rows)
    _require_ok(resp, step)
    body = resp.json()
    print(f"  {len(body)} row(s) stored")
    return body


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=None,
                        help="Deployed backend base URL (or set AGENT3_BASE_URL / AGENT5_BASE_URL)")
    parser.add_argument("--api-key", default=None,
                        help="Tenant API key (or set AGENT3_API_KEY / AGENT5_API_KEY) -- never hardcode this")
    args = parser.parse_args()

    base_url = args.base_url or os.environ.get("AGENT3_BASE_URL") or os.environ.get("AGENT5_BASE_URL")
    api_key = args.api_key or os.environ.get("AGENT3_API_KEY") or os.environ.get("AGENT5_API_KEY")

    if not args.base_url and not os.environ.get("AGENT3_BASE_URL") and os.environ.get("AGENT5_BASE_URL"):
        print("Note: using AGENT5_BASE_URL / AGENT5_API_KEY -- Agent 3's envelope and Agent 5's "
              "brief normally share the Arden tenant.")

    if not base_url:
        print("ERROR: --base-url or AGENT3_BASE_URL is required.", file=sys.stderr)
        return 2
    if not api_key:
        print("ERROR: --api-key or AGENT3_API_KEY is required.", file=sys.stderr)
        return 2

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        with httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=60.0) as client:
            for i, (dimension, title, rows) in enumerate(SECTIONS, start=1):
                _print_step(f"{i}. {title}")
                put_scope(client, dimension, rows, f"PUT scope/{dimension}")

            _print_step("9. Operating state")
            resp = _request(client, "GET", "/agents/tech-regulation/scope/state")
            _require_ok(resp, "GET scope/state")
            state = resp.json()
            print(f"  operating_state: {state['operating_state']}")
            for item in state["items"]:
                suffix = f" ({item['consequence']})" if item["consequence"] else ""
                print(f"  - {item['label']}: {item['status']}, {item['count']} row(s){suffix}")

            if state["operating_state"] != "scoped":
                # Not a failure -- a run is never blocked by an incomplete
                # envelope -- but if this worked example does not come out
                # fully scoped, something above did not land.
                print("\nWARNING: expected 'scoped' after loading the full worked example. "
                      "Check the per-section counts above.", file=sys.stderr)

            print(
                "\nEnvelope loaded. No run was started.\n\n"
                "Two rows here connect to work already in the Agent 5 brief, which is what makes the\n"
                "demo land (scoping spec Part 6):\n"
                "  - DO-254, in progress   -> committed project P-01\n"
                "  - GaN power devices, single source -> committed project P-03 and objective SO-2\n"
                "A regulatory or supplier finding against either lands straight on work Arden is\n"
                "already doing."
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
