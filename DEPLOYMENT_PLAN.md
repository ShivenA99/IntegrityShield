# Deployment Plan for IntegrityShield

## Overview

This document outlines the plan to deploy IntegrityShield to the cloud and connect it with GitHub Pages.

**📋 Important**: See [`DEPLOYMENT_ENV_VARS.md`](./DEPLOYMENT_ENV_VARS.md) for detailed information on managing environment variables in deployment.

## Architecture

```
GitHub Pages (Frontend) → Cloud Backend (API) → Database
```

- **Frontend**: Static React app hosted on GitHub Pages
- **Backend**: Flask API deployed on cloud platform
- **Database**: PostgreSQL or SQLite (depending on platform)

## Deployment Options

### Option 1: Render (Recommended for Simplicity)

**Pros:**
- Free tier available
- Easy PostgreSQL setup
- Automatic HTTPS
- Simple deployment from GitHub

**Steps:**
1. Create account at [render.com](https://render.com)
2. Create new Web Service
3. Connect GitHub repository
4. Configure:
   - Build Command: `cd backend && pip install -r requirements.txt`
   - Start Command: `cd backend && gunicorn run:app`
   - Environment Variables: See [`DEPLOYMENT_ENV_VARS.md`](./DEPLOYMENT_ENV_VARS.md) for complete list
     - `FAIRTESTAI_DATABASE_URL` (PostgreSQL from Render)
     - `FAIRTESTAI_SECRET_KEY` (generate secure key)
     - `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc. (optional, users provide their own)
5. Create PostgreSQL database on Render
6. Update frontend API base URL to point to Render backend

### Option 2: Railway

**Pros:**
- Simple deployment
- Good free tier
- Easy database setup

**Steps:**
1. Create account at [railway.app](https://railway.app)
2. Deploy from GitHub
3. Add PostgreSQL service
4. Configure environment variables
5. Update frontend API URL

### Option 3: AWS (Production Scale)

**Components:**
- **EC2/ECS**: Backend API
- **RDS**: PostgreSQL database
- **S3**: File storage for PDFs
- **CloudFront**: CDN for frontend (optional)

**Steps:**
1. Set up VPC and security groups
2. Launch EC2 instance or ECS cluster
3. Create RDS PostgreSQL instance
4. Configure S3 bucket for file storage
5. Set up load balancer
6. Configure domain and SSL

### Option 4: Google Cloud Platform

**Components:**
- **Cloud Run**: Backend API (serverless)
- **Cloud SQL**: PostgreSQL
- **Cloud Storage**: File storage

**Steps:**
1. Create GCP project
2. Deploy backend to Cloud Run
3. Create Cloud SQL instance
4. Configure Cloud Storage bucket
5. Update frontend API URL

## Frontend Configuration

### Update API Base URL

1. Create `.env.production` file:
```bash
VITE_API_BASE_URL=https://your-backend-url.com/api
```

2. Update `frontend/src/services/api.ts` to use environment variable:
```typescript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";
```

3. For GitHub Pages, update the base URL in build:
```bash
VITE_API_BASE_URL=https://your-backend-url.com/api npm run build:gh-pages
```

## Backend Configuration

### Environment Variables

Required environment variables:
```bash
FAIRTESTAI_SECRET_KEY=<generate-secure-random-key>
FAIRTESTAI_DATABASE_URL=postgresql://user:pass@host:port/dbname
FAIRTESTAI_AUTO_APPLY_MIGRATIONS=true
CORS_ORIGINS=https://your-github-pages-url.github.io
```

Optional (for system-wide API keys if needed):
```bash
OPENAI_API_KEY=<optional>
ANTHROPIC_API_KEY=<optional>
GOOGLE_AI_KEY=<optional>
GROK_API_KEY=<optional>
```

### Database Migrations

Migrations will run automatically if `FAIRTESTAI_AUTO_APPLY_MIGRATIONS=true`.

To run manually:
```bash
cd backend
flask db upgrade
```

## GitHub Pages Integration

### Update "Try It" Button

1. Update the landing page button to point to deployed backend:
```typescript
// In LandingPage.tsx or similar
const TRY_IT_URL = import.meta.env.VITE_API_BASE_URL 
  ? `${import.meta.env.VITE_API_BASE_URL.replace('/api', '')}/try`
  : '/try';
```

2. Or use environment variable:
```bash
VITE_APP_URL=https://your-github-pages-url.github.io/fairtestai_-llm-assessment-vulnerability-simulator-main
```

### CORS Configuration

Update `backend/app/config.py`:
```python
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "https://your-username.github.io"
).split(",")
```

## Security Considerations

1. **API Keys**: Users store their own API keys (encrypted in database)
2. **JWT Tokens**: 30-day expiration, stored in localStorage
3. **HTTPS**: Required for production
4. **CORS**: Restrict to GitHub Pages domain
5. **Rate Limiting**: Consider adding rate limiting for API endpoints
6. **Database Encryption**: Ensure database connections use SSL

## Testing Deployment

1. **Backend Health Check**:
   ```bash
   curl https://your-backend-url.com/api/health
   ```

2. **Frontend Connection**:
   - Open GitHub Pages site
   - Click "Try It"
   - Verify login/register works
   - Test API key management

3. **End-to-End Test**:
   - Register new user
   - Add API keys
   - Start a pipeline run
   - Verify reports generate

## Monitoring

1. **Backend Logs**: Monitor application logs for errors
2. **Database**: Monitor connection pool and query performance
3. **API Usage**: Track API calls and response times
4. **Error Tracking**: Consider Sentry or similar for error tracking

## Rollback Plan

1. Keep previous deployment version
2. Database migrations are reversible (check migration files)
3. Frontend can be rolled back via GitHub Pages history
4. Environment variables stored securely

## Cost Estimation

### Render (Free Tier)
- Web Service: Free (with limitations)
- PostgreSQL: Free (up to 90 days, then $7/month)
- **Total**: ~$0-7/month

### Railway
- Hobby Plan: $5/month
- PostgreSQL: Included
- **Total**: ~$5/month

### AWS (Production)
- EC2: ~$10-50/month
- RDS: ~$15-30/month
- S3: ~$1-5/month
- **Total**: ~$26-85/month

## Next Steps

1. Choose deployment platform
2. Set up backend deployment
3. Configure database
4. Update frontend API URL
5. Test end-to-end
6. Update GitHub Pages "Try It" button
7. Monitor and optimize

## Support

For issues:
1. Check backend logs
2. Verify environment variables
3. Test database connectivity
4. Check CORS configuration
5. Verify API endpoints are accessible

