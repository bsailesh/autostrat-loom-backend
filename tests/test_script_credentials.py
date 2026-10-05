"""
scripts/credentials.py: a base URL and an API key are only used together if
they came from the same source -- both flags, or both halves of one env
prefix. Each test below is a way the old per-script resolution could pair one
environment's key with another's host.
"""
import pytest

from scripts.credentials import CredentialError, resolve_credentials

ALL = ("AGENT1_BASE_URL", "AGENT1_API_KEY", "AGENT3_BASE_URL", "AGENT3_API_KEY", "AGENT5_BASE_URL", "AGENT5_API_KEY")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ALL:
        monkeypatch.delenv(name, raising=False)


def test_half_a_prefix_is_never_completed_from_another(monkeypatch):
    # The case hit for real: AGENT3_API_KEY alone, AGENT5_* complete.
    monkeypatch.setenv("AGENT3_API_KEY", "agent3-key")
    monkeypatch.setenv("AGENT5_BASE_URL", "https://agent5.example")
    monkeypatch.setenv("AGENT5_API_KEY", "agent5-key")
    creds = resolve_credentials(None, None, ("AGENT3", "AGENT5"))
    assert (creds.base_url, creds.api_key, creds.source) == ("https://agent5.example", "agent5-key", "AGENT5")


def test_halves_from_two_prefixes_are_refused(monkeypatch):
    monkeypatch.setenv("AGENT3_API_KEY", "agent3-key")
    monkeypatch.setenv("AGENT5_BASE_URL", "https://agent5.example")
    with pytest.raises(CredentialError, match="never combined across prefixes"):
        resolve_credentials(None, None, ("AGENT3", "AGENT5"))


def test_a_url_flag_is_not_completed_with_an_env_key(monkeypatch):
    # --base-url pointing at staging with a production key in the env.
    monkeypatch.setenv("AGENT5_BASE_URL", "https://prod.example")
    monkeypatch.setenv("AGENT5_API_KEY", "prod-key")
    with pytest.raises(CredentialError, match="Pass both --base-url and --api-key"):
        resolve_credentials("https://staging.example", None, ("AGENT5",))


def test_a_key_flag_is_not_completed_with_an_env_url(monkeypatch):
    monkeypatch.setenv("AGENT5_BASE_URL", "https://prod.example")
    with pytest.raises(CredentialError, match="Pass both"):
        resolve_credentials(None, "staging-key", ("AGENT5",))


def test_both_flags_win_over_env(monkeypatch):
    monkeypatch.setenv("AGENT5_BASE_URL", "https://prod.example")
    monkeypatch.setenv("AGENT5_API_KEY", "prod-key")
    creds = resolve_credentials("https://staging.example", "staging-key", ("AGENT5",))
    assert (creds.base_url, creds.api_key, creds.source) == ("https://staging.example", "staging-key", "flags")


def test_prefix_order_is_respected(monkeypatch):
    for p in ("AGENT1", "AGENT3"):
        monkeypatch.setenv(f"{p}_BASE_URL", f"https://{p}.example")
        monkeypatch.setenv(f"{p}_API_KEY", f"{p}-key")
    creds = resolve_credentials(None, None, ("AGENT1", "AGENT3", "AGENT5"))
    assert creds.source == "AGENT1" and creds.api_key == "AGENT1-key"


def test_nothing_set_names_what_is_expected():
    with pytest.raises(CredentialError, match="AGENT5_BASE_URL \\+ AGENT5_API_KEY"):
        resolve_credentials(None, None, ("AGENT5",))
