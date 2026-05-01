#!/usr/bin/env python3
"""
multi_agent_delegate.py

Helper for a Claude Code skill where Claude Code remains the orchestrator.

This script does NOT decide the whole workflow.
Claude Code decides the route, then uses this helper to generate or execute
safe calls to Codex or OpenCode/Qwen/local models.

Targets:
- codex-implement
- codex-review
- qwen-plan
- qwen-review
- qwen-compare
- local-review
- local-implement
- local-plan

Default behavior:
- Print the command and prompt.
- Use --execute to actually call codex or opencode.

OpenCode assumptions:
- OpenCode is installed as `opencode`.
- OpenCode is configured separately in opencode.json.
- You can pass provider/model through --opencode-model.

Examples:
  python scripts/multi_agent_delegate.py --target codex-review --include-git-diff --task "Review this patch."

  python scripts/multi_agent_delegate.py --target qwen-review --include-git-diff --execute \
    --opencode-model "qwen/qwen3-coder-plus" \
    --task "Review this patch."

Security:
- This script does not manage auth tokens.
- It does not print API keys.
- It does not rotate, pool, or bypass subscription limits.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


TARGETS = {
    "codex-implement",
    "codex-review",
    "qwen-plan",
    "qwen-review",
    "qwen-compare",
    "local-review",
    "local-implement",
    "local-plan",
    "gemini-review",
    "gemini-plan",
    # auto-* targets: detect whichever backend is available and route there
    "auto-review",
    "auto-plan",
    "auto-implement",
}


@dataclass
class Delegation:
    target: str
    tool: str
    command_preview: list[str]
    prompt: str
    notes: list[str]
    local_model_id: str = ""
    local_base_url: str = ""


def run_capture(cmd: list[str], timeout: int = 30) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (proc.stdout or "")
        if proc.stderr:
            out += "\n" + proc.stderr
        return out.strip()
    except Exception as e:
        return f"[could not run {' '.join(cmd)}: {e}]"


def git_context(include_git_diff: bool, max_chars: int) -> str:
    if not include_git_diff:
        return ""

    status = run_capture(["git", "status", "--short"])
    diff_stat = run_capture(["git", "diff", "--stat"])
    diff = run_capture(["git", "diff", "--", "."])

    context = f"""
--- GIT STATUS ---
{status}

--- GIT DIFF STAT ---
{diff_stat}

--- GIT DIFF ---
{diff}
"""
    if len(context) > max_chars:
        context = context[:max_chars] + "\n\n[TRUNCATED: git context exceeded max chars]\n"
    return context


def build_prompt(target: str, task: str, context: str) -> str:
    if target == "codex-implement":
        return f"""You are Codex acting as a focused implementation agent.

Implement the requested change as a minimal patch.
Keep the diff focused.
Avoid broad refactors.
Add or update tests when appropriate.
Run the most relevant tests if possible.
Explain what changed and why.

Task:
{task}
"""

    if target == "codex-review":
        return f"""You are Codex acting as an independent code reviewer.

Review the current task and git diff.
Look for:
- correctness issues
- missed edge cases
- missing or weak tests
- over-broad edits
- security risks
- simpler alternatives
- places where the implementation does not match the user intent

Return:
1. Verdict: approve / approve with minor fixes / reject
2. Top issues, prioritized
3. Specific suggested changes
4. Test recommendations

Task:
{task}

{context}
"""

    if target == "qwen-plan":
        return f"""You are Qwen/Alibaba acting through OpenCode as an API-backed coding architect.

You may not have direct terminal access unless command output is provided.
Create a practical implementation plan.

Return:
1. Likely files/modules to inspect
2. Minimal patch strategy
3. Edge cases
4. Test strategy
5. Risks
6. What Claude Code should do next

Task:
{task}

{context}
"""

    if target == "qwen-review":
        return f"""You are Qwen/Alibaba acting through OpenCode as an independent code reviewer.

Review the task and git diff skeptically.
Look for:
- logical bugs
- missing edge cases
- missing tests
- unnecessary changes
- risky assumptions
- possible simplifications
- production/security/data risks

Return:
1. Verdict: approve / approve with minor fixes / reject
2. Top issues, prioritized
3. Exact changes Claude Code should make
4. Tests that should be run or added

Task:
{task}

{context}
"""

    if target == "qwen-compare":
        return f"""You are Qwen/Alibaba acting through OpenCode as a comparison judge.

Compare the possible approaches to this task.
If a diff is included, judge whether it is better than plausible alternatives.

Return:
1. Best approach
2. Why it is safer/simpler
3. What to avoid
4. Specific next steps for Claude Code
5. Any test or validation recommendations

Task:
{task}

{context}
"""

    if target == "local-review":
        return f"""You are a local model acting through OpenCode as a private/low-cost code reviewer.

Review the task and git diff for obvious issues.
Focus on practical concerns:
- bugs
- test gaps
- unnecessary changes
- unclear logic
- risky commands

Task:
{task}

{context}
"""

    if target == "local-implement":
        return f"""You are a local model acting through OpenCode as a focused implementation agent.

Implement the requested change as a minimal, focused patch.
- Keep changes small and targeted.
- Avoid broad refactors.
- Add or update tests when the task calls for it.
- Explain briefly what changed and why.

Task:
{task}

{context}
"""

    if target == "local-plan":
        return f"""You are a local model acting through OpenCode as a planning assistant.

Create a concise implementation plan for the task below.
You may not have direct repo access unless context is provided.

Return:
1. Files/modules most likely affected
2. Suggested approach (minimal patch strategy)
3. Key edge cases to watch
4. Test strategy
5. Risks or unknowns
6. What Claude Code should do next

Task:
{task}

{context}
"""

    if target == "gemini-review":
        return f"""You are Gemini acting as an independent code reviewer.

Review the task and any included git diff.
Look for:
- correctness bugs
- missed edge cases
- missing or weak tests
- over-broad edits
- security risks
- simpler alternatives
- places where the implementation diverges from the user's intent

Return:
1. Verdict: approve / approve with minor fixes / reject
2. Top issues, prioritized
3. Specific suggested changes
4. Test recommendations

Task:
{task}

{context}
"""

    if target == "gemini-plan":
        return f"""You are Gemini acting as a coding architect and planning assistant.

Create a practical implementation plan for the task below.
You may not have direct repo access unless context is provided.

Return:
1. Files/modules most likely affected
2. Minimal patch strategy
3. Edge cases to watch
4. Test strategy
5. Risks or unknowns
6. What Claude Code should do next

Task:
{task}

{context}
"""

    raise ValueError(f"Unsupported target: {target}")


def build_delegation(
    target: str,
    task: str,
    context: str,
    opencode_model: str,
    local_model_id: str = "",
    local_base_url: str = "",
) -> Delegation:
    prompt = build_prompt(target, task, context)

    if target.startswith("codex"):
        tool = "codex"
        command_preview = ["codex", "<prompt>"]
        notes = [
            "Codex uses its own official CLI authentication.",
            "Claude Code should inspect Codex's output before applying or trusting it.",
        ]
        return Delegation(target=target, tool=tool, command_preview=command_preview, prompt=prompt, notes=notes)

    if target.startswith("local-"):
        tool = "lmstudio"
        command_preview = ["POST", f"{local_base_url}/chat/completions", f"model={local_model_id}"]
        notes = [
            "Calling LM Studio directly via HTTP — no OpenCode required.",
            f"Model: {local_model_id}",
            f"Endpoint: {local_base_url}/chat/completions",
        ]
        return Delegation(
            target=target,
            tool=tool,
            command_preview=command_preview,
            prompt=prompt,
            notes=notes,
            local_model_id=local_model_id,
            local_base_url=local_base_url,
        )

    if target.startswith("gemini-"):
        tool = "gemini"
        command_preview = ["gemini", "--prompt", "<prompt>"]
        notes = [
            "Gemini CLI uses Google OAuth credentials from ~/.gemini/.",
            "Claude Code should inspect Gemini's output before applying or trusting it.",
        ]
        return Delegation(target=target, tool=tool, command_preview=command_preview, prompt=prompt, notes=notes)

    # OpenCode path (qwen-*, etc.)
    tool = "opencode"
    if opencode_model:
        command_preview = ["opencode", "run", "--model", opencode_model, "<prompt>"]
    else:
        command_preview = ["opencode", "run", "<prompt>"]
    notes = [
        "OpenCode should be configured separately for Qwen/API providers.",
        "Use OpenCode as the provider bridge, not as the main orchestrator.",
    ]
    return Delegation(target=target, tool=tool, command_preview=command_preview, prompt=prompt, notes=notes)


def call_lmstudio_direct(prompt: str, model_id: str, base_url: str, timeout: int = 300) -> int:
    """POST directly to LM Studio's OpenAI-compatible API."""
    url = f"{base_url}/chat/completions"
    payload = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": -1,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": "Bearer not-needed"},
        method="POST",
    )

    print(f"\n=== LM Studio ({model_id}) ===\n")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            if "error" in data:
                print(f"LM Studio error: {data['error'].get('message', data['error'])}")
                return 1
            choices = data.get("choices") or []
            if not choices:
                print("LM Studio returned no choices.")
                return 1
            print(choices[0]["message"]["content"])
            return 0
    except urllib.error.HTTPError as e:
        print(f"Error: LM Studio returned HTTP {e.code} for {url}")
        return 1
    except urllib.error.URLError as e:
        print(f"Error: LM Studio not reachable at {url}: {e}")
        return 1
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error parsing LM Studio response: {e}")
        return 1


def execute_delegation(delegation: Delegation, opencode_model: str) -> int:
    if delegation.tool == "codex":
        cmd = ["codex", delegation.prompt]
        print("\n=== Executing ===")
        print(shlex.join([cmd[0], "<prompt>"]))
        print()
        proc = subprocess.run(cmd)
        return proc.returncode

    if delegation.tool == "lmstudio":
        return call_lmstudio_direct(
            delegation.prompt,
            delegation.local_model_id,
            delegation.local_base_url,
        )

    if delegation.tool == "gemini":
        cmd = ["gemini", "--prompt", delegation.prompt, "--yolo"]
        print("\n=== Executing (Gemini CLI) ===")
        print("gemini --prompt <prompt> --yolo")
        print()
        proc = subprocess.run(cmd)
        return proc.returncode

    if delegation.tool == "opencode":
        if opencode_model:
            cmd = ["opencode", "run", "--model", opencode_model, delegation.prompt]
        else:
            cmd = ["opencode", "run", delegation.prompt]
        print("\n=== Executing ===")
        print(shlex.join([cmd[0], *cmd[1:-1], "<prompt>"]))
        print()
        proc = subprocess.run(cmd)
        return proc.returncode

    raise ValueError(f"Unsupported tool: {delegation.tool}")


def _load_check_local():
    """Import check_local_models from the same scripts/ directory."""
    scripts_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts_dir))
    try:
        import check_local_models
        return check_local_models
    except ImportError:
        return None


def _load_detect_backends():
    """Import detect_backends from the same scripts/ directory."""
    scripts_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts_dir))
    try:
        import detect_backends
        return detect_backends
    except ImportError:
        return None


def _resolve_auto_target(auto_role: str, json_mode: bool) -> tuple[str, str, str, str]:
    """
    For auto-review / auto-plan / auto-implement, detect available backends
    and return (resolved_target, opencode_model, local_model_id, local_base_url).
    Prints chosen backend unless json_mode is True.
    Raises SystemExit(1) if nothing is available.
    """
    db = _load_detect_backends()
    if db is None:
        print("Error: detect_backends.py not found — cannot auto-route.", file=sys.stderr)
        raise SystemExit(1)

    backends = db.detect_all()
    rec = db.recommend(auto_role, backends)
    if rec is None:
        print(
            f"Error: no available backend found for role '{auto_role}'.\n"
            "Install Codex ('codex login'), start LM Studio, or configure an API key.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if not json_mode:
        print(f"[auto-route] role={auto_role} → backend={rec.name}")

    opencode_model = ""
    local_model_id = ""
    local_base_url = "http://localhost:1234/v1"

    # Map (backend_kind, role) → a valid explicit delegate target.
    # qwen-implement and codex-plan do not exist; use the closest valid target.
    _target_map: dict[tuple[str, str], str] = {
        ("codex",      "review"):    "codex-review",
        ("codex",      "plan"):      "codex-review",      # no codex-plan target
        ("codex",      "implement"): "codex-implement",
        ("local",      "review"):    "local-review",
        ("local",      "plan"):      "local-plan",
        ("local",      "implement"): "local-implement",
        ("kimi",       "review"):    "qwen-review",
        ("kimi",       "plan"):      "qwen-plan",
        ("kimi",       "implement"): "qwen-plan",          # no qwen-implement target
        ("gemini",     "review"):    "gemini-review",
        ("gemini",     "plan"):      "gemini-plan",
        ("gemini",     "implement"): "gemini-review",      # no gemini-implement target
        ("openrouter", "review"):    "qwen-review",
        ("openrouter", "plan"):      "qwen-plan",
        ("openrouter", "implement"): "qwen-plan",
        ("anthropic",  "review"):    "codex-review",
        ("anthropic",  "plan"):      "qwen-plan",
        ("anthropic",  "implement"): "codex-implement",
    }
    resolved_target = _target_map.get((rec.kind, auto_role), "codex-review")

    if rec.kind == "local":
        local_model_id = rec.models[0] if rec.models else ""
        local_base_url = rec.base_url or local_base_url
        if not json_mode:
            print(f"[auto-route] model={local_model_id} @ {local_base_url}")
    elif rec.kind == "codex":
        pass  # no extra fields needed
    elif rec.kind in ("kimi", "openrouter"):
        # rec.models already contain fully-prefixed IDs (e.g. "bailian-coding-plan/qwen3.5-plus")
        opencode_model = rec.models[0] if rec.models else ""
        if not json_mode:
            print(f"[auto-route] model={opencode_model}")
    elif rec.kind == "gemini":
        if not json_mode:
            model = rec.models[0] if rec.models else "gemini-2.5-pro"
            print(f"[auto-route] model={model} (Gemini CLI)")
    else:
        pass  # anthropic or unknown — codex fallback, no extra fields

    return resolved_target, opencode_model, local_model_id, local_base_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Delegate a Claude Code task to Codex or OpenCode/Qwen/local model.")
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--include-git-diff", action="store_true")
    parser.add_argument("--max-git-chars", type=int, default=24000)
    parser.add_argument("--opencode-model", default=os.environ.get("OPENCODE_MODEL", ""))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--check-local",
        action="store_true",
        help="Query LM Studio for loaded models and print them before delegating. "
             "For local-* targets, auto-selects the first loaded model if --opencode-model is not set.",
    )
    args = parser.parse_args()

    # Resolve auto-* targets first — they override everything else
    target = args.target
    opencode_model = args.opencode_model
    local_model_id = ""
    local_base_url = "http://localhost:1234/v1"

    if target.startswith("auto-"):
        auto_role = target[len("auto-"):]  # "review" | "plan" | "implement"
        target, opencode_model, local_model_id, local_base_url = _resolve_auto_target(
            auto_role, args.json
        )

    if args.check_local or target.startswith("local-"):
        clm = _load_check_local()
        if clm:
            available = clm.check()
            if available:
                if args.check_local and not args.json:
                    print("\n=== Local Models Detected ===")
                    for m in available:
                        print(f"  {m['model_id']}  @ {m['base_url']}")
                    print()
                if target.startswith("local-"):
                    # Use --opencode-model as model_id override if provided (strip provider prefix)
                    if opencode_model:
                        # e.g. "lmstudio/qwen3-coder-next-mlx" → "qwen3-coder-next-mlx"
                        local_model_id = opencode_model.split("/", 1)[-1] if "/" in opencode_model else opencode_model
                        local_base_url = available[0]["base_url"]
                    else:
                        local_model_id = available[0]["model_id"]
                        local_base_url = available[0]["base_url"]
                    if not args.json:
                        print(f"[local model: {local_model_id} @ {local_base_url}]")
            else:
                if not args.json:
                    print("[no local models detected — LM Studio may not be running]")
                if target.startswith("local-") and not opencode_model:
                    print("Error: LM Studio is not running and --opencode-model was not provided.")
                    return 1
                elif target.startswith("local-"):
                    # Fallback: treat --opencode-model as bare model_id; keep default base_url
                    local_model_id = opencode_model.split("/", 1)[-1] if "/" in opencode_model else opencode_model
                    # local_base_url stays as the default "http://localhost:1234/v1"

    context = git_context(args.include_git_diff, args.max_git_chars)
    delegation = build_delegation(
        target, args.task, context, opencode_model,
        local_model_id=local_model_id, local_base_url=local_base_url,
    )

    if args.json:
        print(json.dumps(asdict(delegation), indent=2))
    else:
        print("\n=== Delegation ===")
        print(json.dumps({
            "target": delegation.target,
            "tool": delegation.tool,
            "command_preview": delegation.command_preview,
            "notes": delegation.notes,
        }, indent=2))
        print("\n=== Prompt ===")
        print(delegation.prompt)

    if args.execute:
        return execute_delegation(delegation, opencode_model)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
