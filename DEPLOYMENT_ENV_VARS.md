# Environment Variables for Deployment

This document explains how environment variables are managed in different deployment scenarios.

## Local Development (Current Setup)

In local development, environment variables are loaded from `.env` files:
- **Root `.env`**: Used by `backend/app/__init__.py` via `load_dotenv()`
- **Backend `.env`**: Used by `backend/scripts/run_dev_server.sh`

**⚠️ Important**: `.env` files are in `.gitignore` and should NEVER be committed to git.

## Required Environment Variables

### Critical (Required for Backend to Start)

| Variable | Description | Example | Required For |
|----------|-------------|---------|--------------|
| `INTEGRITYSHIELD_SECRET_KEY` | Flask secret key for sessions/JWT | `your-random-secret-key-here` | Authentication, encryption |
| `INTEGRITYSHIELD_DATABASE_URL` | Database connection string | `postgresql://user:pass@host:5432/dbname` | Database |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` | OpenAI LLM calls |
| `GOOGLE_AI_KEY` | Google/Gemini API key | `AIza...` | Google LLM calls |

### Optional (For Multi-Provider Support)

| Variable | Description | Example | Required For |
|----------|-------------|---------|--------------|
| `ANTHROPIC_API_KEY` | Anthropic/Claude API key | `sk-ant-...` | Anthropic LLM calls |
| `GROK_API_KEY` | Grok/xAI API key | `xai-...` | Grok LLM calls |

### Configuration (Optional, with Defaults)

| Variable | Description | Default | Used For |
|----------|-------------|---------|----------|
| `INTEGRITYSHIELD_ENV` | Environment name | `development` | Config selection |
| `INTEGRITYSHIELD_AUTO_APPLY_MIGRATIONS` | Auto-run DB migrations | `true` | Database setup |
| `INTEGRITYSHIELD_CORS_ORIGINS` | Allowed CORS origins | `*` | Frontend access |
| `INTEGRITYSHIELD_LOG_LEVEL` | Logging level | `DEBUG` | Logging |
| `INTEGRITYSHIELD_PIPELINE_ROOT` | Pipeline storage path | `./data/pipeline_runs` | File storage |
| `INTEGRITYSHIELD_REPORT_ANTHROPIC_MODEL` | Anthropic model | `claude-3-5-haiku-20241022` | Report generation |
| `INTEGRITYSHIELD_REPORT_GOOGLE_MODEL` | Google model | `models/gemini-2.5-flash` | Report generation |
| `INTEGRITYSHIELD_REPORT_GROK_MODEL` | Grok model | `grok-2-latest` | Report generation |

## Cloud Deployment Options

### Option 1: Render (Recommended)

**How to Set Environment Variables:**

1. Go to your Render service dashboard
2. Navigate to **Environment** tab
3. Click **Add Environment Variable**
4. Add each variable one by one

**Example Setup:**
```
INTEGRITYSHIELD_SECRET_KEY=your-secret-key-here
INTEGRITYSHIELD_DATABASE_URL=postgresql://user:pass@host:5432/dbname
OPENAI_API_KEY=sk-...
GOOGLE_AI_KEY=AIza...
ANTHROPIC_API_KEY=sk-ant-...
GROK_API_KEY=xai-...
INTEGRITYSHIELD_ENV=production
INTEGRITYSHIELD_AUTO_APPLY_MIGRATIONS=true
INTEGRITYSHIELD_CORS_ORIGINS=https://shivenagarwal.github.io
```

**Database Setup:**
- Render provides managed PostgreSQL databases
- When you create a PostgreSQL database, Render automatically provides a `DATABASE_URL`
- Set `INTEGRITYSHIELD_DATABASE_URL` to this value (or Render can auto-inject it as `DATABASE_URL`)

**Security:**
- Render encrypts environment variables at rest
- Variables are only visible to service owners
- Never commit secrets to git

### Option 2: Railway

**How to Set Environment Variables:**

1. Go to your Railway project
2. Select your service
3. Go to **Variables** tab
4. Click **New Variable** to add each one

**Example Setup:**
Same as Render above.

**Database Setup:**
- Railway provides managed PostgreSQL
- Railway automatically injects `DATABASE_URL` environment variable
- You can use `DATABASE_URL` directly or set `INTEGRITYSHIELD_DATABASE_URL=$DATABASE_URL`

### Option 3: AWS (Elastic Beanstalk)

**How to Set Environment Variables:**

1. Go to Elastic Beanstalk console
2. Select your environment
3. Go to **Configuration** → **Software**
4. Under **Environment properties**, add each variable

**Alternative (Using EB CLI):**
```bash
eb setenv INTEGRITYSHIELD_SECRET_KEY=your-key INTEGRITYSHIELD_DATABASE_URL=...
```

**Database Setup:**
- Use RDS (Relational Database Service) for PostgreSQL
- Create RDS instance and get connection string
- Set `INTEGRITYSHIELD_DATABASE_URL` to RDS connection string

### Option 4: Google Cloud Platform (App Engine)

**How to Set Environment Variables:**

Create `app.yaml`:
```yaml
env_variables:
  INTEGRITYSHIELD_SECRET_KEY: 'your-secret-key'
  INTEGRITYSHIELD_DATABASE_URL: 'postgresql://...'
  OPENAI_API_KEY: 'sk-...'
  # ... etc
```

**For Secrets (Recommended):**
Use Google Secret Manager:
```yaml
env_variables:
  INTEGRITYSHIELD_SECRET_KEY: 'projects/PROJECT_ID/secrets/SECRET_NAME/versions/latest'
```

**Database Setup:**
- Use Cloud SQL for PostgreSQL
- Get connection string from Cloud SQL console
- Set `INTEGRITYSHIELD_DATABASE_URL`

## Generating a Secure Secret Key

For `INTEGRITYSHIELD_SECRET_KEY`, generate a secure random key:

**Python:**
```python
import secrets
print(secrets.token_urlsafe(32))
```

**OpenSSL:**
```bash
openssl rand -hex 32
```

**Online (use once, then delete):**
- https://randomkeygen.com/

## Environment Variable Priority

The application loads environment variables in this order (highest to lowest priority):

1. **System environment variables** (set in shell/cloud platform)
2. **`.env` file** (local development only, via `load_dotenv()`)
3. **Default values** (in `backend/app/config.py`)

**In production, always use system environment variables (set in cloud platform), not `.env` files.**

## Migration from Local to Cloud

### Step 1: List Your Current Variables

Check what you have in your local `.env`:
```bash
# Don't run this if .env contains secrets - just review manually
cat .env  # Review only, don't share output
```

### Step 2: Generate Production Secret Key

Generate a new `INTEGRITYSHIELD_SECRET_KEY` for production (don't reuse dev key):
```python
import secrets
print(secrets.token_urlsafe(32))
```

### Step 3: Set Variables in Cloud Platform

Add all variables to your cloud platform's environment variable settings (see platform-specific instructions above).

### Step 4: Update Database URL

- **Local**: `sqlite:////path/to/integrityshield.db`
- **Production**: `postgresql://user:password@host:5432/dbname`

### Step 5: Update CORS Origins

Set `INTEGRITYSHIELD_CORS_ORIGINS` to your frontend URL:
```
INTEGRITYSHIELD_CORS_ORIGINS=https://shivenagarwal.github.io
```

## Security Best Practices

1. **Never commit `.env` files** - Already in `.gitignore`, but double-check
2. **Use different keys for dev/prod** - Don't reuse production keys in development
3. **Rotate keys regularly** - Especially if they were ever exposed
4. **Use secret management services** - For production, consider AWS Secrets Manager, Google Secret Manager, etc.
5. **Limit CORS origins** - Don't use `*` in production, specify exact frontend URL
6. **Use strong secret keys** - Generate `INTEGRITYSHIELD_SECRET_KEY` with sufficient entropy (32+ bytes)

## Testing Environment Variables in Production

After deployment, verify environment variables are loaded:

```bash
# Check if backend can access variables (via health check endpoint)
curl https://your-backend-url.com/api/status

# Or check logs for configuration
# Look for: "Starting backend with: INTEGRITYSHIELD_DATABASE_URL=..."
```

## Troubleshooting

### "Missing required environment variables"

**Problem**: Backend fails to start with missing variable error.

**Solution**:
1. Check cloud platform's environment variable settings
2. Ensure variable names match exactly (case-sensitive)
3. Restart the service after adding variables
4. Check for typos or extra spaces

### "Database connection failed"

**Problem**: Can't connect to database.

**Solution**:
1. Verify `INTEGRITYSHIELD_DATABASE_URL` is set correctly
2. Check database credentials
3. Ensure database is accessible from your cloud service (firewall/security groups)
4. For managed databases, check connection string format

### "CORS error" from frontend

**Problem**: Frontend can't call backend API.

**Solution**:
1. Set `INTEGRITYSHIELD_CORS_ORIGINS` to your frontend URL (not `*`)
2. Include protocol: `https://shivenagarwal.github.io` (not just domain)
3. Restart backend after changing CORS settings

## Example: Complete Render Setup

1. **Create PostgreSQL Database**:
   - Render Dashboard → New → PostgreSQL
   - Note the `Internal Database URL`

2. **Create Web Service**:
   - Render Dashboard → New → Web Service
   - Connect GitHub repo
   - Root Directory: `backend`
   - Build Command: `pip install -r requirements.txt && alembic upgrade head`
   - Start Command: `gunicorn run:app --workers 4 --bind 0.0.0.0:$PORT`

3. **Set Environment Variables**:
   ```
   INTEGRITYSHIELD_SECRET_KEY=<generated-secret>
   INTEGRITYSHIELD_DATABASE_URL=<from-postgres-service>
   OPENAI_API_KEY=<your-key>
   GOOGLE_AI_KEY=<your-key>
   ANTHROPIC_API_KEY=<your-key>
   GROK_API_KEY=<your-key>
   INTEGRITYSHIELD_ENV=production
   INTEGRITYSHIELD_AUTO_APPLY_MIGRATIONS=true
   INTEGRITYSHIELD_CORS_ORIGINS=https://shivenagarwal.github.io
   ```

4. **Deploy**: Render will automatically deploy on git push

## Notes

- **User API Keys**: Once deployed, users can add their own API keys via the Settings page. These are stored encrypted in the database, separate from the backend's default API keys.
- **Backend API Keys**: The backend's API keys (from environment variables) are used as fallbacks or for system operations. User API keys take precedence when available.
- **Local Development**: Continue using `.env` files locally. They won't affect production.

