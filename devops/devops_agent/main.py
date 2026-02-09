"""
DevOps Automation Agent - Main Entry Point
CLI interface for the agentic DevOps pipeline.

Includes:
- devops-agent: Original pipeline commands
- devpilot: Autonomous GitHub-to-Cloud Run deployment
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from devops_agent.config import get_config
from devops_agent.core.logger import setup_logging
from devops_agent.agents.orchestrator import DeploymentOrchestrator, deploy_project
from devops_agent.utils.validators import validate_project_path, validate_config

# CLI app
app = typer.Typer(
    name="devops-agent",
    help="🚀 Agentic DevOps Automation - Upload code, get deployed!",
    add_completion=False,
)

# Dev Pilot subcommand group
devpilot_app = typer.Typer(
    name="devpilot",
    help="🤖 Dev Pilot - Autonomous GitHub-to-Cloud Run deployment",
)
app.add_typer(devpilot_app, name="devpilot")

console = Console()


def print_header():
    """Print the application header."""
    console.print(Panel.fit(
        "[bold blue]DevOps Automation Agent[/bold blue]\n"
        "[dim]Powered by Gemini AI[/dim]",
        border_style="blue",
    ))


def print_devpilot_header():
    """Print the Dev Pilot header."""
    console.print(Panel.fit(
        "[bold cyan]🤖 Dev Pilot[/bold cyan]\n"
        "[dim]Autonomous GitHub → Cloud Run Deployment[/dim]",
        border_style="cyan",
    ))



@app.command()
def deploy(
    project_path: Path = typer.Argument(
        ...,
        help="Path to the project directory",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    build: bool = typer.Option(
        False,
        "--build", "-b",
        help="Run actual build (requires dependencies installed)",
    ),
    test: bool = typer.Option(
        False,
        "--test", "-t",
        help="Run tests during build",
    ),
    push: bool = typer.Option(
        False,
        "--push", "-p",
        help="Push container to registry",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose output",
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON",
    ),
):
    """
    🚀 Deploy a project through the DevOps pipeline.
    
    This will:
    1. Analyze your project (detect language, framework, dependencies)
    2. Generate optimized Dockerfile
    3. Create GitHub Actions CI/CD pipeline
    4. Generate Terraform infrastructure config
    5. Optionally build and push container
    
    Example:
        devops-agent deploy ./my-app
        devops-agent deploy ./my-app --build --test
    """
    print_header()
    setup_logging(verbose)
    
    # Validate project path
    is_valid, error = validate_project_path(project_path)
    if not is_valid:
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(1)
    
    # Validate config
    config = get_config()
    issues = validate_config(config)
    if issues:
        console.print("[yellow]Configuration warnings:[/yellow]")
        for issue in issues:
            console.print(f"  • {issue}")
        console.print()
    
    # Run the pipeline
    console.print(f"\n[bold]Processing project:[/bold] {project_path}\n")
    
    try:
        report = asyncio.run(
            deploy_project(
                project_path=project_path,
                run_build=build,
            )
        )
        
        if output_json:
            console.print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_report(report)
        
        # Exit with appropriate code
        if report.status.value == "success":
            raise typer.Exit(0)
        elif report.status.value == "partial":
            raise typer.Exit(0)  # Partial success is still OK
        else:
            raise typer.Exit(1)
            
    except Exception as e:
        if verbose:
            console.print_exception()
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def analyze(
    project_path: Path = typer.Argument(
        ...,
        help="Path to the project directory",
        exists=True,
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON",
    ),
):
    """
    🔍 Analyze a project without deploying.
    
    Detects:
    - Programming language and version
    - Framework being used
    - Dependencies
    - Entry points
    - Build/start commands
    """
    print_header()
    setup_logging(False)
    
    from devops_agent.agents.project_analyzer import ProjectAnalyzer
    
    try:
        analyzer = ProjectAnalyzer()
        info = asyncio.run(analyzer.run(project_path))
        
        if output_json:
            console.print(json.dumps(info.to_dict(), indent=2))
        else:
            _print_project_info(info)
            
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def check():
    """
    🔧 Check prerequisites and configuration.
    
    Verifies:
    - Required environment variables
    - Docker installation
    - Terraform installation (optional)
    - gcloud CLI (optional)
    """
    print_header()
    
    config = get_config()
    
    # Create results table
    table = Table(title="Prerequisites Check")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")
    
    # Check Gemini API key
    if config.gemini.api_key:
        table.add_row("Gemini API Key", "✅ Set", f"Model: {config.gemini.model_name}")
    else:
        table.add_row("Gemini API Key", "❌ Missing", "Set GEMINI_API_KEY env var")
    
    # Check Docker
    from devops_agent.core.executor import CommandExecutor
    executor = CommandExecutor()
    
    docker_check = asyncio.run(executor.run("docker --version", timeout=5))
    if docker_check.success:
        table.add_row("Docker", "✅ Found", docker_check.stdout.strip().split("\n")[0])
    else:
        table.add_row("Docker", "❌ Not found", "Install Docker Desktop")
    
    # Check Terraform
    tf_check = asyncio.run(executor.run("terraform --version", timeout=5))
    if tf_check.success:
        table.add_row("Terraform", "✅ Found", tf_check.stdout.strip().split("\n")[0])
    else:
        table.add_row("Terraform", "⚠️ Not found", "Optional - needed for deployment")
    
    # Check gcloud
    gcloud_check = asyncio.run(executor.run("gcloud --version", timeout=5))
    if gcloud_check.success:
        table.add_row("gcloud CLI", "✅ Found", "Google Cloud SDK installed")
    else:
        table.add_row("gcloud CLI", "⚠️ Not found", "Optional - needed for deployment")
    
    # Check GCP project
    if config.gcp.project_id:
        table.add_row("GCP Project", "✅ Set", config.gcp.project_id)
    else:
        table.add_row("GCP Project", "⚠️ Not set", "Set GCP_PROJECT_ID for deployments")
    
    console.print()
    console.print(table)


def _print_report(report):
    """Print the pipeline report."""
    # Status panel
    status_color = {
        "success": "green",
        "partial": "yellow", 
        "failed": "red",
    }
    color = status_color.get(report.status.value, "white")
    
    console.print(Panel(
        f"[bold {color}]{report.status.value.upper()}[/bold {color}]\n"
        f"Duration: {report.duration_seconds:.2f}s",
        title=f"Pipeline: {report.pipeline_id}",
        border_style=color,
    ))
    
    # Stages table
    table = Table(title="Pipeline Stages")
    table.add_column("Stage", style="cyan")
    table.add_column("Status")
    table.add_column("Duration")
    table.add_column("Message")
    
    for stage, result in report.stages.items():
        status = "✅" if result.success else "❌"
        table.add_row(
            stage.value.title(),
            status,
            f"{result.duration_seconds:.1f}s",
            result.message[:50] if result.message else "-",
        )
    
    console.print(table)
    
    # Generated files
    if report.generated_files:
        console.print("\n[bold]Generated Files:[/bold]")
        for filename in report.generated_files.keys():
            console.print(f"  📄 {filename}")
    
    # Deployment URL
    if report.deployment_url:
        console.print(f"\n[bold green]🚀 Deployed to:[/bold green] {report.deployment_url}")
    
    # Recommendations
    if report.recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for rec in report.recommendations:
            console.print(f"  💡 {rec}")


def _print_project_info(info):
    """Print project analysis info."""
    table = Table(title="Project Analysis")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Name", info.name)
    table.add_row("Type", info.project_type.value)
    table.add_row("Framework", info.framework.value)
    table.add_row("Package Manager", info.package_manager or "-")
    table.add_row("Port", str(info.port))
    table.add_row("Is Web Service", "Yes" if info.is_web_service else "No")
    table.add_row("Entry Point", info.entry_point or "-")
    table.add_row("Build Command", info.build_command or "-")
    table.add_row("Start Command", info.start_command or "-")
    table.add_row("Test Command", info.test_command or "-")
    table.add_row("Dependencies", str(len(info.dependencies)))
    table.add_row("Files", str(info.total_file_count))
    
    console.print(table)


# ═══════════════════════════════════════════════════════════════════════════════
# DEV PILOT COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

@devpilot_app.command("deploy")
def devpilot_deploy(
    repo_url: str = typer.Argument(
        ...,
        help="GitHub repository URL (e.g., https://github.com/user/repo)",
    ),
    branch: str = typer.Option(
        "devpilot-tested",
        "--branch", "-b",
        help="Branch to deploy (should be QA-approved)",
    ),
    security_status: str = typer.Option(
        "PASS",
        "--security", "-s",
        help="Security scan status (PASS/FAIL)",
    ),
    qa_status: str = typer.Option(
        "PASS",
        "--qa", "-q",
        help="QA test status (PASS/FAIL)",
    ),
    project_id: str = typer.Option(
        None,
        "--project", "-p",
        help="GCP project ID (uses GCP_PROJECT_ID if not specified)",
    ),
    region: str = typer.Option(
        "us-central1",
        "--region", "-r",
        help="GCP region for deployment",
    ),
    service_name: str = typer.Option(
        None,
        "--service",
        help="Cloud Run service name (auto-generated if not specified)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose output",
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON",
    ),
):
    """
    🚀 Deploy a GitHub repository to Cloud Run automatically.
    
    This is the autonomous deployment pipeline that:
    1. Validates preconditions (Security & QA status must be PASS)
    2. Clones the repository from the specified branch
    3. Analyzes the project structure
    4. Generates missing configs (Dockerfile, etc.)
    5. Builds Docker image using Cloud Build
    6. Deploys to Cloud Run
    7. Runs health checks
    8. Auto-rollback if unhealthy
    
    Example:
        devops-agent devpilot deploy https://github.com/user/repo
        devops-agent devpilot deploy https://github.com/user/repo --branch main
        devops-agent devpilot deploy https://github.com/user/repo -p my-gcp-project
    """
    print_devpilot_header()
    setup_logging(verbose)
    
    from devops_agent.agents.devpilot_orchestrator import (
        DevPilotOrchestrator,
        DevPilotConfig,
        PipelineStatus,
    )
    
    # Build config
    config = DevPilotConfig(
        project_id=project_id,
        region=region,
        service_name=service_name,
    )
    
    console.print(f"\n[bold]Repository:[/bold] {repo_url}")
    console.print(f"[bold]Branch:[/bold] {branch}")
    console.print(f"[bold]Security Status:[/bold] {security_status}")
    console.print(f"[bold]QA Status:[/bold] {qa_status}")
    console.print(f"[bold]GCP Project:[/bold] {project_id or 'auto-detect'}")
    console.print(f"[bold]Region:[/bold] {region}")
    console.print()
    
    try:
        orchestrator = DevPilotOrchestrator(config=config)
        
        report = asyncio.run(
            orchestrator.run(
                repo_url=repo_url,
                branch=branch,
                security_status=security_status,
                qa_status=qa_status,
            )
        )
        
        if output_json:
            console.print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_devpilot_report(report)
        
        # Exit with appropriate code
        if report.status == PipelineStatus.SUCCESS:
            raise typer.Exit(0)
        elif report.status == PipelineStatus.ROLLED_BACK:
            raise typer.Exit(2)  # Rolled back = partial failure
        else:
            raise typer.Exit(1)
            
    except typer.Exit:
        raise
    except Exception as e:
        if verbose:
            console.print_exception()
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@devpilot_app.command("status")
def devpilot_status(
    service_name: str = typer.Argument(
        ...,
        help="Cloud Run service name",
    ),
    project_id: str = typer.Option(
        None,
        "--project", "-p",
        help="GCP project ID",
    ),
    region: str = typer.Option(
        "us-central1",
        "--region", "-r",
        help="GCP region",
    ),
):
    """
    📊 Check the status of a deployed service.
    """
    print_devpilot_header()
    setup_logging(False)
    
    from devops_agent.core.cloud_run_client import CloudRunClient
    
    try:
        client = CloudRunClient(project_id=project_id, region=region)
        result = asyncio.run(client.get_service_status(service_name))
        
        if result.success:
            console.print(f"[green]✅ Service:[/green] {service_name}")
            console.print(f"[bold]URL:[/bold] {result.service_url}")
            console.print(f"[bold]Revision:[/bold] {result.revision_name}")
            console.print(f"[bold]Status:[/bold] {result.status.value}")
        else:
            console.print(f"[red]❌ Service not found or error:[/red] {result.errors}")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@devpilot_app.command("rollback")
def devpilot_rollback(
    service_name: str = typer.Argument(
        ...,
        help="Cloud Run service name",
    ),
    target_revision: str = typer.Option(
        None,
        "--revision", "-r",
        help="Target revision to rollback to (auto-select previous if not specified)",
    ),
    project_id: str = typer.Option(
        None,
        "--project", "-p",
        help="GCP project ID",
    ),
    region: str = typer.Option(
        "us-central1",
        "--region",
        help="GCP region",
    ),
):
    """
    ⏪ Rollback a service to a previous revision.
    """
    print_devpilot_header()
    setup_logging(False)
    
    from devops_agent.agents.rollback_agent import RollbackAgent
    
    console.print(f"[bold]Rolling back:[/bold] {service_name}")
    if target_revision:
        console.print(f"[bold]Target revision:[/bold] {target_revision}")
    else:
        console.print("[dim]Auto-selecting previous revision...[/dim]")
    
    try:
        agent = RollbackAgent(project_id=project_id, region=region)
        result = asyncio.run(agent.run(
            service_name=service_name,
            target_revision=target_revision,
        ))
        
        if result.success:
            console.print(f"\n[green]✅ Rollback successful![/green]")
            console.print(f"[bold]Now running:[/bold] {result.rolled_back_to}")
            console.print(f"[bold]URL:[/bold] {result.service_url}")
        else:
            console.print(f"\n[red]❌ Rollback failed:[/red] {result.errors}")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@devpilot_app.command("validate")
def devpilot_validate(
    repo_url: Optional[str] = typer.Argument(
        None,
        help="GitHub repository URL (optional)",
    ),
    branch: str = typer.Option(
        "devpilot-tested",
        "--branch", "-b",
        help="Branch name",
    ),
    security_status: str = typer.Option(
        "PASS",
        "--security", "-s",
        help="Security scan status",
    ),
    qa_status: str = typer.Option(
        "PASS",
        "--qa", "-q",
        help="QA test status",
    ),
):
    """
    ✅ Validate deployment preconditions.
    
    Checks if Security and QA status are PASS and branch is approved.
    """
    print_devpilot_header()
    setup_logging(False)
    
    from devops_agent.agents.precondition_validator import (
        PreconditionValidator,
        PipelineInput,
    )
    
    input_data = PipelineInput(
        repo_url=repo_url,
        branch=branch,
        security_status=security_status,
        qa_status=qa_status,
    )
    
    validator = PreconditionValidator()
    result = asyncio.run(validator.validate(input_data))
    
    if result.passed:
        console.print("\n[green]✅ All preconditions passed![/green]")
        console.print("[dim]Deployment is authorized to proceed.[/dim]")
    else:
        console.print("\n[red]❌ Precondition validation failed![/red]")
        for reason in result.failure_reasons:
            console.print(f"  - {reason.value}")
        raise typer.Exit(1)


def _print_devpilot_report(report):
    """Print the Dev Pilot pipeline report."""
    from devops_agent.agents.devpilot_orchestrator import PipelineStatus
    
    # Status colors
    status_colors = {
        PipelineStatus.SUCCESS: "green",
        PipelineStatus.FAILED: "red",
        PipelineStatus.ROLLED_BACK: "yellow",
        PipelineStatus.RUNNING: "blue",
        PipelineStatus.PENDING: "dim",
    }
    color = status_colors.get(report.status, "white")
    
    # Main status panel
    console.print(Panel(
        f"[bold {color}]{report.status.value.upper()}[/bold {color}]\n"
        f"Duration: {report.total_duration_seconds:.1f}s",
        title=f"Deployment: {report.deployment_id}",
        border_style=color,
    ))
    
    # Steps table
    table = Table(title="Pipeline Steps")
    table.add_column("Step", style="cyan")
    table.add_column("Status")
    table.add_column("Duration")
    table.add_column("Message")
    
    for step in report.steps:
        status_icon = "✅" if step.success else "❌"
        table.add_row(
            step.step.value,
            status_icon,
            f"{step.duration_seconds:.1f}s",
            step.message[:50] if step.message else "-",
        )
    
    console.print(table)
    
    # Deployment details
    if report.service_url:
        console.print(f"\n[bold green]🚀 Service URL:[/bold green] {report.service_url}")
    if report.image_url:
        console.print(f"[bold]📦 Image:[/bold] {report.image_url}")
    if report.revision_name:
        console.print(f"[bold]🔖 Revision:[/bold] {report.revision_name}")
    
    # Errors
    if report.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for error in report.errors:
            console.print(f"  ❌ {error}")


if __name__ == "__main__":
    app()

