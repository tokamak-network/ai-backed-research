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

---

## API Key Application System + UI/UX Improvements

### Part 1: index.html Category Tag Position — Done
- [x] `web/styles/main.css`: Added `.card-badges-row` flex container, removed `margin-bottom` from `.card-badge`
- [x] `web/index.html`: Moved category tag + audience badge into `.card-badges-row` alongside New/Featured badge
- [x] Removed trailing `meta-divider` from `categoryHtml`

### Part 2: Moderator Decision Rationale in review.html — Done
- [x] `web/review.html`: `renderRound()` now shows recommendation, key_strengths/weaknesses (side-by-side grid), required_changes, and meta_review (collapsible)
- [x] All fields conditional — gracefully handles missing data

### Part 3: Author Response Display Fix — Done
- [x] `web/review.html`: Removed `!isLastRound` gate so all rounds show previous author response
- [x] Added display of last round's own `author_response` when it exists

### Part 4: API Key Application System — Done
- [x] **4a: `research_cli/db.py`** — SQLite module with 5 tables (researchers, applications, api_keys, key_usage, workflow_ownership), indexes, full CRUD helpers
- [x] **4b: `api_server.py`** — 11 new endpoints: apply, status check, my-profile, my-workflows, my-quota, admin applications CRUD, quota/revoke management. SQLite key verification alongside legacy. Quota enforcement on start-workflow. Ownership tracking.
- [x] **4c: `web/apply.html`** — Researcher application form with tags input, sample works (add/remove), IP rate limiting, status check section
- [x] **4d: `web/admin.html`** — Added tabbed interface (API Keys | Applications). Applications tab shows full detail, approve/reject with notes, generated key display
- [x] **4e: `scripts/migrate_keys.py`** — Migration script: reads keys.json → inserts into SQLite → renames to .backup
- [x] **4f: `web/my-research.html`** — Researcher dashboard: quota circle, profile summary, workflow list with review links
- [x] **4g: Quota + Ownership** — Daily quota check (10/day default) in start-workflow, usage recording, ownership tracking

### New API Endpoints
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | /api/apply | Public (IP rate limited) | Submit application |
| GET | /api/application-status/{email} | Public | Check status |
| GET | /api/my-profile | API Key | Researcher profile |
| GET | /api/my-workflows | API Key | Owned workflows |
| GET | /api/my-quota | API Key | Daily quota |
| GET | /api/admin/applications | Admin | List applications |
| GET | /api/admin/applications/{id} | Admin | Application detail |
| POST | /api/admin/applications/{id}/approve | Admin | Approve + generate key |
| POST | /api/admin/applications/{id}/reject | Admin | Reject with reason |
| PUT | /api/admin/keys/{prefix}/quota | Admin | Update quota |
| POST | /api/admin/keys/{prefix}/revoke | Admin | Revoke key |

### Files Changed
| File | Change |
|------|--------|
| `web/index.html` | Badge row layout, nav links for Apply/My Research |
| `web/styles/main.css` | `.card-badges-row` style, `.card-badge` margin fix |
| `web/review.html` | Moderator rationale display, author response fix |
| `api_server.py` | DB init, SQLite key auth, 11 new endpoints, quota enforcement |
| `research_cli/db.py` | NEW — SQLite module |
| `web/apply.html` | NEW — Application form |
| `web/admin.html` | Tabbed UI with Applications tab |
| `web/my-research.html` | NEW — Researcher dashboard |
| `scripts/migrate_keys.py` | NEW — Migration script |

### Duration Fix (bonus)
- [x] `api_server.py` `_build_project_summary()`: Use wall-clock time (workflow_start → workflow_end) instead of sum of round durations

### Dark Mode Fix (review.html moderator panel)
- [x] Replaced hardcoded `color: #161616` → `var(--text-primary, #161616)`
- [x] Replaced `background: rgba(255,255,255,0.5)` → `var(--background)`
- [x] Replaced `border: rgba(0,0,0,0.08)` → `var(--border-subtle)`

### Verification
- [x] Python syntax: all 3 Python files pass `ast.parse()`
- [x] DB test: create_researcher → approve → check_quota → record_usage all work
- [x] Full E2E test: 11 endpoints tested with FastAPI TestClient - all pass
- [x] Duration fix verified: wall-clock shows 528s vs old 289s for resumed workflow
- [ ] Visual: index.html badges in same row (needs server restart)
- [ ] Visual: review.html moderator rationale sections visible (needs server restart)
- [ ] Functional: apply.html → submit → admin.html approve → key displayed (needs server restart)
- [ ] Functional: my-research.html → enter key → see quota + workflows (needs server restart)

---

## Manuscript Truncation Prevention + Incomplete Manuscript Detection

### Part A: LLMResponse stop_reason — Done
- [x] `research_cli/llm/base.py`: Added `stop_reason: Optional[str]` field to `LLMResponse`
- [x] `research_cli/llm/claude.py`: Capture `stop_reason` in `generate()` and `generate_streaming()`
- [x] `research_cli/llm/openai.py`: Capture `finish_reason` in `generate()`
- [x] `research_cli/llm/gemini.py`: Capture `finish_reason` from candidates in `generate()`

### Part B: Writer Auto-Continuation — Done
- [x] `research_cli/agents/writer.py`: Extracted `_call_llm_once()` from `_generate_with_fallback()`
- [x] `research_cli/agents/writer.py`: `_generate_with_fallback()` now detects `stop_reason="max_tokens"/"length"` and auto-continues up to 3 times
- [x] Continuation stitches output seamlessly using last 500 chars as context
- [x] Cumulative token tracking across continuations

### Part C: Manuscript Completeness Validation — Done
- [x] `research_cli/agents/writer.py`: Added `validate_manuscript_completeness()` function
  - Detects: ends_mid_sentence, missing_references, missing_conclusion
- [x] `research_cli/workflow/orchestrator.py`: Imported `validate_manuscript_completeness`
- [x] `research_cli/workflow/orchestrator.py`: Completeness check after initial manuscript generation
- [x] `research_cli/workflow/orchestrator.py`: Completeness check before moderator decision in `run()` and `_resume_workflow()`
- [x] Completeness warning passed to moderator as `completeness_warning` parameter

### Part D: Moderator Completeness Enforcement — Done
- [x] `research_cli/agents/moderator.py`: Added `completeness_warning` parameter to `make_decision()`
- [x] `research_cli/agents/moderator.py`: System prompt includes CRITICAL COMPLETENESS CHECK instructions
- [x] `research_cli/agents/moderator.py`: Decision prompt injects ⚠ completeness warning when issues detected

### Files Changed
| File | Change |
|------|--------|
| `research_cli/llm/base.py` | `stop_reason` field on `LLMResponse` |
| `research_cli/llm/claude.py` | `stop_reason` capture (2 methods) |
| `research_cli/llm/openai.py` | `stop_reason` capture |
| `research_cli/llm/gemini.py` | `stop_reason` capture |
| `research_cli/agents/writer.py` | Auto-continuation loop + `validate_manuscript_completeness()` |
| `research_cli/agents/moderator.py` | Completeness check in prompts + `completeness_warning` param |
| `research_cli/workflow/orchestrator.py` | Completeness validation + warning plumbing to moderator |

### Verification
- [x] All 7 files pass `ast.parse()` syntax check
- [x] `validate_manuscript_completeness()` unit tests pass (truncated → issues detected, complete → clean)
- [x] `LLMResponse(stop_reason="max_tokens")` field works correctly
- [x] Orchestrator imports resolve cleanly
- [ ] E2E: Long topic → auto-continuation triggers → manuscript not truncated
- [ ] E2E: Truncated manuscript → moderator issues MAJOR_REVISION (not ACCEPT)

---

## Central Model Configuration + Fallback Chain + Gemini Removal

### Part 1: `config/models.json` — Done
- [x] Created `config/models.json` with role-based model assignments, fallback chains, provider config, pricing
- [x] 14 roles defined: writer, writer_light, moderator, reviewer, desk_editor, lead_author, coauthor, team_composer, integration_editor, research_planner, research_notes, paper_writer, propose_reviewers

### Part 2: `research_cli/model_config.py` — Done
- [x] JSON loader with caching
- [x] `get_role_config(role)` — returns RoleConfig dataclass
- [x] `create_llm_for_role(role)` — instantiates primary LLM, falls back if API key missing
- [x] `create_fallback_llm_for_role(role)` — for agents with explicit fallback (WriterAgent)
- [x] `get_pricing(model)` / `get_all_pricing()` — pricing from JSON
- [x] `get_reviewer_models()` — reviewer model cycle for cross-provider distribution
- [x] `_create_llm(provider, model)` — low-level factory used by orchestrator

### Part 3: Agent Refactoring (12 files) — Done
- [x] `agents/writer.py` — role="writer", fallback via create_fallback_llm_for_role
- [x] `agents/moderator.py` — role="moderator"
- [x] `agents/desk_editor.py` — role="desk_editor"
- [x] `agents/lead_author.py` — role="lead_author"
- [x] `agents/coauthor.py` — role="coauthor"
- [x] `agents/team_composer.py` — role="team_composer"
- [x] `agents/integration_editor.py` — role="integration_editor"
- [x] `agents/research_planner.py` — role="research_planner"
- [x] `agents/research_notes_agent.py` — role="research_notes"
- [x] `agents/paper_writer_agent.py` — role="paper_writer"
- [x] `agents/writer_team_composer.py` — role="team_composer"
- [x] `agents/data_analysis_agent.py` — role="research_notes"

### Part 4: Orchestrator + API Server — Done
- [x] `workflow/orchestrator.py` — role-based agent init, _create_llm for reviews, GeminiLLM removed
- [x] `workflow/collaborative_workflow.py` — removed hardcoded coauthor model override
- [x] `api_server.py` — reviewer models from config, pricing from config, propose_reviewers uses create_llm_for_role

### Part 5: Gemini Removal — Done
- [x] `GeminiLLM` import removed from orchestrator.py
- [x] No Gemini models in models.json
- [x] `llm/gemini.py` kept for future use

### Part 6: Performance Pricing Integration — Done
- [x] `performance.py` — MODEL_PRICING loaded from models.json via get_all_pricing()

### Model Assignment Summary

| Role | Primary | Fallback 1 | Fallback 2 |
|------|---------|------------|------------|
| writer | claude-opus-4.5 (anthropic) | gpt-5.2-pro (openai) | qwen3-235b (openai) |
| writer_light | claude-sonnet-4.5 (anthropic) | gpt-5.2-pro (openai) | — |
| moderator | claude-opus-4.5 (anthropic) | gpt-5.2-pro (openai) | — |
| reviewer | gpt-5.2-pro (openai) | qwen3-235b (openai) | claude-sonnet-4.5 (anthropic) |
| desk_editor | claude-haiku-4.5 (anthropic) | claude-sonnet-4.5 (anthropic) | — |
| lead_author | claude-opus-4.5 (anthropic) | gpt-5.2-pro (openai) | — |
| coauthor | gpt-5.2-pro (openai) | qwen3-235b (openai) | claude-sonnet-4.5 (anthropic) |
| team_composer | claude-opus-4.5 (anthropic) | gpt-5.2-pro (openai) | — |
| integration_editor | claude-sonnet-4.5 (anthropic) | gpt-5.2-pro (openai) | — |
| paper_writer | claude-opus-4.5 (anthropic) | gpt-5.2-pro (openai) | — |

### Additional Fixes
- [x] Category detection: added 'health', 'smoke', 'maternal', 'nutrition', etc. to public_health keywords
- [x] Reclassified 17 incomplete articles as rejected with reasons in workflow_complete.json

### Verification
- [x] All 18 files pass `ast.parse()` syntax check (0 FAIL)
- [x] `config/models.json` valid JSON
- [ ] `python scripts/test_api_connections.py` — test all model+provider connections
- [ ] E2E: Submit workflow → verify correct models used per role
- [ ] E2E: Primary API key missing → fallback model used

---

## Railway 배포 준비 (Step 1 — 코드 정리)

### Part 1: Dockerfile + requirements.txt — Done
- [x] `requirements.txt` — pyproject.toml 기반 + fastapi/uvicorn/gunicorn (google-generativeai 제거)
- [x] `Dockerfile` — python:3.11-slim, gunicorn+UvicornWorker, `--workers 1`, `--timeout 900`
- [x] `railway.toml` — dockerfile builder, health check `/api/health`
- [x] `.dockerignore` — .git, .env, venv, __pycache__, data/, results/

### Part 2: keys.json → SQLite 통합 — Done
- [x] `api_server.py` — `KEYS_FILE`, `load_keys_from_file()`, `save_keys_to_file()`, `sync_keys_from_file()` 제거
- [x] `api_server.py` — Admin key endpoints (`GET/POST/DELETE /api/admin/keys`) → `appdb` 사용
- [x] `research_cli/db.py` — `create_api_key_direct()` 추가

### Part 3: 프로덕션 서버 설정 — Done
- [x] `api_server.py` — `__main__` 블록에 `PORT` env var 사용
- [x] Health check endpoint 이미 존재 (`/api/health`)

### Part 4: pyproject.toml + .env.example — Done
- [x] `pyproject.toml` — fastapi, uvicorn[standard], gunicorn 추가; google-generativeai 제거
- [x] `.env.example` — `RESEARCH_API_KEYS`, `RESEARCH_ADMIN_KEY`, `PORT` 추가

### Part 5: Gemini import → lazy — Done
- [x] `research_cli/llm/__init__.py` — `GeminiLLM` import를 `try/except ImportError`로 변경

### Bug Fix: writer.py f-string syntax — Done
- [x] `research_cli/agents/writer.py` — Python 3.11 호환: f-string 내 `\n` → 변수로 추출

### Files Changed
| File | Change |
|------|--------|
| `Dockerfile` | **NEW** — python:3.11-slim, gunicorn |
| `requirements.txt` | **NEW** — pip dependencies |
| `railway.toml` | **NEW** — Railway config |
| `.dockerignore` | **NEW** — build exclusions |
| `api_server.py` | keys.json 제거, admin endpoints → SQLite, PORT env var |
| `research_cli/db.py` | `create_api_key_direct()` 추가 |
| `research_cli/llm/__init__.py` | Gemini lazy import |
| `research_cli/agents/writer.py` | f-string Py3.11 fix |
| `pyproject.toml` | fastapi/uvicorn/gunicorn 추가, gemini 제거 |
| `.env.example` | Auth/Server env vars 추가 |

### Verification
- [x] Python syntax: 모든 파일 `ast.parse()` 통과
- [x] `docker build` 성공
- [x] Container 시작: gunicorn + uvicorn worker 부팅 정상
- [x] `curl /api/health` → `{"status":"ok","service":"AI-Backed Research API"}`
- [x] `curl /` → HTTP 200 (index.html)

---

## Report Download (MD) + Admin External Report Upload

### Part A: Report Download
- [x] **A1**: `GET /api/projects/{project_id}/report` — combines manuscript + full peer review into single .md download
- [x] **A2**: Download button on `web/article.html` — Carbon-styled, in article-meta section
- [x] **A3**: Download button on `web/review.html` — in version-tabs next to "Read Article"

### Part B: Admin Upload
- [x] **B1**: `POST /api/admin/upload-report` — admin-only, creates project from external .md file
- [x] **B2**: Upload Report UI on `web/research-queue.html` — admin-only button + modal with title/topic/type/category/file drop

### Files Changed
| File | Change |
|------|--------|
| `api_server.py` | `Response` import, `GET /api/projects/{id}/report`, `POST /api/admin/upload-report` |
| `web/article.html` | Download button CSS + button in header + `downloadReport()` JS |
| `web/review.html` | Download button CSS + button in version-tabs + `downloadReport()` JS |
| `web/research-queue.html` | Upload modal CSS + admin upload button + modal HTML + upload JS functions |

### Verification
- [x] Python syntax check passes
- [x] Both new routes registered in FastAPI
- [x] Report download tested: 109K chars, all sections present (manuscript + 3 rounds reviews + author responses)
- [x] Upload tested: creates project dir + manuscript_final_v1.md + workflow_complete.json with correct metadata
- [ ] Visual: article.html download button renders correctly (needs server restart)
- [ ] Visual: review.html download button renders correctly (needs server restart)
- [ ] Visual: research-queue.html upload modal renders correctly with admin key (needs server restart)
- [ ] E2E: upload report → appears in project list → renders in article.html

---

## External Manuscript Submission + AI Peer Review Cycle

### Summary
Submit → AI Review → Decision → Revise & Resubmit → Re-review (max 3 rounds)

### Part 1: DB Schema (`research_cli/db.py`) — Done
- [x] `submissions` table: id, researcher_id, api_key, title, category, status, round tracking, deadlines
- [x] `submission_rounds` table: per-round reviews, scores, moderator decisions
- [x] 6 CRUD functions: create_submission, get_submission, get_submissions_by_key, update_submission_status, save_submission_round, expire_overdue_submissions
- [x] Indexes: submissions(api_key), submissions(status), submission_rounds(submission_id)

### Part 2: API Endpoints (`api_server.py`) — Done
- [x] `POST /api/submit-manuscript` — submit manuscript for AI peer review
- [x] `GET /api/submission/{id}` — get submission status + all round data
- [x] `POST /api/submission/{id}/revise` — resubmit revised manuscript
- [x] `GET /api/my-submissions` — list all submissions for authenticated user
- [x] `run_submission_review_background()` — desk screen + reviewer generation + review + moderator decision
- [x] `_check_expired_submission()` — check-on-access deadline enforcement
- [x] Dead code removed: `review_requested` field from SubmitArticleRequest

### Part 3: Web UI (`web/submit.html`) — Done
- [x] Multi-step wizard: API key → metadata → content → deadline → submit
- [x] File upload (drag & drop) + Markdown textarea
- [x] Live preview (marked.js + KaTeX)
- [x] Word count + validation
- [x] Deadline selector (clickable cards: 24h / 72h / 7d)
- [x] Status polling (3s interval) with round-by-round review display
- [x] Revision form with re-upload when awaiting_revision
- [x] URL parameter support (`?id=xxx`) for viewing existing submissions

### Part 4: My Research Update (`web/my-research.html`) — Done
- [x] "My Submissions" section below "My Workflows"
- [x] Submission cards with status badges, round count, deadline countdown
- [x] Click through to `submit.html?id=xxx`

### Part 5: Navigation — Done
- [x] "Submit" link added to `web/index.html` nav bar
- [x] Dockerfile updated with `results/submissions` directory

### State Machine
```
pending → desk_review → reviewing → accepted (publish)
                           ├→ rejected
                           └→ awaiting_revision → reviewing (resubmit)
                                    └→ expired (deadline exceeded)
```

### New API Endpoints
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | /api/submit-manuscript | API Key | Submit manuscript for review |
| GET | /api/submission/{id} | API Key (owner) | Get submission details + rounds |
| POST | /api/submission/{id}/revise | API Key (owner) | Resubmit revised manuscript |
| GET | /api/my-submissions | API Key | List all submissions |

### Files Changed
| File | Change |
|------|--------|
| `research_cli/db.py` | 2 new tables + 6 CRUD functions + 3 indexes |
| `api_server.py` | 4 endpoints + background function + dead code removal + timedelta import |
| `web/submit.html` | **NEW** — manuscript submission wizard |
| `web/my-research.html` | Submissions section + renderSubmissions() |
| `web/index.html` | Submit nav link |
| `Dockerfile` | results/submissions directory |

### Verification
- [x] Python syntax: db.py + api_server.py pass `ast.parse()`
- [x] DB integration test: create → get → update → save_round → expire → list all pass
- [x] All new imports verified
- [x] submit.html: all key UI elements present
- [x] my-research.html: submissions section + API call + render function present
- [x] index.html: Submit nav link present
- [ ] E2E: POST /api/submit-manuscript → desk screen + round 1 → awaiting_revision
- [ ] E2E: GET /api/submission/{id} → review feedback visible
- [ ] E2E: POST /api/submission/{id}/revise → round 2 → decision
- [ ] E2E: Deadline expiry → status auto-expires on access

---

## Workflow Fault Tolerance (JSON Repair + Initial Checkpoint + Partial Failure)

### Part A: JSON Parsing Recovery — Done
- [x] `research_cli/utils/json_repair.py` — **NEW**: `repair_json()` utility
  - Strategy 1: Direct `json.loads()`
  - Strategy 2: Extract ```json code block
  - Strategy 3: First `{` to last `}` extraction
  - Strategy 4: Truncated JSON repair (close open quotes/brackets/braces)
  - Strategy 5: Aggressive repair (binary search for longest parseable prefix)
- [x] `research_cli/utils/__init__.py` — **NEW**: empty init
- [x] Applied `repair_json()` to all agent files (12 JSON parsing sites):
  - `agents/coauthor.py` (3 sites)
  - `agents/lead_author.py` (4 sites)
  - `agents/research_notes_agent.py` (2 sites)
  - `agents/paper_writer_agent.py` (1 site)
  - `agents/research_planner.py` (1 site)
  - `agents/writer_team_composer.py` (1 site)
- [x] Applied `repair_json()` to `workflow/orchestrator.py` `generate_review()`

### Part B: Initial Checkpoint — Done
- [x] `workflow/orchestrator.py` `_run_impl()`: Save checkpoint at round 0 after manuscript_v1.md
- [x] `workflow/orchestrator.py` `_resume_workflow_impl()`: Handle empty `all_rounds` (round 0 checkpoint)

### Part C: Partial Failure Tolerance — Done
- [x] `workflow/collaborative_research.py` `_conduct_parallel_research()`:
  - `asyncio.gather(return_exceptions=True)` + skip failed tasks
  - Raise only if ALL tasks fail
- [x] `workflow/orchestrator.py` `run_review_round()`:
  - `asyncio.gather(return_exceptions=True)` + `_build_on_leave_review()` for failures
  - `overall_average` excludes `on_leave` reviewers
  - Score table shows "on leave" for failed reviewers
  - Raise only if ALL reviewers fail
- [x] `_detect_reviewer_outliers()`: Excludes `on_leave` reviewers
- [x] `web/review.html`: `renderReview()` shows "On Leave" card for failed reviewers
  - Carbon-style CSS: dashed border, 60% opacity, italic message

### Files Changed
| File | Change |
|------|--------|
| `research_cli/utils/json_repair.py` | **NEW** — `repair_json()` utility |
| `research_cli/utils/__init__.py` | **NEW** — empty init |
| `research_cli/agents/coauthor.py` | `repair_json()` (3 sites) |
| `research_cli/agents/lead_author.py` | `repair_json()` (4 sites) |
| `research_cli/agents/research_notes_agent.py` | `repair_json()` (2 sites) |
| `research_cli/agents/paper_writer_agent.py` | `repair_json()` (1 site) |
| `research_cli/agents/research_planner.py` | `repair_json()` (1 site) |
| `research_cli/agents/writer_team_composer.py` | `repair_json()` (1 site) |
| `research_cli/workflow/orchestrator.py` | Round 0 checkpoint + reviewer failure tolerance + `repair_json()` |
| `research_cli/workflow/collaborative_research.py` | Co-author failure tolerance |
| `web/review.html` | On-leave reviewer display + CSS |
| `tests/test_json_repair.py` | **NEW** — 18 unit tests |

### Verification
- [x] `repair_json()`: 18 unit tests pass (truncated JSON, code blocks, edge cases)
- [x] All 10 modified Python files pass `ast.parse()` syntax check
- [x] All key functions/classes present in orchestrator.py
- [ ] E2E: Co-author failure → remaining co-authors continue → workflow completes
- [ ] E2E: Reviewer failure → "On Leave" card in review.html → score excludes failed
- [ ] E2E: Interrupt during review → resume from checkpoint (round 0) → continues from round 1
- [ ] E2E: Truncated JSON from LLM → `repair_json()` recovers → no crash

---

## Stitch Design System Site-Wide Application

### Phase 1: Design System (`web/styles/main.css`) — Done
- [x] Added `--shadow-sharp` / `--shadow-sharp-hover` CSS variables (light + dark)
- [x] `.grid-lines` background pattern (light + dark)
- [x] Custom scrollbar styling
- [x] `.article-card` sharp shadow + hover amber left bar (`::before`)
- [x] `.nav-link` underline hover effect
- [x] `.card-quote` serif italic class
- [x] `.stats-strip` / `.stat-cell` / `.stat-value-large` / `.stat-label-mono` components
- [x] `.content-section`, `.form-section`, `.auth-section` auto sharp shadow
- [x] Dashboard sidebar layout (`.dashboard-layout`, `.dashboard-sidebar`, `.sidebar-nav-link`)
- [x] `.decision-notification` border-l-4 variants (accept/major/minor/reject)
- [x] `.score-display` / `.score-number` / `.score-total` components
- [x] `.hero-accent`, `.hero-badge`, `.hero-cta-group`, `.btn-sharp`
- [x] `.section-header-row`, `.sort-select`, `.card-score-split`
- [x] `.footer-grid-4`, `.footer-brand` — 4-column footer layout
- [x] Responsive breakpoints for stats strip, hero CTA, footer

### Phase 2: Homepage (`web/index.html`) — Done
- [x] Hero: grid-lines background, volume badge (dynamic), serif italic accent subtitle
- [x] Hero: dual CTA buttons (Browse Latest Issue + Submit Research)
- [x] Stats strip: 4 metrics (Published Papers, Avg Score, Avg Rounds, Review Process)
- [x] Section header with Sort By dropdown (Date/Score/Rounds)
- [x] Card: mono date, score-split display, sharp shadow + hover bar
- [x] Footer: 4-column grid (Brand + Platform + Resources + Connect)
- [x] Dynamic stats from API data

### Phase 3: Dashboard (`web/my-research.html`) — Done
- [x] Full Stitch-2 sidebar layout (`dashboard-layout`)
- [x] Sidebar: Scholarly. logo, nav links (My Submissions, Queue, New Research, Home)
- [x] Sidebar footer: API key input + theme toggle
- [x] Mobile responsive: sidebar hidden, mobile header shown
- [x] Top bar with welcome message + New Research CTA
- [x] 3-column stats row (Total Workflows, Success Rate, Avg Score)
- [x] Decision notifications (border-left-4 colored)
- [x] Quota circle SVG display
- [x] Profile grid
- [x] Workflow cards with status badges + hover effects
- [x] Submissions list with deadline countdown

### Phase 4: Content Pages — Done
- [x] `about.html`: grid-lines hero section with serif title
- [x] `ask-topic.html`: step-badge → mono font, border-radius 0
- [x] `submit.html`: step-badge → mono font, border-radius 0
- [x] `apply.html`: form-section sharp shadow auto-applied via main.css

### Phase 5: Data Pages — Done
- [x] `research-queue.html`: stat-card + workflow-card sharp shadow, hover effects
- [x] `review.html`: review-card + chart-container sharp shadow
- [x] `admin.html`: admin-section sharp shadow
- [x] `api-docs.html`: docs-section + endpoint sharp shadow

### Phase 6: Final Pages — Done
- [x] `article.html`: minimal changes (own design preserved)
- [x] `blog-reader.html`: minimal changes (already uses main.css)

### Files Changed
| File | Change |
|------|--------|
| `web/styles/main.css` | +200 lines: design tokens, component classes, responsive |
| `web/index.html` | Hero redesign, stats strip, sort controls, card/footer improvements |
| `web/my-research.html` | Full rewrite → Stitch-2 sidebar dashboard layout |
| `web/about.html` | Grid-lines hero section |
| `web/ask-topic.html` | Step-badge mono font |
| `web/submit.html` | Step-badge mono font |
| `web/research-queue.html` | Stat/workflow card sharp shadow |
| `web/review.html` | Review card + chart sharp shadow |
| `web/admin.html` | Admin section sharp shadow |
| `web/api-docs.html` | Docs section + endpoint sharp shadow |

### Not Changed (per plan)
- Tailwind: no conversion (plain CSS maintained)
- Newsletter section: excluded
- Card images/thumbnails: excluded
- `web/articles/` static files: untouched
- `stitch/` reference files: untouched
- API server code: untouched
- Existing JS logic: preserved

### Verification
- [x] `pytest tests/test_integrity.py -v` — 74 passed, 9 skipped
- [x] `--shadow-sharp` present in main.css (light + dark themes)
- [x] `grid-lines` applied to index.html + about.html heroes
- [x] All 12 pages have Stitch design elements
- [ ] Visual: dark/light toggle on all pages
- [ ] Visual: mobile responsive (sidebar collapse, stats strip reflow)
- [ ] Visual: card hover effects (amber left bar + shadow escalation)
