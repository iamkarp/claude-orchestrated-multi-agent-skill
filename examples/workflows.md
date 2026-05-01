# Example Workflows

## 1. Claude implements, Codex reviews

```bash
# Claude Code makes the change first.
git diff

python scripts/multi_agent_delegate.py \
  --target codex-review \
  --include-git-diff \
  --task "Review the parser fix for correctness and missing tests."
```

## 2. Claude implements, Qwen reviews through OpenCode

```bash
python scripts/multi_agent_delegate.py \
  --target qwen-review \
  --include-git-diff \
  --opencode-model "qwen/qwen3-coder-plus" \
  --task "Review the parser fix for bugs, edge cases, and unnecessary changes."
```

## 3. Qwen plans, Claude implements

```bash
python scripts/multi_agent_delegate.py \
  --target qwen-plan \
  --opencode-model "qwen/qwen3-coder-plus" \
  --task "Plan the safest way to add OAuth refresh-token support."
```

Claude Code then reads the plan, inspects the repo, and implements only what makes sense.

## 4. Codex implements, Claude reviews

```bash
python scripts/multi_agent_delegate.py \
  --target codex-implement \
  --execute \
  --task "Add unit tests for CSV parsing edge cases."
```

Claude Code then inspects `git diff`, runs tests, and accepts/revises/reverts.

## 5. High-risk change: ask both reviewers

```bash
python scripts/multi_agent_delegate.py --target codex-review --include-git-diff \
  --task "Review this auth-related change."

python scripts/multi_agent_delegate.py --target qwen-review --include-git-diff \
  --opencode-model "qwen/qwen3-coder-plus" \
  --task "Review this auth-related change."
```


## 6. Pick Claude model before starting

```bash
python scripts/claude_model_router.py \
  --task "Refactor the auth middleware and preserve existing behavior."
```

Expected pattern:

```text
Opus plans → Sonnet implements → Codex/Qwen reviews → Opus arbitrates if reviewers disagree
```

## 7. Use full Claude model IDs

```bash
python scripts/claude_model_router.py \
  --prefer-full-ids \
  --task "Debug a production database migration failure."
```
