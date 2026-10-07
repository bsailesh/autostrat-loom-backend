"""
Word export cover labels (app/export/docx_builder.py).

The property: `agent_label_for` raises for an agent type it does not know
rather than falling back, so a report pack can never go out with another
agent's name on its cover.

This used to be tested by borrowing a not-yet-built agent as the example of
an unregistered one. With all five agents built there is nothing left to
borrow, and the risk has moved: it is now a NEW agent shipping without a
label. So two tests --

  1. a made-up type raises, independent of which agents exist;
  2. every AGENT_TYPE the app declares has a label, discovered by walking
     the app package, so the next agent fails here automatically if it
     forgets to register.
"""
import importlib
import os
import pkgutil

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

import pytest

import app
from app.export.docx_builder import AGENT_LABELS, agent_label_for


def _declared_agent_types() -> dict[str, str]:
    """{agent_type: module} for every module under app/ with AGENT_TYPE."""
    found: dict[str, str] = {}
    for info in pkgutil.walk_packages(app.__path__, prefix="app."):
        module = importlib.import_module(info.name)
        agent_type = getattr(module, "AGENT_TYPE", None)
        if isinstance(agent_type, str):
            found[agent_type] = info.name
    return found


def test_an_unknown_agent_type_raises():
    with pytest.raises(ValueError):
        agent_label_for("not-an-agent-type")


def test_every_declared_agent_type_has_a_cover_label():
    declared = _declared_agent_types()
    missing = {t: m for t, m in declared.items() if t not in AGENT_LABELS}
    assert not missing, f"agent types with no export cover label: {missing}"


def test_discovery_finds_all_five_agents():
    # Guards the test above against silently finding nothing.
    assert set(_declared_agent_types()) >= {
        "market-insights", "strategy-synthesis", "tech-regulation", "voice-of-customer", "product-sustainment",
    }


def test_labels():
    assert agent_label_for("product-sustainment") == "Product Sustainment"
    assert agent_label_for("tech-regulation") == "Technology & Regulation"
