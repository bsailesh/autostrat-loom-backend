"""
Shared DB-override management for the whole suite.

`app` (app.main.app) is one shared singleton, so `app.dependency_overrides`
is a single global dict -- it isn't scoped per test module. Any test file
that talks to the API via `TestClient(app)` and needs an isolated database
MUST define a module-level `override_get_db` callable (the FastAPI
dependency-override function, e.g. one backed by its own in-memory SQLite
engine). The autouse fixture below pins `app.dependency_overrides[get_db]`
to that module's `override_get_db` before each test in the module and
restores whatever was there before after the test, so the suite passes
regardless of file import/collection order.

Do NOT assign `app.dependency_overrides[get_db]` at module import time in a
test file -- that assignment is exactly the collection-order-dependent
global mutation this fixture exists to prevent. Just define
`override_get_db`; this fixture does the rest.

A module that builds a `TestClient(app)` but has no `override_get_db` fails
collection loudly (see `_require_db_override_convention` below) rather than
silently inheriting whatever database another file happened to leave
active.
"""
import os

# app.config.get_settings() is @lru_cache'd, so whichever import constructs
# it first wins for the whole pytest session. conftest.py is always
# imported before any test module, so these must be set here -- setting
# them only in each test file (as they still do, harmlessly, via the same
# os.environ.setdefault calls) is too late: this file's own `from app.main
# import app` below would already have cached Settings with un-seeded
# defaults first.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LOOM_ADMIN_KEYS", "test-admin-key")

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


@pytest.fixture(autouse=True)
def _pin_db_override(request):
    override = getattr(request.module, "override_get_db", None)
    if override is None:
        yield
        return
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        yield
    finally:
        if previous is not None:
            app.dependency_overrides[get_db] = previous
        else:
            app.dependency_overrides.pop(get_db, None)


def pytest_collection_modifyitems(session, config, items):
    """Fail loudly if a module uses TestClient(app) without opting into the
    override convention above, instead of silently running its requests
    against whatever database another module's fixture left in place."""
    checked_modules = set()
    for item in items:
        module = getattr(item, "module", None)
        if module is None or module in checked_modules:
            continue
        checked_modules.add(module)

        has_test_client = any(isinstance(value, TestClient) for value in vars(module).values())
        has_override = getattr(module, "override_get_db", None) is not None
        if has_test_client and not has_override:
            raise pytest.UsageError(
                f"{module.__name__} builds a TestClient(app) but defines no "
                "module-level `override_get_db`. Without it, this module's "
                "requests will silently run against whatever database "
                "another test module's fixture left active in "
                "app.dependency_overrides, depending on collection order. "
                "Define `override_get_db` (see tests/test_auth_and_contact.py "
                "for the pattern) so tests/conftest.py can pin it per test."
            )
