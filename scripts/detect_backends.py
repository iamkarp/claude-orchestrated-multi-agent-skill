#!/usr/bin/env python3
"""
detect_backends.py

Detects ALL available AI backends for the multi-agent orchestration skill.
Returns a prioritized list of what is currently usable so Claude can
route delegation tasks to whatever is actually available.

Backends checked:
  local      — LM Studio (OpenAI-compatible HTTP, localhost:1234)
  codex      — OpenAI Codex CLI (~/.codex/auth.json or OPENAI_API_KEY)
  kimi       — Alibaba / Kimi K2.5 via OpenCode (~/.config/opencode/opencode.json)
  gemini     — Gemini CLI (~/.gemini/google_accounts.json + 'gemini' binary)
  anthropic  — Claude Opus / Sonnet (ANTHROPIC_API_KEY)
  openrouter — OpenRouter / other providers (OPENROUTER_API_KEY)

Usage:
  python scripts/detect_backends.py
  python scripts/detect_backends.py --json
  python scripts/detect_backends.py --available-only
  python scripts/detect_backends.py --recommend --role review
  python scripts/detect_backends.py --recommend --role plan --task "Debug auth middleware"
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from pathlib import Path


LMSTUDIO_BASE_URL = "http://localhost:1234/v1"
CODEX_AUTH_FILE = Path.home() / ".codex" / "auth.json"
OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"
GEMINI_ACCOUNTS_FILE = Path.home() / ".gemini" / "google_accounts.json"
# Machine-local config (never committed to git) — overrides skill-level config.json
LOCAL_CONFIG_FILE = Path.home() / ".config" / "claude-multi-agent" / "config.json"
# Skill-level default config (committed, all backends enabled)
DEFAULT_CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"
QUERY_TIMEOUT = 3


def _load_disabled_backends() -> set[str]:
    """
    Return the set of backend kinds explicitly disabled on this machine.
    Reads ~/.config/claude-multi-agent/config.json first (machine-local),
    then falls back to the skill's config.json (repo default).
    """
    for path in (LOCAL_CONFIG_FILE, DEFAULT_CONFIG_FILE):
        if path.exists():
            try:
                data = json.loads(path.read_text())
                disabled = data.get("disabled_backends", [])
                return set(disabled)
            except (json.JSONDecodeError, OSError):
                pass
    return set()


@dataclass
class Backend:
    name: str          # human-readable display name
    kind: str          # local | codex | kimi | gemini | anthropic | openrouter
    available: bool
    models: list[str]  # loaded / configured model IDs
    base_url: str = "" # for local kind only
    note: str = ""     # reason available or not
    disabled: bool = False  # True when explicitly turned off in config


# ---------------------------------------------------------------------------
# Individual backend checks
# ---------------------------------------------------------------------------

def _check_lmstudio() -> Backend:
    url = f"{LMSTUDIO_BASE_URL}/models"
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer not-needed"})
        with urllib.request.urlopen(req, timeout=QUERY_TIMEOUT) as resp:
            data = json.loads(resp.read())
            models = [
                m["id"] for m in data.get("data", [])
                if "embedding" not in m["id"].lower()
            ]
            if models:
                return Backend(
                    name="LM Studio (local)",
                    kind="local",
                    available=True,
                    models=models,
                    base_url=LMSTUDIO_BASE_URL,
                    note=f"{len(models)} model(s) loaded",
                )
            return Backend(
                name="LM Studio (local)",
                kind="local",
                available=False,
                models=[],
                base_url=LMSTUDIO_BASE_URL,
                note="running but no models loaded",
            )
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return Backend(
            name="LM Studio (local)",
            kind="local",
            available=False,
            models=[],
            base_url=LMSTUDIO_BASE_URL,
            note="not running",
        )


def _codex_token() -> str | None:
    """Read OAuth access token from ~/.codex/auth.json."""
    if not CODEX_AUTH_FILE.exists():
        return None
    try:
        data = json.loads(CODEX_AUTH_FILE.read_text())
        return (data.get("tokens") or {}).get("access_token") or None
    except (json.JSONDecodeError, KeyError):
        return None


def _check_codex() -> Backend:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    token = _codex_token()
    if api_key or token:
        source = "OPENAI_API_KEY env" if api_key else "~/.codex/auth.json"
        return Backend(
            name="Codex / OpenAI",
            kind="codex",
            available=True,
            models=["codex"],
            note=f"authenticated via {source}",
        )
    return Backend(
        name="Codex / OpenAI",
        kind="codex",
        available=False,
        models=[],
        note="no OPENAI_API_KEY and no ~/.codex/auth.json token — run: codex login",
    )


def _check_kimi() -> Backend:
    """Check for Alibaba/Kimi or any non-local provider with an API key in opencode.json."""
    if not OPENCODE_CONFIG.exists():
        return Backend(
            name="Kimi K2.5 / Alibaba",
            kind="kimi",
            available=False,
            models=[],
            note="~/.config/opencode/opencode.json not found",
        )
    try:
        config = json.loads(OPENCODE_CONFIG.read_text())
        providers = config.get("provider", {})
        for provider_id, cfg in providers.items():
            base_url: str = (cfg.get("options") or {}).get("baseURL", "")
            api_key: str = (cfg.get("options") or {}).get("apiKey", "")
            # Skip local providers — those belong to LM Studio
            if any(h in base_url for h in ("localhost", "127.0.0.1", "0.0.0.0", "::1")):
                continue
            if api_key:
                slugs = list((cfg.get("models") or {}).keys())
                # OpenCode requires "provider_id/model_slug" format for --model flag
                model_names = [f"{provider_id}/{s}" for s in slugs] if slugs else [provider_id]
                display = cfg.get("name", provider_id)
                return Backend(
                    name=f"{display} (via OpenCode)",
                    kind="kimi",
                    available=True,
                    models=model_names,
                    note=f"provider={provider_id}, {len(model_names)} model(s) configured",
                )
    except (json.JSONDecodeError, KeyError):
        pass
    return Backend(
        name="Kimi K2.5 / Alibaba",
        kind="kimi",
        available=False,
        models=[],
        note="opencode.json found but no remote provider with apiKey configured",
    )


def _check_gemini_cli() -> Backend:
    """Check for the Google Gemini CLI (npm @google/gemini-cli)."""
    import shutil
    binary = shutil.which("gemini")
    if not binary:
        return Backend(
            name="Gemini CLI (Google)",
            kind="gemini",
            available=False,
            models=[],
            note="'gemini' binary not found — install with: npm install -g @google/gemini-cli",
        )
    # Presence of google_accounts.json with an active account = authenticated
    if GEMINI_ACCOUNTS_FILE.exists():
        try:
            data = json.loads(GEMINI_ACCOUNTS_FILE.read_text())
            active = data.get("active", "") if isinstance(data, dict) else ""
            if active:
                return Backend(
                    name="Gemini CLI (Google)",
                    kind="gemini",
                    available=True,
                    models=["gemini-2.5-pro", "gemini-2.5-flash"],
                    note=f"authenticated as {active}",
                )
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    return Backend(
        name="Gemini CLI (Google)",
        kind="gemini",
        available=False,
        models=[],
        note="binary found but not authenticated — run: gemini login",
    )


def _check_anthropic() -> Backend:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return Backend(
            name="Claude (Anthropic API)",
            kind="anthropic",
            available=True,
            models=["claude-opus-4-7", "claude-sonnet-4-6"],
            note="ANTHROPIC_API_KEY set",
        )
    return Backend(
        name="Claude (Anthropic API)",
        kind="anthropic",
        available=False,
        models=[],
        note="ANTHROPIC_API_KEY not set (Claude Code itself uses a separate session token)",
    )


def _check_openrouter() -> Backend:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return Backend(
            name="OpenRouter (Gemini, Mistral, etc.)",
            kind="openrouter",
            available=True,
            models=["google/gemini-2.5-pro", "google/gemini-2.5-flash"],
            note="OPENROUTER_API_KEY set",
        )
    return Backend(
        name="OpenRouter (Gemini, Mistral, etc.)",
        kind="openrouter",
        available=False,
        models=[],
        note="OPENROUTER_API_KEY not set",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_all() -> list[Backend]:
    """Return detection results for every backend, available or not."""
    disabled = _load_disabled_backends()
    backends = [
        _check_lmstudio(),
        _check_codex(),
        _check_kimi(),
        _check_gemini_cli(),
        _check_anthropic(),
        _check_openrouter(),
    ]
    for b in backends:
        if b.kind in disabled:
            b.available = False
            b.disabled = True
            b.note = f"disabled in config (was: {b.note})"
    return backends


def available_backends(backends: list[Backend] | None = None) -> list[Backend]:
    if backends is None:
        backends = detect_all()
    return [b for b in backends if b.available]


# Priority ordering per task role.
# Claude Code itself is always the orchestrator and final judge — these priorities
# apply only to *external* review / planning / implementation agents.
_PRIORITY: dict[str, list[str]] = {
    "review":    ["codex", "kimi", "gemini", "local", "openrouter"],
    "plan":      ["kimi", "gemini", "local", "codex", "openrouter"],
    "implement": ["codex", "local", "kimi", "gemini", "openrouter"],
}


def recommend(role: str = "review", backends: list[Backend] | None = None) -> Backend | None:
    """
    Return the best available backend for `role` (review | plan | implement).
    Returns None if nothing is available.
    """
    if backends is None:
        backends = detect_all()
    avail = {b.kind: b for b in backends if b.available}
    for kind in _PRIORITY.get(role, _PRIORITY["review"]):
        if kind in avail:
            return avail[kind]
    return None


def delegate_command(backend: Backend, role: str) -> str:
    """
    Return a ready-to-paste multi_agent_delegate.py command for the given backend and role.
    Caller should append --task "..." --include-git-diff etc.
    """
    script = "python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/multi_agent_delegate.py"
    # Map role → closest valid target per backend kind
    _tmap: dict[tuple[str, str], str] = {
        ("codex",      "review"):    "codex-review",
        ("codex",      "plan"):      "codex-review",
        ("codex",      "implement"): "codex-implement",
        ("local",      "review"):    "local-review",
        ("local",      "plan"):      "local-plan",
        ("local",      "implement"): "local-implement",
        ("kimi",       "review"):    "qwen-review",
        ("kimi",       "plan"):      "qwen-plan",
        ("kimi",       "implement"): "qwen-plan",
        ("gemini",     "review"):    "gemini-review",
        ("gemini",     "plan"):      "gemini-plan",
        ("gemini",     "implement"): "gemini-review",
        ("openrouter", "review"):    "qwen-review",
        ("openrouter", "plan"):      "qwen-plan",
        ("openrouter", "implement"): "qwen-plan",
    }
    target = _tmap.get((backend.kind, role), "codex-review")
    if backend.kind == "local":
        model = backend.models[0] if backend.models else ""
        return f'{script} --target {target} --opencode-model "{model}" --execute'
    if backend.kind in ("kimi", "openrouter"):
        model = backend.models[0] if backend.models else ""
        return f'{script} --target {target} --opencode-model "{model}" --execute'
    return f"{script} --target {target} --execute"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect all available AI backends for multi-agent orchestration."
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON array")
    parser.add_argument("--available-only", action="store_true", help="Show only available backends")
    parser.add_argument("--recommend", action="store_true",
                        help="Print the recommended backend and its delegate command")
    parser.add_argument("--role", choices=["review", "plan", "implement"], default="review",
                        help="Task role for recommendation (default: review)")
    parser.add_argument("--task", default="", help="Task description (informational only)")
    args = parser.parse_args()

    backends = detect_all()
    shown = [b for b in backends if b.available] if args.available_only else backends

    if args.json:
        print(json.dumps([asdict(b) for b in shown], indent=2))
        return 0

    print("\n=== AI Backend Detection ===\n")
    for b in shown:
        mark = "[OK]" if b.available else "[ ]"
        print(f"  {mark} {b.name}")
        if b.available and b.models:
            names = b.models[:4]
            suffix = f" ... +{len(b.models) - 4} more" if len(b.models) > 4 else ""
            print(f"        models : {', '.join(names)}{suffix}")
        print(f"        status : {b.note}")
        print()

    if args.recommend:
        rec = recommend(args.role, backends)
        if rec:
            cmd = delegate_command(rec, args.role)
            print(f"=== Recommended for '{args.role}' ===")
            print(f"  Backend : {rec.name}")
            if rec.kind == "local" and rec.models:
                print(f"  Model   : {rec.models[0]}")
            elif rec.models:
                print(f"  Model   : {rec.models[0]}")
            print(f"  Command : {cmd} --task \"...\"")
        else:
            print(f"No available backend found for role '{args.role}'.")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
