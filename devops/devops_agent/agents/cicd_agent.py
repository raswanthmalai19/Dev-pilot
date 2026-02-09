"""
CI/CD Agent - Generates GitHub Actions workflows.
Supports auto-push to GitHub repository.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base_agent import BaseAgent
from ..models.project import ProjectInfo, ProjectType
from ..integrations.github_client import GitHubClient, GitHubResult


# GitHub Actions workflow templates
WORKFLOW_TEMPLATE = '''name: CI/CD Pipeline

on:
  push:
    branches: [{{ default_branch }}]
  pull_request:
    branches: [{{ default_branch }}]

env:
  PROJECT_ID: ${{ '{{' }} secrets.GCP_PROJECT_ID {{ '}}' }}
  REGION: ${{ '{{' }} secrets.GCP_REGION {{ '}}' }}
  SERVICE_NAME: {{ service_name }}
  REGISTRY: {{ registry }}

jobs:
  # Security scan (integration point for security agent)
  security-scan:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run security scan
        run: |
          echo "Security scan placeholder - integrate with security agent"
          # Add your security scanning tool here

  # Build and test
  build:
    name: Build & Test
    runs-on: ubuntu-latest
    needs: security-scan
    
    steps:
      - uses: actions/checkout@v4
      
      {{ setup_step }}
      
      {{ cache_step }}
      
      - name: Install dependencies
        run: {{ install_command }}
      
      {% if build_command %}
      - name: Build
        run: {{ build_command }}
      {% endif %}
      
      {% if test_command %}
      - name: Test
        run: {{ test_command }}
      {% endif %}

  # Build and push container
  containerize:
    name: Build Container
    runs-on: ubuntu-latest
    needs: build
    if: github.event_name == 'push' && github.ref == 'refs/heads/{{ default_branch }}'
    
    permissions:
      contents: read
      id-token: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ '{{' }} secrets.WIF_PROVIDER {{ '}}' }}
          service_account: ${{ '{{' }} secrets.WIF_SERVICE_ACCOUNT {{ '}}' }}
      
      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2
      
      - name: Configure Docker
        run: gcloud auth configure-docker {{ registry }} --quiet
      
      - name: Build and push image
        run: |
          docker build -t {{ registry }}/${{ '{{' }} env.PROJECT_ID {{ '}}' }}/{{ service_name }}:${{ '{{' }} github.sha {{ '}}' }} .
          docker push {{ registry }}/${{ '{{' }} env.PROJECT_ID {{ '}}' }}/{{ service_name }}:${{ '{{' }} github.sha {{ '}}' }}

  # Deploy to Cloud Run
  deploy:
    name: Deploy
    runs-on: ubuntu-latest
    needs: containerize
    if: github.event_name == 'push' && github.ref == 'refs/heads/{{ default_branch }}'
    
    permissions:
      contents: read
      id-token: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ '{{' }} secrets.WIF_PROVIDER {{ '}}' }}
          service_account: ${{ '{{' }} secrets.WIF_SERVICE_ACCOUNT {{ '}}' }}
      
      - name: Deploy to Cloud Run
        uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: {{ service_name }}
          region: ${{ '{{' }} env.REGION {{ '}}' }}
          image: {{ registry }}/${{ '{{' }} env.PROJECT_ID {{ '}}' }}/{{ service_name }}:${{ '{{' }} github.sha {{ '}}' }}
      
      - name: Show deployment URL
        run: |
          echo "Deployed to: $(gcloud run services describe {{ service_name }} --region ${{ '{{' }} env.REGION {{ '}}' }} --format 'value(status.url)')"
'''

# Language-specific setup steps
SETUP_STEPS = {
    ProjectType.PYTHON: '''- name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '{{ python_version }}'
          cache: 'pip' ''',
    
    ProjectType.NODEJS: '''- name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '{{ node_version }}'
          cache: '{{ package_manager }}' ''',
    
    ProjectType.GO: '''- name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '{{ go_version }}' ''',
    
    ProjectType.JAVA: '''- name: Set up JDK
        uses: actions/setup-java@v4
        with:
          java-version: '{{ java_version }}'
          distribution: 'temurin'
          cache: '{{ package_manager }}' ''',
    
    ProjectType.RUST: '''- name: Set up Rust
        uses: actions-rust-lang/setup-rust-toolchain@v1
        with:
          cache: true ''',
}

# Cache steps
CACHE_STEPS = {
    ProjectType.PYTHON: '',  # Handled by setup-python
    ProjectType.NODEJS: '',  # Handled by setup-node
    ProjectType.GO: '',  # Handled by setup-go
}


class CICDAgent(BaseAgent):
    """
    Generates CI/CD pipelines:
    - GitHub Actions workflows
    - Build, test, containerize, deploy stages
    - Auto-push to GitHub repository
    """
    
    def __init__(self, working_dir: Path = None, gemini_client=None, github_token: str = None):
        super().__init__("CICDAgent", working_dir, gemini_client)
        self.github = GitHubClient(token=github_token)
    
    def _get_system_instruction(self) -> str:
        return """You are a CI/CD expert specializing in GitHub Actions.
You create efficient, secure pipelines with proper caching, secrets management,
and deployment strategies. Follow GitHub Actions best practices."""
    
    async def run(
        self, 
        project_info: ProjectInfo,
        include_security_scan: bool = True,
        include_tests: bool = True,
        environment: str = "production",
        push_to_github: bool = False,  # NEW: Auto-push to GitHub
        github_owner: str = None,
        github_repo: str = None,
        create_pr: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate CI/CD pipeline configuration.
        
        Args:
            project_info: Analyzed project information
            include_security_scan: Include security scanning stage
            include_tests: Include test stage
            environment: Target environment
            push_to_github: Whether to auto-push workflow to GitHub
            github_owner: GitHub repository owner (required if push_to_github)
            github_repo: GitHub repository name (required if push_to_github)
            create_pr: Whether to create a PR instead of direct push
            
        Returns:
            Dict with generated files and configuration
        """
        result = {
            "success": True,
            "files": {},
            "secrets_required": [],
            "setup_instructions": [],
            "github_push": None,
        }
        
        try:
            # Step 1: Generate main workflow
            self.log_step("Generating GitHub Actions workflow", 1)
            workflow = await self._generate_workflow(project_info, include_tests)
            
            # Write workflow file locally
            workflow_dir = project_info.path / ".github" / "workflows"
            await self.file_manager.create_directory(workflow_dir)
            workflow_path = workflow_dir / "ci-cd.yml"
            await self.file_manager.write_file(workflow_path, workflow)
            result["files"]["ci-cd.yml"] = workflow
            
            # Step 2: Document required secrets
            self.log_step("Documenting required secrets", 2)
            result["secrets_required"] = self._get_required_secrets()
            
            # Step 3: Generate setup instructions
            self.log_step("Generating setup instructions", 3)
            result["setup_instructions"] = self._get_setup_instructions(project_info)
            
            # Step 4: Generate secrets documentation
            secrets_doc = self._generate_secrets_doc(result["secrets_required"])
            secrets_path = project_info.path / ".github" / "SECRETS.md"
            await self.file_manager.write_file(secrets_path, secrets_doc)
            result["files"]["SECRETS.md"] = secrets_doc
            
            # Step 5: Push to GitHub (optional)
            if push_to_github and github_owner and github_repo:
                self.log_step("Pushing workflow to GitHub", 4)
                push_result = await self.push_workflow_to_github(
                    workflow=workflow,
                    owner=github_owner,
                    repo=github_repo,
                    create_pr=create_pr,
                )
                result["github_push"] = push_result.to_dict()
                
                if not push_result.success:
                    result["success"] = False
                    self.logger.warning(f"GitHub push failed: {push_result.errors}")
            
            self.log_success("CI/CD pipeline generated successfully")
            
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            self.log_error(f"CI/CD generation failed: {e}", e)
        
        return result
    
    async def push_workflow_to_github(
        self,
        workflow: str,
        owner: str,
        repo: str,
        workflow_name: str = "ci-cd.yml",
        create_pr: bool = True,
    ) -> GitHubResult:
        """
        Push a workflow file to GitHub.
        
        Args:
            workflow: Workflow YAML content
            owner: Repository owner
            repo: Repository name
            workflow_name: Workflow file name
            create_pr: Whether to create a PR
            
        Returns:
            GitHubResult with push status
        """
        # Verify token first
        if not await self.github.verify_token():
            return GitHubResult(
                success=False,
                errors=["GitHub token not configured or invalid"],
            )
        
        return await self.github.push_workflow(
            owner=owner,
            repo=repo,
            workflow_content=workflow,
            workflow_name=workflow_name,
            create_pr=create_pr,
        )
    
    async def _generate_workflow(
        self, 
        project_info: ProjectInfo,
        include_tests: bool = True,
    ) -> str:
        """Generate the GitHub Actions workflow."""
        # Get template context
        context = self._build_context(project_info, include_tests)
        
        # Render template
        workflow = self.file_manager.render_template(WORKFLOW_TEMPLATE, context)
        
        return workflow
    
    def _build_context(
        self, 
        project_info: ProjectInfo,
        include_tests: bool,
    ) -> Dict[str, Any]:
        """Build template context."""
        service_name = project_info.name.lower().replace(" ", "-").replace("_", "-")
        
        # Get setup step
        setup_template = SETUP_STEPS.get(project_info.project_type, "")
        setup_step = self.file_manager.render_template(setup_template, {
            "python_version": project_info.language_version or "3.11",
            "node_version": project_info.language_version or "20",
            "go_version": project_info.language_version or "1.21",
            "java_version": "17",
            "package_manager": project_info.package_manager or "npm",
        })
        
        # Get cache step
        cache_step = CACHE_STEPS.get(project_info.project_type, "")
        
        return {
            "default_branch": "main",
            "service_name": service_name,
            "registry": "gcr.io",
            "setup_step": setup_step,
            "cache_step": cache_step,
            "install_command": project_info.build_command or "echo 'No install step'",
            "build_command": project_info.build_command if "build" in (project_info.build_command or "") else None,
            "test_command": project_info.test_command if include_tests else None,
        }
    
    def _get_required_secrets(self) -> List[Dict[str, str]]:
        """Get list of required GitHub secrets."""
        return [
            {
                "name": "GCP_PROJECT_ID",
                "description": "Google Cloud project ID",
                "required": True,
            },
            {
                "name": "GCP_REGION",
                "description": "Google Cloud region (e.g., us-central1)",
                "required": True,
            },
            {
                "name": "WIF_PROVIDER",
                "description": "Workload Identity Federation provider",
                "required": True,
            },
            {
                "name": "WIF_SERVICE_ACCOUNT",
                "description": "Service account email for WIF",
                "required": True,
            },
        ]
    
    def _get_setup_instructions(self, project_info: ProjectInfo) -> List[str]:
        """Get setup instructions for the CI/CD pipeline."""
        return [
            "1. Create a Google Cloud project if you haven't already",
            "2. Enable Cloud Run, Artifact Registry, and IAM APIs",
            "3. Set up Workload Identity Federation for GitHub Actions:",
            "   - Create a Workload Identity Pool",
            "   - Add GitHub as an OIDC provider",
            "   - Create a service account with necessary permissions",
            "4. Add the required secrets to your GitHub repository",
            "5. Push the .github/workflows/ci-cd.yml file to trigger the pipeline",
        ]
    
    def _generate_secrets_doc(self, secrets: List[Dict[str, str]]) -> str:
        """Generate documentation for required secrets."""
        lines = [
            "# Required GitHub Secrets",
            "",
            "Configure these secrets in your GitHub repository settings:",
            "Settings → Secrets and variables → Actions → New repository secret",
            "",
            "## Secrets",
            "",
        ]
        
        for secret in secrets:
            required = "Required" if secret.get("required") else "Optional"
            lines.append(f"### `{secret['name']}`")
            lines.append(f"- **Description:** {secret['description']}")
            lines.append(f"- **{required}**")
            lines.append("")
        
        lines.extend([
            "## Setup Workload Identity Federation",
            "",
            "```bash",
            "# Create workload identity pool",
            "gcloud iam workload-identity-pools create github-pool \\",
            "  --location=global \\",
            "  --display-name=\"GitHub Actions Pool\"",
            "",
            "# Add GitHub as provider",
            "gcloud iam workload-identity-pools providers create-oidc github-provider \\",
            "  --location=global \\",
            "  --workload-identity-pool=github-pool \\",
            "  --display-name=\"GitHub Provider\" \\",
            "  --attribute-mapping=\"google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository\" \\",
            "  --issuer-uri=\"https://token.actions.githubusercontent.com\"",
            "```",
        ])
        
        return "\n".join(lines)
