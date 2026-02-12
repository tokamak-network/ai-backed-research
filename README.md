# Autonomous Research Press

AI-powered autonomous research paper generation and peer review platform. Submit a topic, and the system composes an expert team, writes a manuscript through collaborative research, conducts multi-round peer review, and publishes the result.

## How It Works

```
Topic Submission -> Category Classification -> Team Composition -> Research Notes
                                                                        |
Publication <-- Moderator Decision <-- Peer Review <-- Desk Edit <-- Writing
                     |                      |
                     +--- Revision Loop ----+
```

1. **Topic Submission** - User provides a research topic via web UI or CLI
2. **Category Classification** - LLM classifies into primary + optional secondary academic field
3. **Team Composition** - AI proposes domain-expert authors and reviewers
4. **Research Notes** - Iterative research note generation with structured analysis
5. **Manuscript Writing** - Section-by-section writing with plan → draft → integrate pipeline
6. **Desk Edit** - Initial quality gate screening before peer review
7. **Peer Review** - Multiple AI reviewers provide scored feedback with detailed critique
8. **Revision Loop** - Author revises based on feedback until quality threshold is met
9. **Moderator Decision** - Final accept/reject judgment
10. **Publication** - Accepted papers exported and published to the web interface

## Features

- **Two Workflow Modes** - Standard (single writer + reviewers) and Collaborative (lead author + co-authors + reviewers)
- **9 Academic Categories** - Computer Science, Engineering, Natural Sciences, Social Sciences, Humanities, Business & Economics, Medicine & Health, Law & Public Policy, Mathematics & Statistics
- **Secondary Category Support** - Optional interdisciplinary classification for cross-domain research
- **Multi-Round Peer Review** - Iterative writing/review/revision cycles with configurable thresholds
- **3 Research Types** - Explainer, Survey, and Original research with tailored prompts
- **3 Audience Levels** - Beginner, Intermediate, Professional with adaptive complexity
- **Article Length Options** - Short (3,000 words) and Full (5,000+ words)
- **External Submissions** - Submit your own manuscripts for AI peer review
- **Role-Based Model Config** - Different AI models per role (writer, reviewer, moderator, etc.)
- **3-Tier Model System** - Reasoning (Gemini Pro/Claude Opus), Support (Claude Sonnet), Light (Gemini Flash/Haiku)
- **Multi-Provider LLM** - Anthropic Claude, Google Gemini, OpenAI GPT with automatic fallback
- **Researcher Applications** - Application and approval system for API key access
- **Job Queue** - Sequential workflow processing with real-time status via SSE
- **Cost Estimation** - Token-based pricing estimates per workflow
- **Checkpoint/Resume** - Workflows save progress and can resume from interruption
- **Web Publishing** - Automatic export to static HTML with version history

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI + Uvicorn + Gunicorn |
| AI/LLM | Google Gemini, Anthropic Claude, OpenAI GPT |
| Database | SQLite (researcher apps, API keys, job queue) |
| Frontend | Static HTML/CSS/JS (IBM Carbon Design System) |
| Deploy | Docker, Railway |

## Project Structure

```
auto-research-press/
├── api_server.py                  # FastAPI application (all REST + SSE endpoints)
├── export_to_web.py               # Exports research results to web/articles + web/data
├── run_full_review.py             # Standalone CLI script for full review workflow
│
├── research_cli/                  # Core research workflow engine
│   ├── __init__.py
│   ├── cli.py                     # Click-based CLI interface
│   ├── config.py                  # Environment variable & LLM config management
│   ├── model_config.py            # 3-tier model selection, pricing, create_llm_for_role()
│   ├── categories.py              # Academic field taxonomy (9 major fields, 40+ subfields)
│   ├── db.py                      # SQLite database (researchers, API keys, jobs)
│   ├── interactive.py             # Interactive CLI team editor (Rich-based)
│   ├── performance.py             # Phase timers, token counters, cost tracking
│   │
│   ├── agents/                    # AI agent implementations
│   │   ├── lead_author.py         # Lead author: plans, researches, writes sections
│   │   ├── coauthor.py            # Co-author: assists lead author on assigned sections
│   │   ├── writer.py              # Single-agent writer (standard workflow)
│   │   ├── paper_writer_agent.py  # Section-by-section paper writer
│   │   ├── research_planner.py    # Creates section-level writing plans
│   │   ├── research_notes_agent.py# Generates structured research notes
│   │   ├── data_analysis_agent.py # Data analysis and chart generation
│   │   ├── desk_editor.py         # Desk screening before peer review
│   │   ├── integration_editor.py  # Merges multi-author sections into coherent manuscript
│   │   ├── moderator.py           # Final accept/reject/revise judgment
│   │   ├── specialist_factory.py  # Creates reviewer ExpertConfig from category pool
│   │   ├── team_composer.py       # LLM-based reviewer team proposal
│   │   └── writer_team_composer.py# LLM-based author team proposal (lead + co-authors)
│   │
│   ├── models/                    # Data models (dataclasses)
│   │   ├── expert.py              # ExpertProposal, ExpertConfig
│   │   ├── author.py              # WriterTeam, LeadAuthor, CoAuthor
│   │   ├── manuscript.py          # ManuscriptPlan, SectionSpec
│   │   ├── research_notes.py      # ResearchNotes, ResearchNote
│   │   ├── section.py             # ResearchPlan, SectionSpec
│   │   └── collaborative_research.py # CollaborativeResearchResult
│   │
│   ├── llm/                       # LLM provider abstraction layer
│   │   ├── base.py                # Abstract LLM base class + retry logic
│   │   ├── claude.py              # Anthropic Claude provider
│   │   ├── gemini.py              # Google Gemini provider (streaming)
│   │   └── openai.py              # OpenAI GPT provider
│   │
│   ├── workflow/                   # Workflow orchestration
│   │   ├── orchestrator.py         # Standard workflow: write → review → revise loop
│   │   ├── collaborative_workflow.py # Collaborative: research → write → review with teams
│   │   ├── collaborative_research.py# Multi-author research note generation
│   │   └── manuscript_writing.py   # Multi-author manuscript writing pipeline
│   │
│   └── utils/                     # Utilities
│       ├── json_repair.py         # LLM JSON output repair (handles markdown fences, etc.)
│       ├── citation_manager.py    # Citation formatting and management
│       ├── source_retriever.py    # Source URL retrieval and validation
│       └── title_generator.py     # Article title generation
│
├── config/
│   └── models.json                # Model tier config (reasoning/support/light + role mappings)
│
├── web/                           # Static frontend (IBM Carbon Design System)
│   ├── index.html                 # Homepage - article listing with filters
│   ├── article.html               # Article reader with version history + review data
│   ├── ask-topic.html             # Start new research (topic → team → workflow)
│   ├── research-queue.html        # Monitor running/completed workflows (SSE)
│   ├── my-research.html           # User's own research history
│   ├── submit.html                # External manuscript submission for review
│   ├── review.html                # Review interface for submitted manuscripts
│   ├── apply.html                 # Researcher API key application form
│   ├── admin.html                 # Admin dashboard (key management, job monitoring)
│   ├── about.html                 # About page
│   ├── api-docs.html              # API documentation
│   ├── blog-reader.html           # Blog-style article reader
│   ├── favicon.svg                # Site favicon
│   ├── js/
│   │   └── main.js                # Shared JS (dark mode, navigation, utilities)
│   ├── styles/
│   │   ├── main.css               # Global styles (IBM Carbon design tokens)
│   │   └── article.css            # Article-specific styles
│   ├── images/
│   │   ├── og-cover.png           # Open Graph social media preview image
│   │   └── thumbnails/            # Article thumbnail SVGs
│   ├── articles/                  # Generated article HTML files (one per published paper)
│   └── data/                      # Generated article JSON data
│       ├── index.json             # Article index (all published articles metadata)
│       ├── {slug}.json            # Per-article review data (scores, rounds, reviewers)
│       └── {slug}_manuscripts.json# Per-article manuscript versions (v1, v2, ..., final)
│
├── scripts/
│   ├── migrate_keys.py            # Migrate API keys between storage backends
│   └── test_api_connections.py    # Test LLM API connectivity
│
├── tests/
│   ├── test_e2e_diagnostic.py     # End-to-end workflow diagnostic tests
│   ├── test_integrity.py          # Data integrity tests
│   ├── test_json_repair.py        # JSON repair unit tests
│   ├── test_team_pipeline.py      # Team composition pipeline tests
│   ├── test_author_response.py    # Author response generation tests
│   ├── test_moderator_judgment.py # Moderator decision tests
│   ├── test_multi_stage_writing.py# Multi-stage writing pipeline tests
│   ├── test_research_notes_workflow.py # Research notes workflow tests
│   ├── test_reviewer_prompt.py    # Reviewer prompt quality tests
│   ├── test_resume.py             # Checkpoint/resume tests
│   ├── test_fault_tolerance.py    # Error handling and recovery tests
│   ├── test_setup.py              # Environment setup verification
│   ├── test_new_features.py       # New feature integration tests
│   ├── test_short_paper_benchmark.py  # Short paper benchmarks
│   ├── test_gemini_flash_roles.py # Gemini Flash role-specific tests
│   ├── test_gemini_streaming.py   # Gemini streaming tests
│   ├── test_model_comparison.py   # Cross-model comparison benchmarks
│   └── results/                   # Test output artifacts
│
├── Dockerfile                     # Python 3.11-slim, gunicorn + uvicorn
├── entrypoint.sh                  # Railway volume symlink setup + seed data merge
├── railway.toml                   # Railway deployment config
├── requirements.txt               # Python dependencies
├── pyproject.toml                 # Project metadata
├── VERSION                        # Semantic version (1.0.0)
├── .env.example                   # Environment variable template
└── .gitignore
```

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Google API key (primary provider for Gemini models) |
| `RESEARCH_API_KEYS` | Comma-separated allowed API keys for users |
| `RESEARCH_ADMIN_KEY` | Admin API key for privileged operations |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key (for Claude models) | - |
| `OPENAI_API_KEY` | OpenAI API key (for GPT models) | - |
| `LLM_API_KEY` | Shared LLM router key (LiteLLM/OpenRouter) | - |
| `LLM_BASE_URL` | Shared LLM router base URL | - |
| `DEFAULT_WRITER_MODEL` | Writer model override | - |
| `DEFAULT_REVIEWER_MODEL` | Reviewer model override | - |
| `MAX_REVIEW_ROUNDS` | Max review iterations | `3` |
| `SCORE_THRESHOLD` | Quality score threshold | `8.0` |
| `PORT` | Server port | `8000` |

## Model Configuration

Models are configured in `config/models.json` with a 3-tier system:

| Tier | Role | Default Model |
|------|------|---------------|
| **Reasoning** | Writer, Lead Author, Paper Writer | `gemini-2.5-pro` |
| **Support** | Reviewer, Moderator, Desk Editor | `claude-sonnet-4-5` |
| **Light** | Categorizer, Planner, Team Composer | `gemini-2.5-flash` |

Each tier has primary + fallback models. Roles map to tiers with per-role temperature and token limits.

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GOOGLE_API_KEY=your-google-key
export RESEARCH_API_KEYS=your-api-key
export RESEARCH_ADMIN_KEY=your-admin-key

# Run the server
python -m uvicorn api_server:app --reload --port 8000

# Open in browser
open http://localhost:8000
```

## Docker

```bash
docker build -t auto-research-press .
docker run -p 8000:8000 \
  -e GOOGLE_API_KEY=your-google-key \
  -e RESEARCH_API_KEYS=your-api-key \
  -e RESEARCH_ADMIN_KEY=your-admin-key \
  auto-research-press
```

## Railway Deployment

1. Deploy from GitHub repo in Railway dashboard
2. Add a Volume mounted at `/app/persistent` (for SQLite DB, results, and articles)
3. Set required environment variables
4. Railway auto-detects the Dockerfile and healthcheck at `/api/health`

## API Endpoints

### Public

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/version` | Version info |
| `GET` | `/api/articles` | List published articles |
| `GET` | `/api/articles/{slug}` | Get article detail |

### Authenticated (X-API-Key header)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/classify-topic` | Classify topic into academic categories |
| `POST` | `/api/propose-team` | Propose expert team for a topic |
| `POST` | `/api/propose-reviewers` | Generate reviewer panel |
| `POST` | `/api/start-workflow` | Start a research workflow |
| `GET` | `/api/workflow-status/{id}` | Get workflow status |
| `GET` | `/api/workflow-stream/{id}` | SSE stream for real-time status |
| `POST` | `/api/submit-manuscript` | Submit external manuscript for review |

### Admin (X-API-Key: admin key)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/admin/applications` | List researcher applications |
| `POST` | `/api/admin/approve/{id}` | Approve application + issue API key |
| `GET` | `/api/admin/keys` | List active API keys |
| `DELETE` | `/api/admin/keys/{key}` | Revoke API key |

## License

MIT
