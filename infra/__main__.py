"""
Apartment Manager — Pulumi AWS Infrastructure

Cost-optimised setup:
  dev  ~$38/mo  — FARGATE_SPOT, no NAT Gateway, single-AZ RDS, no backups
  prod ~$100/mo — FARGATE on-demand, NAT Gateway, Multi-AZ RDS, 7-day backups

Resources:
  - VPC (2 public + 2 private subnets; NAT only on prod)
  - RDS PostgreSQL 16 (private subnet, encrypted)
  - ECR repository
  - ECS Fargate cluster + service
  - ALB (Application Load Balancer)
  - S3 bucket for file uploads
  - CloudWatch log group
  - Secrets Manager (DB password + app secrets)

Usage:
  cd infra
  python -m venv venv && venv\\Scripts\\activate
  pip install -r requirements.txt
  pulumi stack init dev
  pulumi up
"""

import pulumi
import pulumi_aws as aws
from vpc import create_vpc
from ecr import create_ecr
from ecs import create_ecs
from rds import create_rds
from domain import create_domain

config = pulumi.Config()
env = config.get("environment") or "dev"

# ── VPC ──────────────────────────────────────────────────────────────────────
vpc_resources = create_vpc(env)

# ── ECR ──────────────────────────────────────────────────────────────────────
ecr_resources = create_ecr(env)

# ── ECS Security Group placeholder (breaks RDS ↔ ECS circular dependency) ────
ecs_sg_placeholder = aws.ec2.SecurityGroup(
    f"ecs-sg-placeholder-{env}",
    vpc_id=vpc_resources["vpc"].id,
    description="ECS tasks security group (placeholder for RDS reference)",
    tags={"Name": f"apartment-manager-ecs-sg-ref-{env}", "Environment": env},
)

# ── RDS ──────────────────────────────────────────────────────────────────────
rds_resources = create_rds(
    env=env,
    vpc=vpc_resources["vpc"],
    private_subnets=vpc_resources["public_subnets"],  # Use public subnets for public access
    ecs_sg_id=ecs_sg_placeholder.id,
    config=config,
)

# ── ECS ──────────────────────────────────────────────────────────────────────
ecs_resources = create_ecs(
    env=env,
    vpc=vpc_resources["vpc"],
    public_subnets=vpc_resources["public_subnets"],
    private_subnets=vpc_resources["private_subnets"],
    ecs_subnets=vpc_resources["ecs_subnets"],   # public on dev (no NAT), private on prod
    is_prod=vpc_resources["is_prod"],
    ecr_repo_url=ecr_resources["repository_url"],
    database_url=rds_resources["database_url"],
    db_password_secret_arn=rds_resources["db_password_secret_arn"],
    app_secret_arn=rds_resources["app_secret_arn"],
    config=config,
)

# ── Custom Domain + HTTPS ────────────────────────────────────────────────────
create_domain(
    env=env,
    alb=ecs_resources["alb"],
    target_group=ecs_resources["target_group"],
    http_listener=ecs_resources["http_listener"],
    config=config,
)

# ── Outputs ──────────────────────────────────────────────────────────────────
pulumi.export("alb_url", ecs_resources["alb_dns"].apply(lambda dns: f"http://{dns}"))
pulumi.export("api_base_url", ecs_resources["alb_dns"].apply(lambda dns: f"http://{dns}/api/v1"))
pulumi.export("ecr_repository_url", ecr_resources["repository_url"])
pulumi.export("ecs_cluster_name", ecs_resources["cluster"].name)
pulumi.export("ecs_service_name", ecs_resources["service"].name)
pulumi.export("rds_endpoint", rds_resources["instance"].address)
pulumi.export("rds_port", rds_resources["instance"].port)
pulumi.export("db_name", rds_resources["db_name"])
pulumi.export("uploads_bucket", ecs_resources["uploads_bucket"].bucket)
pulumi.export("log_group", ecs_resources["log_group"].name)
pulumi.export("db_password_secret_arn", rds_resources["db_password_secret_arn"])
pulumi.export("app_secret_arn", rds_resources["app_secret_arn"])
