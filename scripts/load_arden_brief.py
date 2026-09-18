"""
Loads the Arden Actuation Systems demo brief (arden_actuation_demo_brief.md)
into a tenant via the Agent 5 (Strategy Synthesis) API: capacity buckets,
config, objectives, framework, scenarios, rules, proposals, and the five
decision-inputs CSVs. Modelled on scripts/agent5_smoke_test.py -- same HTTP
helpers, same step-by-step printing -- but this script stops once the
inputs are loaded. It does not start a run; that's a separate, deliberate
step (see the brief's own "Demo notes" section for the upstream run to pin
and the model to use).

All data below is transcribed by hand from arden_actuation_demo_brief.md's
own tables -- nothing numeric is invented. The one exception, flagged
inline, is the scenarios' per-criterion weight overrides: the brief only
states each scenario's emphasis in prose ("Revenue impact and time
criticality up; strategic alignment down"), not numbers, so this script
picks specific weights that satisfy that direction and keep the merged
total at 1.0 -- an authored operationalization, not a figure from the brief.

Usage:
    python -m scripts.load_arden_brief --base-url https://api.example.com --api-key sk_live_...

Or via environment variables (no credentials are hardcoded in this file),
same names as agent5_smoke_test.py:
    AGENT5_BASE_URL, AGENT5_API_KEY

Each step prints its own result so a failure is immediately locatable.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys

import httpx

# ---------------------------------------------------------------------------
# Brief data (arden_actuation_demo_brief.md)
# ---------------------------------------------------------------------------

# Section 3. Discipline names as given there, mapped to the short,
# column-header-safe bucket keys the roadmap table (Section 5) already uses
# verbatim (MECH/ELEC/SW/SYS/CERT).
BUCKETS = [
    {"bucket_key": "MECH", "bucket_name": "Mechanical", "contractable": "yes"},
    # ITAR-controlled defence work; cleared power electronics engineers
    # cannot be contracted at short notice (Section 3).
    {"bucket_key": "ELEC", "bucket_name": "Power electronics", "contractable": "no"},
    {"bucket_key": "SW", "bucket_name": "Software", "contractable": "partial"},
    {"bucket_key": "SYS", "bucket_name": "Systems", "contractable": "partial"},
    # DER- and test-slot constrained (Section 3).
    {"bucket_key": "CERT", "bucket_name": "Certification & qualification", "contractable": "no"},
]

DISCIPLINE_TO_BUCKET = {
    "Mechanical": "MECH",
    "Power electronics": "ELEC",
    "Software": "SW",
    "Systems": "SYS",
    "Certification & qualification": "CERT",
}

CONFIG = {
    "effort_unit": "weeks",
    "fiscal_year_start_month": 1,
    "fiscal_year_label_format": "FY{yy}",
    # Distinct `type` values from the Section 5 roadmap table, in first-seen order.
    "project_types": ["Compliance", "Sustainment", "Manufacturing", "New product", "Enhancement"],
    "effort_bands": [
        {"band_name": "Small", "min_units": 0, "max_units": 60},
        {"band_name": "Medium", "min_units": 60, "max_units": 200},
        {"band_name": "Large", "min_units": 200, "max_units": 400},
        {"band_name": "Program", "min_units": 400, "max_units": None},
    ],
    "rules": [
        {"rule_type": "mandatory_never_cut", "value": "true",
         "note": "Mandatory projects are never cut at the funding line without escalation."},
        {"rule_type": "min_effort_to_rank", "value": "30",
         "note": "Projects under 30 engineering weeks remaining are not individually ranked."},
        {"rule_type": "cancellation_requires_named_consequence", "value": "true",
         "note": "No project may be recommended for cancellation without naming the contractual or regulatory consequence."},
    ],
}

OBJECTIVES = [
    {"objective_key": "SO-1", "horizon": "2031",
     "text": "Convert defence actuation growth into a commercial flight-control position before the "
             "next-generation narrowbody design-in window closes"},
    {"objective_key": "SO-2", "horizon": "FY28",
     "text": "Eliminate single-source dependency in power electronics and position sensing"},
    {"objective_key": "SO-3", "horizon": "FY29",
     "text": "Establish a qualification pathway that does not depend on a prime's shipset integration"},
    {"objective_key": "SO-4", "horizon": "Ongoing",
     "text": "Protect margin on hydraulic-replacement retrofits as competitors enter"},
]

# Section 8. Weights are given as decimals there already, summing to 1.0.
FRAMEWORK = {
    "framework": "weighted_scoring",
    "criteria": [
        {"criterion": "customer_value", "weight": 0.25},
        {"criterion": "strategic_alignment", "weight": 0.20},
        {"criterion": "revenue_impact", "weight": 0.20},
        {"criterion": "risk_reduction", "weight": 0.15},
        {"criterion": "time_criticality", "weight": 0.10},
        {"criterion": "effort_inverse", "weight": 0.10},
    ],
}

# Section 9 gives each scenario's emphasis in prose only -- no numbers. Each
# scenario's weights are per-criterion overrides on top of FRAMEWORK's
# declared weights (app/models.py's ScenarioWeight docstring); an
# unmentioned criterion keeps its framework weight. PUT /scenarios requires
# the merged result to sum to 1.0, so for each scenario below the overridden
# criteria are chosen to move in the direction the brief states while their
# own subtotal stays equal to what those same criteria summed to in the
# framework -- e.g. Defence-led touches revenue_impact/time_criticality
# (up) and strategic_alignment (down), and 0.28+0.17+0.05 equals the
# framework's own 0.20+0.10+0.20 for those three. "Base" deliberately leaves
# weights empty, meaning "framework's weights, unchanged".
SCENARIOS = {
    "scenarios": [
        {"name": "Base", "emphasis": "Weights as above", "weights": []},
        {"name": "Defence-led", "emphasis": "Revenue impact and time criticality up; strategic alignment down", "weights": [
            {"criterion": "revenue_impact", "weight": 0.28},
            {"criterion": "time_criticality", "weight": 0.17},
            {"criterion": "strategic_alignment", "weight": 0.05},
        ]},
        {"name": "Commercial entry", "emphasis": "Strategic alignment and customer value up; effort down", "weights": [
            {"criterion": "strategic_alignment", "weight": 0.22},
            {"criterion": "customer_value", "weight": 0.28},
            {"criterion": "effort_inverse", "weight": 0.05},
        ]},
        {"name": "Sustainment", "emphasis": "Risk reduction and installed-base protection up", "weights": [
            {"criterion": "risk_reduction", "weight": 0.30},
            {"criterion": "time_criticality", "weight": 0.05},
            {"criterion": "effort_inverse", "weight": 0.0},
        ]},
    ],
}

# Section 7 -- "not yet scoped": no effort estimate given, so none is
# invented here either. `note` maps to `description` (what's known about
# the proposal's status), leaving `rationale` blank rather than inventing one.
PROPOSALS = [
    {"project_key": "U-01", "name": "Electro-hydrostatic actuator line extension",
     "proposed_by": "VP Engineering", "description": "No scope or effort established"},
    {"project_key": "U-02", "name": "Independent shipset qualification capability",
     "proposed_by": "VP Programs", "description": "Would reduce dependence on prime integration; no engineering scope"},
    {"project_key": "U-03", "name": "AAM / eVTOL actuation entry",
     "proposed_by": "CTO", "description": "Exploratory"},
]

# Section 2. region isn't given there, so it's left blank.
PRODUCTS_FLEET = [
    ("AR-FIN", "Missile fin actuator set", "Tactical missile — surface-launched", "Defence, guided weapons", 14200, 4, "Current"),
    ("AR-FIN", "Missile fin actuator set", "Tactical missile — air-launched", "Defence, guided weapons", 8600, 3, "Current"),
    ("AR-TVC", "Thrust vector control actuator", "Small launch vehicle", "Space, launch", 310, 3, "Current"),
    ("AR-TVC", "Thrust vector control actuator", "Upper stage", "Space, launch", 145, 5, "Current"),
    ("AR-UTIL", "Utility and door actuator", "Rotorcraft — medium", "Part 29 rotorcraft", 2900, 9, "Current"),
    ("AR-UTIL", "Utility and door actuator", "Business jet", "Part 25 business", 1750, 7, "Current"),
    ("AR-GBAD", "Ground-based air defence actuator", "Mobile launcher", "Defence, ground", 620, 2, "Current"),
    ("AR-HYDX", "Hydraulic-replacement retrofit kit", "Military transport", "Part 25 / military", 480, 12, "Sunsetting"),
    ("AR-HYDX", "Hydraulic-replacement retrofit kit", "Legacy rotorcraft", "Part 29 rotorcraft", 390, 15, "Sunsetting"),
]

# Section 3. fte/capacity_weeks/budget_usd, by (fiscal_year, discipline).
# FY29 is explicitly blank in the brief ("not yet planned") and is skipped
# here rather than invented.
CAPACITY = [
    ("FY27", "Mechanical", 16, 780, 3_200_000),
    ("FY27", "Power electronics", 7, 350, 1_900_000),
    ("FY27", "Software", 13, 620, 2_600_000),
    ("FY27", "Systems", 10, 470, 2_100_000),
    ("FY27", "Certification & qualification", 6, 300, 1_700_000),
    ("FY28", "Mechanical", 16, 780, 3_300_000),
    ("FY28", "Power electronics", 8, 400, 2_200_000),
    ("FY28", "Software", 13, 620, 2_700_000),
    ("FY28", "Systems", 10, 470, 2_200_000),
    ("FY28", "Certification & qualification", 6, 300, 1_800_000),
]

# Section 5. effort columns are keyed MECH/ELEC/SW/SYS/CERT, exactly the
# brief's own roadmap table headers -- no bucket-name translation needed
# here, unlike the Meridian smoke test. mandatory_driver for the two
# mandatory projects is the compliance standard already named in the
# project's own title; mandatory_deadline is its target_gate. owner isn't
# given in the brief and is left blank.
ROADMAP = [
    # project_id, project, type, pct_complete, {MECH,ELEC,SW,SYS,CERT}, target_gate, mandatory
    ("P-01", "DO-254 design assurance, flight-control motor controller", "Compliance", 40,
     {"MECH": 8, "ELEC": 95, "SW": 40, "SYS": 30, "CERT": 85}, "Q3 FY27", True),
    ("P-02", "Roller-screw life extension qualification", "Sustainment", 55,
     {"MECH": 70, "ELEC": 0, "SW": 0, "SYS": 15, "CERT": 45}, "Q2 FY27", False),
    ("P-03", "Power electronics module redesign — GaN transition", "Sustainment", 18,
     {"MECH": 15, "ELEC": 140, "SW": 25, "SYS": 35, "CERT": 30}, "Q1 FY28", False),
    ("P-04", "Missile fin actuator rate capacity expansion", "Manufacturing", 30,
     {"MECH": 110, "ELEC": 30, "SW": 10, "SYS": 40, "CERT": 15}, "Q4 FY27", False),
    ("P-05", "High-lift actuator demonstrator, narrowbody", "New product", 12,
     {"MECH": 130, "ELEC": 65, "SW": 55, "SYS": 80, "CERT": 40}, "Q2 FY28", False),
    ("P-06", "Motor position sensor dual-source qualification", "Sustainment", 45,
     {"MECH": 20, "ELEC": 35, "SW": 5, "SYS": 12, "CERT": 28}, "Q3 FY27", False),
    ("P-07", "Prognostics and health monitoring software", "Enhancement", 25,
     {"MECH": 0, "ELEC": 10, "SW": 95, "SYS": 30, "CERT": 12}, "Q1 FY28", False),
    ("P-08", "DO-326A airworthiness security", "Compliance", 35,
     {"MECH": 0, "ELEC": 15, "SW": 60, "SYS": 35, "CERT": 25}, "Q4 FY27", True),
    ("P-09", "TVC actuator thermal margin improvement", "Enhancement", 20,
     {"MECH": 55, "ELEC": 15, "SW": 5, "SYS": 25, "CERT": 18}, "Q3 FY28", False),
]

MANDATORY_DRIVER = {
    "P-01": "DO-254 design assurance",
    "P-08": "DO-326A airworthiness security",
}

# Section 6.
DEPENDENCIES = [
    ("P-05", "P-03", "prerequisite", "High-lift demonstrator uses the redesigned power electronics module"),
    ("P-09", "P-03", "prerequisite", "Thermal margin work assumes the GaN drive stage"),
    ("P-07", "P-06", "prerequisite", "PHM algorithms depend on the qualified position sensor"),
]


# ---------------------------------------------------------------------------
# CSV builders
# ---------------------------------------------------------------------------


def _csv_text(header: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def build_products_fleet_csv() -> str:
    header = ["product_id", "product", "platform", "platform_class", "units_in_service", "avg_age_yrs", "status", "region"]
    rows = [
        {"product_id": pid, "product": product, "platform": platform, "platform_class": pclass,
         "units_in_service": units, "avg_age_yrs": age, "status": status, "region": ""}
        for pid, product, platform, pclass, units, age, status in PRODUCTS_FLEET
    ]
    return _csv_text(header, rows)


def build_capacity_csv() -> str:
    header = ["fiscal_year", "bucket_id", "fte", "capacity_units", "budget"]
    rows = [
        {"fiscal_year": fy, "bucket_id": DISCIPLINE_TO_BUCKET[discipline], "fte": fte,
         "capacity_units": capacity_weeks, "budget": budget}
        for fy, discipline, fte, capacity_weeks, budget in CAPACITY
    ]
    return _csv_text(header, rows)


def build_roadmap_csv() -> str:
    bucket_ids = ["MECH", "ELEC", "SW", "SYS", "CERT"]
    header = ["project_id", "project", "type", "status", "pct_complete"]
    for b in bucket_ids:
        header.append(f"effort_remaining_{b}")
    header += ["target_gate", "target_fy", "owner", "mandatory", "mandatory_driver", "mandatory_deadline"]

    rows = []
    for project_id, name, ptype, pct_complete, effort, target_gate, mandatory in ROADMAP:
        target_fy_match = re.search(r"FY\d+", target_gate)
        row = {
            "project_id": project_id,
            "project": name,
            "type": ptype,
            "status": "In flight",
            "pct_complete": pct_complete,
            "target_gate": target_gate,
            "target_fy": target_fy_match.group(0) if target_fy_match else "",
            "owner": "",
            "mandatory": "true" if mandatory else "false",
            "mandatory_driver": MANDATORY_DRIVER.get(project_id, ""),
            "mandatory_deadline": target_gate if mandatory else "",
        }
        for b in bucket_ids:
            row[f"effort_remaining_{b}"] = effort[b]
        rows.append(row)
    return _csv_text(header, rows)


def build_dependencies_csv() -> str:
    header = ["project_id", "depends_on_project_id", "dependency_type", "note"]
    rows = [
        {"project_id": project_key, "depends_on_project_id": depends_on, "dependency_type": dep_type, "note": note}
        for project_key, depends_on, dep_type, note in DEPENDENCIES
    ]
    return _csv_text(header, rows)


def build_financials_csv() -> str:
    # The brief gives no revenue/cost figures for any project -- nothing
    # numeric is invented; every figure is left blank.
    header = ["project_id", "revenue_impact_y1", "revenue_impact_y2", "revenue_impact_y3",
              "revenue_impact_y4", "revenue_impact_y5", "capex", "opex_annual", "discount_rate",
              "currency", "basis"]
    rows = [
        {"project_id": project_id, "revenue_impact_y1": "", "revenue_impact_y2": "", "revenue_impact_y3": "",
         "revenue_impact_y4": "", "revenue_impact_y5": "", "capex": "", "opex_annual": "", "discount_rate": "",
         "currency": "USD", "basis": "Not estimated in brief"}
        for project_id, *_rest in ROADMAP
    ]
    return _csv_text(header, rows)


CSV_BUILDERS = {
    "products_fleet": build_products_fleet_csv,
    "capacity": build_capacity_csv,
    "roadmap": build_roadmap_csv,
    "dependencies": build_dependencies_csv,
    "financials": build_financials_csv,
}
# Upload order matters: dependencies/financials validate project_id against
# whatever roadmap has already stored, so roadmap must land first.
UPLOAD_ORDER = ["products_fleet", "capacity", "roadmap", "dependencies", "financials"]


# ---------------------------------------------------------------------------
# HTTP helpers (same shape as scripts/agent5_smoke_test.py)
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


def put_json(client: httpx.Client, path: str, payload: dict, step: str) -> dict:
    resp = _request(client, "PUT", path, json=payload)
    _require_ok(resp, step)
    body = resp.json()
    print(body)
    return body


def upload_csv(client: httpx.Client, file_type: str, csv_text: str) -> dict:
    resp = _request(
        client, "POST", f"/agents/strategy/files/{file_type}",
        files={"file": (f"{file_type}.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
        data={"uploaded_by": "load_arden_brief"},
    )
    _require_ok(resp, f"upload {file_type}")
    body = resp.json()
    print(
        f"{file_type}: stored={body['stored']} rows={body['row_count']} "
        f"status={body['validation_status']} errors={body['errors']} warnings={body['warnings']}"
    )
    return body


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.environ.get("AGENT5_BASE_URL"),
                         help="Deployed backend base URL (or set AGENT5_BASE_URL)")
    parser.add_argument("--api-key", default=os.environ.get("AGENT5_API_KEY"),
                         help="Tenant API key (or set AGENT5_API_KEY) -- never hardcode this")
    args = parser.parse_args()

    if not args.base_url:
        print("ERROR: --base-url or AGENT5_BASE_URL is required.", file=sys.stderr)
        return 2
    if not args.api_key:
        print("ERROR: --api-key or AGENT5_API_KEY is required.", file=sys.stderr)
        return 2

    headers = {"Authorization": f"Bearer {args.api_key}"}

    try:
        with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=60.0) as client:
            _print_step("1. Capacity buckets")
            put_json(client, "/agents/strategy/buckets", {"buckets": BUCKETS}, "PUT buckets")

            _print_step("2. Config / objectives / framework / scenarios / proposals")
            put_json(client, "/agents/strategy/config", CONFIG, "PUT config")
            put_json(client, "/agents/strategy/objectives", {"objectives": OBJECTIVES}, "PUT objectives")
            put_json(client, "/agents/strategy/framework", FRAMEWORK, "PUT framework")
            put_json(client, "/agents/strategy/scenarios", SCENARIOS, "PUT scenarios")
            put_json(client, "/agents/strategy/proposals", {"proposals": PROPOSALS}, "PUT proposals")

            _print_step("3. CSV uploads")
            for file_type in UPLOAD_ORDER:
                csv_text = CSV_BUILDERS[file_type]()
                result = upload_csv(client, file_type, csv_text)
                if not result["stored"]:
                    raise LoadFailure(f"{file_type}.csv was rejected -- see errors above.")

            _print_step("4. Readiness")
            resp = _request(client, "GET", "/agents/strategy/readiness")
            _require_ok(resp, "GET readiness")
            for item in resp.json():
                print(f"  - {item['item']}: {item['status']} ({item['consequence']})")

            print(
                "\nInputs loaded. No run was started -- see arden_actuation_demo_brief.md's "
                "'Demo notes' for the upstream run to pin (upstream_run_overrides) and the "
                "model to use before starting one."
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
