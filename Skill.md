---
name: Claude-Orchestrated Multi-Agent Coding
description: Use Claude Code as the main coding orchestrator, with automatic backend detection and routing to Codex, Kimi/Alibaba, Gemini CLI, or local LM Studio models for implementation, review, and planning.
---

# Claude-Orchestrated Multi-Agent Coding

## Purpose

Claude Code is the **orchestrator and final decision-maker**. This skill provides scripts to detect all available AI backends and delegate tasks to the best one automatically.

Available backends (detected at runtime):
- **LM Studio** — local, free, private; direct HTTP to OpenAI-compatible API
- **Codex CLI** — OpenAI, best for precise review and implementation
- **Kimi K2.5 / Alibaba** — via OpenCode, good for planning and second opinions
- **Gemini CLI** — Google, good for planning and review
- **Claude (Anthropic API)** — ANTHROPIC_API_KEY if set
- **OpenRouter** — OPENROUTER_API_KEY if set

## Critical principle

Claude Code is the orchestrator. Do **not** put a separate router above Claude. Claude decides when to delegate, to whom, and whether to accept or reject the advice.

## Mandatory narration rule

**Before every tool call or agent delegation, state in one line which AI/tool is being used and why.**

Examples:
- `Using **Bash** (Claude Sonnet) — regenerating manifest`
- `Routing to **Gemini CLI** — review pass on this diff`
- `Routing to **Codex** — independent implementation of this scoped patch`
- `Routing to **Kimi K2.5** via OpenCode — planning pass`
- `Using **Edit** (Claude Sonnet) — applying the approved change`

Never make a tool call silently.

## Auth model

Use each tool through its own authentication. Do not share, extract, or manage credentials.

| Backend | Auth |
|---|---|
| Claude Code | session token (already authenticated) |
| Codex | `codex login` → `~/.codex/auth.json` |
| OpenCode/Kimi | `~/.config/opencode/opencode.json` apiKey |
| Gemini CLI | `gemini login` → `~/.gemini/oauth_creds.json` |
| LM Studio | no auth needed (local HTTP) |

## Per-machine backend configuration

Disable specific backends on a per-machine basis without touching the committed code.

**Machine-local config** (never committed): `~/.config/claude-multi-agent/config.json`

```json
{
  "disabled_backends": ["kimi"],
  "_comment": "Valid values: local, codex, kimi, gemini, anthropic, openrouter"
}
```

**Skill-level default** (committed, all enabled): `<skill_root>/config.json`

```json
{
  "disabled_backends": []
}
```

The machine-local file takes precedence. Disabled backends are still detected but shown as `[DISABLED]` and skipped by auto-routing.

To check which backends are active on the current machine:

```bash
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/detect_backends.py
```

## Balance guidance

| Agent | Natural lane |
|---|---|
| **Claude Opus** | planning, architecture, ambiguous bugs, arbitrating disagreements, high-risk changes |
| **Claude Sonnet** | implementation, localized patches, executing approved plans, docs, tests |
| **Codex** | precise review, well-scoped implementation, test generation |
| **Kimi K2.5** | cheaper planning, second opinions, API-backed review |
| **Gemini CLI** | planning, review, Google-ecosystem reasoning |
| **Local (LM Studio)** | free/private review or planning when quota should be preserved |

## Step 1 — Pick a Claude model

**Use Opus when:**
- Architecture, design, or ambiguous debugging
- Root-cause analysis or investigation
- High-risk changes: auth, billing, security, migrations, data loss, production infra
- Comparing/arbitrating conflicting reviewer outputs
- User explicitly asks for deepest reasoning

**Use Sonnet when:**
- Well-scoped implementation or localized patch
- Tests, docs, boilerplate, renames, small refactors
- Executing an already-approved plan
- Speed matters and the change is low-risk

**Default phase pattern:**
```
Opus → plan/investigate   →   Sonnet → implement   →   external → review (if warranted)   →   Opus → arbitrate
```

Switch model mid-session with `/model`.

## Step 2 — Choose a route

| Route | Use when |
|---|---|
| `claude_only` | Simple task, repo exploration needed, no second opinion warranted |
| `claude_then_local_review` | LM Studio running; free/private review; preserve API quota |
| `claude_then_codex_review` | Medium/large change, correctness matters, want Codex checking |
| `claude_then_qwen_review` | Cheaper API review is enough; preserve Codex quota |
| `claude_then_gemini_review` | Want Google/Gemini perspective on the diff |
| `codex_implement_then_claude_review` | Well-scoped task; Codex makes a patch; Claude inspects and tests |
| `qwen_plan_then_claude_implement` | External planning input wanted; Claude owns all repo edits |
| `local_plan_then_claude_implement` | LM Studio running; free planning input; Claude owns all repo edits |
| `claude_then_codex_and_qwen_review` | High-risk change; want multiple reviewers |

## Step 3 — Detect and delegate

### Detect all available backends

```bash
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/detect_backends.py
```

### Auto-route (picks best available backend automatically)

```bash
# Review — tries: Codex → Kimi → Gemini → Local → OpenRouter
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/multi_agent_delegate.py \
  --target auto-review --include-git-diff --task "..." --execute

# Plan — tries: Kimi → Gemini → Local → Codex → OpenRouter
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/multi_agent_delegate.py \
  --target auto-plan --task "..." --execute

# Implement — tries: Codex → Local → Kimi → Gemini → OpenRouter
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/multi_agent_delegate.py \
  --target auto-implement --task "..." --execute
```

### Get recommendation for a role

```bash
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/detect_backends.py \
  --recommend --role review
```

### Explicit targets (force a specific backend)

```bash
# Codex
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/multi_agent_delegate.py \
  --target codex-review --include-git-diff --task "..."

# Kimi/Alibaba via OpenCode
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/multi_agent_delegate.py \
  --target qwen-review --include-git-diff --opencode-model "bailian-coding-plan/kimi-k2.5" --task "..."

# Gemini CLI
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/multi_agent_delegate.py \
  --target gemini-review --include-git-diff --task "..."

# Local LM Studio (auto-detects loaded model)
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/multi_agent_delegate.py \
  --target local-review --include-git-diff --task "..."
```

Prefer generating the prompt first (without `--execute`) and review before running.

### Available targets

| Target | Backend | What it does |
|---|---|---|
| `auto-review` | best available | detect + route to best reviewer |
| `auto-plan` | best available | detect + route to best planner |
| `auto-implement` | best available | detect + route to best implementer |
| `codex-implement` | Codex | implement a focused patch |
| `codex-review` | Codex | review diff/task |
| `qwen-plan` | OpenCode/Kimi | planning pass |
| `qwen-review` | OpenCode/Kimi | review diff/task |
| `qwen-compare` | OpenCode/Kimi | compare approaches |
| `gemini-plan` | Gemini CLI | planning pass |
| `gemini-review` | Gemini CLI | review diff/task |
| `local-review` | LM Studio | local/private review |
| `local-implement` | LM Studio | local/private implementation |
| `local-plan` | LM Studio | local/private planning |

### Check which local models are loaded

```bash
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/check_local_models.py
```

### Check which Claude model to use

```bash
python3 ~/.claude/skills/claude-orchestrated-multi-agent-skill-v2/scripts/claude_model_router.py \
  --task "Debug a production auth failure"
```

## Backend priority (auto-routing)

| Role | Priority order |
|---|---|
| review | Codex → Kimi/Alibaba → Gemini → Local → OpenRouter |
| plan | Kimi/Alibaba → Gemini → Local → Codex → OpenRouter |
| implement | Codex → Local → Kimi/Alibaba → Gemini → OpenRouter |

## Step 4 — Final judgment

External model outputs are **advice, not authority**. Claude accepts, rejects, or revises based on: tests, codebase fit, minimality, correctness, security, user intent.

Always run relevant tests after applying any patch.

## Preferred workflow

1. Restate the task briefly.
2. Run `detect_backends.py` to see what's available (or use `auto-*` to skip this).
3. Decide route and Claude model.
4. Run or suggest the external agent command (dry-run first).
5. Capture and read the output.
6. Apply only the safest, minimal changes.
7. Run relevant tests.
8. Summarize: what changed, what passed, what reviewers said, any remaining risk.
