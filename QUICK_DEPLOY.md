# Quick Deployment Guide

## ✅ You're Ready to Deploy!

All critical components are in place. Here's what to do:

## Step 1: Deploy Backend (Render Example)

1. **Go to [render.com](https://render.com)** and sign up/login

2. **Create PostgreSQL Database**:
   - Click "New +" → "PostgreSQL"
   - Name it (e.g., `integrityshield-db`)
   - Note the **Internal Database URL** (you'll need this)

3. **Create Web Service**:
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Configure:
     - **Name**: `integrityshield-backend` (or your choice)
     - **Root Directory**: `backend`
     - **Environment**: `Python 3`
     - **Build Command**: `pip install -r requirements.txt && alembic upgrade head`
     - **Start Command**: `gunicorn run:app --workers 4 --bind 0.0.0.0:$PORT --timeout 120`
     - **Plan**: Free tier is fine to start

4. **Add Environment Variables** (in Web Service settings):
   ```
   INTEGRITYSHIELD_SECRET_KEY=4gH_OIfY5qloNOcXuqv5omr7rNUvF4bzP0m18Y2dcfY
   INTEGRITYSHIELD_DATABASE_URL=<paste Internal Database URL from step 2>
   INTEGRITYSHIELD_ENV=production
   INTEGRITYSHIELD_AUTO_APPLY_MIGRATIONS=true
   INTEGRITYSHIELD_CORS_ORIGINS=https://shivenagarwal.github.io
   OPENAI_API_KEY=<your-key-if-you-want-backend-default>
   GOOGLE_AI_KEY=<your-key-if-you-want-backend-default>
   ```

5. **Deploy**: Click "Create Web Service"
   - Wait for build to complete
   - Note your backend URL (e.g., `https://integrityshield-backend.onrender.com`)

## Step 2: Update Frontend Build

1. **Update `frontend/package.json`**:
   ```json
   "build:gh-pages:prod": "VITE_API_BASE_URL=https://YOUR-BACKEND-URL.onrender.com/api GITHUB_PAGES=true vite build"
   ```
   Replace `YOUR-BACKEND-URL` with your actual Render backend URL

2. **Build Frontend**:
   ```bash
   cd frontend
   npm run build:gh-pages:prod
   ```

3. **Verify `docs/` folder** was updated with new build

## Step 3: Deploy Frontend to GitHub Pages

1. **Commit and Push**:
   ```bash
   git add .
   git commit -m "Deploy to production"
   git push
   ```

2. **GitHub Pages** will automatically serve from `docs/` folder

3. **Verify**:
   - Go to your GitHub Pages URL
   - Test registration/login
   - Test adding API keys
   - Test starting a pipeline

## Step 4: Test Everything

1. Visit: `https://shivenagarwal.github.io/integrityshield_-llm-assessment-vulnerability-simulator-main/`
2. Click "Try It" → Register a new account
3. Go to Settings → Add API keys
4. Start a pipeline run
5. Verify it works end-to-end

## Troubleshooting

### Backend won't start
- Check logs in Render dashboard
- Verify all environment variables are set
- Check database connection string format

### Frontend can't connect to backend
- Verify `VITE_API_BASE_URL` in build command matches backend URL
- Check CORS settings (`INTEGRITYSHIELD_CORS_ORIGINS`)
- Check browser console for errors

### Database errors
- Verify `INTEGRITYSHIELD_DATABASE_URL` is correct
- Check `INTEGRITYSHIELD_AUTO_APPLY_MIGRATIONS=true` is set
- Check Render database is running

## What's Working

✅ User authentication (register/login)  
✅ API key management (users can add/update keys)  
✅ API key validation (real API calls)  
✅ Settings page  
✅ Pipeline runs (using backend default keys for now)  
✅ All reports and UI  

## What's Next (Optional)

- Integrate user API keys into pipeline (so runs use user's keys)
- Add more error handling
- Add monitoring/logging
- Scale up if needed

## Security Notes

- ✅ API keys are encrypted in database
- ✅ Passwords are hashed
- ✅ JWT tokens for authentication
- ✅ CORS configured for GitHub Pages
- ⚠️ Generate a NEW `INTEGRITYSHIELD_SECRET_KEY` for production (don't use the example one)

---

**You're all set! 🚀**

