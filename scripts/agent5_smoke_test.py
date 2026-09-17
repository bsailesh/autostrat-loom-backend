"""
End-to-end smoke test for the Agent 5 (Strategy Synthesis) pipeline against
a deployed backend. Exercises the full path a real tenant would walk:
declare capacity buckets, configure the brief, upload the five CSVs, check
readiness, start a run, poll it to completion, and download the export.

Data comes from the strawman brief (agent5_decision_brief_strawman_v2.md,
Meridian Avionics -- fictional). Capacity, projects, and per-project effort
are pulled directly from tests/fixtures/agent5/strawman.py, the same
fixture compute.py's own tests use; that fixture doesn't cover
products/dependencies/financials (it's the decision-inputs side only, per
its own docstring), so those three CSVs are transcribed here straight from
the brief's tables instead.

Usage:
    python -m scripts.agent5_smoke_test --base-url https://api.example.com --api-key sk_live_...

Or via environment variables (no credentials are hardcoded in this file):
    AGENT5_BASE_URL, AGENT5_API_KEY, AGENT5_MODEL (optional model override)

Each step prints its own result so a failure is immediately locatable.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import pathlib
import sys
import time

import httpx

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.fixtures.agent5 import strawman  # noqa: E402

# strawman.py's bucket keys ("hardware", "software", ...) are full words;
# the brief's own capacity_fy26_fy29.csv / roadmap_fy26.csv columns (and this
# script's task) use the short HW/SW/SYS/CERT column-header-safe form.
BUCKET_KEY_MAP = {"hardware": "HW", "software": "SW", "systems": "SYS", "certification": "CERT"}

BUCKETS = [
    {"bucket_key": "HW", "bucket_name": "Hardware", "contractable": "yes"},
    {"bucket_key": "SW", "bucket_name": "Software", "contractable": "yes"},
    {"bucket_key": "SYS", "bucket_name": "Systems", "contractable": "partial"},
    # Certification is DER-gated and cannot be contracted at short notice
    # (agent5_decision_brief_strawman_v2.md Section 3).
    {"bucket_key": "CERT", "bucket_name": "Certification", "contractable": "no"},
]

CONFIG = {
    "effort_unit": "weeks",
    "fiscal_year_start_month": 1,
    "fiscal_year_label_format": "FY{yy}",
    "project_types": ["Compliance", "Sustainment", "New product", "Service", "Enhancement", "Manufacturing"],
    "effort_bands": [
        {"band_name": "Small", "min_units": 0, "max_units": 40},
        {"band_name": "Medium", "min_units": 40, "max_units": 150},
        {"band_name": "Large", "min_units": 150, "max_units": 400},
        {"band_name": "Program", "min_units": 400, "max_units": None},
    ],
    "rules": [
        {"rule_type": "min_effort_to_rank", "value": "20",
         "note": "Projects under 20 engineering weeks remaining are not individually ranked."},
        {"rule_type": "mandatory_never_cut", "value": "true",
         "note": "Mandatory projects are never cut at the funding line without escalation."},
        {"rule_type": "cancellation_requires_named_consequence", "value": "true",
         "note": "No project may be recommended for cancellation without naming the contractual or regulatory consequence."},
    ],
}

OBJECTIVES = [
    {"objective_key": "SO-1", "horizon": "2030",
     "text": "Capture a defensible share of the US 25-hour CVR retrofit cohort before the statutory window closes"},
    {"objective_key": "SO-2", "horizon": "FY28",
     "text": "Reduce dependence on single-source components across the recorder line"},
    {"objective_key": "SO-3", "horizon": "FY29",
     "text": "Establish a route to market that does not depend on airframer service bulletins"},
    {"objective_key": "SO-4", "horizon": "Ongoing",
     "text": "Protect the installed base through the legacy-to-25h transition without margin erosion"},
]

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

# Each scenario's weights are per-criterion overrides on top of FRAMEWORK's
# declared weights (app/models.py ScenarioWeight docstring); an unmentioned
# criterion keeps its framework weight. PUT /scenarios requires the merged
# result to sum to 1.0, so scenarios that touch several criteria (Growth)
# list enough of them to keep the merge balanced -- "Base" deliberately
# leaves weights empty to mean "framework's weights, unchanged".
SCENARIOS = {
    "scenarios": [
        {"name": "Base", "emphasis": "Weights as declared in the framework", "weights": []},
        {"name": "Growth", "emphasis": "Revenue impact and customer value up; effort down", "weights": [
            {"criterion": "revenue_impact", "weight": 0.30},
            {"criterion": "customer_value", "weight": 0.30},
            {"criterion": "strategic_alignment", "weight": 0.15},
            {"criterion": "risk_reduction", "weight": 0.10},
            {"criterion": "time_criticality", "weight": 0.10},
            {"criterion": "effort_inverse", "weight": 0.05},
        ]},
        {"name": "Sustainment", "emphasis": "Risk reduction and installed-base protection up", "weights": [
            {"criterion": "risk_reduction", "weight": 0.35},
            {"criterion": "customer_value", "weight": 0.20},
            {"criterion": "strategic_alignment", "weight": 0.15},
            {"criterion": "revenue_impact", "weight": 0.10},
            {"criterion": "time_criticality", "weight": 0.10},
            {"criterion": "effort_inverse", "weight": 0.10},
        ]},
        {"name": "Compliance-first", "emphasis": "Time criticality and regulatory exposure up", "weights": [
            {"criterion": "time_criticality", "weight": 0.30},
            {"criterion": "risk_reduction", "weight": 0.20},
            {"criterion": "customer_value", "weight": 0.15},
            {"criterion": "strategic_alignment", "weight": 0.15},
            {"criterion": "revenue_impact", "weight": 0.10},
            {"criterion": "effort_inverse", "weight": 0.10},
        ]},
    ],
}

# Section 2 of the brief. region isn't given there, so it's left blank.
PRODUCTS_FLEET = [
    ("MR-CVR20", "CVR-20 (2 h voice)", "A320ceo family", "Part 25 transport", 1850, 14, "Sunsetting"),
    ("MR-CVR20", "CVR-20 (2 h voice)", "B737NG", "Part 25 transport", 2100, 16, "Sunsetting"),
    ("MR-CVR20", "CVR-20 (2 h voice)", "B757 / B767", "Part 25 transport", 640, 24, "Sunsetting"),
    ("MR-CVR20", "CVR-20 (2 h voice)", "CRJ700 / 900", "Part 25 regional", 1120, 17, "Sunsetting"),
    ("MR-CVR20", "CVR-20 (2 h voice)", "ERJ 145", "Part 25 regional", 690, 21, "Sunsetting"),
    ("MR-CVR25", "CVR-25 (25 h voice)", "A320neo family", "Part 25 transport", 190, 2, "Current"),
    ("MR-CVR25", "CVR-25 (25 h voice)", "B737 MAX", "Part 25 transport", 120, 2, "Current"),
    ("MR-FDR140", "FDR-140", "A320 family", "Part 25 transport", 2400, 11, "Current"),
    ("MR-FDR140", "FDR-140", "B737NG / MAX", "Part 25 transport", 2150, 12, "Current"),
    ("MR-FDR140", "FDR-140", "E170 / E190", "Part 25 regional", 1350, 9, "Current"),
    ("MR-CVFDR", "Combined CVFDR", "CRJ / ERJ", "Part 25 regional", 810, 13, "Current"),
    ("MR-CVFDR", "Combined CVFDR", "Q400", "Part 25 regional", 340, 15, "Current"),
    ("MR-CVFDR", "Combined CVFDR", "Challenger / Gulfstream", "Part 25 business", 700, 8, "Current"),
    ("MR-HELI", "Helicopter CVFDR", "S-92 / AW139 / H175", "Part 29 rotorcraft", 740, 10, "Current"),
]

# Section 3: fte is per-discipline and identical across FY27/FY28 in the
# brief; capacity_units/budget come straight from strawman.CAPACITY.
FTE_BY_BUCKET = {"HW": 20, "SW": 16, "SYS": 11, "CERT": 5}

# Section 5: type/status/pct_complete/target_gate aren't in strawman.py
# (that fixture only carries effort figures + mandatory flags), so they're
# transcribed here. target_fy is derived from target_gate's quarter.
ROADMAP_META = {
    "P-01": dict(type="Compliance", status="In flight", pct_complete=72, target_gate="Q2 FY27", target_fy="FY27"),
    "P-02": dict(type="Compliance", status="In flight", pct_complete=35, target_gate="Q4 FY27", target_fy="FY27"),
    "P-03": dict(type="Sustainment", status="In flight", pct_complete=20, target_gate="Q1 FY28", target_fy="FY28"),
    "P-04": dict(type="Sustainment", status="In flight", pct_complete=55, target_gate="Q3 FY27", target_fy="FY27"),
    "P-05": dict(type="New product", status="In flight", pct_complete=15, target_gate="Q2 FY28", target_fy="FY28"),
    "P-06": dict(type="Service", status="In flight", pct_complete=60, target_gate="Q1 FY27", target_fy="FY27"),
    "P-07": dict(type="Enhancement", status="In flight", pct_complete=10, target_gate="Q3 FY28", target_fy="FY28"),
    "P-08": dict(type="Compliance", status="In flight", pct_complete=45, target_gate="Q4 FY27", target_fy="FY27"),
    "P-09": dict(type="Manufacturing", status="In flight", pct_complete=25, target_gate="Q2 FY28", target_fy="FY28"),
}

# Section 9's own note: "P-03 memory IC redesign likely gates P-05 and P-07".
DEPENDENCIES = [
    ("P-05", "P-03", "prerequisite", "P-03 memory IC redesign likely gates P-05 (brief Section 9)."),
    ("P-07", "P-03", "prerequisite", "P-03 memory IC redesign likely gates P-07 (brief Section 9)."),
]

DEFAULT_FISCAL_YEAR = "FY27"


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
    rows = []
    for c in strawman.CAPACITY:
        bucket_id = BUCKET_KEY_MAP[c.bucket_key]
        rows.append({
            "fiscal_year": c.fiscal_year,
            "bucket_id": bucket_id,
            "fte": FTE_BY_BUCKET[bucket_id],
            "capacity_units": c.capacity_units,
            "budget": c.budget,
        })
    return _csv_text(header, rows)


def build_roadmap_csv() -> str:
    bucket_ids = ["HW", "SW", "SYS", "CERT"]
    header = ["project_id", "project", "type", "status", "pct_complete"]
    for b in bucket_ids:
        header.append(f"effort_remaining_{b}")
    header += ["target_gate", "target_fy", "owner", "mandatory", "mandatory_driver", "mandatory_deadline"]

    effort_by_project: dict[str, dict[str, float]] = {}
    for pe in strawman.PROJECT_EFFORT:
        effort_by_project.setdefault(pe.project_key, {})[BUCKET_KEY_MAP[pe.bucket_key]] = pe.effort_remaining

    rows = []
    for p in strawman.PROJECTS:
        meta = ROADMAP_META[p.project_key]
        row = {
            "project_id": p.project_key,
            "project": p.name,
            "type": meta["type"],
            "status": meta["status"],
            "pct_complete": meta["pct_complete"],
            "target_gate": meta["target_gate"],
            "target_fy": meta["target_fy"],
            "owner": "",
            "mandatory": "true" if p.mandatory else "false",
            "mandatory_driver": p.mandatory_driver or "",
            "mandatory_deadline": p.mandatory_deadline or "",
        }
        for b in bucket_ids:
            row[f"effort_remaining_{b}"] = effort_by_project[p.project_key].get(b, "")
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
    # The brief gives no revenue/cost figures for any project (Section 9:
    # "does it refuse to invent effort?" -- the same discipline applies
    # here, so nothing numeric is invented; every figure is left blank).
    header = ["project_id", "revenue_impact_y1", "revenue_impact_y2", "revenue_impact_y3",
              "revenue_impact_y4", "revenue_impact_y5", "capex", "opex_annual", "discount_rate",
              "currency", "basis"]
    rows = [
        {"project_id": p.project_key, "revenue_impact_y1": "", "revenue_impact_y2": "", "revenue_impact_y3": "",
         "revenue_impact_y4": "", "revenue_impact_y5": "", "capex": "", "opex_annual": "", "discount_rate": "",
         "currency": "USD", "basis": "Not estimated in strawman brief"}
        for p in strawman.PROJECTS
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
# HTTP helpers
# ---------------------------------------------------------------------------


class SmokeTestFailure(RuntimeError):
    pass


def _print_step(title: str) -> None:
    print(f"\n=== {title} ===")


def _request(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
    resp = client.request(method, path, **kwargs)
    print(f"{method} {path} -> {resp.status_code}")
    return resp


def _require_ok(resp: httpx.Response, step: str) -> None:
    if resp.status_code >= 400:
        raise SmokeTestFailure(f"{step} failed: {resp.status_code} {resp.text}")


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
        data={"uploaded_by": "agent5_smoke_test"},
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
    parser.add_argument("--model", default=os.environ.get("AGENT5_MODEL"),
                         help="Optional model override for the run (or set AGENT5_MODEL). "
                              "If omitted, the server decides -- see printed note below.")
    parser.add_argument("--fiscal-year", default=DEFAULT_FISCAL_YEAR,
                         help=f"Fiscal year to run against (default: {DEFAULT_FISCAL_YEAR})")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Seconds between run status polls")
    parser.add_argument("--poll-timeout", type=float, default=900.0, help="Max seconds to wait for the run")
    parser.add_argument("--output-dir", default=".", help="Where to save export.docx on success")
    args = parser.parse_args()

    if not args.base_url:
        print("ERROR: --base-url or AGENT5_BASE_URL is required.", file=sys.stderr)
        return 2
    if not args.api_key:
        print("ERROR: --api-key or AGENT5_API_KEY is required.", file=sys.stderr)
        return 2

    headers = {"Authorization": f"Bearer {args.api_key}"}
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=60.0) as client:
            _print_step("1. Capacity buckets")
            put_json(client, "/agents/strategy/buckets", {"buckets": BUCKETS}, "PUT buckets")

            _print_step("2. Config / objectives / framework / scenarios")
            put_json(client, "/agents/strategy/config", CONFIG, "PUT config")
            put_json(client, "/agents/strategy/objectives", {"objectives": OBJECTIVES}, "PUT objectives")
            put_json(client, "/agents/strategy/framework", FRAMEWORK, "PUT framework")
            put_json(client, "/agents/strategy/scenarios", SCENARIOS, "PUT scenarios")

            _print_step("3. CSV uploads")
            upload_results = {}
            for file_type in UPLOAD_ORDER:
                csv_text = CSV_BUILDERS[file_type]()
                result = upload_csv(client, file_type, csv_text)
                upload_results[file_type] = result
                if not result["stored"]:
                    raise SmokeTestFailure(f"{file_type}.csv was rejected -- see errors above.")

            _print_step("4. Readiness")
            resp = _request(client, "GET", "/agents/strategy/readiness")
            _require_ok(resp, "GET readiness")
            for item in resp.json():
                print(f"  - {item['item']}: {item['status']} ({item['consequence']})")

            _print_step("5. Start run")
            run_payload = {"fiscal_year": args.fiscal_year}
            if args.model:
                run_payload["model"] = args.model
            resp = _request(client, "POST", "/agents/strategy/runs", json=run_payload)
            _require_ok(resp, "POST runs")
            run = resp.json()
            run_id = run["id"]
            print(f"run_id={run_id} status={run['status']}")

            if args.model:
                print(f"Model requested for this run: {args.model}")
            else:
                print(
                    "No --model/AGENT5_MODEL override given -- the server chooses "
                    "(STRATEGY_SYNTHESIS_MODEL env var on the backend if set, else "
                    "claude-opus-5 by default, per strategy_synthesis/config.py)."
                )

            _print_step("6. Poll run to completion")
            deadline = time.monotonic() + args.poll_timeout
            status = run["status"]
            while status in ("pending", "running"):
                if time.monotonic() > deadline:
                    raise SmokeTestFailure(f"Run {run_id} did not finish within {args.poll_timeout}s (last status: {status})")
                time.sleep(args.poll_interval)
                resp = _request(client, "GET", f"/agents/strategy/runs/{run_id}")
                _require_ok(resp, "GET run status")
                run = resp.json()
                status = run["status"]
                print(f"  status={status}")

            if status == "failed":
                print(f"\nRun FAILED: {run.get('error')}")
                return 1

            if status != "succeeded":
                raise SmokeTestFailure(f"Unexpected terminal status: {status!r}")

            _print_step("7. Download export.docx")
            resp = _request(client, "GET", f"/agents/strategy/runs/{run_id}/export.docx")
            _require_ok(resp, "GET export.docx")
            out_path = output_dir / f"agent5_smoke_export_{run_id}.docx"
            out_path.write_bytes(resp.content)
            print(f"Saved: {out_path} ({len(resp.content)} bytes)")

            print("\nSMOKE TEST PASSED.")
            return 0

    except SmokeTestFailure as e:
        print(f"\nSMOKE TEST FAILED: {e}", file=sys.stderr)
        return 1
    except httpx.HTTPError as e:
        print(f"\nSMOKE TEST FAILED (network error): {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
