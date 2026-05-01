#!/usr/bin/env python3
"""
claude_model_router.py

Recommends which Claude Code model to use for a coding task:
- opus
- sonnet
- split: opus for planning/arbitration, sonnet for execution

This helper does not change Claude Code settings automatically.
It prints recommended /model commands or startup commands.

Claude Code supports:
- /model inside a session
- claude --model <model> at startup
- aliases like opus and sonnet, depending on account/admin availability
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict


@dataclass
class ModelDecision:
    recommended_model: str
    phase_flow: list[str]
    why: str
    suggested_start_command: str
    suggested_in_session_command: str
    external_review_recommended: bool
    notes: list[str]


def decide(task: str, prefer_full_ids: bool = False) -> ModelDecision:
    t = task.lower()

    high_risk_terms = [
        "auth", "oauth", "password", "secret", "token", "billing", "payment",
        "security", "permissions", "prod", "production", "database migration",
        "migration", "delete", "data loss", "infra", "deployment", "rollback",
        "compliance", "privacy", "encryption"
    ]
    hard_terms = [
        "architecture", "architect", "design", "ambiguous", "debug", "failing",
        "fails", "investigate", "root cause", "race condition", "deadlock",
        "performance", "memory leak", "distributed", "concurrency", "refactor core",
        "large refactor", "multi-agent", "compare", "arbitrate"
    ]
    simple_terms = [
        "typo", "rename", "docs", "documentation", "readme", "small", "localized",
        "boilerplate", "add test", "write tests", "unit test", "format", "lint"
    ]

    high_risk = any(x in t for x in high_risk_terms)
    hard = any(x in t for x in hard_terms)
    simple = any(x in t for x in simple_terms)

    if high_risk:
        model = "opus"
        flow = [
            "Opus: plan and identify risks",
            "Sonnet or Codex: implement narrowly if the plan is clear",
            "Codex and/or OpenCode/Qwen: independent review",
            "Opus: final arbitration before accepting"
        ]
        why = "The task appears high-risk, so Opus should handle planning and final judgment."
        review = True
    elif hard:
        model = "opus"
        flow = [
            "Opus: investigate and plan",
            "Sonnet: execute straightforward edits if the plan is clear",
            "Opus or Codex: review if the diff is non-trivial"
        ]
        why = "The task appears reasoning-heavy or ambiguous, so Opus is the safer starting model."
        review = True
    elif simple:
        model = "sonnet"
        flow = [
            "Sonnet: implement directly",
            "Run relevant tests",
            "Use Codex/Qwen review only if tests fail or the diff grows"
        ]
        why = "The task appears localized or repetitive, so Sonnet is likely sufficient and more quota-efficient."
        review = False
    else:
        model = "sonnet"
        flow = [
            "Sonnet: start with a concise plan",
            "Switch to Opus if ambiguity or risk emerges",
            "Ask Codex/Qwen for review if the diff becomes large"
        ]
        why = "No strong high-risk signal was detected; start with Sonnet and escalate if needed."
        review = False

    if prefer_full_ids:
        # These IDs are intentionally easy to edit if the user's account/docs show different names.
        start_model = "claude-opus-4-7" if model == "opus" else "claude-sonnet-4-6"
    else:
        start_model = model

    return ModelDecision(
        recommended_model=model,
        phase_flow=flow,
        why=why,
        suggested_start_command=f"claude --model {start_model}",
        suggested_in_session_command=f"/model {start_model}",
        external_review_recommended=review,
        notes=[
            "Use /status inside Claude Code to confirm the active model.",
            "Available models may be restricted by account, plan, or enterprise policy.",
            "Use Sonnet for execution when the Opus-generated plan is clear and the task is low-risk.",
            "Use Opus for final arbitration when Codex and Qwen disagree."
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend Opus vs Sonnet for a Claude Code task.")
    parser.add_argument("--task", required=True)
    parser.add_argument("--prefer-full-ids", action="store_true", help="Use current full model names instead of aliases.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    decision = decide(args.task, args.prefer_full_ids)

    if args.json:
        print(json.dumps(asdict(decision), indent=2))
    else:
        print("\n=== Claude Model Recommendation ===")
        print(json.dumps(asdict(decision), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
