# DevOps Automation Agent 🚀

**Fully autonomous, production-ready DevOps pipeline powered by Gemini AI**

Transform any codebase into a deployed application with a single command. The agent analyzes your project, generates optimized Dockerfiles, creates CI/CD pipelines, provisions infrastructure, and deploys to the cloud—all automatically.

## ✨ Features

### Core Capabilities
- 🔍 **Multi-Language Detection** - Python, Node.js, Go, Java, Rust
- 🐳 **Docker SDK Integration** - Real builds with streaming logs
- 🔄 **Self-Healing Builds** - Gemini-powered error recovery
- 🚢 **GitHub Actions CI/CD** - Auto-generated workflows
- ☁️ **Terraform IaC** - Cloud Run deployment automation
- 🔐 **Enterprise Security** - Encrypted secrets, input validation
- 📊 **Health Verification** - Automated deployment checks

### Security Features
- ✅ Path traversal prevention
- ✅ Command injection protection
- ✅ Secrets encryption (Fernet/AES-128)
- ✅ Automatic secrets masking in logs
- ✅ Docker image validation
- ✅ Template injection prevention

## 🚀 Quick Start

### Installation

```bash
# Clone or navigate to project
cd "/Users/raswanthmalaisamy/Desktop/gemini 3"

# Install dependencies
pip install -r requirements.txt

# Install CLI
pip install -e .
```

### Configuration

```bash
# Required
export GEMINI_API_KEY="your_gemini_api_key"
export SECRETS_PASSPHRASE="strong_random_passphrase"

# Optional: GitHub integration
export GITHUB_TOKEN="ghp_xxxxx"

# Optional: GCP deployment
export GCP_PROJECT_ID="your-project-id"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

### Usage

```bash
# Analyze a project
devops-agent analyze ./my-app

# Full deployment pipeline
devops-agent deploy ./my-app --build --test

# Check prerequisites
devops-agent check
```

## 🤖 Dev Pilot - Autonomous GitHub-to-Cloud Run

**NEW:** Dev Pilot is an autonomous deployment system that takes code from GitHub through Security and QA stages to production on GCP Cloud Run.

### Dev Pilot Commands

```bash
# Deploy from GitHub (requires Security=PASS, QA=PASS)
devops-agent devpilot deploy https://github.com/user/repo

# With custom options
devops-agent devpilot deploy https://github.com/user/repo \
  --branch devpilot-tested \
  --service-name my-service \
  --region us-central1 \
  --memory 1Gi

# Check service status
devops-agent devpilot status my-service

# Rollback to previous version
devops-agent devpilot rollback my-service

# Validate preconditions only
devops-agent devpilot validate --security PASS --qa PASS
```

### Dev Pilot Pipeline

```
GitHub Repo → Security Check → QA Check → Clone → Analyze → 
Generate Dockerfile → Build → Deploy → Health Check → 🚀 Live!
                                              ↓ (if unhealthy)
                                        Auto-Rollback
```


## 📋 What It Does

1. **Analyzes** your project (language, framework, dependencies)
2. **Generates** optimized multi-stage Dockerfile
3. **Creates** GitHub Actions CI/CD pipeline
4. **Provisions** Terraform infrastructure (Cloud Run)
5. **Builds** Docker image with streaming logs
6. **Deploys** to cloud with health verification
7. **Auto-fixes** errors using Gemini AI

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│         DeploymentOrchestrator                  │
│         (Master Coordinator)                    │
└─────────────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
┌──────────────┐ ┌──────────┐ ┌──────────────┐
│ProjectAnalyzer│ │BuildAgent│ │ContainerAgent│
│              │ │          │ │              │
│ - Language   │ │ - Build  │ │ - Dockerfile │
│ - Framework  │ │ - Test   │ │ - Docker SDK │
│ - Dependencies│ │ - Auto-fix│ │ - Registry  │
└──────────────┘ └──────────┘ └──────────────┘
        │             │             │
        └─────────────┼─────────────┘
                      ▼
        ┌─────────────┴─────────────┐
        ▼                           ▼
┌──────────────┐           ┌──────────────┐
│  CICDAgent   │           │  InfraAgent  │
│              │           │              │
│ - GitHub     │           │ - Terraform  │
│ - Workflows  │           │ - Cloud Run  │
│ - Auto-push  │           │ - Auto-apply │
└──────────────┘           └──────────────┘
```

## 🔒 Security

This system implements enterprise-grade security:

- **Input Validation** - All user inputs sanitized
- **Secrets Encryption** - Fernet (AES-128) encryption at rest
- **Command Injection Prevention** - Dangerous characters blocked
- **Path Traversal Protection** - Restricted file access
- **Secrets Masking** - Automatic redaction in logs

See [SECURITY.md](file:///Users/raswanthmalaisamy/.gemini/antigravity/brain/585835a4-9fce-41cc-b3c9-f30d3d4c9047/SECURITY.md) for detailed security practices.

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Security tests
pytest tests/unit/test_security.py -v

# Test sample projects
cd samples/flask-app && pytest
cd samples/node-express && npm test
```

## 📁 Project Structure

```
devops_agent/
├── agents/              # Specialized agents
│   ├── project_analyzer.py
│   ├── build_agent.py
│   ├── container_agent.py
│   ├── cicd_agent.py
│   ├── infra_agent.py
│   └── orchestrator.py
├── core/                # Core utilities
│   ├── gemini_client.py
│   ├── executor.py      # Secure command execution
│   ├── docker_client.py
│   ├── terraform_client.py
│   ├── health_checker.py
│   ├── error_recovery.py
│   ├── security.py      # Input validation
│   └── secrets_manager.py
├── integrations/        # External integrations
│   ├── github_client.py
│   └── security_hook.py
├── models/              # Data models
└── utils/               # Helper utilities

samples/                 # Test projects
├── flask-app/
└── node-express/

tests/                   # Test suite
├── unit/
└── integration/
```

## 🎯 Use Cases

### 1. Rapid Prototyping
```bash
# Analyze and deploy in minutes
devops-agent deploy ./prototype --build
```

### 2. CI/CD Setup
```bash
# Generate and push GitHub Actions workflow
devops-agent deploy ./app --push-to-github
```

### 3. Infrastructure as Code
```bash
# Generate Terraform configs
devops-agent analyze ./app
# Terraform files created in ./terraform/
```

### 4. Multi-Language Projects
```bash
# Automatically detects Python, Node.js, Go, Java, Rust
devops-agent analyze ./polyglot-app
```

## 🔧 Advanced Configuration

### Custom Build Commands
```python
from devops_agent.agents.build_agent import BuildAgent, BuildConfig

config = BuildConfig(
    install_command="npm ci",
    build_command="npm run build:prod",
    test_command="npm run test:coverage"
)

agent = BuildAgent()
result = await agent.run(project_info, config, auto_fix=True)
```

### Auto-Apply Terraform
```python
from devops_agent.agents.infra_agent import InfraAgent

agent = InfraAgent()
result = await agent.run(
    project_info,
    auto_apply=True,
    verify_deployment=True
)
```

### GitHub Workflow Push
```python
from devops_agent.agents.cicd_agent import CICDAgent

agent = CICDAgent(github_token="ghp_xxxxx")
result = await agent.run(
    project_info,
    push_to_github=True,
    github_owner="username",
    github_repo="repo",
    create_pr=True
)
```

## 📊 Sample Projects

Two production-ready sample applications included:

### Flask REST API
```bash
cd samples/flask-app
pip install -r requirements.txt
pytest  # Run tests
python app.py  # Start server
```

### Node.js/Express API
```bash
cd samples/node-express
npm install
npm test  # Run tests
npm start  # Start server
```

## 🤝 Contributing

This is a production-ready system with:
- ✅ Comprehensive security
- ✅ Full test coverage
- ✅ Complete documentation
- ✅ Sample projects

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- **Gemini AI** - Intelligent code generation and error recovery
- **Docker SDK** - Container orchestration
- **Terraform** - Infrastructure as code
- **GitHub Actions** - CI/CD automation

## 📚 Documentation

- [Security Best Practices](file:///Users/raswanthmalaisamy/.gemini/antigravity/brain/585835a4-9fce-41cc-b3c9-f30d3d4c9047/SECURITY.md)
- [Walkthrough](file:///Users/raswanthmalaisamy/.gemini/antigravity/brain/585835a4-9fce-41cc-b3c9-f30d3d4c9047/walkthrough.md)
- [Completion Plan](file:///Users/raswanthmalaisamy/.gemini/antigravity/brain/585835a4-9fce-41cc-b3c9-f30d3d4c9047/completion_plan.md)

## 🚨 Support

For issues or questions:
1. Check the [Security Guide](file:///Users/raswanthmalaisamy/.gemini/antigravity/brain/585835a4-9fce-41cc-b3c9-f30d3d4c9047/SECURITY.md)
2. Review sample projects in `samples/`
3. Run `devops-agent check` to verify setup

---

**Built with ❤️ using Gemini AI**
