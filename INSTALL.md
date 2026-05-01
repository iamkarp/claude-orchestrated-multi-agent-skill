# Install

## Option A: install as a Claude Code skill

Copy this folder into your Claude skills directory, for example:

```bash
mkdir -p ~/.claude/skills
cp -R claude-orchestrated-multi-agent-coding ~/.claude/skills/
```

Depending on your Claude Code setup, restart Claude Code or reload skills.

## Option B: use the helper directly

From this folder:

```bash
python scripts/multi_agent_delegate.py --target codex-review --task "Review this patch."
```

## Required tools

### Claude Code

Claude Code should be your main CLI.

```bash
claude auth status
```

### Codex

```bash
codex login
codex --version
```

### OpenCode

```bash
opencode --version
```

Configure OpenCode separately for Qwen, LM Studio, OpenRouter, or your other provider.

## Recommended usage inside Claude Code

Tell Claude Code:

```text
Use the Claude-Orchestrated Multi-Agent Coding skill. You are the orchestrator. Use Codex or OpenCode/Qwen only when useful. For risky changes, get at least one external review before finalizing.
```

Then ask for the coding task.


## Claude model routing helper

```bash
python scripts/claude_model_router.py --task "Add unit tests for CSV parsing."
python scripts/claude_model_router.py --prefer-full-ids --task "Debug a production auth issue."
```

Inside Claude Code, switch models with:

```text
/model
```

or start a new session with:

```bash
claude --model opus
claude --model sonnet
```
