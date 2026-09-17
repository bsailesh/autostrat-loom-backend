"""
Structured stand-in for `agent5_decision_brief_strawman_v2.md` (Meridian
Avionics, fictional). Numbers below are transcribed directly from that brief
so `compute.py` tests exercise the exact shape it was written to probe:
51% aggregate FY27 utilisation with certification alone at 115%.

This is the decision-inputs side only. It intentionally does not attempt to
reconstruct a Market Insights run — `compute.py` never reads upstream report
markdown; that is Pass 1's job, upstream of this module.
"""

from strategy_synthesis.compute import Bucket, Capacity, Project, ProjectEffort

BUCKETS = [
    Bucket(bucket_key="hardware", bucket_name="Hardware", contractable="yes"),
    Bucket(bucket_key="software", bucket_name="Software", contractable="yes"),
    Bucket(bucket_key="systems", bucket_name="Systems", contractable="partial"),
    Bucket(bucket_key="certification", bucket_name="Certification", contractable="no"),
]

# fiscal_year, discipline, capacity_weeks — from `capacity_fy26_fy29.csv`.
# FY29 is deliberately absent: the brief records it as blank/unplanned, not zero.
CAPACITY = [
    Capacity(fiscal_year="FY27", bucket_key="hardware", capacity_units=980, budget=4_100_000),
    Capacity(fiscal_year="FY27", bucket_key="software", capacity_units=760, budget=3_100_000),
    Capacity(fiscal_year="FY27", bucket_key="systems", capacity_units=540, budget=2_300_000),
    Capacity(fiscal_year="FY27", bucket_key="certification", capacity_units=240, budget=1_300_000),
    Capacity(fiscal_year="FY28", bucket_key="hardware", capacity_units=980, budget=4_300_000),
    Capacity(fiscal_year="FY28", bucket_key="software", capacity_units=760, budget=3_200_000),
    Capacity(fiscal_year="FY28", bucket_key="systems", capacity_units=540, budget=2_400_000),
    Capacity(fiscal_year="FY28", bucket_key="certification", capacity_units=240, budget=1_400_000),
]

# `mandatory` mirrors the Mandatory column the reference output (Report 1,
# Report 4) derived from the roadmap's declared project type (Compliance).
PROJECTS = [
    Project(project_key="P-01", name="CVR-25 Part 25 TSO certification", mandatory=True,
            mandatory_driver="No sellable 25h CVR without it", mandatory_deadline="Q2 FY27"),
    Project(project_key="P-02", name="STC package — 5 regional jet types", mandatory=True,
            mandatory_driver="STC required per type before retrofit installation", mandatory_deadline="Q4 FY27"),
    Project(project_key="P-03", name="Crash-survivable memory IC redesign", mandatory=False),
    Project(project_key="P-04", name="ULB dual-source qualification", mandatory=False),
    Project(project_key="P-05", name="Low-SWaP variant, business aviation", mandatory=False),
    Project(project_key="P-06", name="Download tooling and workflow refresh", mandatory=False),
    Project(project_key="P-07", name="FDR capacity extension to 200 h", mandatory=False),
    Project(project_key="P-08", name="DO-326A airworthiness security", mandatory=True,
            mandatory_driver="Airworthiness security precondition", mandatory_deadline="Q4 FY27"),
    Project(project_key="P-09", name="Production line capacity expansion", mandatory=False),
]

# effort remaining, by discipline, in weeks — from `roadmap_fy26.csv`.
_EFFORT_TABLE = {
    "P-01": {"hardware": 6, "software": 4, "systems": 9, "certification": 40},
    "P-02": {"hardware": 20, "software": 15, "systems": 48, "certification": 125},
    "P-03": {"hardware": 130, "software": 18, "systems": 40, "certification": 20},
    "P-04": {"hardware": 22, "software": 0, "systems": 9, "certification": 10},
    "P-05": {"hardware": 150, "software": 60, "systems": 73, "certification": 40},
    "P-06": {"hardware": 0, "software": 38, "systems": 8, "certification": 2},
    "P-07": {"hardware": 70, "software": 45, "systems": 32, "certification": 15},
    "P-08": {"hardware": 5, "software": 30, "systems": 27, "certification": 15},
    "P-09": {"hardware": 95, "software": 10, "systems": 35, "certification": 10},
}

PROJECT_EFFORT = [
    ProjectEffort(project_key=project_key, bucket_key=bucket_key, effort_remaining=weeks)
    for project_key, by_bucket in _EFFORT_TABLE.items()
    for bucket_key, weeks in by_bucket.items()
]

COMMITTED_PROJECT_KEYS = {p.project_key for p in PROJECTS}

# The rank order Report 3 of `agent5_test_output_v2.md` assigns under base
# weighted scoring. Used directly (not re-derived from invented dimension
# scores) so the bottleneck/deferral tests exercise the brief's own case.
BASE_RANK_ORDER = ["P-01", "P-02", "P-09", "P-08", "P-04", "P-06", "P-03", "P-05", "P-07"]
