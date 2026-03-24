# Apartment Manager - Deployment Guide

This guide covers deploying the Apartment Manager SaaS application to AWS using Pulumi.

## Prerequisites

- Docker Desktop installed and running
- AWS CLI configured with `manato-admin` profile
- Pulumi CLI installed
- Python 3.12+ with virtual environment

## Infrastructure Overview

- **VPC**: Custom VPC with public and private subnets
- **RDS**: PostgreSQL 16 database (publicly accessible for dev)
- **ECR**: Docker container registry
- **ECS Fargate**: Containerized application
- **ALB**: Application Load Balancer
- **S3**: File uploads storage
- **Secrets Manager**: Database and app secrets

## Deployment Steps

### 1. Build and Push Docker Image to ECR

```powershell
# Navigate to project root
cd c:\Users\roope\apartment_manager

# Login to ECR
aws ecr get-login-password --region us-east-1 --profile manato-admin | docker login --username AWS --password-stdin 943425173571.dkr.ecr.us-east-1.amazonaws.com

# Build Docker image
docker build -t apartment-manager:latest .

# Tag image for ECR
docker tag apartment-manager:latest 943425173571.dkr.ecr.us-east-1.amazonaws.com/apartment-manager-dev:latest

# Push to ECR
docker push 943425173571.dkr.ecr.us-east-1.amazonaws.com/apartment-manager-dev:latest
```

### 2. Deploy Infrastructure with Pulumi

```powershell
# Navigate to infrastructure directory
cd infra

# Preview changes
pulumi preview

# Deploy infrastructure
pulumi up

# Select 'yes' when prompted
```

This will:
- Update ECS task definition with new Docker image
- Force new deployment of ECS service
- Update any infrastructure changes

### 3. Run Database Migrations

After deployment, run migrations from within the ECS container:

```powershell
# Get the running task ARN
$TASK_ARN = (aws ecs list-tasks --cluster apartment-manager-dev --service-name apartment-manager-dev --region us-east-1 --profile manato-admin --query 'taskArns[0]' --output text)

# Execute migration command in container
aws ecs execute-command --cluster apartment-manager-dev --task $TASK_ARN --container apartment-manager-dev --command "/bin/sh -c 'alembic upgrade head'" --interactive --region us-east-1 --profile manato-admin
```

**Note**: If ECS Exec is not enabled, you may need to enable it first or run migrations locally (though local DNS resolution may fail).

### 4. Verify Deployment

```powershell
# Check health endpoint
curl http://apartment-manager-dev-1490205411.us-east-1.elb.amazonaws.com/health

# Access API documentation
curl http://apartment-manager-dev-1490205411.us-east-1.elb.amazonaws.com/api/v1/docs
```

Expected response from health endpoint:
```json
{"status":"ok","version":"1.0.0"}
```

### 5. Monitor Deployment

```powershell
# Check ECS service status
aws ecs describe-services --cluster apartment-manager-dev --services apartment-manager-dev --region us-east-1 --profile manato-admin

# View ECS task logs
aws logs tail /ecs/apartment-manager-dev --follow --region us-east-1 --profile manato-admin

# Check running tasks
aws ecs list-tasks --cluster apartment-manager-dev --service-name apartment-manager-dev --region us-east-1 --profile manato-admin
```

## Quick Redeploy (Code Changes Only)

When you only change application code (no infrastructure changes):

```powershell
# 1. Build and push new image
cd c:\Users\roope\apartment_manager
aws ecr get-login-password --region us-east-1 --profile manato-admin | docker login --username AWS --password-stdin 943425173571.dkr.ecr.us-east-1.amazonaws.com
docker build -t apartment-manager:latest .
docker tag apartment-manager:latest 943425173571.dkr.ecr.us-east-1.amazonaws.com/apartment-manager-dev:latest
docker push 943425173571.dkr.ecr.us-east-1.amazonaws.com/apartment-manager-dev:latest

# 2. Force ECS service update
aws ecs update-service --cluster apartment-manager-dev --service apartment-manager-dev --force-new-deployment --region us-east-1 --profile manato-admin
```

## Infrastructure Outputs

After deployment, Pulumi exports these outputs:

- **alb_url**: `http://apartment-manager-dev-1490205411.us-east-1.elb.amazonaws.com`
- **api_base_url**: `http://apartment-manager-dev-1490205411.us-east-1.elb.amazonaws.com/api/v1`
- **ecr_repository_url**: `943425173571.dkr.ecr.us-east-1.amazonaws.com/apartment-manager-dev`
- **rds_endpoint**: `apartment-manager-public-dev.c8jm4a2as20x.us-east-1.rds.amazonaws.com`
- **uploads_bucket**: `apartment-manager-uploads-dev`

## Database Connection

**Connection Details:**
- **Host**: `apartment-manager-public-dev.c8jm4a2as20x.us-east-1.rds.amazonaws.com`
- **Port**: `5432`
- **Database**: `apartment_manager`
- **Username**: `appadmin`
- **Password**: Stored in AWS Secrets Manager

Retrieve password:
```powershell
aws secretsmanager get-secret-value --secret-id arn:aws:secretsmanager:us-east-1:943425173571:secret:apartment-manager/dev/db-password-HQg22Z --profile manato-admin --query SecretString --output text
```

## Troubleshooting

### ECS Task Fails to Start

Check logs:
```powershell
aws logs tail /ecs/apartment-manager-dev --follow --region us-east-1 --profile manato-admin
```

### Database Connection Issues

Verify RDS is publicly accessible and security group allows connections.

### Image Not Found in ECR

Ensure you've pushed the latest image:
```powershell
aws ecr describe-images --repository-name apartment-manager-dev --region us-east-1 --profile manato-admin
```

### ALB Health Check Failing

Check that the `/health` endpoint is responding:
```powershell
# Get task private IP
aws ecs describe-tasks --cluster apartment-manager-dev --tasks $TASK_ARN --region us-east-1 --profile manato-admin
```

## Cost Estimate

**Development Environment (~$38/month)**:
- RDS PostgreSQL (db.t3.micro): $13/month
- ECS Fargate Spot: $8/month
- Application Load Balancer: $18/month
- Other services: ~$7/month

## Cleanup

To destroy all infrastructure:

```powershell
cd infra
pulumi destroy
```

**Warning**: This will delete all resources including the database. Make sure to backup data first.

## Next Steps

1. Set up custom domain with Route 53
2. Add SSL certificate with ACM
3. Configure CI/CD with GitHub Actions
4. Set up monitoring with CloudWatch
5. Enable auto-scaling for ECS service
6. Configure backup strategy for RDS
