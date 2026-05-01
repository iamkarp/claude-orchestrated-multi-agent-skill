# Claude-Orchestrated Multi-Agent Coding Skill

This version makes **Claude Code the main orchestrator**.

It does not put a standalone router above Claude. Instead, Claude uses this skill to decide when to call:

- Codex CLI
- OpenCode/Qwen
- OpenCode/local model

The helper script only generates or executes delegation prompts. Claude Code remains responsible for final judgment.


## v2 addition: Claude model routing

This version can also recommend whether Claude Code should use Opus or Sonnet for a task.

```bash
python scripts/claude_model_router.py --task "Debug a production auth failure"
```

Use Opus for hard planning, investigation, high-risk work, and arbitration.
Use Sonnet for focused implementation, tests, docs, and executing a clear plan.
