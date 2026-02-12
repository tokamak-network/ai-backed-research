#!/usr/bin/env python3
"""FastAPI server for AI-backed research platform."""

import asyncio
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Callable

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from research_cli.agents.team_composer import TeamComposerAgent
from research_cli.categories import suggest_category_from_topic, suggest_category_llm, get_expert_pool, get_category_name
from research_cli.workflow.orchestrator import WorkflowOrchestrator
from research_cli.workflow.collaborative_workflow import CollaborativeWorkflowOrchestrator
from research_cli.models.expert import ExpertConfig
from research_cli.models.author import AuthorRole, WriterTeam
from research_cli.utils.citation_manager import CitationManager
from research_cli import db as appdb
from research_cli.model_config import get_role_config, get_reviewer_models, get_pricing, get_all_pricing, create_llm_for_role


app = FastAPI(title="Autonomous Research Press API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Job Queue ---
MAX_CONCURRENT_WORKERS = 3
job_queue: asyncio.Queue = asyncio.Queue()
_active_worker_count = 0  # Track how many workers are currently processing a job


async def job_worker(worker_id: int):
    """Worker: pull jobs from queue and execute."""
    global _active_worker_count
    print(f"  Worker {worker_id} started")
    while True:
        job = await job_queue.get()
        _active_worker_count += 1
        pid = job.get("project_id", "?")
        db_job_id = job.pop("_db_job_id", None)
        print(f"  Worker {worker_id} picked up job: {pid[:50]}")
        if db_job_id:
            try:
                appdb.mark_job_running(db_job_id)
            except Exception:
                pass
        try:
            job_fn = job.pop("_fn")
            await job_fn(**job)
            if db_job_id:
                try:
                    appdb.complete_job(db_job_id, "completed")
                except Exception:
                    pass
        except Exception as e:
            print(f"  Worker {worker_id} error: {e}")
            if db_job_id:
                try:
                    appdb.complete_job(db_job_id, "failed")
                except Exception:
                    pass
        finally:
            _active_worker_count -= 1
            job_queue.task_done()


# --- API Key Auth ---
ALLOWED_API_KEYS: set = set()
_raw_keys = os.environ.get("RESEARCH_API_KEYS", "")
if _raw_keys:
    ALLOWED_API_KEYS = {k.strip() for k in _raw_keys.split(",") if k.strip()}

ADMIN_API_KEY = os.environ.get("RESEARCH_ADMIN_KEY", "")


async def verify_api_key(request: Request) -> str:
    """FastAPI dependency: validate X-API-Key header (env var keys + SQLite)."""
    key = request.headers.get("X-API-Key")
    if not ALLOWED_API_KEYS and not ADMIN_API_KEY:
        # No keys configured → auth disabled (dev mode)
        return key or "anonymous"
    if ADMIN_API_KEY and key == ADMIN_API_KEY:
        return key  # admin key is always valid
    if not key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    # Check env var keys
    if key in ALLOWED_API_KEYS:
        return key
    # Check SQLite
    db_key = appdb.get_api_key(key)
    if db_key:
        return key
    raise HTTPException(status_code=403, detail="Invalid or missing API key")


async def verify_admin_key(request: Request) -> str:
    """FastAPI dependency: validate admin API key."""
    key = request.headers.get("X-API-Key")
    if not ADMIN_API_KEY:
        # Admin key not configured → dev mode: allow all
        return key or "anonymous"
    if key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Admin access required")
    return key


# --- Rate Limit (per API key, 60s cooldown for parallel submission) ---
RATE_LIMIT_SECONDS = 5
rate_limit_store: Dict[str, float] = {}  # api_key → last_request_timestamp


async def check_rate_limit(api_key: str):
    """Enforce 1 request per RATE_LIMIT_SECONDS per API key."""
    last = rate_limit_store.get(api_key, 0)
    now = time.time()
    if now - last < RATE_LIMIT_SECONDS:
        remaining = int(RATE_LIMIT_SECONDS - (now - last))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited. Try again in {remaining}s"
        )
    rate_limit_store[api_key] = now


@app.on_event("startup")
async def startup_event():
    """Initialize DB, scan for interrupted workflows, recover pending jobs, start workers."""
    appdb.init_db()
    await scan_interrupted_workflows()
    await recover_pending_jobs()
    for i in range(MAX_CONCURRENT_WORKERS):
        asyncio.create_task(job_worker(i))


async def recover_pending_jobs():
    """Re-enqueue jobs that were queued or running when the server last stopped."""
    try:
        pending_jobs = appdb.get_pending_jobs()
    except Exception:
        return

    if not pending_jobs:
        return

    print(f"  Recovering {len(pending_jobs)} pending job(s) from DB...")
    for job_row in pending_jobs:
        job_id = job_row["id"]
        job_type = job_row["job_type"]
        try:
            payload = json.loads(job_row["payload_json"]) if isinstance(job_row["payload_json"], str) else job_row["payload_json"]
        except (json.JSONDecodeError, TypeError):
            appdb.complete_job(job_id, "failed")
            continue

        if job_type == "workflow":
            await job_queue.put({
                "_fn": run_workflow_background,
                "_db_job_id": job_id,
                **payload,
            })
        elif job_type == "submission_review":
            await job_queue.put({
                "_fn": run_submission_review_background,
                "_db_job_id": job_id,
                **payload,
            })
        elif job_type == "resume":
            # Convert project_dir back to Path
            payload["project_dir"] = Path(payload["project_dir"])
            await job_queue.put({
                "_fn": resume_workflow_background,
                "_db_job_id": job_id,
                **payload,
            })
        else:
            appdb.complete_job(job_id, "failed")
            continue

        print(f"    Recovered job {job_id[:8]}... ({job_type}, project: {payload.get('project_id', '?')[:40]})")


async def scan_interrupted_workflows():
    """Scan results directory for interrupted workflows (checkpoint exists but no complete)."""
    results_dir = Path("results")
    if not results_dir.exists():
        return

    # Skip test/benchmark directories from queue
    SKIP_PATTERNS = ['benchmark-', '-test', 'test-']

    interrupted_count = 0
    for project_dir in results_dir.iterdir():
        if not project_dir.is_dir():
            continue

        # Skip test/benchmark directories
        if any(pattern in project_dir.name for pattern in SKIP_PATTERNS):
            continue

        checkpoint_file = project_dir / "workflow_checkpoint.json"
        complete_file = project_dir / "workflow_complete.json"

        # Has checkpoint but no complete = interrupted
        if checkpoint_file.exists() and not complete_file.exists():
            project_id = project_dir.name

            try:
                with open(checkpoint_file) as f:
                    checkpoint = json.load(f)

                # Add to workflow_status as "interrupted"
                workflow_status[project_id] = {
                    "topic": checkpoint.get("topic", ""),
                    "status": "interrupted",
                    "current_round": checkpoint.get("current_round", 0),
                    "total_rounds": checkpoint.get("max_rounds", 3),
                    "progress_percentage": int((checkpoint.get("current_round", 0) / checkpoint.get("max_rounds", 3)) * 100),
                    "message": f"Interrupted at Round {checkpoint.get('current_round', 0)} - Resume available",
                    "error": None,
                    "expert_status": [
                        {
                            "expert_id": f"expert-{i+1}",
                            "expert_name": exp.get("name", exp.get("domain", f"Expert {i+1}")),
                            "status": "waiting",
                            "progress": 0,
                            "message": "Waiting to resume",
                            "score": None
                        }
                        for i, exp in enumerate(checkpoint.get("expert_configs", []))
                    ],
                    "cost_estimate": None,
                    "start_time": checkpoint.get("checkpoint_time", _utcnow().isoformat()),
                    "elapsed_time_seconds": 0,
                    "estimated_time_remaining_seconds": (checkpoint.get("max_rounds", 3) - checkpoint.get("current_round", 0)) * 180,
                    "can_resume": True
                }

                # Initialize activity log
                activity_logs[project_id] = [{
                    "timestamp": _utcnow().isoformat(),
                    "level": "warning",
                    "message": f"Workflow interrupted at Round {checkpoint.get('current_round', 0)}. Click Resume to continue.",
                    "details": {"checkpoint_time": checkpoint.get("checkpoint_time")}
                }]

                interrupted_count += 1
                print(f"  Found interrupted workflow: {project_id} (Round {checkpoint.get('current_round', 0)}/{checkpoint.get('max_rounds', 3)})")

            except Exception as e:
                print(f"  Error loading checkpoint for {project_id}: {e}")

        # Orphan directory: has files but no checkpoint and no complete marker
        # (e.g., crashed during team formation or early research phase)
        elif not checkpoint_file.exists() and not complete_file.exists():
            has_files = any(project_dir.iterdir())
            if has_files:
                project_id = project_dir.name
                workflow_status[project_id] = {
                    "topic": project_id.rsplit("-", 2)[0].replace("-", " ") if "-" in project_id else project_id,
                    "status": "failed",
                    "current_round": 0,
                    "total_rounds": 0,
                    "progress_percentage": 0,
                    "message": "Failed during early phase (no checkpoint). Retry to start fresh.",
                    "error": "Workflow crashed before checkpoint was created",
                    "expert_status": [],
                    "cost_estimate": None,
                    "start_time": _utcnow().isoformat(),
                    "elapsed_time_seconds": 0,
                    "estimated_time_remaining_seconds": None,
                    "can_resume": True
                }
                activity_logs[project_id] = [{
                    "timestamp": _utcnow().isoformat(),
                    "level": "error",
                    "message": "Workflow failed before checkpoint was saved. Click Retry to start fresh.",
                    "details": {"orphan_files": [f.name for f in project_dir.iterdir()]}
                }]
                interrupted_count += 1
                print(f"  Found orphan workflow: {project_id} (no checkpoint, has files)")

    if interrupted_count > 0:
        print(f"✓ Found {interrupted_count} interrupted/orphan workflow(s) - available for resume")


# Request/Response Models
class ExpertContext(BaseModel):
    type: str  # "description", "url", "pdf"
    content: str

class ClassifyTopicRequest(BaseModel):
    topic: str

class ClassifyTopicResponse(BaseModel):
    primary_major: str
    primary_subfield: str
    secondary_major: Optional[str] = None
    secondary_subfield: Optional[str] = None
    confidence: float

class ProposeTeamRequest(BaseModel):
    topic: str
    num_experts: Optional[int] = None
    research_type: Optional[str] = "research"  # "survey", "research", or "explainer"
    expert_context: Optional[ExpertContext] = None


class ExpertProposalResponse(BaseModel):
    expert_domain: str
    rationale: str
    focus_areas: List[str]
    suggested_model: str


class CostEstimate(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    model_breakdown: Dict[str, dict]


class TeamProposalResponse(BaseModel):
    topic: str
    proposed_experts: List[ExpertProposalResponse]
    recommended_num_experts: int
    estimated_time_minutes: int
    estimated_rounds: int
    cost_estimate: Optional[CostEstimate] = None


class CategoryInfo(BaseModel):
    major: Optional[str] = None
    subfield: Optional[str] = None
    secondary_major: Optional[str] = None
    secondary_subfield: Optional[str] = None

class StartWorkflowRequest(BaseModel):
    topic: str
    experts: List[dict]
    max_rounds: int = 3
    threshold: float = 7.0
    research_cycles: int = 1  # Number of research note iterations
    category: Optional[CategoryInfo] = None  # Academic category
    article_length: Optional[str] = "full"  # "full" or "short"
    workflow_mode: Optional[str] = "standard"  # "standard" or "collaborative"
    audience_level: Optional[str] = "professional"  # "beginner", "intermediate", "professional"
    research_type: Optional[str] = "survey"  # "survey", "research", or "explainer"


class SubmitArticleRequest(BaseModel):
    title: str
    content: str  # Markdown content
    author: Optional[str] = "Anonymous"
    category: Optional[CategoryInfo] = None


class ExpertStatus(BaseModel):
    expert_id: str
    expert_name: str
    status: str  # "waiting", "active", "completed", "failed"
    progress: int  # 0-100
    message: str
    score: Optional[float] = None

class ActivityLogEntry(BaseModel):
    timestamp: str
    level: str  # "info", "success", "warning", "error"
    message: str
    details: Optional[dict] = None

class WorkflowStatusResponse(BaseModel):
    project_id: str
    status: str  # "queued", "composing_team", "writing", "desk_screening", "reviewing", "revising", "completed", "failed"
    current_round: int
    total_rounds: int
    progress_percentage: int
    message: str
    error: Optional[str] = None
    expert_status: Optional[List[ExpertStatus]] = None
    cost_estimate: Optional[CostEstimate] = None
    elapsed_time_seconds: Optional[int] = None
    estimated_time_remaining_seconds: Optional[int] = None


# In-memory workflow status tracking
workflow_status: Dict[str, dict] = {}
activity_logs: Dict[str, List[dict]] = {}


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "Autonomous Research Press API"}


@app.get("/api/queue-status")
async def queue_status():
    """Return current job queue size and running job info."""
    return {
        "queued_jobs": job_queue.qsize(),
        "active_workers": _active_worker_count,
        "max_workers": MAX_CONCURRENT_WORKERS,
        "active_workflows": sum(
            1 for s in workflow_status.values()
            if s["status"] in ("queued", "composing_team", "writing", "desk_screening", "reviewing", "revising", "research", "writing_sections")
        )
    }


@app.post("/api/classify-topic", response_model=ClassifyTopicResponse)
async def classify_topic(request: ClassifyTopicRequest, api_key: str = Depends(verify_api_key)):
    """Classify research topic into academic categories using gemini-flash."""
    try:
        from research_cli.utils.json_repair import repair_json

        llm = create_llm_for_role("categorizer")

        # Build category reference for LLM
        from research_cli.categories import ACADEMIC_CATEGORIES
        category_ref = []
        for major_id, major_data in ACADEMIC_CATEGORIES.items():
            subfields = list(major_data["subfields"].keys())
            category_ref.append(f"  {major_id}: {major_data['name']} (subfields: {', '.join(subfields)})")
        category_list = "\n".join(category_ref)

        prompt = f"""Classify this research topic into academic categories.

TOPIC: {request.topic}

AVAILABLE CATEGORIES:
{category_list}

Classify into:
1. PRIMARY category (major + subfield) - the main field this research belongs to
2. SECONDARY category (major + subfield) - optional, only if the research has significant overlap with another field

Respond in JSON format:
{{
  "primary_major": "<major_id>",
  "primary_subfield": "<subfield_id>",
  "secondary_major": "<major_id or null>",
  "secondary_subfield": "<subfield_id or null>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>"
}}

Use ONLY the exact major_id and subfield_id values from the category list above."""

        response = await llm.generate(
            prompt=prompt,
            system="You classify research topics into academic categories. Respond with ONLY JSON.",
            temperature=0.3,
            max_tokens=512,
        )

        data = repair_json(response.content)

        return ClassifyTopicResponse(
            primary_major=data.get("primary_major", "computer_science"),
            primary_subfield=data.get("primary_subfield", "ai_ml"),
            secondary_major=data.get("secondary_major"),
            secondary_subfield=data.get("secondary_subfield"),
            confidence=data.get("confidence", 0.8),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")


@app.post("/api/propose-team", response_model=TeamProposalResponse)
async def propose_team(request: ProposeTeamRequest, api_key: str = Depends(verify_api_key)):
    """Propose expert team based on research topic."""
    try:
        # Use TeamComposer to generate proposals
        composer = TeamComposerAgent()

        # If num_experts not specified, let AI decide (default 3)
        num_experts = request.num_experts if request.num_experts else 3

        # Build additional context string
        additional_context = ""

        if request.research_type:
            if request.research_type == "survey":
                additional_context += "Research Type: Survey/Literature Review - Focus on synthesizing existing research, identifying gaps, and providing comprehensive overview.\n\n"
            elif request.research_type == "explainer":
                additional_context += "Research Type: Explainer/Tutorial - Focus on clear concept explanation, intuitive examples, and pedagogical structure.\n\n"
            else:
                additional_context += "Research Type: Original Research - Focus on novel analysis, comparisons, and original insights.\n\n"

        if request.expert_context:
            ctx = request.expert_context
            if ctx.type == "description":
                additional_context += f"Desired Expert Profile: {ctx.content}\n\n"
            elif ctx.type == "url":
                additional_context += f"Reference URL for expertise: {ctx.content}\nPlease consider the expertise and focus of the referenced work when proposing reviewers.\n\n"
            elif ctx.type == "pdf":
                additional_context += f"Reference PDF uploaded: {ctx.content}\nPlease consider the research focus and methodology of the referenced paper when proposing reviewers.\n\n"

        # Secondary category context is handled via suggest_category_llm below
        proposals = await composer.propose_team(request.topic, num_experts, additional_context)

        # Suggest category based on topic (LLM-based, works for any language)
        suggested_category = await suggest_category_llm(request.topic)

        # Estimate time based on number of experts and rounds
        # Rough estimate: 5 min draft + (num_experts * 2 min per round * 2 rounds) + 3 min revision
        estimated_time = 5 + (len(proposals) * 2 * 2) + 3
        estimated_rounds = 2

        # Calculate cost estimate
        num_experts_final = len(proposals)
        model = proposals[0].suggested_model if proposals else "claude-opus-4.5"
        input_tokens = num_experts_final * estimated_rounds * 5000
        output_tokens = num_experts_final * estimated_rounds * 2000
        cost_info = calculate_cost_estimate(input_tokens, output_tokens, model)

        # Build response with suggested category
        response_data = {
            "topic": request.topic,
            "proposed_experts": [
                ExpertProposalResponse(
                    expert_domain=p.expert_domain,
                    rationale=p.rationale,
                    focus_areas=p.focus_areas,
                    suggested_model=p.suggested_model
                ) for p in proposals
            ],
            "recommended_num_experts": len(proposals),
            "estimated_time_minutes": estimated_time,
            "estimated_rounds": estimated_rounds,
            "cost_estimate": CostEstimate(**cost_info)
        }

        # Return as dict to include suggested_category (not in model)
        return JSONResponse(content={
            **response_data,
            "proposed_experts": [
                {
                    "expert_domain": p.expert_domain,
                    "rationale": p.rationale,
                    "focus_areas": p.focus_areas,
                    "suggested_model": p.suggested_model
                } for p in proposals
            ],
            "cost_estimate": cost_info,
            "suggested_category": suggested_category
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to propose team: {str(e)}")


@app.post("/api/start-workflow")
async def start_workflow(request: StartWorkflowRequest, api_key: str = Depends(verify_api_key)):
    """Start workflow via job queue (sequential execution)."""
    # Rate limit check
    await check_rate_limit(api_key)

    # Quota check (SQLite keys only; legacy/anonymous keys skip quota)
    if api_key not in ("anonymous", ADMIN_API_KEY):
        db_key = appdb.get_api_key(api_key)
        if db_key:
            quota = appdb.check_quota(api_key)
            if not quota["allowed"]:
                raise HTTPException(
                    status_code=429,
                    detail=f"Daily quota exceeded ({quota['used']}/{quota['limit']}). Try again tomorrow."
                )

    try:
        # Generate unique project ID (sanitize: lowercase, hyphens, strip control chars)
        project_id = re.sub(r'[^a-z0-9\-]', '-', request.topic.lower().replace(" ", "-"))
        project_id = re.sub(r'-{2,}', '-', project_id).strip('-')
        # Truncate overly long slugs, add timestamp for uniqueness
        project_id = f"{project_id[:80]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # Record usage and ownership in SQLite
        if api_key not in ("anonymous",):
            try:
                appdb.record_usage(api_key, "/api/start-workflow", project_id)
                appdb.record_ownership(project_id, api_key)
            except Exception:
                pass  # Non-critical

        # Initialize status
        workflow_status[project_id] = {
            "topic": request.topic,
            "status": "queued",
            "current_round": 0,
            "total_rounds": request.max_rounds,
            "progress_percentage": 0,
            "message": f"Workflow queued (position {job_queue.qsize() + 1})",
            "error": None,
            "expert_status": [
                {
                    "expert_id": f"expert-{i+1}",
                    "expert_name": exp.get("expert_domain", f"Expert {i+1}"),
                    "status": "waiting",
                    "progress": 0,
                    "message": "Waiting to start",
                    "score": None
                }
                for i, exp in enumerate(request.experts)
            ],
            "cost_estimate": None,
            "start_time": _utcnow().isoformat(),
            "elapsed_time_seconds": 0,
            "estimated_time_remaining_seconds": request.max_rounds * len(request.experts) * 120,
            "research_type": request.research_type or "survey"
        }

        # Initialize activity log
        activity_logs[project_id] = []
        add_activity_log(project_id, "info", f"Workflow created for topic: {request.topic[:50]}...")

        # Persist job to DB and enqueue
        db_job_id = str(uuid.uuid4())
        job_payload = {
            "project_id": project_id,
            "topic": request.topic,
            "experts": request.experts,
            "max_rounds": request.max_rounds,
            "threshold": request.threshold,
            "research_cycles": request.research_cycles,
            "category": request.category.dict() if request.category else None,
            "article_length": request.article_length or "full",
            "workflow_mode": request.workflow_mode or "standard",
            "audience_level": request.audience_level or "professional",
            "research_type": request.research_type or "survey",
        }
        try:
            appdb.enqueue_job(db_job_id, project_id, "workflow", job_payload)
        except Exception:
            pass
        await job_queue.put({
            "_fn": run_workflow_background,
            "_db_job_id": db_job_id,
            **job_payload,
        })

        return {
            "project_id": project_id,
            "status": "queued",
            "message": "Workflow started",
            "queue_position": job_queue.qsize()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")


@app.get("/api/workflow-status/{project_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(project_id: str):
    """Get workflow status."""
    if project_id not in workflow_status:
        raise HTTPException(status_code=404, detail="Workflow not found")

    status = workflow_status[project_id]

    # Calculate elapsed time
    start_time = _parse_start_time(status.get("start_time", _utcnow().isoformat()))
    elapsed_seconds = int((_utcnow() - start_time).total_seconds())

    return WorkflowStatusResponse(
        project_id=project_id,
        status=status["status"],
        current_round=status["current_round"],
        total_rounds=status["total_rounds"],
        progress_percentage=status["progress_percentage"],
        message=status["message"],
        error=status.get("error"),
        expert_status=[ExpertStatus(**exp) for exp in status.get("expert_status", [])],
        cost_estimate=CostEstimate(**status["cost_estimate"]) if status.get("cost_estimate") else None,
        elapsed_time_seconds=elapsed_seconds,
        estimated_time_remaining_seconds=status.get("estimated_time_remaining_seconds")
    )


@app.get("/api/workflows")
async def list_workflows(api_key: str = Depends(verify_api_key)):
    """List all workflows."""
    results = []
    for pid, status in workflow_status.items():
        entry = {"project_id": pid, **status}
        # Dynamically calculate elapsed time for active workflows
        if status.get("status") not in ("completed", "failed", "interrupted", "rejected"):
            try:
                start_time = _parse_start_time(status.get("start_time", _utcnow().isoformat()))
                entry["elapsed_time_seconds"] = int((_utcnow() - start_time).total_seconds())
            except (ValueError, TypeError):
                pass
        results.append(entry)
    return {"workflows": results}


@app.get("/api/workflow-activity/{project_id}")
async def get_workflow_activity(project_id: str, limit: int = 50):
    """Get activity log for a workflow."""
    if project_id not in workflow_status:
        raise HTTPException(status_code=404, detail="Workflow not found")

    logs = activity_logs.get(project_id, [])
    # Return latest logs (newest first)
    return {"activity": logs[-limit:][::-1]}


@app.post("/api/workflows/{project_id}/resume")
async def resume_workflow(project_id: str, api_key: str = Depends(verify_api_key)):
    """Resume a workflow from checkpoint via job queue."""
    try:
        # Find project directory
        results_dir = Path("results")
        project_dir = None

        for dir_path in results_dir.iterdir():
            if dir_path.is_dir() and dir_path.name == project_id:
                project_dir = dir_path
                break

        if not project_dir:
            raise HTTPException(status_code=404, detail=f"Project directory not found: {project_id}")

        # Check for checkpoint
        checkpoint_file = project_dir / "workflow_checkpoint.json"

        # Initialize activity log
        if project_id not in activity_logs:
            activity_logs[project_id] = []

        # Check if another workflow is actively running
        active_statuses = {"composing_team", "writing", "desk_screening", "reviewing", "revising", "research", "writing_sections"}
        active_workflows = [
            pid for pid, s in workflow_status.items()
            if s["status"] in active_statuses and pid != project_id
        ]

        if not checkpoint_file.exists():
            # No checkpoint — restart workflow from scratch using original job payload
            original_job = appdb.get_original_job(project_id)
            if not original_job or not original_job.get("payload"):
                raise HTTPException(status_code=400, detail="No checkpoint and no original job found for this workflow")

            payload = original_job["payload"]
            restart_detail = f"No checkpoint found — restarting workflow from scratch"

            workflow_status[project_id] = {
                "project_id": project_id,
                "topic": payload.get("topic", ""),
                "status": "queued",
                "current_round": 0,
                "total_rounds": payload.get("max_rounds", 3),
                "progress_percentage": 0,
                "message": "Restarting workflow from scratch...",
                "error": None,
                "expert_status": [],
                "cost_estimate": None,
                "start_time": _utcnow().isoformat(),
                "elapsed_time_seconds": 0,
                "estimated_time_remaining_seconds": payload.get("max_rounds", 3) * 180,
                "research_type": payload.get("research_type", "survey"),
            }

            add_activity_log(project_id, "info", restart_detail)

            if active_workflows:
                workflow_status[project_id]["message"] = "Queued to restart (waiting for active workflow to finish)"
                add_activity_log(project_id, "warning", f"Another workflow is running ({active_workflows[0][:40]}...). This restart is queued.")

            # Enqueue as a fresh workflow run
            db_job_id = str(uuid.uuid4())
            try:
                appdb.enqueue_job(db_job_id, project_id, "workflow", payload)
            except Exception:
                pass
            await job_queue.put({
                "_fn": run_workflow_background,
                "_db_job_id": db_job_id,
                **payload,
            })

            queue_position = job_queue.qsize()
            return {
                "project_id": project_id,
                "status": "queued",
                "message": restart_detail,
                "queue_position": queue_position,
                "has_active_workflow": len(active_workflows) > 0,
                "active_workflow_id": active_workflows[0] if active_workflows else None,
                "checkpoint": None,
            }

        # Load checkpoint to get info
        with open(checkpoint_file) as f:
            checkpoint = json.load(f)

        # Reset workflow status to queued (handles both new and failed/interrupted)
        workflow_status[project_id] = {
            "project_id": project_id,
            "topic": checkpoint.get("topic", ""),
            "status": "queued",
            "current_round": checkpoint["current_round"],
            "total_rounds": checkpoint["max_rounds"],
            "progress_percentage": int((checkpoint["current_round"] / checkpoint["max_rounds"]) * 100),
            "message": f"Resuming from Round {checkpoint['current_round']}/{checkpoint['max_rounds']}...",
            "error": None,
            "expert_status": [],
            "cost_estimate": None,
            "start_time": _utcnow().isoformat(),
            "elapsed_time_seconds": 0,
            "estimated_time_remaining_seconds": (checkpoint["max_rounds"] - checkpoint["current_round"]) * 180
        }

        # Detailed resume info
        cp_round = checkpoint['current_round']
        cp_max = checkpoint['max_rounds']
        last_rounds = checkpoint.get("all_rounds", [])
        last_score = last_rounds[-1].get("overall_average", 0) if last_rounds else 0
        last_decision = last_rounds[-1].get("moderator_decision", {}).get("decision", "N/A") if last_rounds else "N/A"
        resume_detail = f"Resuming from Round {cp_round}/{cp_max} (last score: {last_score:.1f}/10, decision: {last_decision})"

        add_activity_log(project_id, "info", resume_detail)

        if active_workflows:
            queue_msg = f"Queued to resume from Round {checkpoint['current_round']} (waiting for active workflow to finish)"
            workflow_status[project_id]["message"] = queue_msg
            add_activity_log(project_id, "warning", f"Another workflow is running ({active_workflows[0][:40]}...). This resume is queued.")

        # Persist job to DB and enqueue
        db_job_id = str(uuid.uuid4())
        job_payload_for_db = {
            "project_id": project_id,
            "project_dir": str(project_dir),
        }
        try:
            appdb.enqueue_job(db_job_id, project_id, "resume", job_payload_for_db)
        except Exception:
            pass
        await job_queue.put({
            "_fn": resume_workflow_background,
            "_db_job_id": db_job_id,
            "project_id": project_id,
            "project_dir": project_dir,
        })

        queue_position = job_queue.qsize()
        return {
            "project_id": project_id,
            "status": "queued",
            "message": resume_detail,
            "queue_position": queue_position,
            "has_active_workflow": len(active_workflows) > 0,
            "active_workflow_id": active_workflows[0] if active_workflows else None,
            "checkpoint": {
                "round": cp_round,
                "max_rounds": cp_max,
                "last_score": round(last_score, 1),
                "last_decision": last_decision,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume workflow: {str(e)}")


def _utcnow() -> datetime:
    """Return current time as timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _parse_start_time(iso_str: str) -> datetime:
    """Parse a start_time string, assuming UTC if no timezone info (backward compat)."""
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def add_activity_log(project_id: str, level: str, message: str, details: dict = None):
    """Add entry to activity log."""
    if project_id not in activity_logs:
        activity_logs[project_id] = []

    entry = {
        "timestamp": _utcnow().isoformat(),
        "level": level,
        "message": message,
        "details": details or {}
    }
    activity_logs[project_id].append(entry)


def calculate_cost_estimate(input_tokens: int, output_tokens: int, model: str = "claude-opus-4.5") -> dict:
    """Calculate cost estimate based on tokens and model."""
    model_price = get_pricing(model)
    input_cost = (input_tokens / 1_000_000) * model_price["input"]
    output_cost = (output_tokens / 1_000_000) * model_price["output"]

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": round(input_cost + output_cost, 4),
        "model_breakdown": {
            model: {
                "input_cost": round(input_cost, 4),
                "output_cost": round(output_cost, 4)
            }
        }
    }


async def resume_workflow_background(project_id: str, project_dir: Path):
    """Resume workflow from checkpoint in background."""
    try:
        from research_cli.workflow.orchestrator import WorkflowOrchestrator
        import json

        # Reset start_time to actual work start (excludes queue wait time)
        if project_id in workflow_status:
            workflow_status[project_id]["start_time"] = _utcnow().isoformat()

        # Load checkpoint to get max_rounds
        checkpoint_file = project_dir / "workflow_checkpoint.json"
        with open(checkpoint_file) as f:
            checkpoint = json.load(f)

        max_rounds = checkpoint.get("max_rounds", 3)
        cp_round = checkpoint.get("current_round", 0)
        cp_all_rounds = checkpoint.get("all_rounds", [])
        cp_last_score = cp_all_rounds[-1].get("overall_average", 0) if cp_all_rounds else 0
        cp_last_decision = cp_all_rounds[-1].get("moderator_decision", {}).get("decision", "N/A") if cp_all_rounds else "N/A"

        add_activity_log(project_id, "info", f"Resume started: Round {cp_round}/{max_rounds}, last score {cp_last_score:.1f}/10, decision: {cp_last_decision}")
        if project_id in workflow_status:
            workflow_status[project_id].update({
                "status": "reviewing",
                "message": f"Resuming from Round {cp_round}/{max_rounds} (score {cp_last_score:.1f}/10)",
            })

        # Status callback
        def status_update(status: str, round_num: int, message: str):
            update_workflow_status(project_id, status, round_num, max_rounds, message)

        # Resume from checkpoint
        result = await WorkflowOrchestrator.resume_from_checkpoint(
            output_dir=project_dir,
            status_callback=status_update
        )

        # Mark as completed or rejected based on actual result
        final_status = "completed" if result.get("passed") else "rejected"
        update_workflow_status(project_id, final_status, result["total_rounds"], result["total_rounds"], "Workflow completed successfully")
        _enrich_completed_status(project_id)
        add_activity_log(project_id, "success", f"Workflow completed with score {result['final_score']}/10")

    except Exception as e:
        error_str = str(e)

        # Extract stage info
        import re as _re
        stage_match = _re.match(r'\[Stage: (.+?)\]', error_str)
        stage_label = stage_match.group(1) if stage_match else ""
        clean_error = _re.sub(r'^\[Stage: .+?\]\s*', '', error_str) if stage_match else error_str

        # Checkpoint still exists (resume didn't finish) → mark as interrupted
        checkpoint_file = project_dir / "workflow_checkpoint.json"
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file) as f:
                    cp = json.load(f)
                cp_round = cp.get("current_round", 0)
                cp_max = cp.get("max_rounds", 3)
            except Exception:
                cp_round, cp_max = 0, 3

            display_msg = f"Resume failed during {stage_label} — Resume available" if stage_label else f"Error at Round {cp_round} — Resume available"

            if project_id in workflow_status:
                workflow_status[project_id].update({
                    "status": "interrupted",
                    "current_round": cp_round,
                    "total_rounds": cp_max,
                    "progress_percentage": int((cp_round / cp_max) * 100) if cp_max else 0,
                    "message": display_msg,
                    "error": clean_error,
                    "error_stage": stage_label,
                    "estimated_time_remaining_seconds": (cp_max - cp_round) * 180,
                    "can_resume": True,
                })
            add_activity_log(project_id, "warning", f"Resume interrupted during {stage_label or f'round {cp_round}'}: {clean_error}. Checkpoint preserved — try again.")
        else:
            error_msg = f"Failed during {stage_label}: {clean_error}" if stage_label else f"Workflow error: {clean_error}"
            update_workflow_status(project_id, "failed", 0, 0, error_msg)
            add_activity_log(project_id, "error", error_msg)
            if project_id in workflow_status:
                workflow_status[project_id]["error"] = clean_error
                workflow_status[project_id]["error_stage"] = stage_label


async def _generate_reviewers_from_category(
    category: dict, topic: str, secondary_category: Optional[dict] = None
) -> List[ExpertConfig]:
    """Generate reviewer ExpertConfigs using LLM based on topic and category.

    The LLM creates 3 reviewers with expertise tailored to the specific
    research topic, rather than using a fixed expert pool per category.

    Args:
        category: Dict with 'major' and 'subfield' keys.
        topic: Research topic for reviewer specialization.
        secondary_category: Optional dict with 'major' and 'subfield' for interdisciplinary topics.

    Returns:
        List of 3 ExpertConfig reviewer objects.
    """
    import logging
    logger = logging.getLogger(__name__)

    if not category or not category.get("major") or not category.get("subfield"):
        return []

    category_name = get_category_name(category["major"], category["subfield"])
    reviewer_model_list = get_reviewer_models()

    # Try LLM-based generation
    try:
        from research_cli.utils.json_repair import repair_json

        # Build secondary category context
        secondary_context = ""
        if secondary_category and secondary_category.get("major") and secondary_category.get("subfield"):
            secondary_name = get_category_name(secondary_category["major"], secondary_category["subfield"])
            secondary_context = f"\nSECONDARY CATEGORY: {secondary_name}\nAt least one reviewer should cover the intersection of the primary topic and this secondary domain.\n"

        llm = create_llm_for_role("categorizer")
        prompt = f"""You are assembling a peer review panel for an academic paper.

TOPIC: {topic}
CATEGORY: {category_name}
{secondary_context}
Propose exactly 3 reviewers, each with a distinct area of expertise relevant to this specific topic.
Each reviewer should bring a different perspective (e.g., theoretical, methodological, applied).

IMPORTANT: Use ONLY role-based titles. DO NOT use personal names like "Dr. Smith" or "Prof. Johnson".

CORRECT FORMAT EXAMPLES:
- "Machine Learning Expert"
- "Quantum Algorithms Specialist"
- "Clinical Psychology Researcher"
- "Computational Fluid Dynamics Expert"

Example output for a Machine Learning paper:
{{"reviewers": [
  {{"name": "Deep Learning Expert", "domain": "Neural Networks", "focus_areas": ["CNNs", "Transformers", "GANs"]}},
  {{"name": "Reinforcement Learning Specialist", "domain": "Sequential Decision Making", "focus_areas": ["Policy Optimization", "Multi-Agent RL", "Model-Based RL"]}},
  {{"name": "Computer Vision Researcher", "domain": "Image Analysis", "focus_areas": ["Object Detection", "Segmentation", "3D Vision"]}}
]}}

Now generate 3 reviewers for the topic above. Respond with ONLY valid JSON:"""

        response = await llm.generate(
            prompt=prompt,
            system="You propose academic peer reviewers. Use ONLY role-based titles, NOT personal names. Respond with ONLY JSON.",
            temperature=0.7,
            max_tokens=1024,
        )

        data = repair_json(response.content)
        reviewer_list = data.get("reviewers", [])

        if len(reviewer_list) < 3:
            raise ValueError(f"LLM returned {len(reviewer_list)} reviewers, expected 3")

        reviewers = []
        for i, rev in enumerate(reviewer_list[:3]):
            rm = reviewer_model_list[i % len(reviewer_model_list)]
            config = ExpertConfig(
                id=f"reviewer-{i+1}",
                name=rev.get("name", f"Reviewer {i+1}"),
                domain=rev.get("domain", "General Research"),
                focus_areas=rev.get("focus_areas", []),
                system_prompt="",
                provider=rm["provider"],
                model=rm["model"],
            )
            reviewers.append(config)

        logger.info(f"LLM generated reviewers for '{topic}': {[r.name for r in reviewers]}")
        return reviewers

    except Exception as e:
        logger.warning(f"LLM reviewer generation failed: {e}, falling back to expert pool")

    # Fallback: use category expert pool (original behavior)
    pool = get_expert_pool(category["major"], category["subfield"])
    if not pool:
        return []

    reviewers = []
    for i, expert_id in enumerate(pool[:3]):  # Take first 3
        name = expert_id.replace("_expert", "").replace("_", " ").title() + " Expert"
        domain = expert_id.replace("_expert", "").replace("_", " ").title()
        # Extract focus from expert_id as fallback
        focus_keyword = expert_id.replace("_expert", "").replace("_", " ").title()

        rm = reviewer_model_list[i % len(reviewer_model_list)]
        config = ExpertConfig(
            id=f"reviewer-{i+1}",
            name=name,
            domain=domain,
            focus_areas=[focus_keyword],  # At least one focus area from expert_id
            system_prompt="",
            provider=rm["provider"],
            model=rm["model"],
        )
        reviewers.append(config)

    return reviewers


async def run_workflow_background(
    project_id: str,
    topic: str,
    experts: List[dict],
    max_rounds: int,
    threshold: float,
    research_cycles: int = 1,
    category: Optional[dict] = None,
    article_length: str = "full",
    workflow_mode: str = "standard",
    audience_level: str = "professional",
    research_type: str = "survey",
):
    """Run workflow in background and update status."""
    try:
        # Reset start_time to actual work start (excludes queue wait time)
        if project_id in workflow_status:
            workflow_status[project_id]["start_time"] = _utcnow().isoformat()

        # Update status: composing team
        workflow_status[project_id].update({
            "status": "composing_team",
            "progress_percentage": 5,
            "message": "Composing expert team..."
        })
        add_activity_log(project_id, "info", f"Starting {workflow_mode} workflow - team composition")

        # Convert expert dicts to ExpertConfig objects
        # Reviewers use Sonnet for speed; writer (WriterAgent) uses Opus separately
        reviewer_model_list = get_reviewer_models()
        expert_configs = []
        for i, exp in enumerate(experts):
            rm = reviewer_model_list[i % len(reviewer_model_list)]
            config = ExpertConfig(
                id=f"expert-{i+1}",
                name=exp.get("expert_domain", f"Expert {i+1}"),
                domain=exp.get("expert_domain", "General"),
                focus_areas=exp.get("focus_areas", []),
                system_prompt="",  # Will be generated by SpecialistFactory
                provider=rm["provider"],
                model=rm["model"]
            )
            expert_configs.append(config)
            add_activity_log(
                project_id,
                "success",
                f"Added expert: {config.name}",
                {"model": config.model, "focus_areas": config.focus_areas}
            )

        # Cap max_rounds for short papers
        if article_length == "short" and max_rounds > 2:
            max_rounds = 2
            add_activity_log(project_id, "info", "Short paper: capped max_rounds to 2")

        status_callback = lambda status, round_num, msg: update_workflow_status(
            project_id, status, round_num, max_rounds, msg
        )

        if workflow_mode == "collaborative":
            # --- Collaborative workflow ---
            add_activity_log(project_id, "info", "Using collaborative workflow mode")

            # Build WriterTeam from experts: first = lead, rest = coauthors
            lead_exp = expert_configs[0]
            lead_author = AuthorRole(
                id=lead_exp.id,
                name=lead_exp.name,
                role="lead",
                expertise=lead_exp.domain,
                focus_areas=lead_exp.focus_areas,
                model=lead_exp.model,
            )

            coauthors = []
            for exp in expert_configs[1:]:
                coauthor = AuthorRole(
                    id=exp.id,
                    name=exp.name,
                    role="coauthor",
                    expertise=exp.domain,
                    focus_areas=exp.focus_areas,
                    model=exp.model,
                )
                coauthors.append(coauthor)

            writer_team = WriterTeam(lead_author=lead_author, coauthors=coauthors)

            add_activity_log(project_id, "info", f"Lead author: {lead_author.name}")
            for ca in coauthors:
                add_activity_log(project_id, "info", f"Co-author: {ca.name}")

            # Build secondary category dict if present
            secondary_cat = None
            if category and category.get("secondary_major") and category.get("secondary_subfield"):
                secondary_cat = {"major": category["secondary_major"], "subfield": category["secondary_subfield"]}

            # Generate reviewers from category expert pool
            reviewer_configs = await _generate_reviewers_from_category(category, topic, secondary_category=secondary_cat)
            if not reviewer_configs:
                add_activity_log(project_id, "warning", "No category reviewers found, using default reviewers")
                # Fallback: use first 2 expert configs as reviewers
                reviewer_configs = expert_configs[:2]

            for rc in reviewer_configs:
                add_activity_log(project_id, "info", f"Reviewer: {rc.name}")

            # Map article_length to target_manuscript_length
            length_map = {"short": 2000, "full": 4000}
            target_manuscript_length = length_map.get(article_length, 4000)

            major_field = category.get("major", "computer_science") if category else "computer_science"
            subfield = category.get("subfield", "theory") if category else "theory"

            # Extract secondary fields
            secondary_major = category.get("secondary_major") if category else None
            secondary_subfield = category.get("secondary_subfield") if category else None

            orchestrator = CollaborativeWorkflowOrchestrator(
                topic=topic,
                major_field=major_field,
                subfield=subfield,
                writer_team=writer_team,
                reviewer_configs=reviewer_configs,
                output_dir=Path(f"results/{project_id}"),
                max_rounds=max_rounds,
                threshold=threshold,
                target_manuscript_length=target_manuscript_length,
                research_cycles=research_cycles,
                status_callback=status_callback,
                article_length=article_length,
                research_type=research_type,
                secondary_major=secondary_major,
                secondary_subfield=secondary_subfield,
            )

            add_activity_log(project_id, "info", "Starting collaborative workflow execution")
            await orchestrator.run()
            add_activity_log(project_id, "success", "Collaborative workflow completed")

        else:
            # --- Standard workflow (unchanged) ---
            orchestrator = WorkflowOrchestrator(
                expert_configs=expert_configs,
                topic=topic,
                max_rounds=max_rounds,
                threshold=threshold,
                output_dir=Path(f"results/{project_id}"),
                status_callback=status_callback,
                category=category,
                article_length=article_length,
                audience_level=audience_level,
                research_type=research_type,
            )

            add_activity_log(project_id, "info", "Starting standard workflow execution")
            await orchestrator.run()
            add_activity_log(project_id, "success", "Workflow execution completed")

        # Read actual cost from workflow_complete.json (written by orchestrator)
        try:
            complete_file = Path(f"results/{project_id}/workflow_complete.json")
            if complete_file.exists():
                with open(complete_file) as f:
                    wf_data = json.load(f)
                perf = wf_data.get("performance", {})
                cost_info = {
                    "total_tokens": perf.get("total_tokens", 0),
                    "estimated_cost_usd": perf.get("estimated_cost", 0),
                    "tokens_by_model": perf.get("tokens_by_model", {}),
                }
                workflow_status[project_id]["cost_estimate"] = cost_info
        except Exception:
            pass  # Non-critical

        # Update status based on actual result (completed vs rejected)
        _enrich_completed_status(project_id)
        enriched_status = workflow_status.get(project_id, {}).get("status", "completed")
        if enriched_status not in ("completed", "rejected"):
            workflow_status[project_id].update({
                "status": "completed",
                "progress_percentage": 100,
                "message": "Workflow completed successfully",
                "estimated_time_remaining_seconds": 0
            })
            add_activity_log(project_id, "success", "Workflow completed successfully")

    except Exception as e:
        # Check if a checkpoint exists — if so, mark as "interrupted" (resumable)
        checkpoint_file = Path(f"results/{project_id}/workflow_checkpoint.json")
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file) as f:
                    cp = json.load(f)
                cp_round = cp.get("current_round", 0)
                cp_max = cp.get("max_rounds", 3)
            except Exception:
                cp_round, cp_max = 0, 3

            # Extract stage info from error message if available
            error_str = str(e)
            stage_label = ""
            import re as _re
            stage_match = _re.match(r'\[Stage: (.+?)\]', error_str)
            if stage_match:
                stage_label = stage_match.group(1)
                # Clean the stage prefix from stored error for readability
                clean_error = _re.sub(r'^\[Stage: .+?\]\s*', '', error_str)
            else:
                clean_error = error_str

            display_msg = f"Error during {stage_label} — Resume available" if stage_label else f"Error at Round {cp_round} — Resume available"

            workflow_status[project_id].update({
                "status": "interrupted",
                "current_round": cp_round,
                "total_rounds": cp_max,
                "progress_percentage": int((cp_round / cp_max) * 100) if cp_max else 0,
                "message": display_msg,
                "error": clean_error,
                "error_stage": stage_label,
                "estimated_time_remaining_seconds": (cp_max - cp_round) * 180,
                "can_resume": True,
            })
            add_activity_log(project_id, "warning", f"Workflow interrupted during {stage_label or f'round {cp_round}'}: {clean_error}. Checkpoint saved — resume available.")
        else:
            error_str = str(e)
            import re as _re
            stage_match = _re.match(r'\[Stage: (.+?)\]', error_str)
            stage_label = stage_match.group(1) if stage_match else ""
            clean_error = _re.sub(r'^\[Stage: .+?\]\s*', '', error_str) if stage_match else error_str
            display_msg = f"Failed during {stage_label}" if stage_label else "Workflow failed"

            workflow_status[project_id].update({
                "status": "failed",
                "progress_percentage": 0,
                "message": display_msg,
                "error": clean_error,
                "error_stage": stage_label,
                "estimated_time_remaining_seconds": 0,
            })
            add_activity_log(project_id, "error", f"Workflow failed during {stage_label or 'execution'}: {clean_error}")


def _enrich_completed_status(project_id: str):
    """Read workflow_complete.json and enrich in-memory status with round/score data."""
    try:
        complete_file = Path(f"results/{project_id}/workflow_complete.json")
        if not complete_file.exists():
            return
        with open(complete_file) as f:
            data = json.load(f)

        rounds_summary = []
        for r in data.get("rounds", []):
            mod_decision = r.get("moderator_decision", {})
            rounds_summary.append({
                "round": r.get("round", r.get("round_number", 0)),
                "score": r.get("overall_average", 0),
                "decision": mod_decision.get("decision", "") if isinstance(mod_decision, dict) else "",
            })

        passed = data.get("passed", False)
        perf = data.get("performance", {})
        workflow_status[project_id].update({
            "status": "completed" if passed else "rejected",
            "progress_percentage": 100,
            "message": "Workflow completed successfully",
            "estimated_time_remaining_seconds": 0,
            "rounds": rounds_summary,
            "final_score": data.get("final_score"),
            "final_decision": "ACCEPT" if passed else (
                rounds_summary[-1]["decision"] if rounds_summary else "UNKNOWN"
            ),
            "total_rounds": data.get("total_rounds", len(rounds_summary)),
            "total_tokens": perf.get("total_tokens", 0),
            "estimated_cost": perf.get("estimated_cost", 0),
            "research_type": data.get("research_type", workflow_status[project_id].get("research_type", "research")),
            "title": data.get("title"),  # May be None for legacy articles
            "system_version": data.get("system_version", "legacy"),  # "legacy" for old articles
            "generated_at": data.get("generated_at"),  # May be None for legacy articles
        })
    except Exception:
        pass  # Non-critical: don't break workflow on enrichment failure


def update_workflow_status(project_id: str, status: str, round_num: int, total_rounds: int, message: str):
    """Update workflow status."""
    if project_id not in workflow_status:
        return

    # Calculate progress
    if status == "research":
        progress = 8
        add_activity_log(project_id, "info", message)
    elif status == "writing_sections":
        progress = 15
        add_activity_log(project_id, "info", message)
    elif status == "writing":
        progress = 10
        add_activity_log(project_id, "info", message)
    elif status == "desk_screening":
        progress = 8
        add_activity_log(project_id, "info", "Editor screening manuscript...")
    elif status == "reviewing":
        # Progress based on current round within review phase (10-80%)
        review_progress = (round_num / total_rounds) * 70
        progress = 10 + review_progress
        add_activity_log(project_id, "info", f"Round {round_num}/{total_rounds}: {message}")
    elif status == "revising":
        # Progress during revision (slightly ahead of review progress)
        review_progress = (round_num / total_rounds) * 70
        progress = 10 + review_progress + 5
        add_activity_log(project_id, "info", f"Round {round_num}/{total_rounds}: Revising manuscript")
    elif status == "completed":
        progress = 100
        add_activity_log(project_id, "success", "All rounds completed")
    else:
        progress = workflow_status[project_id]["progress_percentage"]
        add_activity_log(project_id, "info", message)

    # Update estimated time remaining
    start_time = _parse_start_time(workflow_status[project_id].get("start_time", _utcnow().isoformat()))
    elapsed = (_utcnow() - start_time).total_seconds()

    if progress > 5 and progress < 100:  # Only estimate if we have meaningful progress
        estimated_total = (elapsed / progress) * 100
        estimated_remaining = max(0, int(estimated_total - elapsed))
    elif progress >= 100:
        estimated_remaining = 0
    else:
        # Initial estimate based on typical workflow
        estimated_remaining = workflow_status[project_id].get("estimated_time_remaining_seconds", total_rounds * 180)

    workflow_status[project_id].update({
        "status": status,
        "current_round": round_num,
        "progress_percentage": int(progress),
        "message": message,
        "estimated_time_remaining_seconds": estimated_remaining
    })


# --- Projects API: serve directly from results/ ---

def _extract_title(markdown_text: str) -> Optional[str]:
    """Extract the first H1 heading as the article title."""
    for line in markdown_text.split('\n'):
        match = re.match(r'^#\s+(.+)', line)
        if match:
            return match.group(1).strip()
    return None


def _get_latest_manuscript(project_dir: Path) -> tuple[Optional[str], Optional[str]]:
    """Get the latest manuscript text and its version key from a project dir.

    Returns (manuscript_text, version_key) or (None, None).
    """
    manuscripts = {}
    for f in project_dir.glob("manuscript_*.md"):
        manuscripts[f.stem] = f.read_text(encoding="utf-8")
    if not manuscripts:
        return None, None
    versioned = [k for k in manuscripts if '_v' in k]
    if versioned:
        latest_key = max(versioned, key=lambda x: int(x.split('_v')[1]))
    else:
        latest_key = 'manuscript_final' if 'manuscript_final' in manuscripts else list(manuscripts.keys())[0]
    return manuscripts[latest_key], latest_key


def _build_project_summary(project_dir: Path) -> Optional[dict]:
    """Build a project summary dict from a results/ subdirectory."""
    workflow_file = project_dir / "workflow_complete.json"
    if not workflow_file.exists():
        return None

    try:
        with open(workflow_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    project_id = project_dir.name

    # Determine status from final round decision
    rounds = data.get("rounds", [])
    final_decision = "PENDING"
    if rounds:
        final_decision = rounds[-1].get("moderator_decision", {}).get("decision", "PENDING")
    if final_decision in ("ACCEPT", "MINOR_REVISION"):
        status = "completed"
    elif data.get("uploaded") and data.get("passed"):
        # Uploaded external reports bypass review — treat as completed
        status = "completed"
        final_decision = "UPLOADED"
    else:
        # REJECT, MAJOR_REVISION → editorial rejection
        status = "rejected"

    # Round summaries
    rounds_summary = []
    for rd in rounds:
        rounds_summary.append({
            "round": rd.get("round", 0),
            "score": rd.get("overall_average", 0),
            "decision": rd.get("moderator_decision", {}).get("decision", ""),
            "passed": rd.get("passed", False),
        })

    # Extract title: prefer workflow_complete.json (new articles), fallback to manuscript H1 (legacy articles)
    title = data.get("title")
    if not title:
        manuscript_text, _ = _get_latest_manuscript(project_dir)
        title = _extract_title(manuscript_text) if manuscript_text else None

    # Word count from last round
    word_count = rounds[-1].get("word_count", 0) if rounds else 0

    performance = data.get("performance", {})
    category = data.get("category")

    # Calculate total tokens from all rounds (review + moderator tokens)
    total_tokens = 0
    for rd in rounds:
        total_tokens += sum(rev.get("tokens", 0) for rev in rd.get("reviews", []))
        total_tokens += rd.get("moderator_decision", {}).get("tokens", 0)

    # Calculate elapsed time: prefer wall-clock (workflow_start → workflow_end),
    # then total_duration, then sum of round durations as last resort
    elapsed_seconds = 0
    ws = performance.get("workflow_start", "")
    we = performance.get("workflow_end", "")
    if ws and we:
        try:
            start_dt_perf = datetime.fromisoformat(ws)
            end_dt_perf = datetime.fromisoformat(we)
            elapsed_seconds = int((end_dt_perf - start_dt_perf).total_seconds())
        except (ValueError, TypeError):
            pass
    if not elapsed_seconds:
        elapsed_seconds = int(performance.get("total_duration", 0))
    if not elapsed_seconds:
        perf_rounds = performance.get("rounds", [])
        if perf_rounds:
            elapsed_seconds = int(sum(r.get("review_duration", 0) + (r.get("revision_time", 0) or 0) for r in perf_rounds))
            elapsed_seconds += int(performance.get("initial_draft_time", 0))
            elapsed_seconds += int(performance.get("team_composition_time", 0))

    # Use performance total_tokens if available (more comprehensive than round-level sum)
    perf_tokens = performance.get("total_tokens", 0)
    if perf_tokens > total_tokens:
        total_tokens = perf_tokens

    start_time_str = ""
    ts_match = re.search(r'(\d{8}-\d{6})$', project_id)
    if ts_match:
        try:
            start_dt = datetime.strptime(ts_match.group(1), "%Y%m%d-%H%M%S")
            start_time_str = start_dt.isoformat()
        except (ValueError, TypeError):
            pass

    return {
        "id": project_id,
        "title": title,
        "topic": data.get("topic", project_id.replace("-", " ").title()),
        "system_version": data.get("system_version", "legacy"),
        "generated_at": data.get("generated_at"),
        "final_score": data.get("final_score", 0),
        "passed": data.get("passed", False),
        "status": status,
        "total_rounds": data.get("total_rounds", 0),
        "rounds": rounds_summary,
        "timestamp": data.get("timestamp", ""),
        "start_time": start_time_str,
        "elapsed_time_seconds": elapsed_seconds,
        "final_decision": final_decision,
        "word_count": word_count,
        "category": category,
        "total_tokens": total_tokens,
        "estimated_cost": round(performance.get("estimated_cost", 0), 4),
        "expert_team": data.get("expert_team", []),
        "audience_level": data.get("audience_level", "professional"),
        "research_type": data.get("research_type", None),
    }


@app.get("/api/projects")
async def list_projects():
    """List all completed projects from results/ directory."""
    results_dir = Path("results")
    if not results_dir.exists():
        return {"projects": [], "updated_at": datetime.now().isoformat()}

    projects = []
    for project_dir in results_dir.iterdir():
        if not project_dir.is_dir():
            continue
        summary = _build_project_summary(project_dir)
        if summary:
            projects.append(summary)

    # Sort by timestamp (newest first)
    projects.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {"projects": projects, "updated_at": datetime.now().isoformat()}


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    """Get full workflow data for a project."""
    project_dir = Path("results") / project_id
    workflow_file = project_dir / "workflow_complete.json"

    if not workflow_file.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        with open(workflow_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Error reading project data: {e}")

    return data


@app.get("/api/projects/{project_id}/manuscripts")
async def get_project_manuscripts(project_id: str):
    """Get all manuscript versions for a project, with citation hyperlinks applied."""
    project_dir = Path("results") / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    manuscripts = {}
    for f in project_dir.glob("manuscript_*.md"):
        text = f.read_text(encoding="utf-8")
        # Apply citation hyperlinks
        text = CitationManager.add_citation_hyperlinks(text)
        manuscripts[f.stem] = text

    if not manuscripts:
        raise HTTPException(status_code=404, detail="No manuscripts found")

    return manuscripts


# --- Reviewer Enrichment ---

class ProposeReviewersRequest(BaseModel):
    topic: str
    major_field: str
    subfield: str
    secondary_major_field: Optional[str] = None
    secondary_subfield: Optional[str] = None


@app.post("/api/propose-reviewers")
async def propose_reviewers(request: ProposeReviewersRequest):
    """Generate reviewers dynamically using gemini-flash based on topic and category."""
    try:
        category = {"major": request.major_field, "subfield": request.subfield}
        secondary = None
        if request.secondary_major_field and request.secondary_subfield:
            secondary = {"major": request.secondary_major_field, "subfield": request.secondary_subfield}
        reviewer_configs = await _generate_reviewers_from_category(category, request.topic, secondary_category=secondary)

        if not reviewer_configs:
            raise HTTPException(status_code=500, detail="Failed to generate reviewers for this category")

        # Convert ExpertConfig to response format
        reviewer_profiles = [
            {
                "expert_id": config.id,
                "display_name": config.name,
                "description": config.domain,
                "focus_areas": config.focus_areas,
                "relevance_to_topic": f"Specializes in {config.domain}",
            }
            for config in reviewer_configs
        ]

        return {"proposed_reviewers": reviewer_profiles}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reviewer generation failed: {str(e)}")


@app.get("/api/version")
async def get_version():
    """Get system version and changelog information."""
    version_file = Path("VERSION")
    changelog_file = Path("CHANGELOG.md")

    version = "unknown"
    if version_file.exists():
        version = version_file.read_text().strip()

    changelog = ""
    if changelog_file.exists():
        changelog = changelog_file.read_text()

    return {
        "version": version,
        "changelog": changelog,
        "updated_at": datetime.now().isoformat()
    }


@app.get("/api/check-admin")
async def check_admin(request: Request):
    """Check if the current API key has admin privileges."""
    key = request.headers.get("X-API-Key")
    is_admin = bool(ADMIN_API_KEY and key == ADMIN_API_KEY)
    # No admin key configured → dev mode: everyone is admin
    if not ADMIN_API_KEY:
        is_admin = True
    return {"is_admin": is_admin}


@app.delete("/api/workflows/{project_id}")
async def delete_workflow(project_id: str, api_key: str = Depends(verify_admin_key)):
    """Delete a workflow (admin only). Only interrupted/completed/failed workflows can be deleted."""
    results_path = Path(f"results/{project_id}")

    if project_id in workflow_status:
        status = workflow_status[project_id]["status"]
        deletable_statuses = {"interrupted", "completed", "failed", "rejected"}
        if status not in deletable_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete workflow in '{status}' state. Only {', '.join(sorted(deletable_statuses))} workflows can be deleted."
            )
        del workflow_status[project_id]
        activity_logs.pop(project_id, None)
    elif not results_path.exists():
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Remove results directory
    import shutil
    results_path = Path(f"results/{project_id}")
    if results_path.exists():
        shutil.rmtree(results_path)

    # Remove article HTML
    article_path = Path(f"web/articles/{project_id}.html")
    if article_path.exists():
        article_path.unlink()

    # Remove from index.json
    index_path = Path("web/data/index.json")
    if index_path.exists():
        try:
            with open(index_path) as f:
                index_data = json.load(f)
            index_data["projects"] = [
                p for p in index_data.get("projects", [])
                if p.get("id") != project_id
            ]
            index_data["updated_at"] = datetime.now().isoformat()
            with open(index_path, "w") as f:
                json.dump(index_data, f, indent=2)
        except Exception:
            pass  # Non-critical: index.json update failure shouldn't block deletion

    return {"message": f"Workflow '{project_id}' deleted", "project_id": project_id}


# --- Admin: Dynamic API Key Management ---

@app.get("/api/admin/keys")
async def list_keys(api_key: str = Depends(verify_admin_key)):
    """List all API keys (admin only)."""
    keys = appdb.list_api_keys()
    return {"keys": [
        {
            "key_prefix": entry["key"][:8] + "...",
            "label": entry.get("label", ""),
            "created": entry.get("created_at", ""),
            "revoked": entry.get("revoked_at"),
            "daily_quota": entry.get("daily_quota", 10),
            "researcher_name": entry.get("name"),
            "researcher_email": entry.get("email"),
        }
        for entry in keys
    ]}


class CreateKeyRequest(BaseModel):
    label: str = ""


@app.post("/api/admin/keys")
async def create_key(request: CreateKeyRequest, api_key: str = Depends(verify_admin_key)):
    """Generate a new API key (admin only)."""
    result = appdb.create_api_key_direct(label=request.label)
    return {"key": result["key"], "label": request.label, "message": "Key created. Copy it now — it will not be shown again."}


@app.delete("/api/admin/keys/{key_prefix}")
async def delete_key(key_prefix: str, api_key: str = Depends(verify_admin_key)):
    """Revoke an API key by its prefix (admin only)."""
    revoked = appdb.revoke_api_key(key_prefix)
    if not revoked:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"message": "Key revoked", "deleted": revoked}


@app.post("/api/submit-article")
async def submit_article(request: SubmitArticleRequest, api_key: str = Depends(verify_api_key)):
    """Direct article submission (no AI workflow). Saves article to web/articles/ and updates index.json."""
    try:
        # Generate project ID from title (sanitize: lowercase, hyphens, strip control chars)
        project_id = re.sub(r'[^a-z0-9\-]', '-', request.title.lower().replace(" ", "-"))
        project_id = re.sub(r'-{2,}', '-', project_id).strip('-')
        project_id = f"{project_id[:80]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # Escape markdown for JS embedding
        # Only escape ${ (JS template literal interpolation), not bare $ (needed for KaTeX math)
        escaped_markdown = (
            request.content
            .replace('\\', '\\\\')
            .replace('`', '\\`')
            .replace('${', '\\${')
        )

        # Extract headings for TOC
        import re
        headings = []
        for line in request.content.split('\n'):
            match = re.match(r'^##\s+(.+)', line)
            if match:
                title = match.group(1).strip()
                slug = re.sub(r'[^\w\s-]', '', title.lower()).replace(' ', '-')
                headings.append({"title": title, "slug": slug})

        toc_items = '\n'.join([
            f'                        <li><a href="#{h["slug"]}">{h["title"]}</a></li>'
            for h in headings[:10]
        ])

        # Generate HTML article (same template as export_to_web.py)
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{request.title} | Autonomous Research Press</title>
    <meta name="description" content="{request.title} - Direct submission">
    <link rel="icon" type="image/svg+xml" href="../favicon.svg">
    <link rel="stylesheet" href="../styles/main.css">
    <link rel="stylesheet" href="../styles/article.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css">
</head>
<body>
    <header class="site-header">
        <div class="container">
            <div class="header-nav">
                <a href="../index.html" class="back-link">
                    <svg viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clip-rule="evenodd"/>
                    </svg>
                    Back to Research
                </a>
                <div class="header-content">
                    <h1 class="site-title">Autonomous Research Press</h1>
                    <p class="site-subtitle">Autonomous Research Platform</p>
                </div>
                <button class="theme-toggle" aria-label="Toggle dark mode">
                    <svg class="sun-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="5"></circle>
                        <line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line>
                        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                        <line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line>
                        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
                    </svg>
                    <svg class="moon-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                    </svg>
                </button>
            </div>
        </div>
    </header>
    <main class="article-layout">
        <aside class="toc-sidebar">
            <div class="toc-sticky">
                <h3 class="toc-title">On This Page</h3>
                <nav class="toc-nav">
                    <ul>
{toc_items}
                    </ul>
                </nav>
            </div>
        </aside>
        <article class="research-report">
            <header class="article-header">
                <h1 class="article-title">{request.title}</h1>
                <div class="article-meta">
                    <span class="meta-item"><strong>Author:</strong> {request.author}</span>
                    <span class="meta-item"><strong>Source:</strong> Direct Submission</span>
                    <span class="meta-item"><strong>Date:</strong> {datetime.now().strftime("%Y-%m-%d")}</span>
                </div>
            </header>
            <div id="article-content"></div>
        </article>
    </main>
    <footer class="site-footer">
        <div class="container">
            <p><strong>Platform:</strong> Autonomous Research Press</p>
            <p class="copyright">2026 Autonomous Research Press. All rights reserved.</p>
        </div>
    </footer>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/contrib/auto-render.min.js"></script>
    <script src="../js/main.js"></script>
    <script>
        // Protect math blocks from marked processing
        const rawMarkdown = `{escaped_markdown}`;
        const mathBlocks = [];
        let protectedContent = rawMarkdown
            .replace(/\\$\\$[\\s\\S]+?\\$\\$/g, match => {{
                mathBlocks.push(match);
                return `%%MATH_BLOCK_${{mathBlocks.length - 1}}%%`;
            }})
            .replace(/\\$(?!\\$)([^\\$\\n]+?)\\$/g, match => {{
                mathBlocks.push(match);
                return `%%MATH_BLOCK_${{mathBlocks.length - 1}}%%`;
            }});

        // Parse markdown (math is safely extracted)
        let htmlContent = marked.parse(protectedContent);

        // Restore math blocks
        mathBlocks.forEach((block, i) => {{
            htmlContent = htmlContent.replace(`%%MATH_BLOCK_${{i}}%%`, block);
        }});

        document.getElementById('article-content').innerHTML = htmlContent;

        // Render math with KaTeX
        function renderMath() {{
            if (window.renderMathInElement) {{
                renderMathInElement(document.getElementById('article-content'), {{
                    delimiters: [
                        {{left: '$$', right: '$$', display: true}},
                        {{left: '$', right: '$', display: false}},
                        {{left: '\\\\(', right: '\\\\)', display: false}},
                        {{left: '\\\\[', right: '\\\\]', display: true}}
                    ],
                    throwOnError: false
                }});
            }} else {{
                setTimeout(renderMath, 100);
            }}
        }}
        renderMath();
    </script>
</body>
</html>'''

        # Save article HTML
        articles_dir = Path("web/articles")
        articles_dir.mkdir(parents=True, exist_ok=True)
        article_path = articles_dir / f"{project_id}.html"
        article_path.write_text(html, encoding="utf-8")

        # Update index.json
        index_path = Path("web/data/index.json")
        index_data = {"projects": [], "updated_at": datetime.now().isoformat()}
        if index_path.exists():
            with open(index_path) as f:
                index_data = json.load(f)

        new_entry = {
            "id": project_id,
            "topic": request.title,
            "final_score": None,
            "passed": True,
            "status": "completed",
            "total_rounds": 0,
            "rounds": [],
            "timestamp": _utcnow().isoformat(),
            "data_file": None,
            "elapsed_time_seconds": 0,
            "final_decision": "DIRECT_SUBMISSION",
            "source": "direct_submission",
            "author": request.author,
        }

        index_data["projects"].insert(0, new_entry)
        index_data["updated_at"] = datetime.now().isoformat()

        with open(index_path, "w") as f:
            json.dump(index_data, f, indent=2)

        return {
            "project_id": project_id,
            "status": "published",
            "article_url": f"/articles/{project_id}.html",
            "message": "Article published successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit article: {str(e)}")


# --- Manuscript Submission (External Peer Review) ---

class SubmitManuscriptRequest(BaseModel):
    title: str
    content: str  # Markdown
    category: CategoryInfo


class ReviseManuscriptRequest(BaseModel):
    content: str  # Revised Markdown
    author_response: Optional[str] = None


def _check_expired_submission(sub: dict) -> dict:
    """Check if an awaiting_revision submission is past its deadline; expire it if so."""
    if sub["status"] == "awaiting_revision" and sub.get("revision_deadline"):
        try:
            deadline = datetime.fromisoformat(sub["revision_deadline"])
            now = datetime.now(timezone.utc)
            if now > deadline:
                appdb.update_submission_status(
                    sub["id"], "expired",
                    final_decision="EXPIRED",
                )
                sub["status"] = "expired"
                sub["final_decision"] = "EXPIRED"
        except (ValueError, TypeError):
            pass
    return sub


@app.post("/api/submit-manuscript")
async def submit_manuscript(request: SubmitManuscriptRequest, api_key: str = Depends(verify_api_key)):
    """Submit a manuscript for AI peer review."""
    # Rate limit
    await check_rate_limit(api_key)

    # Validate content
    word_count = len(request.content.split())
    if word_count < 500:
        raise HTTPException(status_code=400, detail=f"Manuscript too short ({word_count} words). Minimum 500 words required.")
    if word_count > 50000:
        raise HTTPException(status_code=400, detail=f"Manuscript too long ({word_count} words). Maximum 50,000 words.")
    if not request.title or not request.title.strip():
        raise HTTPException(status_code=400, detail="Title is required.")
    if not request.category or not request.category.major or not request.category.subfield:
        raise HTTPException(status_code=400, detail="Category (major + subfield) is required.")

    # Get researcher_id from api_key
    db_key = appdb.get_api_key(api_key)
    researcher_id = db_key["researcher_id"] if db_key else None

    # Create DB record
    sub = appdb.create_submission(
        researcher_id=researcher_id,
        api_key=api_key,
        title=request.title,
        category_major=request.category.major,
        category_subfield=request.category.subfield,
        deadline_hours=24,
    )
    submission_id = sub["id"]

    # Save manuscript file
    sub_dir = Path(f"results/submissions/{submission_id}")
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / "manuscript_v1.md").write_text(request.content, encoding="utf-8")

    # Record usage
    if api_key not in ("anonymous",):
        try:
            appdb.record_usage(api_key, "/api/submit-manuscript", submission_id)
        except Exception:
            pass

    # Persist job to DB and enqueue
    db_job_id = str(uuid.uuid4())
    job_payload = {
        "project_id": f"sub-{submission_id}",
        "submission_id": submission_id,
        "round_number": 1,
        "is_first_round": True,
    }
    try:
        appdb.enqueue_job(db_job_id, f"sub-{submission_id}", "submission_review", job_payload)
    except Exception:
        pass
    await job_queue.put({
        "_fn": run_submission_review_background,
        "_db_job_id": db_job_id,
        **job_payload,
    })

    return {
        "submission_id": submission_id,
        "status": "pending",
        "message": "Manuscript submitted. Review will begin shortly.",
    }


@app.get("/api/submission/{submission_id}")
async def get_submission(submission_id: str, api_key: str = Depends(verify_api_key)):
    """Get submission details (owner only)."""
    sub = appdb.get_submission(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Ownership check
    if sub["api_key"] != api_key and api_key != ADMIN_API_KEY:
        # Dev mode: no admin key configured → allow all
        if ADMIN_API_KEY:
            raise HTTPException(status_code=403, detail="Not authorized to view this submission")

    # Check expiration
    sub = _check_expired_submission(sub)

    # Calculate remaining hours for awaiting_revision
    remaining_hours = None
    if sub["status"] == "awaiting_revision" and sub.get("revision_deadline"):
        try:
            deadline = datetime.fromisoformat(sub["revision_deadline"])
            now = datetime.now(timezone.utc)
            remaining = (deadline - now).total_seconds() / 3600
            remaining_hours = max(0, round(remaining, 1))
        except (ValueError, TypeError):
            pass

    return {
        "id": sub["id"],
        "title": sub["title"],
        "status": sub["status"],
        "current_round": sub["current_round"],
        "max_rounds": sub["max_rounds"],
        "category_major": sub["category_major"],
        "category_subfield": sub["category_subfield"],
        "final_decision": sub.get("final_decision"),
        "final_score": sub.get("final_score"),
        "revision_deadline": sub.get("revision_deadline"),
        "remaining_hours": remaining_hours,
        "deadline_hours": sub.get("deadline_hours", 24),
        "created_at": sub["created_at"],
        "updated_at": sub["updated_at"],
        "rounds": [
            {
                "round_number": rd["round_number"],
                "manuscript_version": rd["manuscript_version"],
                "word_count": rd.get("word_count"),
                "reviews": rd.get("reviews_json", []),
                "overall_average": rd.get("overall_average"),
                "moderator_decision": rd.get("moderator_decision_json"),
                "started_at": rd.get("started_at"),
                "completed_at": rd.get("completed_at"),
            }
            for rd in sub.get("rounds", [])
        ],
    }


@app.post("/api/submission/{submission_id}/revise")
async def revise_submission(submission_id: str, request: ReviseManuscriptRequest, api_key: str = Depends(verify_api_key)):
    """Submit a revised manuscript for the next review round."""
    await check_rate_limit(api_key)

    sub = appdb.get_submission(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Ownership check
    if sub["api_key"] != api_key and api_key != ADMIN_API_KEY:
        if ADMIN_API_KEY:
            raise HTTPException(status_code=403, detail="Not authorized")

    # Check expiration first
    sub = _check_expired_submission(sub)

    if sub["status"] != "awaiting_revision":
        raise HTTPException(status_code=400, detail=f"Cannot revise: submission status is '{sub['status']}', expected 'awaiting_revision'")

    # Validate content
    word_count = len(request.content.split())
    if word_count < 500:
        raise HTTPException(status_code=400, detail=f"Revised manuscript too short ({word_count} words).")
    if word_count > 50000:
        raise HTTPException(status_code=400, detail=f"Revised manuscript too long ({word_count} words). Maximum 50,000 words.")

    next_round = sub["current_round"] + 1
    if next_round > sub["max_rounds"]:
        raise HTTPException(status_code=400, detail="Maximum review rounds reached.")

    # Save revised manuscript
    sub_dir = Path(f"results/submissions/{submission_id}")
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / f"manuscript_v{next_round}.md").write_text(request.content, encoding="utf-8")

    # Save author response if provided
    if request.author_response:
        (sub_dir / f"author_response_round_{next_round}.md").write_text(
            request.author_response, encoding="utf-8"
        )

    # Update status
    appdb.update_submission_status(submission_id, "reviewing", current_round=next_round)

    # Persist job to DB and enqueue
    db_job_id = str(uuid.uuid4())
    job_payload = {
        "project_id": f"sub-{submission_id}-r{next_round}",
        "submission_id": submission_id,
        "round_number": next_round,
        "is_first_round": False,
    }
    try:
        appdb.enqueue_job(db_job_id, f"sub-{submission_id}-r{next_round}", "submission_review", job_payload)
    except Exception:
        pass
    await job_queue.put({
        "_fn": run_submission_review_background,
        "_db_job_id": db_job_id,
        **job_payload,
    })

    return {
        "submission_id": submission_id,
        "status": "reviewing",
        "round": next_round,
        "message": f"Revised manuscript submitted for round {next_round} review.",
    }


@app.get("/api/my-submissions")
async def get_my_submissions(api_key: str = Depends(verify_api_key)):
    """Get all submissions for the authenticated user."""
    # Expire overdue first
    appdb.expire_overdue_submissions()

    subs = appdb.get_submissions_by_key(api_key)

    results = []
    for s in subs:
        remaining_hours = None
        if s["status"] == "awaiting_revision" and s.get("revision_deadline"):
            try:
                deadline = datetime.fromisoformat(s["revision_deadline"])
                now = datetime.now(timezone.utc)
                remaining = (deadline - now).total_seconds() / 3600
                remaining_hours = max(0, round(remaining, 1))
            except (ValueError, TypeError):
                pass

        results.append({
            "id": s["id"],
            "title": s["title"],
            "status": s["status"],
            "current_round": s["current_round"],
            "max_rounds": s["max_rounds"],
            "final_decision": s.get("final_decision"),
            "final_score": s.get("final_score"),
            "remaining_hours": remaining_hours,
            "created_at": s["created_at"],
            "updated_at": s["updated_at"],
        })

    return {"submissions": results}


async def run_submission_review_background(
    project_id: str,
    submission_id: str,
    round_number: int,
    is_first_round: bool = False,
):
    """Run AI peer review for an externally submitted manuscript."""
    from research_cli.agents.desk_editor import DeskEditorAgent
    from research_cli.agents.moderator import ModeratorAgent
    from research_cli.agents.specialist_factory import SpecialistFactory
    from research_cli.workflow.orchestrator import generate_review
    from research_cli.performance import PerformanceTracker

    try:
        sub = appdb.get_submission(submission_id)
        if not sub:
            return

        # Load manuscript
        sub_dir = Path(f"results/submissions/{submission_id}")
        manuscript_file = sub_dir / f"manuscript_v{round_number}.md"
        if not manuscript_file.exists():
            appdb.update_submission_status(submission_id, "rejected", final_decision="ERROR")
            return
        manuscript = manuscript_file.read_text(encoding="utf-8")
        word_count = len(manuscript.split())

        # Update status
        appdb.update_submission_status(submission_id, "desk_review" if is_first_round else "reviewing", current_round=round_number)

        # Round 1: desk screening
        if is_first_round:
            desk_editor = DeskEditorAgent()
            desk_result = await desk_editor.screen(manuscript, sub["title"])

            if desk_result["decision"] == "DESK_REJECT":
                appdb.update_submission_status(
                    submission_id, "rejected",
                    final_decision="DESK_REJECT",
                )
                # Save desk reject as round data
                appdb.save_submission_round(
                    submission_id, round_number,
                    reviews=[],
                    overall_average=0,
                    moderator_decision={"decision": "DESK_REJECT", "reason": desk_result["reason"]},
                    word_count=word_count,
                )
                # Save to file
                with open(sub_dir / "round_1_decision.json", "w") as f:
                    json.dump({"decision": "DESK_REJECT", "reason": desk_result["reason"]}, f, indent=2)
                return

            appdb.update_submission_status(submission_id, "reviewing", current_round=round_number)

        # Generate reviewers from category
        category = {"major": sub["category_major"], "subfield": sub["category_subfield"]}
        reviewer_configs = await _generate_reviewers_from_category(category, sub["title"])

        if not reviewer_configs:
            # Fallback: generate generic reviewers
            reviewer_model_list = get_reviewer_models()
            reviewer_configs = [
                ExpertConfig(
                    id=f"reviewer-{i+1}",
                    name=f"Reviewer {i+1}",
                    domain="General Research",
                    focus_areas=[],
                    system_prompt="",
                    provider=reviewer_model_list[i % len(reviewer_model_list)]["provider"],
                    model=reviewer_model_list[i % len(reviewer_model_list)]["model"],
                )
                for i in range(3)
            ]

        # Build specialists dict for review
        specialists = {}
        for rc in reviewer_configs:
            spec = SpecialistFactory.create_specialist(rc, sub["title"])
            specialists[rc.id] = spec

        # Get previous round data for context
        previous_reviews = None
        previous_manuscript = None
        author_response = None
        if round_number > 1 and sub.get("rounds"):
            prev_round = next(
                (r for r in sub["rounds"] if r["round_number"] == round_number - 1),
                None
            )
            if prev_round:
                previous_reviews = prev_round.get("reviews_json", [])
                prev_ms_file = sub_dir / f"manuscript_v{round_number - 1}.md"
                if prev_ms_file.exists():
                    previous_manuscript = prev_ms_file.read_text(encoding="utf-8")
            # Load author response for this round
            ar_file = sub_dir / f"author_response_round_{round_number}.md"
            if ar_file.exists():
                author_response = ar_file.read_text(encoding="utf-8")

        # Run reviews concurrently
        tracker = PerformanceTracker()
        tracker.start_round(round_number)

        review_tasks = [
            generate_review(
                specialist_id=sid,
                specialist=spec,
                manuscript=manuscript,
                round_number=round_number,
                tracker=tracker,
                previous_reviews=previous_reviews,
                previous_manuscript=previous_manuscript,
                author_response=author_response,
            )
            for sid, spec in specialists.items()
        ]

        reviews = []
        for coro in asyncio.as_completed(review_tasks):
            review = await coro
            reviews.append(review)

        overall_average = sum(r["average"] for r in reviews) / len(reviews) if reviews else 0

        # Get previous rounds for moderator trajectory analysis
        previous_rounds = []
        if sub.get("rounds"):
            for rd in sub["rounds"]:
                previous_rounds.append({
                    "round": rd["round_number"],
                    "overall_average": rd.get("overall_average", 0),
                    "moderator_decision": rd.get("moderator_decision_json", {}),
                })

        # Moderator decision
        moderator = ModeratorAgent()
        decision = await moderator.make_decision(
            manuscript=manuscript,
            reviews=reviews,
            round_number=round_number,
            max_rounds=sub["max_rounds"],
            previous_rounds=previous_rounds if previous_rounds else None,
        )

        # Save round data to DB
        appdb.save_submission_round(
            submission_id, round_number,
            reviews=reviews,
            overall_average=overall_average,
            moderator_decision=decision,
            word_count=word_count,
        )

        # Save to files
        with open(sub_dir / f"round_{round_number}_reviews.json", "w") as f:
            json.dump(reviews, f, indent=2)
        with open(sub_dir / f"round_{round_number}_decision.json", "w") as f:
            json.dump(decision, f, indent=2)

        # Process decision
        mod_decision = decision.get("decision", "REJECT").upper()

        if mod_decision == "ACCEPT":
            appdb.update_submission_status(
                submission_id, "accepted",
                final_decision="ACCEPT",
                final_score=overall_average,
            )
            # Save completion
            with open(sub_dir / "submission_complete.json", "w") as f:
                json.dump({
                    "submission_id": submission_id,
                    "decision": "ACCEPT",
                    "final_score": overall_average,
                    "total_rounds": round_number,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, f, indent=2)

        elif mod_decision == "REJECT":
            appdb.update_submission_status(
                submission_id, "rejected",
                final_decision="REJECT",
                final_score=overall_average,
            )

        elif mod_decision in ("MAJOR_REVISION", "MINOR_REVISION"):
            if round_number >= sub["max_rounds"]:
                # Max rounds reached → reject
                appdb.update_submission_status(
                    submission_id, "rejected",
                    final_decision="REJECT",
                    final_score=overall_average,
                )
            else:
                # Set revision deadline (fixed 24h)
                deadline = datetime.now(timezone.utc) + timedelta(hours=24)
                appdb.update_submission_status(
                    submission_id, "awaiting_revision",
                    revision_deadline=deadline.isoformat(),
                )
        else:
            # Unknown decision, treat as reject
            appdb.update_submission_status(
                submission_id, "rejected",
                final_decision=mod_decision,
                final_score=overall_average,
            )

    except Exception as e:
        print(f"  Submission review error ({submission_id}): {e}")
        try:
            appdb.update_submission_status(submission_id, "rejected", final_decision="ERROR")
        except Exception:
            pass


# --- Researcher Application System ---

# Rate limit store for application submissions (IP-based)
apply_rate_limit: Dict[str, list] = {}  # ip → [timestamp, ...]

APPLY_RATE_LIMIT_PER_HOUR = 3


class ApplyRequest(BaseModel):
    name: str
    email: str
    affiliation: str = ""
    research_interests: List[str] = []
    sample_works: List[dict] = []  # [{type, url, description}]
    bio: str = ""


class ApplicationStatusRequest(BaseModel):
    email: str


class ApproveRequest(BaseModel):
    admin_notes: str = ""


class RejectRequest(BaseModel):
    reason: str = ""


@app.post("/api/apply")
async def apply_for_key(request: Request, body: ApplyRequest):
    """Submit a researcher application (public, rate-limited by IP)."""
    # IP rate limit: max 3 per hour
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    timestamps = apply_rate_limit.get(client_ip, [])
    timestamps = [t for t in timestamps if now - t < 3600]
    if len(timestamps) >= APPLY_RATE_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many applications. Try again later.")
    timestamps.append(now)
    apply_rate_limit[client_ip] = timestamps

    # Validate required fields
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not body.email or not body.email.strip():
        raise HTTPException(status_code=400, detail="Email is required")
    # Basic email format check
    if "@" not in body.email or "." not in body.email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Invalid email format")

    # Validate sample work URLs
    for work in body.sample_works:
        url = work.get("url", "")
        if url and not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail=f"Invalid URL: {url}. Only HTTP/HTTPS allowed.")

    try:
        result = appdb.create_researcher(
            email=body.email,
            name=body.name,
            affiliation=body.affiliation,
            research_interests=body.research_interests,
            sample_works=body.sample_works,
            bio=body.bio,
        )
        return {
            "status": "submitted",
            "message": "Application submitted successfully. You will be notified once reviewed.",
            "email": result["email"],
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/application-status/{email}")
async def get_application_status(email: str):
    """Check application status by email (public)."""
    result = appdb.get_application_status_by_email(email)
    if not result:
        raise HTTPException(status_code=404, detail="No application found for this email")
    return result


@app.get("/api/my-profile")
async def get_my_profile(api_key: str = Depends(verify_api_key)):
    """Get profile for the authenticated researcher."""
    db_key = appdb.get_api_key(api_key)
    if not db_key or not db_key.get("researcher_id"):
        raise HTTPException(status_code=404, detail="No researcher profile linked to this key")
    researcher = appdb.get_researcher(db_key["researcher_id"])
    if not researcher:
        raise HTTPException(status_code=404, detail="Researcher not found")
    # Remove internal fields
    researcher.pop("id", None)
    return researcher


@app.get("/api/my-workflows")
async def get_my_workflows(api_key: str = Depends(verify_api_key)):
    """Get workflows owned by the authenticated researcher."""
    db_key = appdb.get_api_key(api_key)
    if db_key and db_key.get("researcher_id"):
        workflows = appdb.get_researcher_workflows(db_key["researcher_id"])
    else:
        workflows = appdb.get_key_workflows(api_key)

    # Enrich with project summaries
    enriched = []
    for wf in workflows:
        project_dir = Path("results") / wf["project_id"]
        summary = _build_project_summary(project_dir) if project_dir.exists() else None
        enriched.append({
            "project_id": wf["project_id"],
            "created_at": wf["created_at"],
            "summary": summary,
        })
    return {"workflows": enriched}


@app.get("/api/my-quota")
async def get_my_quota(api_key: str = Depends(verify_api_key)):
    """Get remaining daily quota for the authenticated key."""
    quota = appdb.check_quota(api_key)
    return quota


# --- Admin Application Management ---

@app.get("/api/admin/applications")
async def list_applications(status: str = "pending", api_key: str = Depends(verify_admin_key)):
    """List applications (admin only)."""
    if status == "all":
        apps = appdb.list_all_applications()
    else:
        apps = appdb.list_pending_applications()
    return {"applications": apps}


@app.get("/api/admin/applications/{application_id}")
async def get_application_detail(application_id: str, api_key: str = Depends(verify_admin_key)):
    """Get full application details (admin only)."""
    app_data = appdb.get_application(application_id)
    if not app_data:
        raise HTTPException(status_code=404, detail="Application not found")
    return app_data


@app.post("/api/admin/applications/{application_id}/approve")
async def approve_application(application_id: str, body: ApproveRequest, api_key: str = Depends(verify_admin_key)):
    """Approve an application and generate API key (admin only)."""
    try:
        result = appdb.approve_application(application_id, reviewed_by="admin", admin_notes=body.admin_notes)
        return {
            "status": "approved",
            "api_key": result["api_key"],
            "message": "Application approved. API key generated.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/admin/applications/{application_id}/reject")
async def reject_application(application_id: str, body: RejectRequest, api_key: str = Depends(verify_admin_key)):
    """Reject an application (admin only)."""
    try:
        appdb.reject_application(application_id, reason=body.reason, reviewed_by="admin")
        return {"status": "rejected", "message": "Application rejected."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/admin/keys/{key_prefix}/quota")
async def update_key_quota(key_prefix: str, daily_quota: int, api_key: str = Depends(verify_admin_key)):
    """Update daily quota for a key (admin only)."""
    if daily_quota < 0 or daily_quota > 1000:
        raise HTTPException(status_code=400, detail="Quota must be between 0 and 1000")
    updated = appdb.update_key_quota(key_prefix, daily_quota)
    if not updated:
        raise HTTPException(status_code=404, detail="No active key found with this prefix")
    return {"message": f"Quota updated to {daily_quota}", "updated": updated}


@app.post("/api/admin/keys/{key_prefix}/revoke")
async def revoke_key(key_prefix: str, api_key: str = Depends(verify_admin_key)):
    """Revoke an API key (admin only)."""
    revoked = appdb.revoke_api_key(key_prefix)
    if not revoked:
        raise HTTPException(status_code=404, detail="No active key found with this prefix")
    return {"message": "Key revoked", "revoked": revoked}


# --- Report Download & Upload ---

@app.get("/api/projects/{project_id}/report")
async def download_report(project_id: str):
    """Download full report (manuscript + peer review) as a single Markdown file."""
    project_dir = Path("results") / project_id
    workflow_file = project_dir / "workflow_complete.json"

    if not workflow_file.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        with open(workflow_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Error reading project data: {e}")

    # Load latest manuscript
    manuscript_text, _ = _get_latest_manuscript(project_dir)
    if not manuscript_text:
        raise HTTPException(status_code=404, detail="No manuscript found")

    # Extract title from manuscript
    title = _extract_title(manuscript_text) or data.get("topic", project_id)

    # Build metadata header
    perf = data.get("performance", {})
    rounds = data.get("rounds", [])
    final_score = data.get("final_score", 0)
    final_decision = "ACCEPT" if data.get("passed") else (
        rounds[-1].get("moderator_decision", {}).get("decision", "UNKNOWN") if rounds else "UNKNOWN"
    )
    total_tokens = perf.get("total_tokens", 0)
    estimated_cost = perf.get("estimated_cost", 0)
    research_type = data.get("research_type", "research")

    md_parts = []
    md_parts.append(f"# {title}\n")
    md_parts.append(f"**Topic**: {data.get('topic', '')}")
    md_parts.append(f"**Research Type**: {research_type}")
    md_parts.append(f"**Date**: {data.get('timestamp', '')}")
    md_parts.append(f"**Final Score**: {final_score}/10 | **Decision**: {final_decision}")
    md_parts.append(f"**Total Rounds**: {data.get('total_rounds', 0)} | **Tokens**: {total_tokens:,} | **Cost**: ${estimated_cost:.4f}")
    md_parts.append("")
    md_parts.append("---")
    md_parts.append("")

    # Manuscript content
    md_parts.append(manuscript_text)
    md_parts.append("")
    md_parts.append("---")
    md_parts.append("")

    # Peer Review Report
    if rounds:
        md_parts.append("# Peer Review Report\n")

        for rd in rounds:
            round_num = rd.get("round", rd.get("round_number", 0))
            md_parts.append(f"## Round {round_num}\n")

            # Reviews
            for review in rd.get("reviews", []):
                specialist_name = review.get("specialist_name", review.get("specialist", "Reviewer"))
                model = review.get("model", "")
                avg = review.get("average", 0)
                scores = review.get("scores", {})

                md_parts.append(f"### Reviewer: {specialist_name}")
                md_parts.append(f"**Score**: {avg}/10 | **Model**: {model}")

                if scores:
                    score_items = ", ".join(f"{k.title()} {v}/10" for k, v in scores.items())
                    md_parts.append(f"**Scores**: {score_items}")

                md_parts.append("")

                if review.get("summary"):
                    md_parts.append(f"**Summary**: {review['summary']}")
                    md_parts.append("")

                if review.get("strengths"):
                    md_parts.append("**Strengths**:")
                    for s in review["strengths"]:
                        md_parts.append(f"- {s}")
                    md_parts.append("")

                if review.get("weaknesses"):
                    md_parts.append("**Weaknesses**:")
                    for w in review["weaknesses"]:
                        md_parts.append(f"- {w}")
                    md_parts.append("")

                if review.get("suggestions"):
                    md_parts.append("**Suggestions**:")
                    for s in review["suggestions"]:
                        md_parts.append(f"- {s}")
                    md_parts.append("")

            # Moderator decision (supports both new compact and legacy verbose format)
            mod = rd.get("moderator_decision", {})
            if mod:
                decision = mod.get("decision", "")
                confidence = mod.get("confidence", "")
                md_parts.append(f"### Moderator Decision: {decision}")
                md_parts.append(f"**Confidence**: {confidence}/5")
                md_parts.append("")

                # New format: "note" field
                if mod.get("note"):
                    md_parts.append(mod["note"])
                    md_parts.append("")

                # Legacy format: "recommendation" + "meta_review"
                if mod.get("recommendation") and not mod.get("note"):
                    md_parts.append(mod["recommendation"])
                    md_parts.append("")
                if mod.get("meta_review"):
                    md_parts.append(mod["meta_review"])
                    md_parts.append("")

                # Legacy: key_strengths / key_weaknesses
                if mod.get("key_strengths"):
                    md_parts.append("**Key Strengths**:")
                    for s in mod["key_strengths"]:
                        md_parts.append(f"- {s}")
                    md_parts.append("")

                if mod.get("key_weaknesses"):
                    md_parts.append("**Key Weaknesses**:")
                    for w in mod["key_weaknesses"]:
                        md_parts.append(f"- {w}")
                    md_parts.append("")

                if mod.get("required_changes"):
                    md_parts.append("**Required Changes**:")
                    for c in mod["required_changes"]:
                        md_parts.append(f"- {c}")
                    md_parts.append("")

            # Author response
            author_response_file = project_dir / f"author_response_round_{round_num}.md"
            if author_response_file.exists():
                ar_text = author_response_file.read_text(encoding="utf-8")
                md_parts.append("### Author Response")
                md_parts.append(ar_text)
                md_parts.append("")

    report_md = "\n".join(md_parts)

    return Response(
        content=report_md,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{project_id}-report.md"'
        }
    )


class UploadReportRequest(BaseModel):
    title: str
    topic: str
    content: str  # markdown content
    research_type: Optional[str] = "research"  # "survey", "research", or "explainer"
    category: Optional[CategoryInfo] = None
    audience_level: Optional[str] = "professional"


@app.post("/api/admin/upload-report")
async def upload_report(request: UploadReportRequest, api_key: str = Depends(verify_admin_key)):
    """Upload an external markdown report as a completed article (admin only)."""
    if not request.title or not request.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    if not request.content or not request.content.strip():
        raise HTTPException(status_code=400, detail="Content is required")

    # Generate project ID
    project_id = re.sub(r'[^a-z0-9\-]', '-', request.topic.lower().replace(" ", "-"))
    project_id = re.sub(r'-{2,}', '-', project_id).strip('-')
    project_id = f"{project_id[:80]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Create project directory
    project_dir = Path(f"results/{project_id}")
    project_dir.mkdir(parents=True, exist_ok=True)

    # Save manuscript
    (project_dir / "manuscript_final_v1.md").write_text(request.content, encoding="utf-8")

    # Build workflow_complete.json (minimal metadata)
    workflow_data = {
        "topic": request.topic,
        "output_directory": f"results/{project_id}",
        "research_type": request.research_type or "research",
        "category": request.category.dict() if request.category else None,
        "audience_level": request.audience_level or "professional",
        "expert_team": [],
        "rounds": [],
        "final_score": 10.0,
        "passed": True,
        "total_rounds": 0,
        "max_rounds": 0,
        "threshold": 0,
        "performance": {
            "total_tokens": 0,
            "estimated_cost": 0,
        },
        "timestamp": _utcnow().isoformat(),
        "uploaded": True,
    }

    with open(project_dir / "workflow_complete.json", "w") as f:
        json.dump(workflow_data, f, indent=2)

    return {
        "project_id": project_id,
        "status": "completed",
        "message": "Report uploaded successfully",
    }


# Explicit route for root path to ensure proper OG meta tags for social media
@app.get("/")
async def serve_index():
    """Serve index.html at root path for proper OG meta tag rendering."""
    from fastapi.responses import FileResponse
    return FileResponse("web/index.html")


# Serve web/ directory as static files (must be last — catches all unmatched routes)
app.mount("/", StaticFiles(directory="web", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
