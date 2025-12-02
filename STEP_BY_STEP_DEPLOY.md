# Step-by-Step Deployment Guide

## 🎯 Where to Deploy

**Recommended: Render.com** (Free tier available, easy setup)
- Backend: Render Web Service
- Database: Render PostgreSQL
- Frontend: GitHub Pages (already configured)

**Alternative: Railway.app** (Similar to Render, also has free tier)

---

## 📋 Part 1: Deploy Backend to Render

### Step 1.1: Create Render Account

1. Go to **https://render.com**
2. Sign up with GitHub (recommended) or email
3. Verify your email if needed

### Step 1.2: Create PostgreSQL Database

1. In Render dashboard, click **"New +"** button (top right)
2. Select **"PostgreSQL"**
3. Configure:
   - **Name**: `fairtestai-db` (or your choice)
   - **Database**: `fairtestai` (or leave default)
   - **User**: Leave default
   - **Region**: Choose closest to you
   - **PostgreSQL Version**: Latest (14+)
   - **Plan**: Free tier is fine to start
4. Click **"Create Database"**
5. **IMPORTANT**: Wait for database to be created, then:
   - Go to database dashboard
   - Find **"Internal Database URL"** (looks like: `postgresql://user:pass@host:5432/dbname`)
   - **Copy this URL** - you'll need it in Step 1.4

### Step 1.3: Create Web Service (Backend)

1. In Render dashboard, click **"New +"** button
2. Select **"Web Service"**
3. **Connect Repository**:
   - Click **"Connect account"** if not connected
   - Select your GitHub account
   - Find and select: `fairtestai_-llm-assessment-vulnerability-simulator-main`
   - Click **"Connect"**

4. **Configure Service**:
   - **Name**: `fairtestai-backend` (or your choice)
   - **Region**: Same as database
   - **Branch**: `main` (or your default branch)
   - **Root Directory**: `backend` ⚠️ **IMPORTANT: Set this!**
   - **Environment**: `Python 3`
   - **Build Command**: 
     ```
     pip install -r requirements.txt && alembic upgrade head
     ```
   - **Start Command**: 
     ```
     gunicorn run:app --workers 4 --bind 0.0.0.0:$PORT --timeout 120
     ```
   - **Plan**: Free tier (or Starter for better performance)

5. **DON'T click "Create Web Service" yet!** First add environment variables.

### Step 1.4: Add Environment Variables

1. Scroll down to **"Environment Variables"** section
2. Click **"Add Environment Variable"** for each:

   **Required Variables:**
   
   | Key | Value | Notes |
   |-----|-------|-------|
   | `FAIRTESTAI_SECRET_KEY` | Generate new one (see below) | **Generate a new secret key** |
   | `FAIRTESTAI_DATABASE_URL` | Paste Internal Database URL from Step 1.2 | From PostgreSQL service |
   | `FAIRTESTAI_ENV` | `production` | |
   | `FAIRTESTAI_AUTO_APPLY_MIGRATIONS` | `true` | Auto-run database migrations |
   | `FAIRTESTAI_CORS_ORIGINS` | `https://shivenagarwal.github.io` | Your GitHub Pages URL |

   **Optional (Backend Default Keys - users can override):**
   
   | Key | Value |
   |-----|-------|
   | `OPENAI_API_KEY` | Your OpenAI key (optional) |
   | `GOOGLE_AI_KEY` | Your Google/Gemini key (optional) |
   | `ANTHROPIC_API_KEY` | Your Anthropic key (optional) |
   | `GROK_API_KEY` | Your Grok key (optional) |

3. **Generate Secret Key**:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Copy the output and use it for `FAIRTESTAI_SECRET_KEY`

### Step 1.5: Deploy Backend

1. Click **"Create Web Service"** at the bottom
2. Wait for deployment (5-10 minutes):
   - Render will install dependencies
   - Run database migrations
   - Start the service
3. **Note your service URL**: 
   - It will be something like: `https://fairtestai-backend.onrender.com`
   - **Copy this URL** - you'll need it for frontend!

### Step 1.6: Verify Backend is Running

1. Go to your service dashboard
2. Check **"Logs"** tab - should see:
   ```
   Starting gunicorn...
   Pipeline orchestrator initialized...
   ```
3. Visit your backend URL in browser:
   - Should see: `{"error": "Not found"}` or similar (this is OK - means backend is running)
4. Test health endpoint:
   ```
   https://your-backend-url.onrender.com/api/status
   ```

---

## 📋 Part 2: Update Frontend for Production

### Step 2.1: Update Build Script

1. Open `frontend/package.json`
2. Find the `build:gh-pages:prod` script
3. Replace `YOUR-BACKEND-URL` with your actual Render backend URL:
   ```json
   "build:gh-pages:prod": "VITE_API_BASE_URL=https://fairtestai-backend.onrender.com/api GITHUB_PAGES=true vite build"
   ```
   ⚠️ **Replace `fairtestai-backend.onrender.com` with YOUR actual backend URL!**

### Step 2.2: Build Frontend

```bash
cd frontend
npm run build:gh-pages:prod
```

This will:
- Build the React app
- Output to `docs/` folder
- Configure it to use your Render backend URL

### Step 2.3: Verify Build

```bash
# Check docs folder was updated
ls -la docs/
# Should see index.html and assets/ folder
```

---

## 📋 Part 3: Deploy Frontend to GitHub Pages

### Step 3.1: Commit Changes

```bash
# From project root
git add .
git commit -m "Deploy to production - connect frontend to Render backend"
git push
```

### Step 3.2: Configure GitHub Pages (if not already done)

1. Go to your GitHub repository
2. Click **Settings** → **Pages** (left sidebar)
3. Under **"Source"**:
   - Select **"Deploy from a branch"**
   - Branch: `main` (or your default)
   - Folder: `/docs`
   - Click **"Save"**

### Step 3.3: Verify Deployment

1. Wait 1-2 minutes for GitHub Pages to build
2. Visit your GitHub Pages URL:
   ```
   https://shivenagarwal.github.io/fairtestai_-llm-assessment-vulnerability-simulator-main/
   ```
3. You should see your landing page!

---

## 📋 Part 4: Test Everything

### Step 4.1: Test Authentication

1. Visit your GitHub Pages URL
2. Click **"Try It"** button
3. **Register** a new account:
   - Enter email, password, name
   - Click "Register"
4. You should be logged in and see the dashboard

### Step 4.2: Test API Keys

1. Go to **Settings** page
2. Add an API key (e.g., OpenAI):
   - Enter your API key
   - Click "Validate"
   - Should show "API key is valid"
   - Click "Save API Keys"
3. Verify it shows "Configured" status

### Step 4.3: Test Pipeline

1. Go to **Dashboard**
2. Upload a PDF
3. Start a pipeline run
4. Verify it processes correctly

---

## 🔧 Troubleshooting

### Backend Issues

**Problem**: Backend won't start
- **Check**: Render logs (in service dashboard)
- **Common fixes**:
  - Verify `Root Directory` is set to `backend`
  - Check all environment variables are set
  - Verify database URL format is correct

**Problem**: Database connection failed
- **Check**: `FAIRTESTAI_DATABASE_URL` is correct
- **Check**: Database is running (in Render dashboard)
- **Fix**: Ensure you used "Internal Database URL" not "External"

**Problem**: Migrations failed
- **Check**: `FAIRTESTAI_AUTO_APPLY_MIGRATIONS=true` is set
- **Fix**: Manually run in Render shell: `alembic upgrade head`

### Frontend Issues

**Problem**: Frontend can't connect to backend
- **Check**: Browser console (F12) for errors
- **Check**: `VITE_API_BASE_URL` in build command matches backend URL
- **Check**: CORS settings - `FAIRTESTAI_CORS_ORIGINS` should match GitHub Pages URL

**Problem**: 404 errors on routes
- **Check**: `docs/404.html` exists (should be a copy of index.html)
- **Fix**: Rebuild frontend with `npm run build:gh-pages:prod`

### General Issues

**Problem**: Slow first request
- **Normal**: Render free tier services "spin down" after inactivity
- **First request** takes 30-60 seconds to wake up
- **Solution**: Upgrade to paid plan for always-on service

---

## ✅ Deployment Checklist

- [ ] Render account created
- [ ] PostgreSQL database created
- [ ] Database URL copied
- [ ] Web service created with correct root directory
- [ ] All environment variables added
- [ ] Backend deployed and running
- [ ] Backend URL noted
- [ ] Frontend build script updated with backend URL
- [ ] Frontend built successfully
- [ ] Changes committed and pushed
- [ ] GitHub Pages configured
- [ ] Tested registration/login
- [ ] Tested API key management
- [ ] Tested pipeline run

---

## 🎉 You're Deployed!

Your application is now live at:
- **Frontend**: `https://shivenagarwal.github.io/fairtestai_-llm-assessment-vulnerability-simulator-main/`
- **Backend**: `https://your-backend.onrender.com`

Users can now:
- Register accounts
- Add their own API keys
- Run pipeline analyses
- View reports

---

## 📝 Next Steps (Optional)

1. **Custom Domain**: Add your own domain to GitHub Pages
2. **Monitoring**: Set up error tracking (Sentry, etc.)
3. **User API Keys**: Integrate user keys into pipeline (currently uses backend defaults)
4. **Scaling**: Upgrade Render plan if you get traffic

---

## 🆘 Need Help?

- **Render Docs**: https://render.com/docs
- **GitHub Pages Docs**: https://docs.github.com/en/pages
- **Check Logs**: Render dashboard → Your service → Logs tab

