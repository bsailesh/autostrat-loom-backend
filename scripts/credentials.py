"""
Credential resolution shared by the scripts in this directory.

The rule: a base URL and an API key are only ever used together if they
came from the SAME source -- both command-line flags, or both halves of one
environment-variable prefix. Resolving them independently pairs one
environment's key with another's host whenever only part of a source is
set, e.g.:

  * AGENT3_API_KEY alone plus AGENT5_BASE_URL sends the Agent 3 key to the
    Agent 5 host (hit for real while testing load_arden_voc_context.py; it
    reached only a local server, by luck);
  * --base-url pointing at staging plus AGENT5_API_KEY set for production
    sends the production key to staging.

Both stay harmless until staging and production are configured in the same
shell. So a single flag is rejected rather than completed from the
environment, and an environment prefix only counts when it has both halves.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


class CredentialError(Exception):
    """Raised with the message to print; callers exit 2."""


@dataclass(frozen=True)
class Credentials:
    base_url: str
    api_key: str
    source: str  # "flags" or an env prefix such as "AGENT5"


def resolve_credentials(url_flag: str | None, key_flag: str | None, prefixes: tuple[str, ...]) -> Credentials:
    if url_flag or key_flag:
        if not (url_flag and key_flag):
            raise CredentialError(
                "Pass both --base-url and --api-key, or neither. A single flag is not completed "
                "from environment variables: that could pair one environment's key with another's host."
            )
        return Credentials(url_flag, key_flag, "flags")

    half_set = []
    for prefix in prefixes:
        url = os.environ.get(f"{prefix}_BASE_URL")
        key = os.environ.get(f"{prefix}_API_KEY")
        if url and key:
            return Credentials(url, key, prefix)
        if url or key:
            half_set.append(prefix)

    expected = " or ".join(f"{p}_BASE_URL + {p}_API_KEY" for p in prefixes)
    detail = (
        f" Only half of {', '.join(f'{p}_*' for p in half_set)} is set, and halves are never "
        "combined across prefixes."
        if half_set
        else ""
    )
    raise CredentialError(f"No credentials: pass --base-url and --api-key, or set {expected}.{detail}")
