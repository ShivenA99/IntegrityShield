# GCP Cloud Run Deployment Guide (<$20/Month)

**IntegrityShield Backend Deployment for EACL Demo**

This guide walks you through deploying the IntegrityShield backend to Google Cloud Platform (GCP) for less than $20/month.

---

## 💰 Cost Breakdown

| Service | Configuration | Monthly Cost |
|---------|---------------|--------------|
| **Cloud Run** | 8GB RAM, scale-to-zero, ~10 hours active | $5-8 |
| **Cloud SQL** | db-f1-micro (FREE tier) | $0 |
| **Cloud Storage** | 5GB, minimal operations | $0.50 |
| **Secret Manager** | 7 secrets | $0.30 |
| **Network Egress** | ~10GB | $1-2 |
| **Total** | | **$7-11/month** |

**With $300 free credit**: Covers 3+ months of deployment!

---

## ✅ Prerequisites

- ✅ **GCP Account**: Personal Gmail with $300 free trial activated
- ✅ **Project Created**: `integrityshield` (or your project name)
- ✅ **Budget Alert**: Set to $20/month
- ✅ **gcloud CLI**: Installed and authenticated

### Install gcloud CLI (if needed)

```bash
# macOS
brew install --cask google-cloud-sdk

# Or download from: https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth login
# Select your personal Gmail (shiven.999a@gmail.com)

# Set project
gcloud config set project integrityshield
```

---

## 📋 Deployment Steps

### Step 1: Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

**Expected output**: "Operation completed successfully" for each API

---

### Step 2: Create Cloud SQL Database (FREE Tier)

#### 2.1 Create Instance

```bash
gcloud sql instances create integrityshield-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --storage-type=HDD \
  --storage-size=10GB \
  --backup-start-time=03:00 \
  --maintenance-window-day=SUN \
  --maintenance-window-hour=4 \
  --availability-type=zonal \
  --assign-ip
```

**Wait time**: 5-10 minutes for instance creation

**Cost**: $0/month (FREE tier - 0.6GB RAM, shared CPU, 10GB storage)

#### 2.2 Create Database and User

```bash
# Create database
gcloud sql databases create fairtestai --instance=integrityshield-db

# Generate strong password
DB_PASSWORD=$(openssl rand -base64 32)
echo "Database Password: $DB_PASSWORD"
# IMPORTANT: Save this password securely!

# Create user
gcloud sql users create fairtestai_user \
  --instance=integrityshield-db \
  --password="$DB_PASSWORD"
```

#### 2.3 Get Connection Details

```bash
# Get connection name (format: project:region:instance)
CLOUD_SQL_CONNECTION_NAME=$(gcloud sql instances describe integrityshield-db \
  --format="value(connectionName)")

echo "Cloud SQL Connection Name: $CLOUD_SQL_CONNECTION_NAME"
# Example: integrityshield:us-central1:integrityshield-db
```

---

### Step 3: Create Cloud Storage Bucket

```bash
# Create bucket
gcloud storage buckets create gs://integrityshield-pipeline-runs \
  --location=us-central1 \
  --uniform-bucket-level-access \
  --public-access-prevention

# Set lifecycle policy (auto-delete files after 30 days to save costs)
cat > lifecycle.json <<'EOF'
{
  "lifecycle": {
    "rule": [{
      "action": {"type": "Delete"},
      "condition": {"age": 30}
    }]
  }
}
EOF

gcloud storage buckets update gs://integrityshield-pipeline-runs \
  --lifecycle-file=lifecycle.json

rm lifecycle.json
```

**Cost**: ~$0.50/month for 5GB storage

---

### Step 4: Configure Secret Manager

```bash
# Database password
echo -n "$DB_PASSWORD" | gcloud secrets create fairtestai-db-password \
  --data-file=- --replication-policy=automatic

# Generate Flask secret key
FLASK_SECRET=$(openssl rand -hex 32)
echo -n "$FLASK_SECRET" | gcloud secrets create fairtestai-secret-key \
  --data-file=- --replication-policy=automatic

# API Keys (get from your .env file)
# IMPORTANT: Replace <YOUR_KEY> with actual values
echo -n "<YOUR_OPENAI_KEY>" | gcloud secrets create openai-api-key \
  --data-file=- --replication-policy=automatic

echo -n "<YOUR_ANTHROPIC_KEY>" | gcloud secrets create anthropic-api-key \
  --data-file=- --replication-policy=automatic

echo -n "<YOUR_GOOGLE_AI_KEY>" | gcloud secrets create google-ai-key \
  --data-file=- --replication-policy=automatic

echo -n "<YOUR_MISTRAL_KEY>" | gcloud secrets create mistral-api-key \
  --data-file=- --replication-policy=automatic

echo -n "<YOUR_GROK_KEY>" | gcloud secrets create grok-api-key \
  --data-file=- --replication-policy=automatic
```

**To get your API keys**:
```bash
# View your current .env file
cat backend/.env | grep API_KEY
```

**Cost**: ~$0.30/month for 7 secrets

---

### Step 5: Create Service Account

```bash
# Create service account
gcloud iam service-accounts create integrityshield-backend \
  --display-name="IntegrityShield Backend Service Account"

PROJECT_ID=$(gcloud config get-value project)
SA_EMAIL="integrityshield-backend@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant Cloud SQL Client role (for Cloud SQL Proxy)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudsql.client"

# Grant Storage Object Admin role
gcloud storage buckets add-iam-policy-binding gs://integrityshield-pipeline-runs \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin"

# Grant Secret Manager access
for secret in fairtestai-db-password fairtestai-secret-key openai-api-key anthropic-api-key google-ai-key mistral-api-key grok-api-key; do
  gcloud secrets add-iam-policy-binding $secret \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor"
done
```

---

### Step 6: Build and Push Docker Image

```bash
# Navigate to project root
cd /Users/shivenagarwal/Downloads/fairtestai_-llm-assessment-vulnerability-simulator-main

# Create Artifact Registry repository
gcloud artifacts repositories create integrityshield \
  --repository-format=docker \
  --location=us-central1 \
  --description="IntegrityShield Docker images"

# Configure Docker auth
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build image (this takes 5-10 minutes)
docker build \
  -t us-central1-docker.pkg.dev/${PROJECT_ID}/integrityshield/backend:v1.0.0 \
  -t us-central1-docker.pkg.dev/${PROJECT_ID}/integrityshield/backend:latest \
  -f backend/Dockerfile \
  backend/

# Push to Artifact Registry
docker push us-central1-docker.pkg.dev/${PROJECT_ID}/integrityshield/backend:v1.0.0
docker push us-central1-docker.pkg.dev/${PROJECT_ID}/integrityshield/backend:latest
```

---

### Step 7: Deploy to Cloud Run

```bash
# Deploy with all environment variables and secrets
gcloud run deploy integrityshield-backend \
  --image us-central1-docker.pkg.dev/${PROJECT_ID}/integrityshield/backend:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 8Gi \
  --cpu 2 \
  --timeout 300 \
  --concurrency 80 \
  --min-instances 0 \
  --max-instances 5 \
  --service-account ${SA_EMAIL} \
  --set-env-vars "\
FAIRTESTAI_ENV=production,\
FAIRTESTAI_DATABASE_URL=postgresql://fairtestai_user:PASSWORD_PLACEHOLDER@localhost:5432/fairtestai,\
FAIRTESTAI_FILE_STORAGE_BUCKET=integrityshield-pipeline-runs,\
FAIRTESTAI_PIPELINE_ROOT=/tmp/pipeline_runs,\
FAIRTESTAI_CORS_ORIGINS=https://shivenagarwal.github.io,http://localhost:5173,\
PORT=8080,\
FAIRTESTAI_LOG_LEVEL=INFO,\
FAIRTESTAI_AUTO_APPLY_MIGRATIONS=true,\
CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_CONNECTION_NAME}" \
  --set-secrets "\
FAIRTESTAI_DATABASE_PASSWORD=fairtestai-db-password:latest,\
FAIRTESTAI_SECRET_KEY=fairtestai-secret-key:latest,\
OPENAI_API_KEY=openai-api-key:latest,\
ANTHROPIC_API_KEY=anthropic-api-key:latest,\
GOOGLE_AI_KEY=google-ai-key:latest,\
MISTRAL_API_KEY=mistral-api-key:latest,\
GROK_API_KEY=grok-api-key:latest"
```

**Wait time**: 2-5 minutes for deployment

---

### Step 8: Get Service URL and Test

```bash
# Get Cloud Run URL
SERVICE_URL=$(gcloud run services describe integrityshield-backend \
  --region us-central1 \
  --format="value(status.url)")

echo "🎉 Backend deployed at: $SERVICE_URL"

# Test health endpoint
curl $SERVICE_URL/api/developer/system/health | jq
```

**Expected output**:
```json
{
  "database": true,
  "ai_clients": {
    "openai": true,
    "anthropic": true,
    "google": true
  },
  "storage": true,
  "status": "healthy"
}
```

---

## 🧪 Testing with Local Frontend

### Test Phase 1: Local Frontend → GCP Backend

```bash
cd frontend

# Point local dev to Cloud Run backend
echo "VITE_API_BASE_URL=$SERVICE_URL/api" > .env.local

# Install dependencies (if needed)
npm install

# Start dev server
npm run dev
```

**Open**: http://localhost:5173

**Test scenarios**:
1. ✅ Register new user
2. ✅ Login
3. ✅ Configure API keys in settings
4. ✅ Upload PDF (try 50MB+ file to test memory)
5. ✅ Create pipeline run (Detection or Prevention mode)
6. ✅ Monitor progress via WebSocket
7. ✅ Download enhanced PDFs

### Test Phase 2: Check Memory Usage

**GCP Console** → Cloud Run → integrityshield-backend → Metrics

Watch:
- **Memory utilization**: Should stay under 60-70% of 8GB during PDF processing
- **Request count**: Should show activity during pipeline runs
- **Instance count**: Should scale to 0 when idle (after 15 minutes)

---

## 🚀 Deploy Production Frontend

Once testing is complete, update your GitHub Pages frontend:

```bash
cd frontend

# Extract Cloud Run domain
BACKEND_DOMAIN=$(echo $SERVICE_URL | sed 's|https://||')

# Build frontend with GCP backend
VITE_API_BASE_URL=https://${BACKEND_DOMAIN}/api GITHUB_PAGES=true npm run build

# Commit and push
git add docs/
git commit -m "Deploy frontend with GCP Cloud Run backend"
git push origin eacl-demo-gcp

# Merge to main (after testing)
git checkout main
git merge eacl-demo-gcp
git push origin main
```

**Verify**: https://shivenagarwal.github.io/IntegrityShield/

---

## 📊 Monitor Costs

### View Current Spend

```bash
# In GCP Console: Billing → Overview
# Or via command line:
gcloud billing accounts list
```

**Check daily**:
- **Free trial credit remaining**: Should show $300 minus usage
- **Current month estimate**: Should be <$10-15

### Set Up Additional Alerts

```bash
# Alert at $15 (75% of budget)
gcloud billing budgets create \
  --billing-account=$(gcloud billing accounts list --format="value(name)" | head -1) \
  --display-name="IntegrityShield $15 Alert" \
  --budget-amount=20USD \
  --threshold-rule=percent=75
```

---

## 🔧 Maintenance

### Update Backend Code

```bash
# Make code changes
git add backend/
git commit -m "Update backend feature"

# Rebuild and deploy
docker build -t us-central1-docker.pkg.dev/${PROJECT_ID}/integrityshield/backend:latest -f backend/Dockerfile backend/
docker push us-central1-docker.pkg.dev/${PROJECT_ID}/integrityshield/backend:latest

# Cloud Run will auto-deploy new image on next request (or force it)
gcloud run services update integrityshield-backend \
  --region us-central1 \
  --image us-central1-docker.pkg.dev/${PROJECT_ID}/integrityshield/backend:latest
```

### View Logs

```bash
# Real-time logs
gcloud run services logs tail integrityshield-backend --region us-central1

# Filter errors only
gcloud run services logs read integrityshield-backend \
  --region us-central1 \
  --log-filter='severity>=ERROR'

# Filter pipeline logs
gcloud run services logs read integrityshield-backend \
  --region us-central1 \
  --log-filter='textPayload:"pipeline_run"'
```

### Pause Database (When Not Using)

```bash
# Stop Cloud SQL (saves costs)
gcloud sql instances patch integrityshield-db --activation-policy=NEVER

# Start Cloud SQL (when needed)
gcloud sql instances patch integrityshield-db --activation-policy=ALWAYS
```

---

## 🎯 Cost Optimization Tips

### For Demo/Testing Period

1. **Pause database overnight**:
   ```bash
   gcloud sql instances patch integrityshield-db --activation-policy=NEVER
   ```

2. **Use scale-to-zero** (already configured):
   - Cloud Run scales to 0 instances after 15 minutes of inactivity
   - Only pay for active request time

3. **Limit pipeline runs**:
   - For EACL demo: ~20-30 runs total
   - Each run costs ~$0.20-0.40

### Expected Usage for EACL Demo (2-3 Months)

| Activity | Frequency | Cost |
|----------|-----------|------|
| Pipeline runs (testing) | 10 runs | ~$3 |
| Pipeline runs (demo) | 5 runs | ~$2 |
| Idle time | 90% of month | $0 |
| Database (always-on) | 1 month | $0 |
| Storage | 5GB | $0.50 |
| **Total per month** | | **~$6-8** |

**With $300 credit**: Covers 35-50 months!

---

## 🆘 Troubleshooting

### Issue: "Cloud SQL connection failed"

**Solution**: Check Cloud SQL Proxy is running in container
```bash
# View container logs
gcloud run services logs read integrityshield-backend --region us-central1 | grep "cloud-sql-proxy"
```

### Issue: "Module 'google.cloud.storage' not found"

**Solution**: Rebuild Docker image (google-cloud-storage added to requirements.txt)

### Issue: "Memory limit exceeded"

**Solution**: Check Cloud Run metrics, may need to optimize PDF processing

### Issue: "Permission denied for Cloud Storage"

**Solution**: Verify service account has Storage Object Admin role
```bash
gcloud storage buckets add-iam-policy-binding gs://integrityshield-pipeline-runs \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin"
```

---

## 🔒 Security Notes

- ✅ All API keys stored in Secret Manager (encrypted at rest)
- ✅ Cloud SQL uses IAM authentication via Cloud SQL Proxy
- ✅ Cloud Run service account has minimal required permissions
- ✅ CORS configured for specific origins only
- ✅ No VPC Connector needed (Cloud SQL Proxy connects securely)

---

## 📞 Support

**Issues or questions?**
- Check logs: `gcloud run services logs tail integrityshield-backend --region us-central1`
- Check GCP Console: https://console.cloud.google.com
- Verify budget: Billing → Overview

---

## ✅ Deployment Checklist

Before marking as complete, verify:

- [ ] Cloud SQL instance created and accessible
- [ ] Cloud Storage bucket created with lifecycle policy
- [ ] All secrets created in Secret Manager
- [ ] Service account has all required permissions
- [ ] Docker image built and pushed successfully
- [ ] Cloud Run service deployed successfully
- [ ] Health check passes (`/api/developer/system/health`)
- [ ] Local frontend connects successfully
- [ ] Can register user and login
- [ ] Can upload PDF and create pipeline run
- [ ] Pipeline run completes without errors
- [ ] Enhanced PDFs downloadable
- [ ] Memory usage under 70% of 8GB
- [ ] Budget alert configured at $20/month
- [ ] Current costs <$15/month

---

**🎉 Congratulations!** Your IntegrityShield backend is now deployed on GCP for <$20/month!
