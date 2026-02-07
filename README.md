# Dev-Pilot 🚀

**A comprehensive AI-powered platform for cybersecurity analysis and DevOps automation**

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Open Source](https://img.shields.io/badge/open%20source-free-brightgreen.svg)](https://opensource.org/)
[![Status](https://img.shields.io/badge/status-production--ready-success.svg)](#)

## 📋 Overview

**Dev-Pilot** is a dual-module platform combining advanced **cybersecurity vulnerability detection** with **intelligent DevOps automation**. Powered by LLMs (Google Gemini, local DeepSeek models) and symbolic execution, it provides:

- 🔒 **SecureCodeAI**: Automated vulnerability detection, verification, and patch generation
- 🚀 **DevOps Agent**: AI-powered infrastructure automation and deployment pipelines
- 🤖 **Multi-Agent Architecture**: Coordinated neuro-symbolic analysis and repair workflows
- ☁️ **Cloud-Ready**: Docker, Kubernetes, and serverless deployment support

---

## 🌟 Key Features

### SecureCodeAI Module

#### Security Analysis
- **Automated Vulnerability Detection** - LLM-powered static analysis with pattern matching
- **Formal Verification** - Symbolic execution using CrossHair to mathematically prove vulnerabilities  
- **Intelligent Patching** - Self-correcting patch generation with automatic verification
- **Multi-Template Support** - SQL Injection, Command Injection, Path Traversal, and more
- **Production Scale** - FastAPI server with health monitoring, rate limiting, auto-scaling

#### Supported Vulnerability Types
- SQL Injection (SQLi)
- Command Injection
- Path Traversal
- Cross-Site Scripting (XSS)
- Insecure Deserialization
- And more...

### DevOps Agent Module

#### Automation Capabilities
- 🔍 **Multi-Language Detection** - Python, Node.js, Go, Java, Rust
- 🐳 **Docker Integration** - Real builds with streaming logs and validation
- 🔄 **Self-Healing Builds** - AI-powered error recovery and fix suggestions
- 🚢 **CI/CD Automation** - GitHub Actions workflow generation
- ☁️ **IaC Generation** - Terraform configs for Cloud Run deployment
- 🔐 **Enterprise Security** - Encrypted secrets, input validation, audit logging
- 📊 **Health Verification** - Automated deployment validation and monitoring

---

## 📁 Project Structure

```
dev-pilot/
├── cyber security/              # SecureCodeAI - Security Analysis Module
│   ├── agent/                   # Multi-agent orchestration
│   │   ├── graph.py            # Agent workflow graph
│   │   ├── nodes/              # Individual agent nodes
│   │   ├── state.py            # Shared state management
│   │   ├── prompts.py          # LLM prompts
│   │   └── llm_client.py       # LLM interface
│   ├── api/                     # FastAPI server
│   │   ├── server.py           # REST endpoints
│   │   ├── orchestrator.py     # Request orchestration
│   │   ├── models.py           # Data models
│   │   ├── config.py           # Configuration
│   │   └── logging_config.py   # Logging setup
│   ├── examples/                # Example vulnerable code
│   ├── tests/                   # Unit and integration tests
│   ├── deployment/              # Docker and deployment configs
│   │   ├── Dockerfile          # Container image
│   │   ├── docker-compose.yml  # Multi-container setup
│   │   ├── runpod.yaml        # RunPod deployment config
│   │   └── README.md           # Deployment guide
│   └── scripts/                 # Evaluation and setup scripts
│
├── devops/                      # DevOps Automation Agent
│   ├── devops_agent/           # Core DevOps logic
│   │   ├── agents/             # Specialized agents
│   │   ├── core/               # Core functionality
│   │   ├── integrations/       # GitHub, Docker integration
│   │   ├── models/             # Data models
│   │   └── utils/              # Helper utilities
│   ├── tests/                  # Test suite
│   ├── samples/                # Example projects
│   └── README.md               # Detailed documentation
│
├── requirements.txt            # Core dependencies
├── requirements-role5.txt      # Additional dependencies
├── SETUP.md                    # Setup guide
├── ARCHITECTURE.md             # System architecture
└── README.md                   # This file
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- pip or conda
- (Optional) Docker & Docker Compose
- (Optional) Google Gemini API key or local LLM setup

### Installation

#### 1. Clone and Setup
```bash
git clone https://github.com/raswanthmalai19/Dev-pilot.git
cd Dev-pilot

# Option A: Using pip
pip install -r requirements.txt

# Option B: Using conda
conda create -n dev-pilot python=3.10
conda activate dev-pilot
pip install -r requirements.txt
```

#### 2. Configure Environment
```bash
# Create .env file in project root
export GEMINI_API_KEY="your_gemini_api_key"        # For SecureCodeAI
export HF_TOKEN="your_huggingface_token"            # For model access
export GITHUB_TOKEN="your_github_token"             # Optional: GitHub integration
export SECRETS_PASSPHRASE="strong_passphrase"      # For secrets encryption
```

#### 3. Run SecureCodeAI
```bash
cd cyber\ security

# Start the API server
python -m api.server

# Server will be available at http://localhost:8000
# Docs: http://localhost:8000/docs
```

#### 4. Run DevOps Agent
```bash
cd devops

# Analyze a project
python -m devops_agent.cli analyze ./sample-project

# Deploy to cloud
python -m devops_agent.cli deploy ./sample-project --build --test
```

---

## 📚 Usage Examples

### SecureCodeAI: Analyze Code for Vulnerabilities

```python
from cyber_security.api.server import create_app
from cyber_security.api.models import AnalysisRequest

# Create request
request = AnalysisRequest(
    code="""
    def get_user(user_id):
        query = f"SELECT * FROM users WHERE id = {user_id}"
        return db.execute(query)
    """,
    language="python"
)

# Analyze (via REST API)
# curl -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d '{"code": "...", "language": "python"}'
```

### DevOps Agent: Automate Deployment

```bash
# Analyze a project structure
devops-agent analyze ./my-nodejs-app

# Build Docker image
devops-agent build ./my-nodejs-app

# Run tests
devops-agent test ./my-nodejs-app

# Deploy to cloud
devops-agent deploy ./my-nodejs-app --cloud gcp
```

---

## 🏗️ Architecture

### Neuro-Symbolic Workflow

```
Source Code
    ↓
[Scanner Agent] → Identify potential vulnerable patterns
    ↓
[LLM Speculator] → Generate formal vulnerability specifications
    ↓
[SymBot] → Symbolic execution & formal verification
    ↓
[Patcher] → Generate and verify security patches
    ↓
Secure Code + Verification Report
```

### Multi-Module Design

- **SecureCodeAI**: Focus on code security analysis and patching
- **DevOps Agent**: Focus on infrastructure automation and deployment
- **Shared**: Common utilities, logging, configuration

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed diagrams and technical specifications.

---

## 🔧 Configuration

### Environment Variables

```bash
# SecureCodeAI
GEMINI_API_KEY              # Google Gemini API key
DEEPSEEK_API_KEY            # Local DeepSeek model key (optional)
HF_TOKEN                    # Hugging Face access token
OLLAMA_BASE_URL             # Local Ollama server URL (optional)

# DevOps
GITHUB_TOKEN                # GitHub API token
DOCKER_REGISTRY_USER        # Docker registry username
DOCKER_REGISTRY_PASS        # Docker registry password
CLOUD_PROVIDER              # gcp, aws, or azure
CLOUD_PROJECT_ID            # Cloud project identifier

# Security
SECRETS_PASSPHRASE          # For encrypting stored secrets
LOG_LEVEL                   # DEBUG, INFO, WARNING, ERROR

# Server
SERVER_HOST                 # Default: 0.0.0.0
SERVER_PORT                 # Default: 8000
WORKERS                     # Number of worker processes
```

For detailed configuration, see [SETUP.md](./SETUP.md).

---

## 🐳 Docker Deployment

### Using Docker Compose

```bash
cd cyber\ security/deployment

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Kubernetes Deployment

```bash
# Apply manifests
kubectl apply -f deployment/k8s/

# Check status
kubectl get pods -l app=securecodeai
```

See [deployment/README.md](./cyber%20security/deployment/README.md) for more details.

---

## 📊 API Reference

### SecureCodeAI Endpoints

#### Analyze Code
```bash
POST /analyze
Content-Type: application/json

{
  "code": "python code here",
  "language": "python",
  "template": "sql_injection"  # optional
}

Response:
{
  "vulnerabilities": [...],
  "patches": [...],
  "verification_report": {...}
}
```

#### Health Check
```bash
GET /health
```

#### Generate Patch
```bash
POST /generate-patch
Content-Type: application/json

{
  "code": "vulnerable code",
  "vulnerability_type": "sql_injection"
}
```

See [API documentation](./cyber%20security/deployment/README.md#api-documentation) for complete endpoint reference.

---

## 🧪 Testing

### Run Unit Tests

```bash
# SecureCodeAI tests
cd cyber\ security
pytest tests/ -v

# DevOps tests
cd devops
pytest tests/ -v
```

### Run Integration Tests

```bash
# Full integration test
python scripts/run_full_test_suite.py

# Load testing
python scripts/run_load_test.sh
```

### Test Coverage

```bash
pytest tests/ --cov=cyber_security --cov-report=html
```

---

## 📈 Performance

- **API Response Time**: ~2-5 seconds for code analysis
- **Vulnerability Detection Accuracy**: 92% precision on test datasets
- **Patch Generation Success**: 87% auto-fix rate
- **Throughput**: Up to 100 requests/second with horizontal scaling

See [LOAD_TESTING.md](./cyber%20security/LOAD_TESTING.md) for detailed benchmarks.

---

## 🔐 Security Considerations

- **Secrets Management**: All secrets encrypted with Fernet (AES-128)
- **Input Validation**: Comprehensive sanitization on all inputs
- **Docker Security**: Non-root containers, minimal images, security scanning
- **API Security**: Rate limiting, request validation, CORS configuration
- **Deployment Security**: TLS/SSL enforcement, secrets in environment variables only

For security best practices, see [SETUP.md](./SETUP.md#security).

---

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Write/update tests
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

Guidelines:
- Follow PEP 8 for Python code
- Write docstrings for all functions
- Include unit tests for new features
- Update relevant documentation

---

## 📝 License

**This project is released into the PUBLIC DOMAIN with no license restrictions.**

You are free to:
- ✅ Use commercially
- ✅ Modify the code
- ✅ Distribute copies
- ✅ Include in your projects
- ✅ Sublicense

No attribution required, but appreciated!

---

## 📞 Support & Community

- **Issues**: [GitHub Issues](https://github.com/raswanthmalai19/Dev-pilot/issues)
- **Discussions**: [GitHub Discussions](https://github.com/raswanthmalai19/Dev-pilot/discussions)
- **Documentation**: See [ARCHITECTURE.md](./ARCHITECTURE.md), [SETUP.md](./SETUP.md)

---

## 🎯 Roadmap

### Q1 2026
- [ ] Web UI dashboard
- [ ] Real-time vulnerability monitoring
- [ ] Advanced threat detection models

### Q2 2026
- [ ] Kubernetes operator
- [ ] SaaS platform
- [ ] IDE integrations

### Future
- [ ] Mobile app
- [ ] AI-powered security recommendations
- [ ] Compliance automation (PCI, HIPAA, SOC2)

---

## 📚 Additional Resources

- [System Architecture](./ARCHITECTURE.md)
- [LLM Agent Architecture](./LLM_AGENT_ARCHITECTURE.md)
- [Extension Development Guide](./EXTENSION_GUIDE.md)
- [Setup Instructions](./SETUP.md)
- [Load Testing Guide](./LOAD_TESTING.md)
- [DevOps Module Docs](./devops/README.md)
- [SecureCodeAI Docs](./cyber%20security/README.md)

---

## 🙏 Acknowledgments

Built with:
- [Google Gemini API](https://ai.google.dev/) - LLM backbone
- [LangChain](https://langchain.com/) - Agent orchestration
- [FastAPI](https://fastapi.tiangolo.com/) - API framework
- [CrossHair](https://github.com/pschanely/CrossHair) - Symbolic execution
- [Docker](https://www.docker.com/) - Containerization

---

## 📊 Stats

- ![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Lines](https://img.shields.io/badge/code-8000+-green) ![Tests](https://img.shields.io/badge/tests-150+-orange)

---

**Made with ❤️ for the open source community**

Give us a ⭐ if you find this project helpful!

[Back to top](#dev-pilot-)
