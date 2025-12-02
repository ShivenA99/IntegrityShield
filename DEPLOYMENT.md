# IntegrityShield Deployment Guide - Google Cloud Run

This guide walks through deploying IntegrityShield backend to Google Cloud Platform.

## Prerequisites

- Google Cloud account with $300 credit
- `gcloud` CLI installed: https://cloud.google.com/sdk/docs/install
- Docker installed (for local testing)
- API keys: OpenAI, Anthropic, Google AI, Grok (optional), Mistral

## Architecture

```
Frontend (GitHub Pages)
    ↓ HTTPS
Backend (Cloud Run) ←→ Cloud SQL (PostgreSQL)
    ↓
Cloud Storage (pipeline files)
```

## Step 1: Setup GCP Project (5 min)

```bash
# Login to GCP
gcloud auth login

# Create new project
gcloud projects create integrityshield-demo --name="IntegrityShield Demo"

# Set as active project
gcloud config set project integrityshield-demo

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  storage-api.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com

# Set default region (us-central1 recommended)
gcloud config set run/region us-central1
```

## Step 2: Create Cloud SQL Database (10 min)

```bash
# Create PostgreSQL instance (smallest tier for demo)
gcloud sql instances create integrityshield-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --root-password=GENERATE_SECURE_PASSWORD_HERE

# Create database
gcloud sql databases create integrityshield --instance=integrityshield-db

# Get connection name (save this!)
gcloud sql instances describe integrityshield-db --format="value(connectionName)"
# Output: PROJECT_ID:us-central1:integrityshield-db
```

## Step 3: Create Storage Bucket (2 min)

```bash
# Create bucket for pipeline files
gsutil mb -l us-central1 gs://integrityshield-files

# Set lifecycle to delete old files after 90 days (optional)
cat > lifecycle.json << 'EOF'
{
  "lifecycle": {
    "rule": [{
      "action": {"type": "Delete"},
      "condition": {"age": 90}
    }]
  }
}
EOF
gsutil lifecycle set lifecycle.json gs://integrityshield-files
```

## Step 4: Store Secrets (5 min)

```bash
# Create secrets in Secret Manager
echo -n "YOUR_OPENAI_API_KEY" | gcloud secrets create openai-api-key --data-file=-
echo -n "YOUR_ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=-
echo -n "YOUR_GOOGLE_AI_KEY" | gcloud secrets create google-ai-key --data-file=-
echo -n "YOUR_GROK_API_KEY" | gcloud secrets create grok-api-key --data-file=-
echo -n "YOUR_MISTRAL_API_KEY" | gcloud secrets create mistral-api-key --data-file=-

# Generate and store app secret key
python3 -c "import secrets; print(secrets.token_urlsafe(32))" | gcloud secrets create app-secret-key --data-file=-

# Create database URL secret
# Format: postgresql://postgres:PASSWORD@/integrityshield?host=/cloudsql/PROJECT_ID:us-central1:integrityshield-db
echo -n "postgresql://postgres:YOUR_DB_PASSWORD@/integrityshield?host=/cloudsql/PROJECT_ID:us-central1:integrityshield-db" \
  | gcloud secrets create database-url --data-file=-
```

## Step 5: Build and Deploy (10-15 min)

```bash
# Navigate to backend directory
cd backend

# Build container image
gcloud builds submit --tag gcr.io/PROJECT_ID/integrityshield-backend

# Deploy to Cloud Run
gcloud run deploy integrityshield-backend \
  --image gcr.io/PROJECT_ID/integrityshield-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 5 \
  --min-instances 0 \
  --add-cloudsql-instances PROJECT_ID:us-central1:integrityshield-db \
  --set-secrets="OPENAI_API_KEY=openai-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,GOOGLE_AI_KEY=google-ai-key:latest,GROK_API_KEY=grok-api-key:latest,MISTRAL_API_KEY=mistral-api-key:latest,INTEGRITYSHIELD_SECRET_KEY=app-secret-key:latest,INTEGRITYSHIELD_DATABASE_URL=database-url:latest" \
  --set-env-vars="INTEGRITYSHIELD_ENV=production,INTEGRITYSHIELD_FILE_STORAGE_BUCKET=integrityshield-files,INTEGRITYSHIELD_PIPELINE_ROOT=/tmp/pipeline_runs,INTEGRITYSHIELD_ENABLE_DEV_TOOLS=false,INTEGRITYSHIELD_AUTO_APPLY_MIGRATIONS=true"

# Get the service URL
gcloud run services describe integrityshield-backend --region us-central1 --format="value(status.url)"
# Output: https://integrityshield-backend-RANDOM.run.app
```

## Step 6: Update Frontend (2 min)

Update your frontend's API endpoint to point to the Cloud Run URL:

```javascript
// In your frontend config
const API_BASE_URL = 'https://integrityshield-backend-RANDOM.run.app'
```

Commit and push to GitHub to update GitHub Pages.

## Step 7: Test Deployment

```bash
# Health check
curl https://integrityshield-backend-RANDOM.run.app/api/health

# Test with authentication
curl -X POST https://integrityshield-backend-RANDOM.run.app/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}'
```

## Monitoring & Logs

```bash
# View logs
gcloud run services logs read integrityshield-backend --region us-central1

# View metrics
gcloud run services describe integrityshield-backend --region us-central1
```

## Cost Optimization

For demo period, costs should be minimal (~$5-10 total):
- Cloud Run: Free tier covers most demo usage
- Cloud SQL: ~$7/month (can delete after demo)
- Cloud Storage: ~$0.02/GB/month

To minimize costs:
```bash
# Stop Cloud SQL when not in use
gcloud sql instances patch integrityshield-db --activation-policy=NEVER

# Restart when needed
gcloud sql instances patch integrityshield-db --activation-policy=ALWAYS
```

## Cleanup (After Demo)

```bash
# Delete Cloud Run service
gcloud run services delete integrityshield-backend --region us-central1

# Delete Cloud SQL instance
gcloud sql instances delete integrityshield-db

# Delete storage bucket
gsutil rm -r gs://integrityshield-files

# Delete secrets
gcloud secrets delete openai-api-key
gcloud secrets delete anthropic-api-key
gcloud secrets delete google-ai-key
gcloud secrets delete grok-api-key
gcloud secrets delete mistral-api-key
gcloud secrets delete app-secret-key
gcloud secrets delete database-url

# Delete project (removes everything)
gcloud projects delete integrityshield-demo
```

## Troubleshooting

### Database Connection Issues
```bash
# Check Cloud SQL connection
gcloud sql instances describe integrityshield-db

# View Cloud Run logs for errors
gcloud run services logs read integrityshield-backend --region us-central1 --limit=50
```

### Memory/Timeout Issues
```bash
# Increase memory and timeout
gcloud run services update integrityshield-backend \
  --memory 4Gi \
  --timeout 600 \
  --region us-central1
```

### Cold Start Issues
```bash
# Set minimum instances to 1 (costs ~$5/month extra)
gcloud run services update integrityshield-backend \
  --min-instances 1 \
  --region us-central1
```

## Support

For issues, check:
1. Cloud Run logs: `gcloud run services logs read`
2. Cloud SQL status: `gcloud sql instances describe integrityshield-db`
3. Secret Manager: `gcloud secrets versions access latest --secret=SECRET_NAME`
