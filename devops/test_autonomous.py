#!/usr/bin/env python3
"""
Test script for DevOps Agent autonomous capabilities.

Tests the full system without requiring GCP credentials.
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from devops_agent.config import get_config
from devops_agent.core.gemini_client import GeminiClient
from devops_agent.core.uncertainty_handler import UncertaintyHandler
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


async def test_configuration():
    """Test configuration loading."""
    console.print("\n[bold cyan]Testing Configuration[/bold cyan]")
    
    config = get_config()
    
    table = Table(title="Configuration Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Value")
    
    # Check Gemini API
    api_key_status = "✅ Set" if config.gemini.api_key else "❌ Not Set"
    api_key_value = config.gemini.api_key[:20] + "..." if config.gemini.api_key else "N/A"
    table.add_row("Gemini API Key", api_key_status, api_key_value)
    
    # Check GCP Project
    gcp_status = "✅ Set" if config.gcp.project_id else "⚠️ Not Set"
    table.add_row("GCP Project ID", gcp_status, config.gcp.project_id or "N/A")
    
    # Check GitHub Token
    gh_status = "✅ Set" if config.github.token else "⚠️ Optional"
    gh_value = config.github.token[:20] + "..." if config.github.token else "N/A"
    table.add_row("GitHub Token", gh_status, gh_value)
    
    # Check DevPilot Settings
    table.add_row("Auto Rollback", "✅ Enabled" if config.devpilot.auto_rollback else "❌ Disabled", str(config.devpilot.auto_rollback))
    table.add_row("Strict Mode", "✅ Enabled" if config.devpilot.strict_mode else "❌ Disabled", str(config.devpilot.strict_mode))
    table.add_row("Approved Branches", "✅ Set", ", ".join(config.devpilot.approved_branches))
    
    console.print(table)
    
    # Validate
    issues = config.validate()
    if issues:
        console.print("\n[bold red]Configuration Issues:[/bold red]")
        for issue in issues:
            console.print(f"  ❌ {issue}")
        return False
    else:
        console.print("\n[bold green]✅ Configuration Valid![/bold green]")
        return True


async def test_gemini_client():
    """Test Gemini AI client."""
    console.print("\n[bold cyan]Testing Gemini Client[/bold cyan]")
    
    try:
        client = GeminiClient()
        console.print("✅ Gemini client initialized")
        
        # Test simple generation
        response = await client.generate(
            "Say 'DevOps Agent is ready!' in exactly 5 words.",
            enable_tools=False
        )
        console.print(f"✅ Generation test passed: [green]{response.strip()}[/green]")
        
        return True
        
    except Exception as e:
        console.print(f"[red]❌ Gemini client test failed: {e}[/red]")
        return False


async def test_uncertainty_handler():
    """Test uncertainty resolution."""
    console.print("\n[bold cyan]Testing Uncertainty Handler[/bold cyan]")
    
    try:
        handler = UncertaintyHandler()
        console.print("✅ Uncertainty handler initialized")
        
        # Test port resolution
        result = await handler.resolve_port(
            project_path=Path("/tmp"),
            detected_framework="fastapi",
        )
        
        console.print(f"✅ Port resolution: {result.value} (confidence: {result.confidence.value})")
        console.print(f"   Reasoning: {result.reasoning}")
        
        # Test start command resolution
        result = await handler.resolve_start_command(
            project_type="python",
            framework="fastapi",
            entry_point="main.py",
        )
        
        console.print(f"✅ Start command: [green]{result.value}[/green]")
        console.print(f"   Confidence: {result.confidence.value}")
        
        return True
        
    except Exception as e:
        console.print(f"[red]❌ Uncertainty handler test failed: {e}[/red]")
        return False


async def test_project_detection():
    """Test project type detection on sample projects."""
    console.print("\n[bold cyan]Testing Project Detection[/bold cyan]")
    
    # Create a temporary Python project
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        
        # Create Python project files
        (project_path / "requirements.txt").write_text("flask==2.0.0\n")
        (project_path / "app.py").write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/")
def home():
    return "Hello!"

if __name__ == "__main__":
    app.run(port=5000)
""")
        
        # Test detection
        handler = UncertaintyHandler()
        
        file_patterns = {".py": 1, ".txt": 1}
        result = await handler.resolve_project_type(project_path, file_patterns)
        
        console.print(f"✅ Detected: {result.value}")
        console.print(f"   Confidence: {result.confidence.value}")
        console.print(f"   Strategy: {result.strategy_used.value}")
        
        # Test port detection from code
        code = (project_path / "app.py").read_text()
        port_result = await handler.resolve_port(
            project_path=project_path,
            detected_framework="flask",
            code_samples=[code],
        )
        
        console.print(f"✅ Port detected: {port_result.value}")
        
        return True


async def main():
    """Run all tests."""
    console.print(Panel.fit(
        "[bold white]DevOps Agent - Autonomous System Test Suite[/bold white]",
        border_style="cyan"
    ))
    
    results = []
    
    # Run tests
    results.append(("Configuration", await test_configuration()))
    results.append(("Gemini Client", await test_gemini_client()))
    results.append(("Uncertainty Handler", await test_uncertainty_handler()))
    results.append(("Project Detection", await test_project_detection()))
    
    # Summary
    console.print("\n" + "="*60)
    console.print("[bold]Test Summary:[/bold]")
    console.print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[green]✅ PASS[/green]" if result else "[red]❌ FAIL[/red]"
        console.print(f"  {status} - {test_name}")
    
    console.print("="*60)
    
    if passed == total:
        console.print(f"\n[bold green]All {total} tests passed! 🎉[/bold green]")
        console.print("\n[cyan]The autonomous DevOps agent is ready to deploy![/cyan]")
        return 0
    else:
        console.print(f"\n[bold yellow]{passed}/{total} tests passed[/bold yellow]")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
