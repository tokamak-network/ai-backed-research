"""Command-line interface for AI research workflow."""

import asyncio
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import get_config, Config
from .llm import ClaudeLLM, GeminiLLM, OpenAILLM

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """AI-native research workflow with multi-provider LLM peer review.

    Generate high-quality research reports through iterative AI peer review.
    Multiple specialist reviewers (cryptography, economics, distributed systems)
    provide feedback until quality threshold is met.
    """
    pass


@cli.command()
@click.argument("topic")
@click.option(
    "--profile",
    default="default",
    help="Research profile (e.g., 'suhyeon', 'technical')"
)
@click.option(
    "--specialists",
    default="crypto,economics,systems",
    help="Comma-separated list of specialist reviewers"
)
def init(topic: str, profile: str, specialists: str):
    """Initialize a new research project.

    Creates directory structure and metadata file for a research topic.

    Example:
        ai-research init "Layer 2 Fee Structures" --profile suhyeon
    """
    config = get_config()
    project_dir = config.results_dir / topic.replace(" ", "-").lower()

    if project_dir.exists():
        console.print(f"[yellow]Project already exists:[/yellow] {project_dir}")
        return

    # Create directory structure
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "rounds").mkdir(exist_ok=True)

    # Create metadata
    metadata = {
        "topic": topic,
        "profile": profile,
        "specialists": specialists.split(","),
        "status": "initialized",
        "created_at": None,  # Will be set when workflow starts
    }

    import json
    metadata_path = project_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    console.print(Panel.fit(
        f"[green]✓[/green] Initialized research project: [bold]{topic}[/bold]\n"
        f"Directory: {project_dir}\n"
        f"Profile: {profile}\n"
        f"Specialists: {', '.join(specialists.split(','))}",
        title="Project Created",
        border_style="green"
    ))


@cli.command()
@click.option(
    "--check-keys",
    is_flag=True,
    help="Verify API keys are configured"
)
def status(check_keys: bool):
    """Show configuration status and available providers.

    Displays which LLM providers are configured and ready to use.
    """
    config = get_config()

    table = Table(title="AI Research Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Max Review Rounds", str(config.max_review_rounds))
    table.add_row("Score Threshold", f"{config.score_threshold}/10")
    table.add_row("Results Directory", str(config.results_dir))
    table.add_row("Default Writer Model", config.default_writer_model)
    table.add_row("Default Reviewer Model", config.default_reviewer_model)

    console.print(table)

    if check_keys:
        console.print("\n[bold]API Key Status:[/bold]")
        validation = config.validate()

        for provider, configured in validation.items():
            status_icon = "✓" if configured else "✗"
            status_color = "green" if configured else "red"
            console.print(f"  [{status_color}]{status_icon}[/{status_color}] {provider.capitalize()}")

        if not all(validation.values()):
            console.print(
                "\n[yellow]Missing API keys.[/yellow] "
                "Set environment variables or create .env file.\n"
                "See .env.example for template."
            )


@cli.command(name="list")
def list_projects():
    """List all research projects."""
    config = get_config()
    results_dir = config.results_dir

    if not results_dir.exists():
        console.print("[yellow]No research projects found.[/yellow]")
        console.print(f"Results directory: {results_dir}")
        return

    projects = [d for d in results_dir.iterdir() if d.is_dir()]

    if not projects:
        console.print("[yellow]No research projects found.[/yellow]")
        return

    table = Table(title="Research Projects")
    table.add_column("Topic", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Rounds", style="yellow")

    import json
    for project_dir in sorted(projects):
        metadata_path = project_dir / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)

            topic = metadata.get("topic", project_dir.name)
            status = metadata.get("status", "unknown")
            rounds_dir = project_dir / "rounds"
            num_rounds = len([f for f in rounds_dir.glob("round_*.json")]) if rounds_dir.exists() else 0

            table.add_row(topic, status, str(num_rounds))

    console.print(table)


@cli.command()
@click.option(
    "--test-providers",
    is_flag=True,
    help="Test all configured LLM providers"
)
def test(test_providers: bool):
    """Run system tests and diagnostics.

    Verifies that LLM providers are working correctly.
    """
    if test_providers:
        asyncio.run(_test_providers())
    else:
        console.print("[yellow]Use --test-providers to test LLM connectivity[/yellow]")


async def _test_providers():
    """Test all configured LLM providers."""
    config = get_config()
    validation = config.validate()

    console.print("[bold]Testing LLM Providers...[/bold]\n")

    test_prompt = "Say 'Hello from {provider}' and nothing else."

    # Test Anthropic
    if validation["anthropic"]:
        try:
            llm_config = config.get_llm_config("anthropic")
            llm = ClaudeLLM(api_key=llm_config.api_key, model=llm_config.model)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Testing Anthropic Claude...", total=None)
                response = await llm.generate(
                    test_prompt.format(provider="Claude"),
                    max_tokens=50
                )
                progress.update(task, completed=True)

            console.print(f"[green]✓[/green] Anthropic: {response.content}")
            console.print(f"  Model: {response.model}")
            console.print(f"  Tokens: {response.total_tokens}\n")

        except Exception as e:
            console.print(f"[red]✗[/red] Anthropic failed: {e}\n")

    # Test OpenAI
    if validation["openai"]:
        try:
            llm_config = config.get_llm_config("openai")
            llm = OpenAILLM(api_key=llm_config.api_key, model=llm_config.model)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Testing OpenAI GPT...", total=None)
                response = await llm.generate(
                    test_prompt.format(provider="GPT"),
                    max_tokens=50
                )
                progress.update(task, completed=True)

            console.print(f"[green]✓[/green] OpenAI: {response.content}")
            console.print(f"  Model: {response.model}")
            console.print(f"  Tokens: {response.total_tokens}\n")

        except Exception as e:
            console.print(f"[red]✗[/red] OpenAI failed: {e}\n")

    # Test Google
    if validation["google"]:
        try:
            llm_config = config.get_llm_config("google")
            llm = GeminiLLM(api_key=llm_config.api_key, model=llm_config.model)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Testing Google Gemini...", total=None)
                response = await llm.generate(
                    test_prompt.format(provider="Gemini"),
                    max_tokens=50
                )
                progress.update(task, completed=True)

            console.print(f"[green]✓[/green] Google: {response.content}")
            console.print(f"  Model: {response.model}")
            console.print(f"  Tokens: {response.total_tokens}\n")

        except Exception as e:
            console.print(f"[red]✗[/red] Google failed: {e}\n")


@cli.command()
@click.argument("topic")
@click.option("--num-experts", type=int, default=3, help="Number of expert reviewers")
@click.option("--auto-accept-team", is_flag=True, help="Skip interactive team editing")
@click.option("--max-rounds", type=int, default=3, help="Maximum review rounds")
@click.option("--threshold", type=float, default=7.5, help="Score threshold for acceptance")
@click.option("--manuscript", type=click.Path(exists=True), help="Path to existing manuscript (skip generation)")
@click.option("--article-length", type=click.Choice(["short", "full"]), default="full", help="Article length: short (1,500-2,500 words) or full (3,000-5,000 words)")
def run(
    topic: str,
    num_experts: int,
    auto_accept_team: bool,
    max_rounds: int,
    threshold: float,
    manuscript: Optional[str],
    article_length: str,
):
    """Run complete research workflow with AI team composition.

    This command:
    1. Analyzes the topic and proposes an expert review team
    2. Allows interactive team editing (unless --auto-accept-team)
    3. Generates or uses provided manuscript
    4. Runs iterative peer review until quality threshold met
    5. Tracks performance metrics and exports results

    Example:
        ai-research run "Optimistic Rollups Security" --num-experts 4
        ai-research run "MEV in Ethereum" --auto-accept-team
        ai-research run "Layer 2 Bridges" --manuscript paper.md --max-rounds 5
    """
    asyncio.run(_run_workflow(
        topic,
        num_experts,
        auto_accept_team,
        max_rounds,
        threshold,
        manuscript,
        article_length,
    ))


async def _run_workflow(
    topic: str,
    num_experts: int,
    auto_accept_team: bool,
    max_rounds: int,
    threshold: float,
    manuscript_path: Optional[str],
    article_length: str = "full",
):
    """Run the complete workflow asynchronously."""
    from .agents import TeamComposerAgent
    from .categories import suggest_category_from_topic
    from .interactive import TeamEditor
    from .workflow import WorkflowOrchestrator
    from .models.expert import ExpertConfig

    config = get_config()

    # Check API key
    if not config.anthropic_api_key:
        console.print("[red]Error: No LLM API key configured[/red]")
        console.print("Set LLM_API_KEY or ANTHROPIC_API_KEY environment variable (or create .env file)")
        return 1

    console.print(Panel.fit(
        "[bold cyan]AI Research Workflow[/bold cyan]\n"
        f"Topic: {topic}\n"
        f"Team size: {num_experts} experts\n"
        f"Max rounds: {max_rounds}\n"
        f"Threshold: {threshold}/10",
        title="Starting Workflow",
        border_style="cyan"
    ))

    # Step 1: Team Composition
    console.print("\n[bold cyan]Step 1: AI Team Composition[/bold cyan]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Analyzing topic and proposing expert team...", total=None)
        composer = TeamComposerAgent()
        proposals = await composer.propose_team(topic, num_experts)
        progress.update(task, completed=True)

    console.print(f"[green]✓[/green] Team composition complete\n")

    # Parse analysis if available (would need to modify TeamComposerAgent to return it)
    TeamEditor.show_proposed_team(proposals, topic)

    # Step 2: Interactive Team Editing (optional)
    expert_configs: List[ExpertConfig] = []

    if auto_accept_team:
        console.print("\n[yellow]--auto-accept-team enabled, using proposed team[/yellow]\n")
        # Convert proposals to configs
        for idx, proposal in enumerate(proposals):
            config = ExpertConfig(
                id=f"expert_{idx + 1}",
                name=proposal.expert_domain,
                domain=proposal.expert_domain,
                focus_areas=proposal.focus_areas,
                system_prompt="",  # Will be generated
                provider=proposal.suggested_provider,
                model=proposal.suggested_model
            )
            expert_configs.append(config)
    else:
        console.print("\n[bold cyan]Step 2: Review and Edit Team[/bold cyan]\n")
        expert_configs = TeamEditor.edit_team(proposals, topic)

        if not expert_configs:
            console.print("[yellow]Workflow cancelled by user[/yellow]")
            return 1

    console.print(f"\n[green]✓[/green] Final team: {len(expert_configs)} experts\n")

    # Display final team
    final_table = Table(title="Final Expert Team", show_header=True)
    final_table.add_column("Expert", style="cyan")
    final_table.add_column("Model", style="yellow")

    for config in expert_configs:
        final_table.add_row(config.name, config.model)

    console.print(final_table)
    console.print()

    # Step 3: Run Workflow
    console.print("[bold cyan]Step 3: Running Peer Review Workflow[/bold cyan]\n")

    # Load manuscript if provided
    initial_manuscript = None
    if manuscript_path:
        manuscript_file = Path(manuscript_path)
        initial_manuscript = manuscript_file.read_text()
        console.print(f"[green]✓[/green] Loaded manuscript: {manuscript_file}")
        console.print(f"   Length: {len(initial_manuscript.split()):,} words\n")

    # Detect academic category from topic
    category = suggest_category_from_topic(topic)

    # Create and run orchestrator
    orchestrator = WorkflowOrchestrator(
        expert_configs=expert_configs,
        topic=topic,
        max_rounds=max_rounds,
        threshold=threshold,
        category=category,
        article_length=article_length,
    )

    try:
        workflow_data = await orchestrator.run(initial_manuscript)

        # Step 4: Export to web viewer
        console.print("[bold cyan]Step 4: Exporting to Web Viewer[/bold cyan]\n")
        try:
            import subprocess
            import sys
            result = subprocess.run(
                [sys.executable, "export_to_web.py"],
                capture_output=True,
                text=True,
                check=True
            )
            console.print("[green]✓ Results exported to web/data/[/green]")
            console.print("[dim]View at: http://localhost:8080/web/review-viewer.html[/dim]\n")
        except Exception as e:
            console.print(f"[yellow]⚠ Could not export to web: {e}[/yellow]\n")

        console.print("[bold green]✓ Workflow complete![/bold green]\n")
        return 0

    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1


@cli.command()
@click.argument("topic")
@click.option("--major-field", default="computer_science", help="Major academic field")
@click.option("--subfield", default="security", help="Subfield")
@click.option("--num-coauthors", default=2, help="Number of co-authors (0-3)")
@click.option("--max-rounds", default=3, help="Maximum review rounds")
@click.option("--threshold", default=7.5, help="Acceptance threshold")
@click.option("--target-length", default=4000, help="Target manuscript length in words")
def collaborate(
    topic: str,
    major_field: str,
    subfield: str,
    num_coauthors: int,
    max_rounds: int,
    threshold: float,
    target_length: int
):
    """Run collaborative research workflow with writer team.

    Example:
        ai-research collaborate "ZK Rollup Security" --major-field computer_science --subfield security
    """
    return asyncio.run(_run_collaborative_workflow(
        topic, major_field, subfield, num_coauthors, max_rounds, threshold, target_length
    ))


async def _run_collaborative_workflow(
    topic: str,
    major_field: str,
    subfield: str,
    num_coauthors: int,
    max_rounds: int,
    threshold: float,
    target_length: int
):
    """Run collaborative workflow async."""
    from datetime import datetime
    from .models.author import AuthorRole, WriterTeam
    from .models.expert import ExpertConfig
    from .workflow.collaborative_workflow import CollaborativeWorkflowOrchestrator
    from .categories import get_expert_pool, get_category_name

    console.print("\n[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]")
    console.print("[bold cyan] Collaborative Research Setup[/bold cyan]")
    console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]\n")

    console.print(f"[bold]Topic:[/bold] {topic}")
    console.print(f"[bold]Category:[/bold] {get_category_name(major_field, subfield)}\n")

    # Step 1: AI-composed writer team
    console.print("[bold cyan]Step 1: Composing Writer Team (AI)[/bold cyan]\n")

    from .agents.writer_team_composer import WriterTeamComposerAgent

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("AI analyzing topic and proposing writer team...", total=None)

        composer = WriterTeamComposerAgent()
        team_config = await composer.propose_and_format_team(
            topic=topic,
            major_field=major_field,
            subfield=subfield,
            num_coauthors=num_coauthors
        )

        progress.update(task, completed=True)

    # Display proposed team
    lead_config = team_config["lead_author"]
    console.print(f"  [bold]Lead Author:[/bold] {lead_config['name']}")
    console.print(f"    Expertise: {lead_config['expertise']}")
    console.print(f"    Focus: {', '.join(lead_config['focus_areas'][:2])}")

    if team_config["coauthors"]:
        console.print()
        for i, ca_config in enumerate(team_config["coauthors"], 1):
            console.print(f"  [bold]Co-Author {i}:[/bold] {ca_config['name']}")
            console.print(f"    Expertise: {ca_config['expertise']}")
            console.print(f"    Focus: {', '.join(ca_config['focus_areas'][:2])}")

    console.print()

    # Convert to AuthorRole objects
    lead_author = AuthorRole(
        id=lead_config["id"],
        name=lead_config["name"],
        role=lead_config["role"],
        expertise=lead_config["expertise"],
        focus_areas=lead_config["focus_areas"],
        model=lead_config["model"]
    )

    coauthors = []
    for ca_config in team_config["coauthors"]:
        coauthor = AuthorRole(
            id=ca_config["id"],
            name=ca_config["name"],
            role=ca_config["role"],
            expertise=ca_config["expertise"],
            focus_areas=ca_config["focus_areas"],
            model=ca_config["model"]
        )
        coauthors.append(coauthor)

    writer_team = WriterTeam(lead_author=lead_author, coauthors=coauthors)

    # Step 2: Compose reviewer pool (external, not writers)
    console.print("[bold cyan]Step 2: Composing Reviewer Pool[/bold cyan]\n")

    # Get expert pool from category and generate reviewer configs dynamically
    expert_pool = get_expert_pool(major_field, subfield)

    reviewer_configs = []
    for i, expert_id in enumerate(expert_pool):
        name = expert_id.replace("_expert", "").replace("_", " ").title() + " Expert"
        domain = expert_id.replace("_expert", "").replace("_", " ").title()
        reviewer_configs.append(ExpertConfig(
            id=f"reviewer_{i+1}",
            name=name,
            domain=domain,
            focus_areas=[],
            system_prompt="",  # SpecialistFactory will auto-generate
            provider="anthropic",
            model="claude-sonnet-4.5"
        ))

    console.print(f"  ✓ {len(reviewer_configs)} external reviewers assigned from {get_category_name(major_field, subfield)}")
    console.print("  (Reviewer names hidden to ensure objectivity)\n")

    # Step 3: Create output directory
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_topic = topic.lower().replace(" ", "-").replace("/", "-")
    project_id = f"{safe_topic}-{timestamp}"
    output_dir = Path("results") / project_id
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[dim]Output directory: {output_dir}[/dim]\n")

    # Step 4: Run workflow
    orchestrator = CollaborativeWorkflowOrchestrator(
        topic=topic,
        major_field=major_field,
        subfield=subfield,
        writer_team=writer_team,
        reviewer_configs=reviewer_configs,
        output_dir=output_dir,
        max_rounds=max_rounds,
        threshold=threshold,
        target_manuscript_length=target_length
    )

    try:
        result = await orchestrator.run()

        console.print("\n[bold green]✓ Complete collaborative workflow finished![/bold green]")
        console.print(f"\n[dim]Results saved to: {output_dir}[/dim]\n")

        return 0

    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    cli()
