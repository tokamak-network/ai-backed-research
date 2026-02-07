# Hybrid Model Strategy (Option D) + 5-Topic Benchmark

## Code Changes
- [x] Override coauthor models to Sonnet in `collaborative_workflow.py`
  - Set `ca.model = "claude-sonnet-4"` for all coauthors before phase construction
  - Coauthors handle: research, plan feedback, section review (auxiliary tasks)
- [x] Add `light_writer` (Sonnet) in `orchestrator.py`
  - `self.light_writer = WriterAgent(model="claude-sonnet-4")` for author response + citation verification
  - Swapped `write_author_response()` calls in both `run()` and `_resume_workflow()`
  - Swapped `verify_citations()` call in `run()`
- [x] Preserved Opus for quality-critical tasks:
  - Lead Author (all operations)
  - Writer (initial draft, revisions)
  - Moderator (accept/reject decisions)

## Model Assignment Summary

| Agent | Task | Model |
|-------|------|-------|
| Lead Author | research notes, gap analysis, structure planning, section writing | Opus 4.5 |
| Coauthors | research, plan feedback, section review | **Sonnet 4** |
| Writer | initial draft, manuscript revisions | Opus 4.5 |
| Writer (light) | author response, citation verification | **Sonnet 4** |
| Moderator | accept/reject decisions | Opus 4.5 |
| Desk Editor | screening | Sonnet 4.5 |

## 5-Topic Benchmark
- [ ] Submit 5 topics and monitor results
- [ ] Collect final scores, pass/fail, duration, token usage
- [ ] Compare results across fields

| # | Field | Topic | Length | Mode |
|---|-------|-------|--------|------|
| 1 | Humanities / Philosophy | Wittgenstein's Language Games and Modern AI | short | collaborative |
| 2 | Natural Sciences / Physics | Dark Matter Detection Methods: Current State and Challenges | full | collaborative |
| 3 | Social Sciences / Economics | Central Bank Digital Currencies: Economic Implications | full | collaborative |
| 4 | Engineering / Renewable Energy | Perovskite Solar Cells: Stability Challenges and Solutions | full | collaborative |
| 5 | Computer Science / AI | Retrieval-Augmented Generation: Architectures and Limitations | full | collaborative |

## Benchmark Results
_(to be filled after completion)_

---

## Parallel Workers + GPT Reviewer Distribution + Category Badge

### Changes Applied
- [x] `api_server.py`: 3 concurrent job workers (`MAX_CONCURRENT_WORKERS = 3`)
- [x] `api_server.py`: Rate limit reduced 1800s → 60s for parallel submission
- [x] `api_server.py`: Reviewer cross-assignment: Claude Sonnet 4, GPT-4.1, GPT-4.1-mini
- [x] `research_cli/workflow/orchestrator.py`: Provider branching in `generate_review()` (OpenAI/Gemini/Claude)
- [x] `research_cli/llm/openai.py`: Added `base_url` parameter for OpenRouter support
- [x] `research_cli/config.py`: Added `OPENAI_BASE_URL` env var + OpenRouter fallback (reuse Anthropic key)
- [x] `web/index.html`: Category display changed from `meta-category` to `category-tag` badge
- [x] `web/styles/main.css`: Added `.category-tag` Carbon-style badge

### Reviewer Model Assignment
| Reviewer | Provider | Model |
|----------|----------|-------|
| Reviewer 1 | anthropic | claude-sonnet-4 |
| Reviewer 2 | openai | gpt-4.1 |
| Reviewer 3 | openai | gpt-4.1-mini |

### Connection Error → Interrupted (Resumable)
- [x] `api_server.py` `run_workflow_background()`: exception + checkpoint exists → status "interrupted" (not "failed")
- [x] `api_server.py` `resume_workflow_background()`: same logic — checkpoint preserved → "interrupted"
- [x] `web/research-queue.html`: "failed" (error) stays in main list, only "rejected" (score-based) in Rejected section
- [x] `web/research-queue.html`: "failed" workflows show activity log + delete button
- [x] `web/research-queue.html`: Stats now show error count separately

### Verification
- [ ] Set `OPENAI_API_KEY` / `OPENAI_BASE_URL` (or let OpenRouter fallback work)
- [ ] Restart server
- [ ] Submit 2-3 workflows simultaneously → verify parallel execution
- [ ] Check `workflow_complete.json` for GPT reviewer model fields
- [ ] Verify category badge on index.html
- [ ] Simulate connection error mid-workflow → verify "interrupted" status with Resume button

---

## Audience Level (Target Audience) Feature

### Changes Applied
- [x] `api_server.py`: `StartWorkflowRequest.audience_level` field (default: "professional")
- [x] `api_server.py`: `run_workflow_background()` passes `audience_level` to orchestrator
- [x] `api_server.py`: `_build_project_summary()` returns `audience_level` from workflow data
- [x] `research_cli/workflow/orchestrator.py`: `__init__` stores `self.audience_level`
- [x] `research_cli/workflow/orchestrator.py`: `generate_review()` adds audience-level evaluation criteria
- [x] `research_cli/workflow/orchestrator.py`: `run_review_round()` passes `audience_level` through
- [x] `research_cli/workflow/orchestrator.py`: `_finalize_workflow()` saves `audience_level` in workflow_complete.json
- [x] `research_cli/workflow/orchestrator.py`: `_save_checkpoint()` includes `audience_level`
- [x] `research_cli/workflow/orchestrator.py`: `resume_from_checkpoint()` restores `audience_level`
- [x] `research_cli/agents/writer.py`: `write_manuscript()` adjusts system prompt per audience level
- [x] `research_cli/agents/writer.py`: `revise_manuscript()` includes audience-level revision guidance
- [x] `web/ask-topic.html`: 3-column audience selector (Beginner/Intermediate/Professional)
- [x] `web/ask-topic.html`: `startWorkflow()` sends `audience_level` parameter
- [x] `web/index.html`: Audience badge (Beginner-Friendly green / Intermediate blue) on cards
- [x] `web/article.html`: Audience metadata in article header

### Verification
- [ ] ask-topic.html: beginner 선택 후 제출 → 서버 로그에 audience_level 전달 확인
- [ ] workflow_complete.json에 `audience_level: "beginner"` 저장 확인
- [ ] 원고 문체가 비전문가 대상인지 확인 (용어 설명, 비유 등)
- [ ] 리뷰어 피드백에 독자층 기준 반영 확인
- [ ] index.html에 "Beginner-Friendly" 배지 표시 확인
- [ ] article.html 메타데이터에 독자층 표시 확인

---

## Token Tracking Bug Fix + ask-topic.html UX Redesign

### Part 1: Token Tracking — Fixed
- [x] `research_cli/agents/writer.py`: Added `_last_*_tokens` attributes, token saving in `_generate_with_fallback()`, `get_last_token_usage()` method
- [x] `research_cli/performance.py`: Added cumulative fields (`_citation_tokens`, `_revision_tokens`, `_author_response_tokens`, `_desk_editor_tokens`, `_moderator_tokens`), per-model tracking (`_tokens_by_model`), model-based cost calculation (`MODEL_PRICING`), new recording methods, extended `PerformanceMetrics` dataclass + `to_dict()`
- [x] `research_cli/workflow/orchestrator.py`: Token recording after every writer/moderator/desk_editor call in `run()`, `_resume_workflow()`, and `_generate_initial_manuscript()`

### Part 2: ask-topic.html UX — Fixed
- [x] Moved Article Length + Workflow Mode from Step 3 to Step 1 (after Audience Level)
- [x] Smart defaults: beginner/intermediate → short/standard; professional → full/collaborative
- [x] Standard mode hides Co-Authors section; collaborative shows it
- [x] Reviewer count limited to 3 (matching backend `pool[:3]`)
- [x] Fixed `selectResearchType()` scoping bug (was deselecting all selectors)
- [x] Team size estimate now uses actual reviewer count (3) and mode-aware author count

### Verification
- [ ] Python syntax checks: all 3 files pass `ast.parse()`
- [ ] Integration test: `PerformanceTracker` accumulates tokens correctly (29500 total)
- [ ] ask-topic.html: beginner → auto-selects short/standard
- [ ] ask-topic.html: professional → auto-selects full/collaborative
- [ ] ask-topic.html: standard mode → co-author section hidden
- [ ] ask-topic.html: only 3 reviewers displayed
- [ ] workflow_complete.json: `initial_draft_tokens > 0`, `revision_tokens > 0`, `tokens_by_model` populated
