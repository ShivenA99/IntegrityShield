#!/usr/bin/env bash
set -euo pipefail

# FairTestAI - Automated GCP Deployment Script
# This script automates the deployment of FairTestAI to Google Cloud Run

echo "🚀 FairTestAI GCP Deployment Script"
echo "===================================="
echo ""

# Check prerequisites
command -v gcloud >/dev/null 2>&1 || { echo "❌ gcloud CLI not found. Install from https://cloud.google.com/sdk/docs/install"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "⚠️  Docker not found. Continuing without local build test..."; }

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-fairtestai-demo}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="fairtestai-backend"
DB_INSTANCE="fairtestai-db"
STORAGE_BUCKET="fairtestai-files-$(date +%s)"

echo "📋 Configuration:"
echo "   Project ID: $PROJECT_ID"
echo "   Region: $REGION"
echo "   Service Name: $SERVICE_NAME"
echo ""

# Prompt for API keys
read -p "Enter OpenAI API Key: " OPENAI_KEY
read -p "Enter Anthropic API Key: " ANTHROPIC_KEY
read -p "Enter Google AI Key: " GOOGLE_AI_KEY
read -p "Enter Grok API Key (optional, press Enter to skip): " GROK_KEY
read -p "Enter Mistral API Key: " MISTRAL_KEY
read -sp "Enter Database Password: " DB_PASSWORD
echo ""

# Generate app secret
APP_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

echo ""
echo "Step 1/7: Setting up GCP project..."
gcloud config set project $PROJECT_ID 2>/dev/null || {
    echo "   Creating project $PROJECT_ID..."
    gcloud projects create $PROJECT_ID --name="FairTestAI Demo"
    gcloud config set project $PROJECT_ID
}

echo "Step 2/7: Enabling required APIs..."
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
    storage-api.googleapis.com secretmanager.googleapis.com \
    cloudbuild.googleapis.com --quiet

gcloud config set run/region $REGION

echo "Step 3/7: Creating Cloud SQL database..."
if gcloud sql instances describe $DB_INSTANCE --quiet 2>/dev/null; then
    echo "   Database instance already exists, skipping..."
else
    gcloud sql instances create $DB_INSTANCE \
        --database-version=POSTGRES_15 \
        --tier=db-f1-micro \
        --region=$REGION \
        --root-password="$DB_PASSWORD" \
        --quiet

    gcloud sql databases create fairtestai --instance=$DB_INSTANCE --quiet
fi

# Get connection name
CONNECTION_NAME=$(gcloud sql instances describe $DB_INSTANCE --format="value(connectionName)")
echo "   Connection name: $CONNECTION_NAME"

# Build database URL
DATABASE_URL="postgresql://postgres:$DB_PASSWORD@/fairtestai?host=/cloudsql/$CONNECTION_NAME"

echo "Step 4/7: Creating storage bucket..."
gsutil mb -l $REGION gs://$STORAGE_BUCKET 2>/dev/null || echo "   Bucket already exists or created"

echo "Step 5/7: Storing secrets..."
for secret in openai-api-key anthropic-api-key google-ai-key grok-api-key mistral-api-key app-secret-key database-url; do
    gcloud secrets delete $secret --quiet 2>/dev/null || true
done

echo -n "$OPENAI_KEY" | gcloud secrets create openai-api-key --data-file=- --quiet
echo -n "$ANTHROPIC_KEY" | gcloud secrets create anthropic-api-key --data-file=- --quiet
echo -n "$GOOGLE_AI_KEY" | gcloud secrets create google-ai-key --data-file=- --quiet
echo -n "${GROK_KEY:-skip}" | gcloud secrets create grok-api-key --data-file=- --quiet
echo -n "$MISTRAL_KEY" | gcloud secrets create mistral-api-key --data-file=- --quiet
echo -n "$APP_SECRET" | gcloud secrets create app-secret-key --data-file=- --quiet
echo -n "$DATABASE_URL" | gcloud secrets create database-url --data-file=- --quiet

echo "Step 6/7: Building container image..."
cd backend
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME --quiet

echo "Step 7/7: Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --max-instances 5 \
    --min-instances 0 \
    --add-cloudsql-instances $CONNECTION_NAME \
    --set-secrets="OPENAI_API_KEY=openai-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,GOOGLE_AI_KEY=google-ai-key:latest,GROK_API_KEY=grok-api-key:latest,MISTRAL_API_KEY=mistral-api-key:latest,FAIRTESTAI_SECRET_KEY=app-secret-key:latest,FAIRTESTAI_DATABASE_URL=database-url:latest" \
    --set-env-vars="FAIRTESTAI_ENV=production,FAIRTESTAI_FILE_STORAGE_BUCKET=$STORAGE_BUCKET,FAIRTESTAI_PIPELINE_ROOT=/tmp/pipeline_runs,FAIRTESTAI_ENABLE_DEV_TOOLS=false,FAIRTESTAI_AUTO_APPLY_MIGRATIONS=true,FAIRTESTAI_LOG_LEVEL=INFO" \
    --quiet

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format="value(status.url)")

echo ""
echo "✅ Deployment Complete!"
echo "======================="
echo ""
echo "Backend URL: $SERVICE_URL"
echo "Storage Bucket: gs://$STORAGE_BUCKET"
echo "Database: $CONNECTION_NAME"
echo ""
echo "Next steps:"
echo "1. Test the deployment: curl $SERVICE_URL/api/health"
echo "2. Update your frontend API endpoint to: $SERVICE_URL"
echo "3. Commit and push frontend changes to update GitHub Pages"
echo ""
echo "View logs: gcloud run services logs read $SERVICE_NAME --region $REGION"
echo "Monitor: gcloud run services describe $SERVICE_NAME --region $REGION"
echo ""
echo "Estimated monthly cost: ~$7-10 for demo period"
echo "To cleanup: See DEPLOYMENT.md for cleanup commands"
