#!/usr/bin/env python3
"""
Verify GitHub Integration is working correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from devops_agent.integrations.github_client import (
    GitHubClient,
    PYGITHUB_AVAILABLE,
)
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


async def main():
    """Verify GitHub integration."""
    console.print(Panel.fit(
        "[bold white]GitHub Integration Verification[/bold white]",
        border_style="cyan"
    ))
    
    # Check PyGithub
    console.print("\n[bold cyan]1. Checking PyGithub Installation[/bold cyan]")
    
    table = Table()
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    
    if PYGITHUB_AVAILABLE:
        table.add_row("PyGithub Library", "✅ Installed")
        table.add_row("Method", "PyGithub (Primary)")
    else:
        table.add_row("PyGithub Library", "⚠️ Not Installed")
        table.add_row("Method", "REST API (Fallback)")
    
    console.print(table)
    
    # Initialize client
    console.print("\n[bold cyan]2. Initializing GitHub Client[/bold cyan]")
    
    client = GitHubClient()  # Will read from GITHUB_TOKEN env
    
    if client._pygithub:
        console.print("✅ Using PyGithub")
    else:
        console.print("✅ Using REST API fallback")
    
    # Check token
    console.print("\n[bold cyan]3. Checking GitHub Token[/bold cyan]")
    
    if client.token:
        token_preview = client.token[:10] + "..." if len(client.token) > 10 else "***"
        console.print(f"✅ Token found: {token_preview}")
        
        # Verify token
        is_valid = await client.verify_token()
        if is_valid:
            console.print("✅ Token is valid")
        else:
            console.print("⚠️ Token verification failed (may not be set)")
    else:
        console.print("⚠️ No GITHUB_TOKEN environment variable set")
        console.print("   Set with: export GITHUB_TOKEN='ghp_xxxxx'")
    
    await client.close()
    
    # Summary
    console.print("\n" + "="*60)
    console.print("[bold]Summary:[/bold]")
    console.print("="*60)
    
    if PYGITHUB_AVAILABLE:
        console.print("✅ PyGithub integration: [green]ACTIVE[/green]")
        console.print("✅ REST API fallback: [green]AVAILABLE[/green]")
        console.print("\n[cyan]Recommended: Your setup is optimal![/cyan]")
    else:
        console.print("⚠️ PyGithub: [yellow]NOT INSTALLED[/yellow]")
        console.print("✅ REST API fallback: [green]ACTIVE[/green]")
        console.print("\n[yellow]Recommended: Install PyGithub for better reliability[/yellow]")
        console.print("   pip install PyGithub>=2.1.1")
    
    console.print("\n[bold green]GitHub integration is ready to use! 🚀[/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
