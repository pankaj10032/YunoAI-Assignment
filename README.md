---
title: AI Orchestrator
emoji: "🤖"
colorFrom: blue
colorTo: green
sdk: gradio
python_version: "3.11"
app_file: app.py
pinned: false
---

# 🚀 GitHub to Hugging Face CI/CD Setup

This repository contains the complete setup for automatic CI/CD deployment from GitHub to Hugging Face Spaces.

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [SETUP_INSTRUCTIONS.md](./SETUP_INSTRUCTIONS.md) | Step-by-step setup guide |
| [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) | Comprehensive deployment guide |
| [DEPLOYMENT_VERIFICATION.md](./DEPLOYMENT_VERIFICATION.md) | Verification checklist |
| [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) | Common issues and solutions |

---

## 🎯 Quick Start

### 1. Create Hugging Face Space
- Visit: https://huggingface.co/spaces
- Create new Space with name: `AI-Orchestrator`

### 2. Get Hugging Face Token
- Go to: https://huggingface.co/settings/tokens
- Create new token with **Write** access
- Copy the token (format: `hf_xxxxxxxxxxxxx`)

### 3. Add Token to GitHub
- Go to your GitHub repository
- Settings → Secrets and variables → Actions
- New repository secret:
  - Name: `HF_TOKEN`
  - Value: [Paste your token]

### 4. Update Workflow Configuration
Edit `.github/workflows/deploy.yml`:
```yaml
env:
  HF_USERNAME: Pankaj10346          # Your Hugging Face username
  HF_SPACE_NAME: AI-Orchestrator    # Your space name
```

### 5. Trigger Deployment
```bash
git push origin main
```

---

## 📋 Prerequisites

- ✅ GitHub account
- ✅ Hugging Face account
- ✅ Git installed
- ✅ AI Orchestrator code in repository

---

## 🔄 How It Works

```mermaid
graph LR
    A[Push to main] --> B[GitHub Actions]
    B --> C[Checkout Code]
    C --> D[Install Dependencies]
    D --> E[Clone HF Space]
    E --> F[Sync Files]
    F --> G[Commit & Push]
    G --> H[Space Builds]
    H --> I[Live!]
```

**Every push to main** → **Automatic deployment** in ~2-5 minutes

---

## 📁 File Structure

```
ai-orchestrator/
├── .github/
│   └── workflows/
│       └── deploy.yml          # ← CI/CD workflow
├── app.py                       # Gradio interface
├── requirements.txt
├── backend/
│   └── app/
│       └── app.py              # FastAPI backend
├── README.md
├── SETUP_INSTRUCTIONS.md       # Setup guide
├── DEPLOYMENT_GUIDE.md         # Deployment guide
├── DEPLOYMENT_VERIFICATION.md  # Verification checklist
└── TROUBLESHOOTING.md          # Troubleshooting guide
```

---

## ✅ Verification

After setup, verify:

1. **GitHub Actions**
   - Go to Actions tab
   - Trigger workflow
   - Check for green checkmarks

2. **Hugging Face Space**
   - Visit: https://huggingface.co/spaces/Pankaj10346/AI-Orchestrator
   - Check Files tab
   - Test App tab

3. **Automatic Deployment**
   - Make a small change
   - Push to main
   - Verify automatic deployment

---

## 🐛 Troubleshooting

Common issues:

- ❌ "HF_TOKEN secret is not set" → Add secret in GitHub
- ❌ "Authentication failed" → Generate new token with Write access
- ❌ "Space not found" → Verify HF_USERNAME and HF_SPACE_NAME
- ❌ "No changes to deploy" → Make a change and push again

See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for detailed solutions.

---

## 📖 Next Steps

1. **Read Setup Instructions**
   - [SETUP_INSTRUCTIONS.md](./SETUP_INSTRUCTIONS.md)

2. **Configure Your Space**
   - Create Hugging Face Space
   - Get access token
   - Add to GitHub secrets

3. **Test Deployment**
   - Trigger first deployment
   - Verify it works
   - Test automatic deployment

4. **Monitor and Maintain**
   - Check logs regularly
   - Update dependencies
   - Keep documentation current

---

## 🎉 Success!

When everything is configured:

- ✅ Every push to main triggers deployment
- ✅ Your app updates automatically on Hugging Face
- ✅ No manual deployment needed
- ✅ Full CI/CD pipeline running

**Your space URL**: https://huggingface.co/spaces/Pankaj10346/AI-Orchestrator

---

## 📞 Need Help?

- **Setup Issues**: See [SETUP_INSTRUCTIONS.md](./SETUP_INSTRUCTIONS.md)
- **Deployment Guide**: See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)
- **Verification**: See [DEPLOYMENT_VERIFICATION.md](./DEPLOYMENT_VERIFICATION.md)
- **Troubleshooting**: See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

---

**Happy Deploying! 🚀**