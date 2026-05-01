# OpenCode Configuration Notes

Use OpenCode as the provider bridge for:

- Alibaba/Qwen
- local LM Studio
- OpenRouter
- other OpenAI-compatible APIs

Do not use OpenCode to replace Claude Code as the orchestrator unless the user explicitly wants that.

## Example conceptual opencode.json for LM Studio

Exact provider syntax may vary by OpenCode version, but the pattern is:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "lmstudio": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "LM Studio",
      "options": {
        "baseURL": "http://127.0.0.1:1234/v1",
        "apiKey": "not-needed"
      },
      "models": {
        "qwen3-coder-local": {
          "name": "qwen3-coder-local"
        }
      }
    }
  },
  "model": "lmstudio/qwen3-coder-local"
}
```

## Example conceptual opencode.json for Alibaba/Qwen

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "alibaba": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Alibaba Qwen",
      "options": {
        "baseURL": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "apiKey": "{env:DASHSCOPE_API_KEY}"
      },
      "models": {
        "qwen3-coder-plus": {
          "name": "qwen3-coder-plus"
        }
      }
    }
  },
  "model": "alibaba/qwen3-coder-plus"
}
```

If your OpenCode version rejects a key, run:

```bash
opencode --help
opencode models
```

Then adjust the provider syntax to match your installed version.
