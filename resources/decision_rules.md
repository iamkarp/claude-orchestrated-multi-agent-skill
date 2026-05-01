# Decision Rules for Claude Code

Claude Code is the orchestrator. Use this checklist before delegating.

## Claude model routing

Before delegating or coding, decide whether Claude should be in Opus or Sonnet.

### Use Opus

Use Opus for:
- architecture
- ambiguous debugging
- root-cause analysis
- high-risk changes
- security/auth/billing/production/migrations/data loss
- reviewing a large or risky diff
- arbitrating disagreement between Codex and Qwen/OpenCode

### Use Sonnet

Use Sonnet for:
- straightforward implementation
- small localized patches
- tests
- docs
- boilerplate
- executing an Opus-approved plan
- repetitive edits

### Phase pattern

Preferred non-trivial flow:

```text
Opus plans → Sonnet implements → Codex/Qwen reviews if needed → Opus arbitrates only if risk remains
```

Use the helper:

```bash
python scripts/claude_model_router.py --task "..."
```

or with full current model IDs:

```bash
python scripts/claude_model_router.py --prefer-full-ids --task "..."
```


## Step 1: classify the task

Ask:

1. Is this ambiguous or exploratory?
2. Is this a focused implementation task?
3. Is this risky?
4. Is a second opinion worth the quota/API cost?
5. Would Alibaba/Qwen/local be enough as a reviewer?
6. Does the user explicitly ask for a specific model/tool?

## Step 2: choose route

### Route: claude_only

Use when:
- task is simple
- repo exploration matters
- no second opinion needed
- user wants speed

### Route: claude_then_codex_review

Use when:
- Claude makes a medium/large change
- correctness matters
- Codex is best as a precise reviewer
- user wants OpenAI/Codex checking

Command:

```bash
python scripts/multi_agent_delegate.py --target codex-review --include-git-diff --task "..."
```

### Route: claude_then_qwen_review

Use when:
- Qwen/Alibaba should be the third auth/API reviewer
- cheaper review is enough
- Codex quota should be preserved
- user asks for Alibaba/Qwen

Command:

```bash
python scripts/multi_agent_delegate.py --target qwen-review --include-git-diff --opencode-model "qwen/qwen3-coder-plus" --task "..."
```

### Route: codex_implement_then_claude_review

Use when:
- task is well-scoped
- Codex can make a PR-like patch
- Claude will inspect and test afterward

Command:

```bash
python scripts/multi_agent_delegate.py --target codex-implement --task "..."
```

### Route: qwen_plan_then_claude_implement

Use when:
- user wants Alibaba/Qwen input first
- task needs architecture planning
- Claude should own the actual repo edits

Command:

```bash
python scripts/multi_agent_delegate.py --target qwen-plan --opencode-model "qwen/qwen3-coder-plus" --task "..."
```

### Route: claude_then_codex_and_qwen_review

Use when:
- high risk
- core logic
- auth/billing/security/data/prod/migration
- user explicitly wants multiple opinions

Commands:

```bash
python scripts/multi_agent_delegate.py --target codex-review --include-git-diff --task "..."
python scripts/multi_agent_delegate.py --target qwen-review --include-git-diff --opencode-model "qwen/qwen3-coder-plus" --task "..."
```

## Step 3: final arbitration

Claude should compare reviewer outputs and decide:

- accept
- revise
- reject
- ask one agent for a narrower follow-up
- run more tests

External agents advise. Claude decides.
