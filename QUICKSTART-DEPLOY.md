# Quick Deployment Guide - For Demo with OpenAI Only

This is a simplified deployment using just OpenAI API key. Add other providers later.

## Step 1: Install gcloud CLI

### macOS (Apple Silicon)
```bash
brew install --cask google-cloud-sdk
source "$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"
gcloud --version
```

## Step 2: Login to Google Cloud
```bash
gcloud auth login
gcloud auth application-default login
```

## Step 3: Create GCP Project
```bash
# Create project (use your own project ID if you want)
gcloud projects create integrityshield-demo --name="IntegrityShield Demo"

# Set as active
gcloud config set project integrityshield-demo

# Link billing account (REQUIRED - use your $300 credit)
# Get billing account ID
gcloud billing accounts list

# Link it (replace BILLING_ACCOUNT_ID)
gcloud billing projects link integrityshield-demo --billing-account=BILLING_ACCOUNT_ID
```

## Step 4: Enable APIs
```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  storage-api.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com

gcloud config set run/region us-central1
```

## Step 5: Create Database
```bash
# Generate secure password
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
echo "Database Password: $DB_PASSWORD"  # SAVE THIS!

# Create instance (takes 5-10 minutes)
gcloud sql instances create integrityshield-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --root-password="$DB_PASSWORD"

# Create database
gcloud sql databases create integrityshield --instance=integrityshield-db

# Get connection name
CONNECTION_NAME=$(gcloud sql instances describe integrityshield-db --format="value(connectionName)")
echo "Connection Name: $CONNECTION_NAME"  # SAVE THIS!
```

## Step 6: Create Storage
```bash
BUCKET_NAME="integrityshield-files-$(date +%s)"
gsutil mb -l us-central1 gs://$BUCKET_NAME
echo "Bucket: $BUCKET_NAME"  # SAVE THIS!
```

## Step 7: Store Secrets (OpenAI Only for Now)
```bash
# Your OpenAI API key
read -p "Enter OpenAI API Key: " OPENAI_KEY
echo -n "$OPENAI_KEY" | gcloud secrets create openai-api-key --data-file=-

# Placeholder secrets (add real keys later)
echo -n "placeholder" | gcloud secrets create anthropic-api-key --data-file=-
echo -n "placeholder" | gcloud secrets create google-ai-key --data-file=-
echo -n "placeholder" | gcloud secrets create grok-api-key --data-file=-
echo -n "placeholder" | gcloud secrets create mistral-api-key --data-file=-

# Generate app secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))" | \
  gcloud secrets create app-secret-key --data-file=-

# Database URL
DATABASE_URL="postgresql://postgres:$DB_PASSWORD@/integrityshield?host=/cloudsql/$CONNECTION_NAME"
echo -n "$DATABASE_URL" | gcloud secrets create database-url --data-file=-
```

## Step 8: Build and Deploy
```bash
cd backend

# Build (takes 5-10 minutes)
gcloud builds submit --tag gcr.io/integrityshield-demo/integrityshield-backend

# Deploy (takes 2-3 minutes)
gcloud run deploy integrityshield-backend \
  --image gcr.io/integrityshield-demo/integrityshield-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 3 \
  --min-instances 0 \
  --add-cloudsql-instances $CONNECTION_NAME \
  --set-secrets="OPENAI_API_KEY=openai-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,GOOGLE_AI_KEY=google-ai-key:latest,GROK_API_KEY=grok-api-key:latest,MISTRAL_API_KEY=mistral-api-key:latest,INTEGRITYSHIELD_SECRET_KEY=app-secret-key:latest,INTEGRITYSHIELD_DATABASE_URL=database-url:latest" \
  --set-env-vars="INTEGRITYSHIELD_ENV=production,INTEGRITYSHIELD_FILE_STORAGE_BUCKET=$BUCKET_NAME,INTEGRITYSHIELD_PIPELINE_ROOT=/tmp/pipeline_runs,INTEGRITYSHIELD_ENABLE_DEV_TOOLS=false,INTEGRITYSHIELD_AUTO_APPLY_MIGRATIONS=true,INTEGRITYSHIELD_LOG_LEVEL=INFO"

# Get URL
SERVICE_URL=$(gcloud run services describe integrityshield-backend --region us-central1 --format="value(status.url)")
echo ""
echo "✅ Deployment Complete!"
echo "Backend URL: $SERVICE_URL"
echo ""
echo "Test: curl $SERVICE_URL/api/health"
```

## Step 9: Update Frontend
In your frontend repo, update the API endpoint:
```javascript
const API_BASE_URL = 'YOUR_SERVICE_URL_HERE'
```

Commit and push to update GitHub Pages.

## Adding More API Keys Later
```bash
# Update a secret
echo -n "YOUR_NEW_ANTHROPIC_KEY" | gcloud secrets versions add anthropic-api-key --data-file=-

# Redeploy to pick up new secret
gcloud run services update integrityshield-backend --region us-central1
```

## Troubleshooting
```bash
# View logs
gcloud run services logs read integrityshield-backend --region us-central1

# Check database
gcloud sql instances describe integrityshield-db

# Check secrets
gcloud secrets versions access latest --secret=openai-api-key
```

## Cost Monitoring
```bash
# Check billing
gcloud billing projects describe integrityshield-demo
```
