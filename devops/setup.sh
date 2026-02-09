#!/bin/bash
# Quick setup script for autonomous DevOps agent

set -e

echo "🚀 Setting up Autonomous DevOps Agent..."
echo ""

# 1. Install Python dependencies
echo "📦 Installing dependencies..."
python3 -m pip install --user google-generativeai python-dotenv httpx rich pytest 2>&1 | grep -v "already satisfied" || true

# 2. Check .env file
if [ -f ".env" ]; then
    echo "✅ .env file exists"
    if grep -q "GEMINI_API_KEY=" .env && ! grep -q "your_gemini_api_key" .env; then
        echo "✅ Gemini API key configured"
    else
        echo "⚠️  Gemini API key not set in .env"
    fi
    
    if grep -q "GCP_PROJECT_ID=" .env && ! grep -q "your-gcp-project-id" .env && grep -v "^#" .env | grep -q "GCP_PROJECT_ID=."; then
        echo "✅ GCP Project ID configured"
    else
        echo "⚠️  GCP Project ID not set in .env - you'll need this for deployment"
        echo "    Edit .env and set: GCP_PROJECT_ID=your-project-id"
    fi
else
    echo "❌ .env file not found! Copying from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env and set your credentials"
fi

echo ""
echo "🧪 Running autonomous system tests..."
python3 test_autonomous.py

echo ""
echo "✅ Setup complete!"
echo ""
echo "📚 Next steps:"
echo "  1. Set GCP_PROJECT_ID in .env (if not done)"
echo "  2. Authenticate: gcloud auth application-default login"
echo "  3. Enable GCP APIs (see SETUP_GUIDE.md)"
echo "  4. Deploy: devops-agent devpilot deploy <github-url>"
echo ""
echo "📖 Full guide: SETUP_GUIDE.md"
