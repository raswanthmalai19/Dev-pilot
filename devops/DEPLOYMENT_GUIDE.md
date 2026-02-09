# Real-World Deployment Guide

## 🌍 Making the DevOps Agent Production-Ready

This guide covers everything you need to connect and configure for real-world deployments.

---

## 📋 Prerequisites Checklist

### 1. Required Accounts & Services

#### ✅ Google Cloud Platform (GCP)
**Why:** For deploying to Cloud Run and managing infrastructure

**Setup:**
```bash
# 1. Create GCP account: https://console.cloud.google.com
# 2. Create a new project
# 3. Enable required APIs:
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable compute.googleapis.com

# 4. Create service account
gcloud iam service-accounts create devops-agent \
    --display-name="DevOps Agent Service Account"

# 5. Grant permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:devops-agent@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.admin"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:devops-agent@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:devops-agent@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"

# 6. Download service account key
gcloud iam service-accounts keys create ~/devops-agent-key.json \
    --iam-account=devops-agent@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

**Environment Variables:**
```bash
export GCP_PROJECT_ID="your-project-id"
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/devops-agent-key.json"
```

---

#### ✅ Google Gemini API
**Why:** For AI-powered code generation and error recovery

**Setup:**
```bash
# 1. Go to: https://makersuite.google.com/app/apikey
# 2. Create API key
# 3. Set environment variable
export GEMINI_API_KEY="AIzaSy..."
```

**Test:**
```bash
python3 -c "
import google.generativeai as genai
genai.configure(api_key='YOUR_KEY')
model = genai.GenerativeModel('gemini-pro')
print('✅ Gemini API working!')
"
```

---

#### ✅ GitHub Account & Personal Access Token
**Why:** For auto-pushing CI/CD workflows

**Setup:**
```bash
# 1. Go to: https://github.com/settings/tokens
# 2. Generate new token (classic)
# 3. Select scopes:
#    - repo (Full control of private repositories)
#    - workflow (Update GitHub Action workflows)
# 4. Copy token (starts with ghp_)
```

**Environment Variable:**
```bash
export GITHUB_TOKEN="ghp_..."
```

---

#### ✅ Docker Hub (or GCR)
**Why:** For storing container images

**Option A: Docker Hub**
```bash
# 1. Create account: https://hub.docker.com
# 2. Login locally
docker login

# Set environment variables
export DOCKER_REGISTRY="docker.io"
export DOCKER_USERNAME="your-username"
```

**Option B: Google Container Registry (Recommended)**
```bash
# Already configured with GCP service account
export DOCKER_REGISTRY="gcr.io/YOUR_PROJECT_ID"
```

---

### 2. Local Tools Installation

#### Install Docker
```bash
# macOS
brew install --cask docker

# Verify
docker --version
docker ps
```

#### Install Terraform
```bash
# macOS
brew tap hashicorp/tap
brew install hashicorp/tap/terraform

# Verify
terraform --version
```

#### Install gcloud CLI
```bash
# macOS
brew install --cask google-cloud-sdk

# Initialize
gcloud init
gcloud auth application-default login
```

---

## 🔧 Configuration Files

### 1. Create `.env` file
```bash
cd "/Users/raswanthmalaisamy/Desktop/gemini 3"
cat > .env << 'EOF'
# Required
GEMINI_API_KEY=AIzaSy...your_key_here
SECRETS_PASSPHRASE=your_strong_random_passphrase_here

# GCP Configuration
GCP_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/Users/raswanthmalaisamy/devops-agent-key.json
GCP_REGION=us-central1

# GitHub (Optional - for auto-push)
GITHUB_TOKEN=ghp_...your_token_here

# Docker Registry
DOCKER_REGISTRY=gcr.io/your-project-id
# OR for Docker Hub:
# DOCKER_REGISTRY=docker.io
# DOCKER_USERNAME=your-username

# Security
VALIDATE_COMMANDS=true
ALLOWED_COMMANDS=npm,docker,terraform,gcloud,python,pip,node

# Logging
LOG_LEVEL=INFO
EOF

# Secure the file
chmod 600 .env
```

### 2. Load environment variables
```bash
# Add to your ~/.zshrc or ~/.bashrc
echo 'export $(cat "/Users/raswanthmalaisamy/Desktop/gemini 3/.env" | xargs)' >> ~/.zshrc
source ~/.zshrc
```

---

## 🚀 Installation & Setup

### 1. Install Python Dependencies
```bash
cd "/Users/raswanthmalaisamy/Desktop/gemini 3"

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install the CLI
pip install -e .
```

### 2. Verify Installation
```bash
# Check prerequisites
devops-agent check

# Expected output:
# ✅ Gemini API Key - Set
# ✅ Docker - Found
# ✅ Terraform - Found
# ✅ gcloud CLI - Found
# ✅ GCP Project - Set
```

---

## 🧪 Test with Sample Projects

### Test 1: Flask Application
```bash
cd samples/flask-app

# Run tests
pytest

# Deploy locally first
python app.py

# Deploy with DevOps Agent
devops-agent deploy . --build --test
```

### Test 2: Node.js Application
```bash
cd samples/node-express

# Install dependencies
npm install

# Run tests
npm test

# Deploy with DevOps Agent
devops-agent deploy . --build --test
```

---

## 🌐 Real-World Deployment

### Scenario 1: Deploy Your Own Application

```bash
# 1. Navigate to your project
cd /path/to/your/app

# 2. Analyze the project
devops-agent analyze .

# 3. Deploy with full pipeline
devops-agent deploy . \
    --build \
    --test \
    --push

# 4. The agent will:
#    ✅ Detect language/framework
#    ✅ Generate Dockerfile
#    ✅ Build Docker image
#    ✅ Run tests
#    ✅ Push to registry
#    ✅ Generate Terraform configs
#    ✅ Generate GitHub Actions workflow
```

### Scenario 2: Auto-Push to GitHub

```bash
# Deploy and push workflow to GitHub
devops-agent deploy . \
    --build \
    --test \
    --push-to-github \
    --github-owner your-username \
    --github-repo your-repo \
    --create-pr
```

### Scenario 3: Full Auto-Deploy to Cloud Run

```bash
# Complete automated deployment
devops-agent deploy . \
    --build \
    --test \
    --push \
    --auto-apply-terraform \
    --verify-deployment
```

---

## 🔐 Security Configuration

### 1. Set Secrets Passphrase
```bash
# Generate strong passphrase
openssl rand -base64 32

# Set environment variable
export SECRETS_PASSPHRASE="generated_passphrase_here"
```

### 2. Store Secrets Securely
```python
from devops_agent.core.secrets_manager import set_secret

# Store GitHub token
set_secret("github_token", "ghp_xxxxx")

# Store Docker credentials
set_secret("docker_password", "your_password")

# Store API keys
set_secret("api_key", "your_api_key")
```

### 3. Verify Security
```bash
# Run security tests
pytest tests/unit/test_security.py -v

# Check for vulnerabilities
pip install bandit safety
bandit -r devops_agent/
safety check
```

---

## 📊 Monitoring & Debugging

### Enable Verbose Logging
```bash
devops-agent deploy ./app --verbose
```

### Check Deployment Logs
```bash
# GCP Cloud Run logs
gcloud run services logs read your-service-name \
    --project=YOUR_PROJECT_ID \
    --region=us-central1

# Docker build logs
docker logs <container_id>
```

### Health Check
```bash
# After deployment, verify service
curl https://your-service-url.run.app/health
```

---

## 🎯 Common Issues & Solutions

### Issue 1: Docker Build Fails
```bash
# Solution: Check Docker daemon
docker ps

# Restart Docker Desktop if needed
# Then retry
devops-agent deploy ./app --build
```

### Issue 2: Terraform Apply Fails
```bash
# Solution: Check GCP credentials
gcloud auth application-default login

# Verify project
gcloud config get-value project

# Manually apply
cd terraform/
terraform init
terraform plan
terraform apply
```

### Issue 3: GitHub Push Fails
```bash
# Solution: Verify token scopes
# Token needs: repo, workflow

# Test token
curl -H "Authorization: token $GITHUB_TOKEN" \
    https://api.github.com/user
```

### Issue 4: Gemini API Errors
```bash
# Solution: Check API key and quota
# Go to: https://makersuite.google.com/app/apikey

# Test API
python3 -c "
import google.generativeai as genai
genai.configure(api_key='$GEMINI_API_KEY')
print('✅ API working')
"
```

---

## 📝 Production Checklist

Before deploying to production:

- [ ] All environment variables set
- [ ] GCP service account created with correct permissions
- [ ] Gemini API key configured and tested
- [ ] GitHub token created with correct scopes
- [ ] Docker registry configured and accessible
- [ ] Terraform installed and working
- [ ] gcloud CLI authenticated
- [ ] Security tests passing
- [ ] Sample projects deploy successfully
- [ ] `.env` file secured (chmod 600)
- [ ] Secrets encrypted with strong passphrase
- [ ] Monitoring/logging configured

---

## 🚀 Quick Start Commands

```bash
# 1. Install
cd "/Users/raswanthmalaisamy/Desktop/gemini 3"
pip install -r requirements.txt
pip install -e .

# 2. Configure
export GEMINI_API_KEY="your_key"
export GCP_PROJECT_ID="your_project"
export GITHUB_TOKEN="your_token"
export SECRETS_PASSPHRASE="strong_passphrase"

# 3. Test
devops-agent check

# 4. Deploy
devops-agent deploy ./your-app --build --test
```

---

## 📞 Need Help?

1. Check `devops-agent check` output
2. Review logs with `--verbose` flag
3. Test with sample projects first
4. Verify all environment variables are set
5. Check GCP/GitHub/Docker credentials

**You're now ready for real-world deployments! 🎉**
