# Autonomous Research Press

AI-powered autonomous research paper generation and peer review platform. Submit a topic, and the system composes an expert review team, writes a manuscript, conducts multi-round peer review, and publishes the result.

## How It Works

```
Topic Submission -> Team Composition -> Draft Writing -> Desk Edit
                                                            |
Publication <-- Moderator Decision <-- Peer Review <--------+
                     |                      |
                     +--- Revision Loop ----+
```

1. **Topic Submission** - User provides a research topic and field
2. **Team Composition** - AI proposes domain-expert reviewers
3. **Multi-Stage Writing** - Draft composed with research notes and structured sections
4. **Desk Edit** - Initial quality gate before peer review
5. **Peer Review** - Multiple AI reviewers provide scored feedback
6. **Revision Loop** - Author revises based on feedback until quality threshold is met
7. **Moderator Decision** - Final accept/reject judgment
8. **Publication** - Accepted papers published to the web interface

## Features

- **9 Academic Categories** - Computer Science, Engineering, Natural Sciences, Social Sciences, Humanities, Business & Economics, Medicine & Health, Law & Public Policy
- **Multi-Round Peer Review** - Iterative writing/review/revision cycles with configurable thresholds
- **External Submissions** - Submit your own manuscripts for AI peer review
- **Role-Based Model Config** - Different AI models for writer, reviewer, moderator, desk editor
- **Researcher Applications** - Application and approval system for API key access
- **Job Queue** - Concurrent workflow processing with status tracking
- **Cost Estimation** - Token-based pricing estimates per workflow

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI + Uvicorn + Gunicorn |
| AI/LLM | Anthropic Claude, OpenAI GPT |
| Database | SQLite |
| Frontend | Static HTML/CSS/JS (IBM Carbon Design) |
| Deploy | Docker, Railway |

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` | Shared LLM API key (LiteLLM/OpenRouter router key) |
| `LLM_BASE_URL` | Shared LLM base URL (router endpoint) |
| `RESEARCH_API_KEYS` | Comma-separated allowed API keys for users |
| `RESEARCH_ADMIN_KEY` | Admin API key for privileged operations |

### Optional (provider-specific overrides)

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic direct API key (overrides `LLM_API_KEY`) | - |
| `OPENAI_API_KEY` | OpenAI direct API key (overrides `LLM_API_KEY`) | - |
| `GOOGLE_API_KEY` | Google API key | - |
| `DEFAULT_WRITER_MODEL` | Writer model override | `claude-sonnet-4-20250514` |
| `DEFAULT_REVIEWER_MODEL` | Reviewer model override | `claude-sonnet-4-20250514` |
| `MAX_REVIEW_ROUNDS` | Max review iterations | `3` |
| `SCORE_THRESHOLD` | Quality score threshold | `8.0` |
| `PORT` | Server port (Railway sets automatically) | `8000` |

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export LLM_API_KEY=your-router-key
export LLM_BASE_URL=https://your-litellm-endpoint/v1
export RESEARCH_API_KEYS=your-api-key
export RESEARCH_ADMIN_KEY=your-admin-key

# Run the server
python -m uvicorn api_server:app --reload --port 8000
```

## Docker

```bash
docker build -t auto-research-press .
docker run -p 8000:8000 \
  -e LLM_API_KEY=your-router-key \
  -e LLM_BASE_URL=https://your-litellm-endpoint/v1 \
  -e RESEARCH_API_KEYS=your-api-key \
  -e RESEARCH_ADMIN_KEY=your-admin-key \
  auto-research-press
```

## Railway Deployment

1. Deploy from GitHub repo in Railway dashboard
2. Add a Volume mounted at `/app/persistent` (for SQLite DB and generated articles)
3. Set required environment variables
4. Railway auto-detects the Dockerfile and healthcheck at `/api/health`

## Project Structure

```
auto-research-press/
├── api_server.py          # FastAPI application
├── research_cli/          # Core research workflow engine
│   ├── workflow.py        # WorkflowOrchestrator
│   ├── agents/            # Writer, Reviewer, Moderator agents
│   ├── categories.py      # Academic field definitions
│   └── llm_client.py      # LLM API client
├── config/                # Model configuration
├── web/                   # Static frontend
│   ├── index.html         # Homepage
│   ├── ask-topic.html     # Start new research
│   ├── research-queue.html# Monitor workflows
│   ├── submit.html        # External submission
│   └── admin.html         # Admin dashboard
├── Dockerfile
├── railway.toml
└── entrypoint.sh          # Volume symlink setup
```

## License

MIT
