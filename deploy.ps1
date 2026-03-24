# Apartment Manager Deployment Script
# This script runs migrations and deploys the application to AWS ECS

param(
    [string]$Profile = "manato-admin",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Apartment Manager Deployment ===" -ForegroundColor Cyan
Write-Host ""

# Configuration from Pulumi outputs
$ECR_REPO = "943425173571.dkr.ecr.us-east-1.amazonaws.com/apartment-manager-dev"
$ECS_CLUSTER = "apartment-manager-dev"
$ECS_SERVICE = "apartment-manager-dev"

# Step 1: Login to ECR
Write-Host "Step 1: Logging into ECR..." -ForegroundColor Yellow
$ECR_LOGIN = aws ecr get-login-password --region $Region --profile $Profile
$ECR_LOGIN | docker login --username AWS --password-stdin 943425173571.dkr.ecr.$Region.amazonaws.com
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ ECR login failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ ECR login successful" -ForegroundColor Green
Write-Host ""

# Step 2: Build Docker Image
Write-Host "Step 2: Building Docker image..." -ForegroundColor Yellow
$IMAGE_TAG = "latest"
docker build -t apartment-manager:$IMAGE_TAG .
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Docker build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Docker image built successfully" -ForegroundColor Green
Write-Host ""

# Step 3: Tag and Push to ECR
Write-Host "Step 3: Pushing image to ECR..." -ForegroundColor Yellow
docker tag apartment-manager:$IMAGE_TAG ${ECR_REPO}:$IMAGE_TAG
docker push ${ECR_REPO}:$IMAGE_TAG
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Docker push failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Image pushed to ECR successfully" -ForegroundColor Green
Write-Host ""

# Step 4: Update ECS Service
Write-Host "Step 4: Updating ECS service..." -ForegroundColor Yellow
aws ecs update-service `
    --cluster $ECS_CLUSTER `
    --service $ECS_SERVICE `
    --force-new-deployment `
    --region $Region `
    --profile $Profile `
    --no-cli-pager
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ ECS service update failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ ECS service update initiated" -ForegroundColor Green
Write-Host ""

# Step 5: Wait for deployment
Write-Host "Step 5: Waiting for deployment to complete..." -ForegroundColor Yellow
Write-Host "This may take 2-3 minutes..."
aws ecs wait services-stable `
    --cluster $ECS_CLUSTER `
    --services $ECS_SERVICE `
    --region $Region `
    --profile $Profile

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Deployment completed successfully!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Deployment may still be in progress. Check AWS Console for status." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Deployment Summary ===" -ForegroundColor Cyan
Write-Host "API URL: http://apartment-manager-dev-1490205411.us-east-1.elb.amazonaws.com/api/v1"
Write-Host "Health Check: http://apartment-manager-dev-1490205411.us-east-1.elb.amazonaws.com/api/v1/health"
Write-Host ""
Write-Host "To check service status:"
Write-Host "  aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE --profile $Profile"
Write-Host ""
