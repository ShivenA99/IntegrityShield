# IntegrityShield - Render.com Deployment Guide

Quick and free deployment to Render.com - no credit card required for free tier!

## Prerequisites

- GitHub account
- OpenAI API key (at minimum)
- 10 minutes

## Step 1: Push Code to GitHub

Make sure your latest code is pushed to GitHub:

```bash
git add render.yaml RENDER_DEPLOY.md
git commit -m "Add Render deployment configuration"
git push origin eacl-demo-deployment
```

## Step 2: Create Render Account

1. Go to: https://render.com
2. Click **"Get Started"**
3. Sign up with your GitHub account
4. Authorize Render to access your repositories

## Step 3: Create New Web Service

1. From Render Dashboard, click **"New +"** → **"Web Service"**
2. Connect your GitHub repository:
   - Search for: `fairtestai_-llm-assessment-vulnerability-simulator-main`
   - Click **"Connect"**
3. Configure the service:
   - **Name:** `integrityshield-backend`
   - **Region:** Choose closest to you (e.g., Oregon USA)
   - **Branch:** `eacl-demo-deployment`
   - **Root Directory:** Leave empty (repo root)
   - **Runtime:** **Python 3**
   - **Build Command:**
     ```bash
     cd backend && pip install -r requirements.txt
     ```
   - **Start Command:**
     ```bash
     cd backend && python -m flask db upgrade && gunicorn run:app --workers 2 --threads 4 --timeout 300 --bind 0.0.0.0:$PORT
     ```

## Step 4: Create PostgreSQL Database

1. Click **"New +"** → **"PostgreSQL"**
2. Configure:
   - **Name:** `integrityshield-db`
   - **Database:** `integrityshield`
   - **Region:** Same as your web service
   - **Plan:** **Free** (512 MB storage)
3. Click **"Create Database"**
4. Wait ~2 minutes for provisioning

## Step 5: Link Database to Web Service

1. Go to your **integrityshield-backend** web service
2. Go to **"Environment"** tab
3. Add environment variable:
   - **Key:** `INTEGRITYSHIELD_DATABASE_URL`
   - **Value:** Copy from your database's **Internal Database URL**

## Step 6: Add Environment Variables

In the **Environment** tab, add these variables:

### Required:
```
INTEGRITYSHIELD_ENV=production
INTEGRITYSHIELD_SECRET_KEY=[generate random 32-char string]
INTEGRITYSHIELD_LOG_LEVEL=INFO
INTEGRITYSHIELD_ENABLE_DEV_TOOLS=false
INTEGRITYSHIELD_AUTO_APPLY_MIGRATIONS=true
INTEGRITYSHIELD_PIPELINE_ROOT=/tmp/pipeline_runs

# At least OpenAI (required)
OPENAI_API_KEY=sk-...your-key...
```

### Optional (add as needed):
```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_AI_KEY=AIza...
GROK_API_KEY=xai-...
MISTRAL_API_KEY=...
```

### Generate Secret Key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Step 7: Deploy!

1. Click **"Create Web Service"** (or **"Manual Deploy"** if already created)
2. Wait 5-10 minutes for first build
3. Watch the logs for:
   ```
   ==> Build successful!
   ==> Starting service...
   ```

## Step 8: Test Deployment

Once deployed, you'll get a URL like: `https://integrityshield-backend.onrender.com`

Test it:
```bash
curl https://your-service.onrender.com/api/health
```

Should return:
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

## Step 9: Update Frontend

Update your frontend's API endpoint to point to your new Render URL:

```javascript
const API_BASE_URL = 'https://integrityshield-backend.onrender.com'
```

Commit and push to update GitHub Pages.

## Cost & Limits (Free Tier)

- **Web Service:** Free for 750 hours/month
- **Database:** 512 MB PostgreSQL (free forever)
- **Build Time:** 500 build minutes/month
- **Bandwidth:** Free
- **Cold Start:** ~30 seconds if idle for 15+ minutes
- **Always On:** Upgrade to paid ($7/month) to eliminate cold starts

## Troubleshooting

### Database Connection Error
```bash
# Check database URL is set correctly
# Should be: postgresql://user:pass@host:port/dbname
```

### Build Fails
```bash
# Check requirements.txt exists in backend/
# Check Python version matches (3.11)
```

### Cold Starts
Free tier services sleep after 15 minutes of inactivity. First request after sleep takes ~30 seconds.

**Solution:** Upgrade to paid plan ($7/month) for always-on service.

## Next Steps

1. Monitor logs: Render Dashboard → Your Service → Logs
2. View metrics: Dashboard → Your Service → Metrics
3. Set up custom domain (optional): Dashboard → Settings → Custom Domains

---

**That's it!** Your IntegrityShield backend is now live! 🚀
