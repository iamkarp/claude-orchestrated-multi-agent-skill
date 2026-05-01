#!/usr/bin/env python3
"""
check_local_models.py

Detects which local LM Studio models are currently loaded by:
1. Reading ~/.config/opencode/opencode.json to find configured local providers.
2. Querying each provider's /v1/models endpoint to see what's actually running.
3. Returning the intersection as ready-to-use opencode model IDs.

Usage:
  python scripts/check_local_models.py
  python scripts/check_local_models.py --json
  python scripts/check_local_models.py --quiet   # only print model IDs, one per line
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any


OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"
QUERY_TIMEOUT = 3  # seconds — LM Studio responds instantly if running


def load_opencode_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def find_local_providers(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return providers whose baseURL looks like a local address."""
    providers = config.get("provider", {})
    local = []
    for provider_id, cfg in providers.items():
        base_url: str = (cfg.get("options") or {}).get("baseURL", "")
        if any(h in base_url for h in ("localhost", "127.0.0.1", "0.0.0.0", "::1")):
            local.append({
                "provider_id": provider_id,
                "name": cfg.get("name", provider_id),
                "base_url": base_url.rstrip("/"),
                "configured_models": list((cfg.get("models") or {}).keys()),
            })
    return local


def query_loaded_models(base_url: str) -> list[str] | None:
    """Hit the /v1/models endpoint. Returns None if the server isn't reachable."""
    url = f"{base_url}/models"
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer not-needed"})
        with urllib.request.urlopen(req, timeout=QUERY_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return [m["id"] for m in data.get("data", [])]
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def check(config_path: Path = OPENCODE_CONFIG) -> list[dict[str, Any]]:
    """
    Returns a list of available local model entries, each with:
      provider_id, name, base_url, opencode_model_id, model_id, configured

    All models currently loaded in LM Studio are returned — not just those
    listed in opencode.json. The opencode_model_id is always
    "<provider_id>/<model_id>" which OpenCode accepts as long as the provider
    is configured.
    """
    config = load_opencode_config(config_path)
    local_providers = find_local_providers(config)

    available: list[dict[str, Any]] = []
    for prov in local_providers:
        loaded = query_loaded_models(prov["base_url"])
        if loaded is None:
            continue  # LM Studio not running for this provider

        configured_set = set(prov["configured_models"])

        for model_id in loaded:
            # Skip embedding models — not useful for text generation tasks
            if "embedding" in model_id.lower():
                continue
            available.append({
                "provider_id": prov["provider_id"],
                "name": prov["name"],
                "base_url": prov["base_url"],
                "model_id": model_id,
                "opencode_model_id": f"{prov['provider_id']}/{model_id}",
                "configured": model_id in configured_set,
            })

    return available


def main() -> int:
    parser = argparse.ArgumentParser(description="Check which local LM Studio models are loaded.")
    parser.add_argument("--config", default=str(OPENCODE_CONFIG), help="Path to opencode.json")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--quiet", action="store_true", help="Print only opencode model IDs, one per line")
    args = parser.parse_args()

    available = check(Path(args.config))

    if args.quiet:
        for m in available:
            print(m["opencode_model_id"])
        return 0

    if args.json:
        print(json.dumps(available, indent=2))
        return 0

    if not available:
        print("No local models detected. Is LM Studio running?")
        print()
        print("Configured local providers in opencode.json:")
        config = load_opencode_config(Path(args.config))
        for prov in find_local_providers(config):
            print(f"  [{prov['provider_id']}] {prov['name']} @ {prov['base_url']}")
        return 1

    print("\n=== Local Models Loaded in LM Studio ===")
    for m in available:
        tag = " [configured]" if m["configured"] else ""
        print(f"  {m['opencode_model_id']}{tag}")
    print()
    first = available[0]["opencode_model_id"]
    print("Use with multi_agent_delegate.py:")
    print(f"  --target local-review --opencode-model \"{first}\"")
    print()
    print("Or let it auto-select (picks the first non-embedding model above):")
    print(f"  --target local-review  (no --opencode-model needed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
