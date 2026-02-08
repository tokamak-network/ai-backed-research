# Model Assignments Reference

## Standard Workflow

| Role | Model | Fallback | Temp | Max Tokens | File |
|------|-------|----------|------|------------|------|
| Writer (draft, revision) | `claude-opus-4.5` | `claude-sonnet-4` (180s timeout) | 0.7 | 16384 | `agents/writer.py` |
| Writer (author response) | `claude-sonnet-4` | — | 0.7 | 4096 | `agents/writer.py` |
| Writer (citation verify) | `claude-sonnet-4` | — | 0.3 | 16384 | `agents/writer.py` |
| Moderator | `claude-opus-4.5` | — | 0.3 | 2048 | `agents/moderator.py` |
| Desk Editor | `claude-sonnet-4.5` | — | 0.1 | 512 | `agents/desk_editor.py` |
| Reviewer 1 | `claude-sonnet-4` | — | 0.3 | 4096 | `workflow/orchestrator.py` |
| Reviewer 2 | `gpt-5.2-pro` | — | 0.3 | 4096 | `api_server.py` |
| Reviewer 3 | `gpt-5.2-pro` | — | 0.3 | 4096 | `api_server.py` |
| Propose Reviewers | `claude-haiku-4.5` | static fallback | 0.7 | 2000 | `api_server.py` |

## Collaborative Workflow (additional)

| Role | Model | Fallback | Temp | Max Tokens | File |
|------|-------|----------|------|------------|------|
| Lead Author | `claude-opus-4.5` | — | 0.7 | 4096-8192 | `agents/lead_author.py` |
| Coauthors | `claude-sonnet-4` (forced) | — | 0.7 | 2048-8192 | `agents/coauthor.py` |
| Team Composer | `claude-opus-4.5` | — | 0.7 | 4096 | `agents/team_composer.py` |
| Writer Team Composer | `claude-opus-4.5` | — | 0.8 | 4096 | `agents/writer_team_composer.py` |
| Research Planner | `claude-sonnet-4` | — | 0.7 | 4096 | `agents/research_planner.py` |
| Research Notes | `claude-sonnet-4` | — | 0.5-0.7 | 1024-4096 | `agents/research_notes_agent.py` |
| Data Analysis | `claude-sonnet-4` | — | 0.5-0.8 | 2048-4096 | `agents/data_analysis_agent.py` |
| Integration Editor | `claude-sonnet-4` | — | 0.5 | 8192 | `agents/integration_editor.py` |
| Paper Writer | `claude-opus-4.5` | — | 0.7 | 3072-16384 | `agents/paper_writer_agent.py` |

## Orchestrator Instantiation

```python
# workflow/orchestrator.py
self.writer       = WriterAgent(model="claude-opus-4.5")   # draft + revisions
self.light_writer = WriterAgent(model="claude-sonnet-4")    # author response + citations
self.moderator    = ModeratorAgent(model="claude-opus-4.5")
self.desk_editor  = DeskEditorAgent(model="claude-sonnet-4.5")

# workflow/collaborative_workflow.py
for ca in self.writer_team.coauthors:
    ca.model = "claude-sonnet-4"  # forced downgrade for cost
```

## Temperature Guide

| Purpose | Temp | Rationale |
|---------|------|-----------|
| Desk screening | 0.1 | Near-deterministic pass/reject |
| Reviewing / Moderation | 0.3 | Consistent scoring and judgment |
| Citation verification | 0.3 | Accuracy-critical |
| Integration editing | 0.5 | Balanced merge quality |
| Data analysis | 0.5-0.8 | Balanced accuracy/creativity |
| Writing (prose) | 0.7 | Creative, varied prose |
| Team composition | 0.7-0.8 | Creative team design |

## Fallback Mechanisms

1. **Writer timeout fallback**: Opus → Sonnet after 180s timeout or connection error (`writer.py:_call_llm_once`)
2. **Writer auto-continuation**: On `stop_reason="max_tokens"`, retries up to 3x stitching output (`writer.py:_generate_with_fallback`)
3. **Propose-reviewers fallback**: If AI call fails, returns static default reviewer profiles (`api_server.py`)
4. **LLM_API_KEY fallback**: If provider-specific key missing, falls back to shared `LLM_API_KEY` + `LLM_BASE_URL` (`model_config.py`, `config.py`)

## Environment Variables

```bash
# Shared router key (covers all providers via LiteLLM/OpenRouter)
LLM_API_KEY=...                                # Required (shared key)
LLM_BASE_URL=...                               # Required (router endpoint)

# Provider-specific overrides (optional, take priority over LLM_API_KEY)
ANTHROPIC_API_KEY=...                          # Optional (direct Anthropic)
ANTHROPIC_BASE_URL=...                         # Optional (custom endpoint)
OPENAI_API_KEY=...                             # Optional (direct OpenAI)
OPENAI_BASE_URL=...                            # Optional (custom endpoint)
GOOGLE_API_KEY=...                             # Optional (Gemini)

DEFAULT_WRITER_MODEL=claude-opus-4-5-20251101  # Override writer model
DEFAULT_REVIEWER_MODEL=claude-sonnet-4-20250514 # Override reviewer model
```

## Cost Reference (per 1M tokens)

| Model | Input | Output |
|-------|-------|--------|
| `claude-opus-4.5` | $15.00 | $75.00 |
| `claude-sonnet-4` / `4.5` | $3.00 | $15.00 |
| `claude-haiku-4.5` | $0.80 | $4.00 |
| `gpt-4.1` | $2.00 | $8.00 |
| `gpt-4.1-mini` | $0.40 | $1.60 |
| `gpt-5.2-pro` | _(not in pricing table yet)_ | |
