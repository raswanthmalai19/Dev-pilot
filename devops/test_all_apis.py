#!/usr/bin/env python3
"""
Comprehensive API and Integration Testing Script
Tests all API keys, configurations, and service accessibility.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def test_environment_variables():
    """Test if all required environment variables are set."""
    console.print(Panel.fit(
        "[bold white]Environment Variables Check[/bold white]",
        border_style="cyan"
    ))
    
    env_vars = {
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "GCP_PROJECT_ID": os.getenv("GCP_PROJECT_ID"),
        "GCP_REGION": os.getenv("GCP_REGION"),
        "GCP_ARTIFACT_REGISTRY": os.getenv("GCP_ARTIFACT_REGISTRY"),
        "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN"),
        "DOCKER_REGISTRY": os.getenv("DOCKER_REGISTRY"),
        "DOCKER_USERNAME": os.getenv("DOCKER_USERNAME"),
        "DOCKER_PASSWORD": os.getenv("DOCKER_PASSWORD"),
    }
    
    table = Table(title="Environment Variables")
    table.add_column("Variable", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Value Preview", style="yellow")
    
    all_set = True
    for var_name, var_value in env_vars.items():
        if var_value:
            preview = var_value[:20] + "..." if len(var_value) > 20 else var_value
            if "KEY" in var_name or "TOKEN" in var_name or "PASSWORD" in var_name:
                preview = "***" + var_value[-4:] if len(var_value) > 4 else "***"
            table.add_row(var_name, "✅ Set", preview)
        else:
            table.add_row(var_name, "❌ Not Set", "-")
            all_set = False
    
    console.print(table)
    return all_set, env_vars


async def test_gemini_api(api_key):
    """Test Gemini API connectivity."""
    console.print("\n[bold cyan]Testing Gemini API...[/bold cyan]")
    
    if not api_key:
        console.print("❌ GEMINI_API_KEY not set")
        return False
    
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('models/gemini-2.0-flash')
        
        # Simple test
        response = model.generate_content("Say 'Hello DevPilot' in one word")
        
        if response.text:
            console.print(f"✅ Gemini API working - Response: {response.text[:50]}")
            return True
        else:
            console.print("⚠️ Gemini API responded but no text received")
            return False
            
    except Exception as e:
        console.print(f"❌ Gemini API Error: {str(e)}")
        return False


async def test_github_api(token):
    """Test GitHub API connectivity."""
    console.print("\n[bold cyan]Testing GitHub API...[/bold cyan]")
    
    if not token:
        console.print("❌ GITHUB_TOKEN not set")
        return False
    
    try:
        from devops_agent.integrations.github_client import GitHubClient
        
        client = GitHubClient()
        is_valid = await client.verify_token()
        
        if is_valid:
            console.print("✅ GitHub API token is valid")
            
            # Try to get user info
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    headers = {"Authorization": f"token {token}"}
                    async with session.get("https://api.github.com/user", headers=headers) as resp:
                        if resp.status == 200:
                            user_data = await resp.json()
                            console.print(f"✅ Authenticated as: {user_data.get('login', 'Unknown')}")
                            console.print(f"   Rate limit info available")
            except Exception as e:
                console.print(f"⚠️ Could not fetch user info: {e}")
            
            await client.close()
            return True
        else:
            console.print("❌ GitHub token validation failed")
            await client.close()
            return False
            
    except Exception as e:
        console.print(f"❌ GitHub API Error: {str(e)}")
        return False


async def test_gcp_apis(project_id, credentials_path):
    """Test Google Cloud Platform APIs."""
    console.print("\n[bold cyan]Testing Google Cloud APIs...[/bold cyan]")
    
    if not project_id:
        console.print("❌ GCP_PROJECT_ID not set")
        return False
    
    results = {}
    
    # Test Cloud Run API
    console.print("\n  [yellow]Testing Cloud Run API...[/yellow]")
    try:
        from google.cloud import run_v2
        
        if credentials_path and Path(credentials_path).exists():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        
        client = run_v2.ServicesClient()
        parent = f"projects/{project_id}/locations/us-central1"
        
        # Try to list services (doesn't create anything)
        try:
            list(client.list_services(parent=parent, page_size=1))
            console.print("  ✅ Cloud Run API accessible")
            results['cloud_run'] = True
        except Exception as e:
            if "403" in str(e):
                console.print(f"  ⚠️ Cloud Run API: Permission denied (enable Cloud Run API)")
            elif "404" in str(e):
                console.print(f"  ⚠️ Cloud Run API: Not found (enable Cloud Run API)")
            else:
                console.print(f"  ❌ Cloud Run API Error: {str(e)[:100]}")
            results['cloud_run'] = False
            
    except ImportError:
        console.print("  ⚠️ google-cloud-run not installed")
        console.print("     Install: pip install google-cloud-run")
        results['cloud_run'] = False
    except Exception as e:
        console.print(f"  ❌ Cloud Run Error: {str(e)[:100]}")
        results['cloud_run'] = False
    
    # Test Artifact Registry API
    console.print("\n  [yellow]Testing Artifact Registry API...[/yellow]")
    try:
        from google.cloud import artifactregistry_v1
        
        client = artifactregistry_v1.ArtifactRegistryClient()
        parent = f"projects/{project_id}/locations/us-central1"
        
        try:
            list(client.list_repositories(parent=parent, page_size=1))
            console.print("  ✅ Artifact Registry API accessible")
            results['artifact_registry'] = True
        except Exception as e:
            if "403" in str(e):
                console.print(f"  ⚠️ Artifact Registry: Permission denied")
            elif "404" in str(e):
                console.print(f"  ⚠️ Artifact Registry: Not found (enable API)")
            else:
                console.print(f"  ❌ Artifact Registry Error: {str(e)[:100]}")
            results['artifact_registry'] = False
            
    except ImportError:
        console.print("  ⚠️ google-cloud-artifact-registry not installed")
        results['artifact_registry'] = False
    except Exception as e:
        console.print(f"  ❌ Artifact Registry Error: {str(e)[:100]}")
        results['artifact_registry'] = False
    
    # Test Cloud Build API
    console.print("\n  [yellow]Testing Cloud Build API...[/yellow]")
    try:
        from google.cloud import cloudbuild_v1
        
        client = cloudbuild_v1.CloudBuildClient()
        parent = f"projects/{project_id}/locations/us-central1"
        
        try:
            list(client.list_builds(project_id=project_id, page_size=1))
            console.print("  ✅ Cloud Build API accessible")
            results['cloud_build'] = True
        except Exception as e:
            if "403" in str(e):
                console.print(f"  ⚠️ Cloud Build: Permission denied")
            elif "404" in str(e):
                console.print(f"  ⚠️ Cloud Build: Not found (enable API)")
            else:
                console.print(f"  ❌ Cloud Build Error: {str(e)[:100]}")
            results['cloud_build'] = False
            
    except ImportError:
        console.print("  ⚠️ google-cloud-build not installed")
        results['cloud_build'] = False
    except Exception as e:
        console.print(f"  ❌ Cloud Build Error: {str(e)[:100]}")
        results['cloud_build'] = False
    
    return any(results.values())


async def test_docker_config(registry, username, password):
    """Test Docker configuration."""
    console.print("\n[bold cyan]Testing Docker Configuration...[/bold cyan]")
    
    if not all([registry, username, password]):
        console.print("⚠️ Docker credentials not fully configured")
        console.print(f"   Registry: {'✅' if registry else '❌'}")
        console.print(f"   Username: {'✅' if username else '❌'}")
        console.print(f"   Password: {'✅' if password else '❌'}")
        return False
    
    try:
        import docker
        client = docker.from_env()
        
        # Test Docker daemon
        client.ping()
        console.print("✅ Docker daemon is running")
        
        # Test Docker version
        version = client.version()
        console.print(f"✅ Docker version: {version.get('Version', 'Unknown')}")
        
        return True
        
    except ImportError:
        console.print("⚠️ docker library not installed")
        console.print("   Install: pip install docker")
        return False
    except Exception as e:
        console.print(f"❌ Docker Error: {str(e)}")
        return False


async def main():
    """Run all tests."""
    console.print(Panel.fit(
        "[bold white]🔍 Comprehensive API & Integration Tests[/bold white]",
        border_style="cyan",
        padding=(1, 2)
    ))
    
    # Test 1: Environment Variables
    console.print("\n[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    console.print("[bold yellow]Step 1: Environment Variables[/bold yellow]")
    console.print("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    env_ok, env_vars = test_environment_variables()
    
    # Test 2: Gemini API
    console.print("\n[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    console.print("[bold yellow]Step 2: Gemini AI API[/bold yellow]")
    console.print("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    gemini_ok = await test_gemini_api(env_vars.get("GEMINI_API_KEY"))
    
    # Test 3: GitHub API
    console.print("\n[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    console.print("[bold yellow]Step 3: GitHub API[/bold yellow]")
    console.print("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    github_ok = await test_github_api(env_vars.get("GITHUB_TOKEN"))
    
    # Test 4: Google Cloud APIs
    console.print("\n[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    console.print("[bold yellow]Step 4: Google Cloud Platform APIs[/bold yellow]")
    console.print("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    gcp_ok = await test_gcp_apis(
        env_vars.get("GCP_PROJECT_ID"),
        env_vars.get("GOOGLE_APPLICATION_CREDENTIALS")
    )
    
    # Test 5: Docker
    console.print("\n[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    console.print("[bold yellow]Step 5: Docker Configuration[/bold yellow]")
    console.print("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    docker_ok = await test_docker_config(
        env_vars.get("DOCKER_REGISTRY"),
        env_vars.get("DOCKER_USERNAME"),
        env_vars.get("DOCKER_PASSWORD")
    )
    
    # Final Summary
    console.print("\n" + "="*70)
    console.print("[bold white]FINAL SUMMARY[/bold white]")
    console.print("="*70)
    
    summary_table = Table(show_header=True, header_style="bold magenta")
    summary_table.add_column("Component", style="cyan", width=30)
    summary_table.add_column("Status", style="green", width=15)
    summary_table.add_column("Notes", style="yellow")
    
    summary_table.add_row(
        "Environment Variables",
        "✅ Pass" if env_ok else "⚠️ Issues",
        "All required vars set" if env_ok else "Some vars missing"
    )
    
    summary_table.add_row(
        "Gemini AI API",
        "✅ Working" if gemini_ok else "❌ Failed",
        "Ready for AI operations" if gemini_ok else "Check API key"
    )
    
    summary_table.add_row(
        "GitHub API",
        "✅ Working" if github_ok else "❌ Failed",
        "GitHub integration ready" if github_ok else "Check token"
    )
    
    summary_table.add_row(
        "Google Cloud APIs",
        "✅ Working" if gcp_ok else "❌ Failed",
        "GCP services accessible" if gcp_ok else "Check credentials/APIs"
    )
    
    summary_table.add_row(
        "Docker",
        "✅ Working" if docker_ok else "⚠️ Issues",
        "Docker ready" if docker_ok else "Partial configuration"
    )
    
    console.print(summary_table)
    
    # Overall status
    console.print("\n" + "="*70)
    all_ok = gemini_ok and github_ok
    
    if all_ok and gcp_ok:
        console.print("[bold green]🎉 ALL CRITICAL SYSTEMS OPERATIONAL! 🎉[/bold green]")
        console.print("\n[green]Your DevPilot is ready for deployment![/green]")
    elif all_ok:
        console.print("[bold yellow]⚠️ CORE SYSTEMS OPERATIONAL[/bold yellow]")
        console.print("\n[yellow]Gemini and GitHub working. GCP needs attention.[/yellow]")
    else:
        console.print("[bold red]❌ CRITICAL SYSTEMS NEED ATTENTION[/bold red]")
        console.print("\n[red]Please fix the failed components to use DevPilot.[/red]")
    
    console.print("="*70)
    
    # Recommendations
    if not gemini_ok:
        console.print("\n[bold red]🔧 Fix Gemini API:[/bold red]")
        console.print("   export GEMINI_API_KEY='your-api-key-here'")
    
    if not github_ok:
        console.print("\n[bold red]🔧 Fix GitHub API:[/bold red]")
        console.print("   export GITHUB_TOKEN='ghp_xxxxxxxxxxxxx'")
    
    if not gcp_ok:
        console.print("\n[bold yellow]🔧 Fix Google Cloud:[/bold yellow]")
        console.print("   1. Set GCP_PROJECT_ID")
        console.print("   2. Set GOOGLE_APPLICATION_CREDENTIALS path")
        console.print("   3. Enable required APIs in GCP Console")
    
    return 0 if all_ok else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
