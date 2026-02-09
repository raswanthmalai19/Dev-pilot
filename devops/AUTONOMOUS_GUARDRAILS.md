# Autonomous DevOps Agent - Guardrails & Safety Rules

## 🛡️ Purpose

This document defines the safety guardrails and rules that govern the autonomous operation of the DevOps Agent system.

---

## 🚫 Hard Stops (Deployment Will Be Rejected)

The following conditions will **immediately halt** deployment:

### 1. Security Checks
- ❌ Security status is not "PASS"
- ❌ Secrets detected in repository code
- ❌ Dockerfile contains hardcoded credentials
- ❌ Container runs as root without justification
- ❌ Known vulnerabilities in dependencies (Critical/High)

### 2. QA Checks
- ❌ QA status is not "PASS"
- ❌ Test coverage below 50% (if tests exist)
- ❌ Build fails on target platform
- ❌ Critical lint errors present

### 3. Branch Restrictions
- ❌ Branch is not in approved list (strict mode)
- ❌ Deploying from feature branch without override
- ❌ No commit history (empty repository)

### 4. Infrastructure Limits
- ❌ Requested resources exceed project quotas
- ❌ No GCP project configured
- ❌ GCP APIs not enabled
- ❌ Invalid service name (contains special chars)

---

## ⚠️ Warnings (Deployment Continues with Logging)

The following will trigger warnings but allow deployment:

### 1. Code Quality
- ⚠️ No tests found
- ⚠️ Missing README.md
- ⚠️ No .gitignore file
- ⚠️ Large container size (>1GB)

### 2. Configuration
- ⚠️ No health check endpoint
- ⚠️ Missing environment variable documentation
- ⚠️ No Dockerfile optimization (multi-stage build)
- ⚠️ Port not explicitly defined

### 3. Dependencies
- ⚠️ Outdated dependencies (not critical vulnerabilities)
- ⚠️ Many dependencies (>100)
- ⚠️ Unused dependencies detected

---

## 🤖 Autonomous Decision Making

### Project Type Detection

The agent will analyze projects in this order:

```
1. Check for package.json → Node.js
2. Check for requirements.txt/pyproject.toml → Python
3. Check for go.mod → Go
4. Check for pom.xml/build.gradle → Java
5. Check for Cargo.toml → Rust
6. Ask Gemini AI for help if uncertain
```

### Framework Detection

For ambiguous cases, the agent will:
1. Scan entry point files for framework imports
2. Check dependency lists for framework packages
3. Use Gemini AI to analyze code structure
4. Default to generic configuration if uncertain

### Port Selection

Priority order:
1. PORT environment variable in code
2. `listen()` call in entry point
3. Framework defaults (Flask:5000, Express:3000, etc.)
4. Gemini AI recommendation
5. Default: 8080

---

## 🔧 Auto-Fixing Strategy

### When Build Fails

```
Attempt 1: Build with detected configuration
    ↓ (if fails)
Attempt 2: Ask Gemini AI to analyze error and suggest fix
    ↓ (if fails)
Attempt 3: Try alternative base image
    ↓ (if fails)
ABORT and report to user
```

### When Deployment Fails

```
Attempt 1: Deploy with detected settings
    ↓ (if fails)
Attempt 2: Retry with increased memory/CPU
    ↓ (if fails)
ABORT and report to user
```

### When Health Check Fails

```
Attempt 1: Check /health endpoint
    ↓ (if fails)
Attempt 2: Check / endpoint
    ↓ (if fails)
AUTO-ROLLBACK to previous version
```

---

## 🎯 Uncertainty Handling

### Unknown Project Type

```yaml
Strategy: Multi-phase analysis
  1. File structure scan (package files, extensions)
  2. Content analysis (imports, syntax patterns)
  3. Gemini AI deep analysis with code samples
  4. If still uncertain: Reject with detailed report
```

### Missing Critical Information

| Missing Item | Resolution |
|-------------|------------|
| Start command | Use framework defaults → Ask Gemini → Manual |
| Port | Check code → Framework default → 8080 |
| Entry point | Scan for main.* → Ask Gemini → Manual |
| Dependencies | Auto-detect from imports → Manual |

### Conflicting Signals

Example: `package.json` exists but no Node.js code
```
Resolution:
  1. Count files by language
  2. Check which has entry point
  3. Ask Gemini AI to analyze intent
  4. Pick dominant language
```

---

## 📊 Validation Checkpoints

### Before Clone
- ✅ GitHub URL is valid
- ✅ Repository is accessible
- ✅ Branch exists
- ✅ Security status = PASS
- ✅ QA status = PASS

### Before Build
- ✅ Project type detected
- ✅ Dockerfile generated/exists
- ✅ No secrets in code
- ✅ Dependencies installable

### Before Deploy
- ✅ Image built successfully
- ✅ Image size < 2GB
- ✅ GCP project configured
- ✅ Service name valid
- ✅ Region available

### After Deploy
- ✅ Service URL accessible
- ✅ Health endpoint responds
- ✅ Status code 200/201
- ✅ Response time < 10s

---

## 🚨 Rollback Triggers

Auto-rollback will occur if:

1. **Health Check Fails** (3 consecutive attempts)
2. **Service Crashes** within 2 minutes
3. **Error Rate > 50%** within 5 minutes
4. **Response Time > 30s** consistently
5. **Manual Trigger** via CLI

---

## 🔐 Security Constraints

### Secrets Management
- ❌ NEVER log secrets in plain text
- ❌ NEVER commit secrets to repository
- ✅ All secrets must use Secret Manager
- ✅ Auto-detect and mask secrets in logs

### Container Security
- ❌ NEVER use `:latest` tag in production
- ❌ NEVER run as root unless justified
- ✅ Always scan for vulnerabilities
- ✅ Use minimal base images

### Network Security
- ✅ All Cloud Run services use HTTPS
- ✅ Internal services not publicly exposed
- ✅ API keys rotate every 90 days (recommendation)

---

## 📈 Resource Limits

### Default Limits
```yaml
CPU: 1 core
Memory: 512Mi
Timeout: 300s
Concurrency: 80
Min Instances: 0
Max Instances: 10
```

### Maximum Allowed
```yaml
CPU: 4 cores
Memory: 4Gi
Timeout: 900s
Max Instances: 100
```

### Cost Protection
- ⚠️ Warning if estimated cost > $10/day
- ❌ Reject if estimated cost > $100/day

---

## 🔄 Retry Logic

| Operation | Max Retries | Backoff |
|-----------|-------------|---------|
| Build | 2 | None |
| Deploy | 2 | 5s |
| Health Check | 5 | Exponential (5s, 10s, 20s...) |
| Rollback | 1 | None |

---

## 📝 Logging Requirements

Every deployment must log:
1. ✅ Deployment ID (unique identifier)
2. ✅ Timestamp (ISO 8601)
3. ✅ Repository URL + commit hash
4. ✅ User/service account
5. ✅ All decisions made
6. ✅ All errors encountered
7. ✅ Final status (success/failure/rollback)

---

## 🎓 Learning from Failures

When deployment fails:
1. Log detailed error analysis
2. Store for pattern recognition
3. Update auto-fix database
4. Generate recommendations

---

## ⚖️ Override Mechanism

For emergency deployments, authorized users can:
```bash
# Skip security check (DANGEROUS)
--skip-security-check

# Skip branch validation
--allow-any-branch

# Skip health check
--skip-health-check
```

⚠️ **All overrides are logged and audited**

---

## 🎯 Success Criteria

A deployment is considered successful when:
- ✅ All checkpoints passed
- ✅ Service is healthy
- ✅ No rollback triggered
- ✅ Logs show no errors
- ✅ Service URL responds correctly

---

## 📞 Human Escalation

Auto-escalate to human when:
1. Build fails 3+ times
2. Unknown project type after analysis
3. Security vulnerabilities found
4. Cost exceeds limits
5. Rollback fails

---

**Last Updated:** 2026-02-07  
**Version:** 1.0
