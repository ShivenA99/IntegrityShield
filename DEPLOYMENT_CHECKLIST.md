# Deployment Readiness Checklist

## ✅ Completed

- [x] User authentication system (register, login, JWT)
- [x] API key management (save, update, delete, validate)
- [x] Settings page for users to manage API keys
- [x] API key validation (real API calls to verify keys)
- [x] API key encryption (Fernet encryption)
- [x] Database migrations for user/auth tables
- [x] Frontend authentication flow
- [x] GitHub Pages configuration
- [x] Deployment documentation (`DEPLOYMENT_PLAN.md`)
- [x] Environment variables guide (`DEPLOYMENT_ENV_VARS.md`)

## ⚠️ Pending (Optional - Can Deploy Without)

- [ ] **User API keys integration into pipeline** (auth-8)
  - Currently: Pipeline uses backend's default API keys from env vars
  - Impact: Users can save keys, but pipeline won't use them yet
  - Status: Can deploy without this - users can still add keys, backend defaults will be used
  - Priority: Medium (nice-to-have, not blocking)

## 🔧 Pre-Deployment Tasks

### 1. Backend Production Server

**Status**: Need to verify/add `gunicorn` to requirements.txt

```bash
# Check if gunicorn is in requirements.txt
grep -i gunicorn backend/requirements.txt
```

**Action**: If missing, add:
```
gunicorn>=21.2.0
```

### 2. Create Procfile (for Render/Railway)

**File**: `backend/Procfile`
```procfile
web: gunicorn run:app --workers 4 --bind 0.0.0.0:$PORT --timeout 120
```

### 3. Frontend API URL Configuration

**Status**: Need to verify frontend uses environment variable for API URL

**File**: `frontend/src/services/api.ts`
- Should use: `import.meta.env.VITE_API_BASE_URL || "/api"`
- For GitHub Pages build: Set `VITE_API_BASE_URL` during build

### 4. Database Migrations

**Status**: Should auto-apply in production
- Set `INTEGRITYSHIELD_AUTO_APPLY_MIGRATIONS=true` in cloud platform
- Or run manually: `alembic upgrade head`

### 5. Environment Variables

**Required in Cloud Platform**:
- `INTEGRITYSHIELD_SECRET_KEY` (generate new one for production)
- `INTEGRITYSHIELD_DATABASE_URL` (PostgreSQL connection string)
- `INTEGRITYSHIELD_CORS_ORIGINS` (set to GitHub Pages URL)
- `INTEGRITYSHIELD_AUTO_APPLY_MIGRATIONS=true`
- `INTEGRITYSHIELD_ENV=production`

**Optional** (for backend fallback keys):
- `OPENAI_API_KEY`
- `GOOGLE_AI_KEY`
- `ANTHROPIC_API_KEY`
- `GROK_API_KEY`

### 6. GitHub Pages Build

**Update build script** to inject backend URL:
```json
"build:gh-pages": "VITE_API_BASE_URL=https://your-backend-url.com/api GITHUB_PAGES=true vite build"
```

## 🚀 Deployment Steps

### Step 1: Prepare Backend

1. ✅ Verify `gunicorn` in `requirements.txt`
2. ✅ Create `backend/Procfile`
3. ✅ Test backend starts locally with gunicorn:
   ```bash
   cd backend
   gunicorn run:app --workers 2 --bind 0.0.0.0:8000
   ```

### Step 2: Deploy Backend (Render Example)

1. Create Render account
2. Create PostgreSQL database
3. Create Web Service:
   - Connect GitHub repo
   - Root Directory: `backend`
   - Build Command: `pip install -r requirements.txt && alembic upgrade head`
   - Start Command: `gunicorn run:app --workers 4 --bind 0.0.0.0:$PORT`
4. Set environment variables (see `DEPLOYMENT_ENV_VARS.md`)
5. Deploy and get backend URL

### Step 3: Update Frontend

1. Update `frontend/package.json` build script with backend URL
2. Build for GitHub Pages:
   ```bash
   cd frontend
   npm run build:gh-pages
   ```
3. Commit `docs/` folder (contains built frontend)

### Step 4: Deploy Frontend to GitHub Pages

1. Push to GitHub
2. GitHub Pages will serve from `docs/` folder
3. Verify frontend connects to backend

### Step 5: Test End-to-End

1. Visit GitHub Pages URL
2. Register a new user
3. Add API keys in Settings
4. Start a pipeline run
5. Verify everything works

## 📝 Notes

- **User API Keys**: Users can add/update keys anytime, but pipeline currently uses backend defaults. This is fine for initial deployment - we can integrate user keys later.
- **Backend API Keys**: Set in cloud platform env vars as fallback/default keys
- **Database**: Use PostgreSQL in production (SQLite is for local dev only)

## ⚡ Quick Deploy Commands

```bash
# 1. Add gunicorn if missing
echo "gunicorn>=21.2.0" >> backend/requirements.txt

# 2. Create Procfile
echo "web: gunicorn run:app --workers 4 --bind 0.0.0.0:\$PORT --timeout 120" > backend/Procfile

# 3. Test backend locally with gunicorn
cd backend && gunicorn run:app --workers 2 --bind 0.0.0.0:8000

# 4. Build frontend for GitHub Pages (after setting backend URL)
cd frontend && VITE_API_BASE_URL=https://your-backend.onrender.com/api GITHUB_PAGES=true npm run build

# 5. Commit and push
git add .
git commit -m "Prepare for deployment"
git push
```

