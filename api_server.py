#!/usr/bin/env python3
"""FastAPI server for AI-backed research platform."""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from research_cli.agents.team_composer import TeamComposerAgent
from research_cli.workflow.orchestrator import WorkflowOrchestrator
from research_cli.models.expert import ExpertConfig


app = FastAPI(title="AI-Backed Research API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class StartWorkflowRequest(BaseModel):
    topic: str
    experts: List[dict]
    max_rounds: int = 3
    threshold: float = 8.0


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
    status: str  # "queued", "composing_team", "writing", "reviewing", "revising", "completed", "failed"
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


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "AI-Backed Research API"}


@app.post("/api/propose-team", response_model=TeamProposalResponse)
async def propose_team(request: ProposeTeamRequest):
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

        return TeamProposalResponse(
            topic=request.topic,
            proposed_experts=[
                ExpertProposalResponse(
                    expert_domain=p.expert_domain,
                    rationale=p.rationale,
                    focus_areas=p.focus_areas,
                    suggested_model=p.suggested_model
                ) for p in proposals
            ],
            recommended_num_experts=len(proposals),
            estimated_time_minutes=estimated_time,
            estimated_rounds=estimated_rounds,
            cost_estimate=CostEstimate(**cost_info)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to propose team: {str(e)}")


@app.post("/api/start-workflow")
async def start_workflow(request: StartWorkflowRequest, background_tasks: BackgroundTasks):
    """Start workflow in background."""
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
            "message": "Workflow queued",
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

        # Start workflow in background
        background_tasks.add_task(
            run_workflow_background,
            project_id=project_id,
            topic=request.topic,
            experts=request.experts,
            max_rounds=request.max_rounds,
            threshold=request.threshold
        )

        return {
            "project_id": project_id,
            "status": "queued",
            "message": "Workflow started"
        }
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
async def list_workflows():
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
async def resume_workflow(project_id: str, background_tasks: BackgroundTasks):
    """Resume a workflow from checkpoint."""
    try:
        from pathlib import Path

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
        import json
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

        # Start resume task in background
        background_tasks.add_task(
            resume_workflow_background,
            project_id=project_id,
            project_dir=project_dir
        )

        return {
            "project_id": project_id,
            "status": "queued",
            "message": f"Workflow resumed from Round {checkpoint['current_round']}"
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

        # Status callback
        def status_update(status: str, round_num: int, message: str):
            update_workflow_status(project_id, status, round_num, 0, message)

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


async def run_workflow_background(
    project_id: str,
    topic: str,
    experts: List[dict],
    max_rounds: int,
    threshold: float
):
    """Run workflow in background and update status."""
    try:
        # Update status: composing team
        workflow_status[project_id].update({
            "status": "composing_team",
            "progress_percentage": 5,
            "message": "Composing expert team..."
        })
        add_activity_log(project_id, "info", "Starting expert team composition")

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

        # Create orchestrator with status callback
        orchestrator = WorkflowOrchestrator(
            expert_configs=expert_configs,
            topic=topic,
            max_rounds=max_rounds,
            threshold=threshold,
            output_dir=Path(f"results/{project_id}"),
            status_callback=lambda status, round_num, msg: update_workflow_status(
                project_id, status, round_num, max_rounds, msg
            )
        )

        # Run workflow
        add_activity_log(project_id, "info", "Starting workflow execution")
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
    if status == "writing":
        progress = 10
        add_activity_log(project_id, "info", message)
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
