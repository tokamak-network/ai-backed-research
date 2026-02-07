#!/usr/bin/env python3
"""FastAPI server for AI-backed research platform."""

import asyncio
import json
import os
import secrets
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from research_cli.agents.team_composer import TeamComposerAgent
from research_cli.categories import suggest_category_from_topic, get_expert_pool
from research_cli.workflow.orchestrator import WorkflowOrchestrator
from research_cli.workflow.collaborative_workflow import CollaborativeWorkflowOrchestrator
from research_cli.models.expert import ExpertConfig
from research_cli.models.author import AuthorRole, WriterTeam


app = FastAPI(title="AI-Backed Research API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Job Queue ---
job_queue: asyncio.Queue = asyncio.Queue()


async def job_worker():
    """Single worker: pull jobs from queue and execute sequentially."""
    while True:
        job = await job_queue.get()
        try:
            job_fn = job.pop("_fn")
            await job_fn(**job)
        except Exception as e:
            # Error handling is inside run_workflow_background / resume_workflow_background
            print(f"Job worker error: {e}")
        finally:
            job_queue.task_done()


# --- API Key Auth ---
ALLOWED_API_KEYS: set = set()
_raw_keys = os.environ.get("RESEARCH_API_KEYS", "")
if _raw_keys:
    ALLOWED_API_KEYS = {k.strip() for k in _raw_keys.split(",") if k.strip()}

ADMIN_API_KEY = os.environ.get("RESEARCH_ADMIN_KEY", "")

# --- Dynamic key file management ---
KEYS_FILE = Path("keys.json")


def load_keys_from_file() -> list:
    """Load dynamic keys from keys.json."""
    if not KEYS_FILE.exists():
        return []
    try:
        with open(KEYS_FILE) as f:
            data = json.load(f)
        return data.get("keys", [])
    except (json.JSONDecodeError, IOError):
        return []


def save_keys_to_file(keys: list):
    """Save dynamic keys to keys.json."""
    with open(KEYS_FILE, "w") as f:
        json.dump({"keys": keys}, f, indent=2)


def sync_keys_from_file():
    """Sync keys.json entries into ALLOWED_API_KEYS set."""
    for entry in load_keys_from_file():
        ALLOWED_API_KEYS.add(entry["key"])


# Load dynamic keys on module init
sync_keys_from_file()


async def verify_api_key(request: Request) -> str:
    """FastAPI dependency: validate X-API-Key header."""
    key = request.headers.get("X-API-Key")
    if not ALLOWED_API_KEYS and not ADMIN_API_KEY:
        # No keys configured → auth disabled (dev mode)
        return key or "anonymous"
    if ADMIN_API_KEY and key == ADMIN_API_KEY:
        return key  # admin key is always valid
    if not ALLOWED_API_KEYS:
        return key or "anonymous"
    if not key or key not in ALLOWED_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return key


async def verify_admin_key(request: Request) -> str:
    """FastAPI dependency: validate admin API key."""
    key = request.headers.get("X-API-Key")
    if not ADMIN_API_KEY:
        # Admin key not configured → dev mode: allow all
        return key or "anonymous"
    if key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Admin access required")
    return key


# --- Rate Limit (per API key, 30 min = 1800s) ---
RATE_LIMIT_SECONDS = 1800
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
    """Scan for interrupted workflows and start job worker on startup."""
    await scan_interrupted_workflows()
    asyncio.create_task(job_worker())


async def scan_interrupted_workflows():
    """Scan results directory for interrupted workflows (checkpoint exists but no complete)."""
    results_dir = Path("results")
    if not results_dir.exists():
        return

    interrupted_count = 0
    for project_dir in results_dir.iterdir():
        if not project_dir.is_dir():
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
                    "start_time": checkpoint.get("checkpoint_time", datetime.now().isoformat()),
                    "elapsed_time_seconds": 0,
                    "estimated_time_remaining_seconds": (checkpoint.get("max_rounds", 3) - checkpoint.get("current_round", 0)) * 180,
                    "can_resume": True
                }

                # Initialize activity log
                activity_logs[project_id] = [{
                    "timestamp": datetime.now().isoformat(),
                    "level": "warning",
                    "message": f"Workflow interrupted at Round {checkpoint.get('current_round', 0)}. Click Resume to continue.",
                    "details": {"checkpoint_time": checkpoint.get("checkpoint_time")}
                }]

                interrupted_count += 1
                print(f"  Found interrupted workflow: {project_id} (Round {checkpoint.get('current_round', 0)}/{checkpoint.get('max_rounds', 3)})")

            except Exception as e:
                print(f"  Error loading checkpoint for {project_id}: {e}")

    if interrupted_count > 0:
        print(f"✓ Found {interrupted_count} interrupted workflow(s) - available for resume")


# Request/Response Models
class ExpertContext(BaseModel):
    type: str  # "description", "url", "pdf"
    content: str

class ProposeTeamRequest(BaseModel):
    topic: str
    num_experts: Optional[int] = None
    research_type: Optional[str] = "research"  # "survey" or "research"
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

class StartWorkflowRequest(BaseModel):
    topic: str
    experts: List[dict]
    max_rounds: int = 3
    threshold: float = 8.0
    research_cycles: int = 1  # Number of research note iterations
    category: Optional[CategoryInfo] = None  # Academic category
    article_length: Optional[str] = "full"  # "full" or "short"
    workflow_mode: Optional[str] = "standard"  # "standard" or "collaborative"


class SubmitArticleRequest(BaseModel):
    title: str
    content: str  # Markdown content
    author: Optional[str] = "Anonymous"
    category: Optional[CategoryInfo] = None
    review_requested: Optional[bool] = False


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
    return {"status": "ok", "service": "AI-Backed Research API"}


@app.get("/api/queue-status")
async def queue_status():
    """Return current job queue size and running job info."""
    return {
        "queued_jobs": job_queue.qsize(),
        "active_workflows": sum(
            1 for s in workflow_status.values()
            if s["status"] in ("queued", "composing_team", "writing", "desk_screening", "reviewing", "revising", "research", "writing_sections")
        )
    }


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

        proposals = await composer.propose_team(request.topic, num_experts, additional_context)

        # Suggest category based on topic
        suggested_category = suggest_category_from_topic(request.topic)

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

    try:
        # Generate unique project ID
        project_id = request.topic.lower().replace(" ", "-")
        # Add timestamp to make it unique
        project_id = f"{project_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # Initialize status
        workflow_status[project_id] = {
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
            "start_time": datetime.now().isoformat(),
            "elapsed_time_seconds": 0,
            "estimated_time_remaining_seconds": request.max_rounds * len(request.experts) * 120
        }

        # Initialize activity log
        activity_logs[project_id] = []
        add_activity_log(project_id, "info", f"Workflow created for topic: {request.topic[:50]}...")

        # Enqueue job (worker will execute it)
        await job_queue.put({
            "_fn": run_workflow_background,
            "project_id": project_id,
            "topic": request.topic,
            "experts": request.experts,
            "max_rounds": request.max_rounds,
            "threshold": request.threshold,
            "research_cycles": request.research_cycles,
            "category": request.category.dict() if request.category else None,
            "article_length": request.article_length or "full",
            "workflow_mode": request.workflow_mode or "standard",
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
    start_time = datetime.fromisoformat(status.get("start_time", datetime.now().isoformat()))
    elapsed_seconds = int((datetime.now() - start_time).total_seconds())

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
    return {"workflows": [
        {"project_id": pid, **status}
        for pid, status in workflow_status.items()
    ]}


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
        if not checkpoint_file.exists():
            raise HTTPException(status_code=400, detail="No checkpoint found for this workflow")

        # Load checkpoint to get info
        with open(checkpoint_file) as f:
            checkpoint = json.load(f)

        # Initialize workflow status if not exists
        if project_id not in workflow_status:
            workflow_status[project_id] = {
                "project_id": project_id,
                "status": "queued",
                "current_round": checkpoint["current_round"],
                "total_rounds": checkpoint["max_rounds"],
                "progress_percentage": int((checkpoint["current_round"] / checkpoint["max_rounds"]) * 100),
                "message": f"Resuming from Round {checkpoint['current_round']}...",
                "error": None,
                "expert_status": [],
                "cost_estimate": None,
                "start_time": datetime.now().isoformat(),
                "elapsed_time_seconds": 0,
                "estimated_time_remaining_seconds": (checkpoint["max_rounds"] - checkpoint["current_round"]) * 180
            }

        # Initialize activity log
        if project_id not in activity_logs:
            activity_logs[project_id] = []

        add_activity_log(project_id, "info", f"Resuming workflow from Round {checkpoint['current_round']}")

        # Enqueue resume job
        await job_queue.put({
            "_fn": resume_workflow_background,
            "project_id": project_id,
            "project_dir": project_dir,
        })

        return {
            "project_id": project_id,
            "status": "queued",
            "message": f"Workflow resumed from Round {checkpoint['current_round']}",
            "queue_position": job_queue.qsize()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume workflow: {str(e)}")


def add_activity_log(project_id: str, level: str, message: str, details: dict = None):
    """Add entry to activity log."""
    if project_id not in activity_logs:
        activity_logs[project_id] = []

    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
        "details": details or {}
    }
    activity_logs[project_id].append(entry)


def calculate_cost_estimate(input_tokens: int, output_tokens: int, model: str = "claude-opus-4.5") -> dict:
    """Calculate cost estimate based on tokens and model."""
    # Pricing per 1M tokens (as of 2026)
    pricing = {
        "claude-opus-4.5": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4": {"input": 3.0, "output": 15.0},
        "claude-haiku-4": {"input": 0.8, "output": 4.0}
    }

    model_price = pricing.get(model, pricing["claude-opus-4.5"])
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

        # Load checkpoint to get max_rounds
        checkpoint_file = project_dir / "workflow_checkpoint.json"
        with open(checkpoint_file) as f:
            checkpoint = json.load(f)

        max_rounds = checkpoint.get("max_rounds", 3)

        # Status callback
        def status_update(status: str, round_num: int, message: str):
            update_workflow_status(project_id, status, round_num, max_rounds, message)

        # Resume from checkpoint
        result = await WorkflowOrchestrator.resume_from_checkpoint(
            output_dir=project_dir,
            status_callback=status_update
        )

        # Mark as completed
        update_workflow_status(project_id, "completed", result["total_rounds"], result["total_rounds"], "Workflow completed successfully")
        add_activity_log(project_id, "success", f"Workflow completed with score {result['final_score']}/10")

    except Exception as e:
        error_msg = f"Workflow failed: {str(e)}"
        update_workflow_status(project_id, "failed", 0, 0, error_msg)
        add_activity_log(project_id, "error", error_msg, {"error": str(e)})

        if project_id in workflow_status:
            workflow_status[project_id]["error"] = error_msg


def _generate_reviewers_from_category(category: dict, topic: str) -> List[ExpertConfig]:
    """Generate reviewer ExpertConfigs from category expert pool.

    Args:
        category: Dict with 'major' and 'subfield' keys.
        topic: Research topic (for context in domain description).

    Returns:
        List of up to 3 ExpertConfig reviewer objects.
    """
    if not category or not category.get("major") or not category.get("subfield"):
        return []

    pool = get_expert_pool(category["major"], category["subfield"])
    if not pool:
        return []

    reviewers = []
    for i, expert_id in enumerate(pool[:3]):
        # Convert snake_case ID to human-readable name
        name = expert_id.replace("_expert", "").replace("_", " ").title() + " Expert"
        domain = expert_id.replace("_expert", "").replace("_", " ").title()

        config = ExpertConfig(
            id=f"reviewer-{i+1}",
            name=name,
            domain=domain,
            focus_areas=[],
            system_prompt="",  # SpecialistFactory will auto-generate
            provider="anthropic",
            model="claude-sonnet-4"
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
):
    """Run workflow in background and update status."""
    try:
        # Update status: composing team
        workflow_status[project_id].update({
            "status": "composing_team",
            "progress_percentage": 5,
            "message": "Composing expert team..."
        })
        add_activity_log(project_id, "info", f"Starting {workflow_mode} workflow - team composition")

        # Convert expert dicts to ExpertConfig objects
        expert_configs = []
        for i, exp in enumerate(experts):
            config = ExpertConfig(
                id=f"expert-{i+1}",
                name=exp.get("expert_domain", f"Expert {i+1}"),
                domain=exp.get("expert_domain", "General"),
                focus_areas=exp.get("focus_areas", []),
                system_prompt="",  # Will be generated by SpecialistFactory
                provider="anthropic",
                model=exp.get("suggested_model", "claude-opus-4.5")
            )
            expert_configs.append(config)
            add_activity_log(
                project_id,
                "success",
                f"Added expert: {config.name}",
                {"model": config.model, "focus_areas": config.focus_areas}
            )

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

            # Generate reviewers from category expert pool
            reviewer_configs = _generate_reviewers_from_category(category, topic)
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
            )

            add_activity_log(project_id, "info", "Starting standard workflow execution")
            await orchestrator.run()
            add_activity_log(project_id, "success", "Workflow execution completed")

        # Calculate final cost estimate
        # TODO: Get actual token counts from orchestrator
        total_input = len(experts) * max_rounds * 5000  # Rough estimate
        total_output = len(experts) * max_rounds * 2000
        cost_info = calculate_cost_estimate(total_input, total_output, experts[0].get("suggested_model", "claude-opus-4.5"))
        workflow_status[project_id]["cost_estimate"] = cost_info

        # Export results to web directory
        try:
            add_activity_log(project_id, "info", "Exporting results to web directory")
            import subprocess
            result = subprocess.run(
                ["./venv/bin/python", "export_to_web.py", f"results/{project_id}"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                print(f"✓ Exported {project_id} to web directory")
                add_activity_log(project_id, "success", "Results exported successfully")
            else:
                print(f"✗ Failed to export {project_id}: {result.stderr}")
                add_activity_log(project_id, "warning", f"Export failed: {result.stderr[:100]}")
        except Exception as e:
            print(f"✗ Error exporting {project_id}: {e}")
            add_activity_log(project_id, "error", f"Export error: {str(e)}")

        # Update status: completed (if not already done by callback)
        if workflow_status[project_id]["status"] != "completed":
            workflow_status[project_id].update({
                "status": "completed",
                "progress_percentage": 100,
                "message": "Workflow completed successfully",
                "estimated_time_remaining_seconds": 0
            })
            add_activity_log(project_id, "success", "Workflow completed successfully")

    except Exception as e:
        workflow_status[project_id].update({
            "status": "failed",
            "progress_percentage": 0,
            "message": "Workflow failed",
            "error": str(e),
            "estimated_time_remaining_seconds": 0
        })
        add_activity_log(project_id, "error", f"Workflow failed: {str(e)}")


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
    start_time = datetime.fromisoformat(workflow_status[project_id].get("start_time", datetime.now().isoformat()))
    elapsed = (datetime.now() - start_time).total_seconds()

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
    if project_id not in workflow_status:
        raise HTTPException(status_code=404, detail="Workflow not found")

    status = workflow_status[project_id]["status"]
    deletable_statuses = {"interrupted", "completed", "failed", "rejected"}
    if status not in deletable_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete workflow in '{status}' state. Only {', '.join(sorted(deletable_statuses))} workflows can be deleted."
        )

    # Remove from in-memory stores
    del workflow_status[project_id]
    activity_logs.pop(project_id, None)

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
    """List all dynamic API keys (admin only)."""
    keys = load_keys_from_file()
    # Mask keys: show first 8 chars only
    return {"keys": [
        {"key_prefix": entry["key"][:8] + "...", "label": entry.get("label", ""), "created": entry.get("created", "")}
        for entry in keys
    ]}


class CreateKeyRequest(BaseModel):
    label: str = ""


@app.post("/api/admin/keys")
async def create_key(request: CreateKeyRequest, api_key: str = Depends(verify_admin_key)):
    """Generate a new API key (admin only)."""
    new_key = secrets.token_urlsafe(24)
    keys = load_keys_from_file()
    keys.append({"key": new_key, "label": request.label, "created": datetime.now().isoformat()})
    save_keys_to_file(keys)
    ALLOWED_API_KEYS.add(new_key)
    return {"key": new_key, "label": request.label, "message": "Key created. Copy it now — it will not be shown again."}


@app.delete("/api/admin/keys/{key_prefix}")
async def delete_key(key_prefix: str, api_key: str = Depends(verify_admin_key)):
    """Delete an API key by its prefix (admin only)."""
    keys = load_keys_from_file()
    to_remove = [entry for entry in keys if entry["key"].startswith(key_prefix)]
    if not to_remove:
        raise HTTPException(status_code=404, detail="Key not found")
    for entry in to_remove:
        ALLOWED_API_KEYS.discard(entry["key"])
    keys = [entry for entry in keys if not entry["key"].startswith(key_prefix)]
    save_keys_to_file(keys)
    return {"message": "Key deleted", "deleted": len(to_remove)}


@app.post("/api/submit-article")
async def submit_article(request: SubmitArticleRequest, api_key: str = Depends(verify_api_key)):
    """Direct article submission (no AI workflow). Saves article to web/articles/ and updates index.json."""
    try:
        # Generate project ID from title
        project_id = request.title.lower().replace(" ", "-")
        project_id = f"{project_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

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
                    {"<span class='meta-item'><strong>Review:</strong> Requested</span>" if request.review_requested else ""}
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
    <script src="../js/main.js"></script>
    <script>
        const rawMarkdown = `{escaped_markdown}`;
        document.getElementById('article-content').innerHTML = marked.parse(rawMarkdown);
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
            "timestamp": datetime.now().isoformat(),
            "data_file": None,
            "elapsed_time_seconds": 0,
            "final_decision": "DIRECT_SUBMISSION",
            "source": "direct_submission",
            "author": request.author,
            "review_requested": request.review_requested,
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


# Serve web/ directory as static files (must be last — catches all unmatched routes)
app.mount("/", StaticFiles(directory="web", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
