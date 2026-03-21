"""ECS Fargate cluster, task definition, service, ALB, and security groups.

Cost strategy:
  dev  — FARGATE_SPOT (up to 70% cheaper), ECS in public subnets (no NAT cost),
          256 vCPU / 512 MB, no container insights, 7-day log retention.
  prod — FARGATE on-demand, ECS in private subnets, container insights on,
          30-day log retention, auto-scaling.
"""
import json
import pulumi
import pulumi_aws as aws


def create_ecs(
    env: str,
    vpc,
    public_subnets: list,
    private_subnets: list,
    ecs_subnets: list,          # public for dev, private for prod
    is_prod: bool,
    ecr_repo_url: pulumi.Output,
    database_url: pulumi.Output,
    db_password_secret_arn: pulumi.Output,
    app_secret_arn: pulumi.Output,
    config: pulumi.Config,
):
    app_port = int(config.get("app_port") or "8000")
    cpu = config.get("ecs_cpu") or ("256" if not is_prod else "512")
    memory = config.get("ecs_memory") or ("512" if not is_prod else "1024")
    desired_count = int(config.get("ecs_desired_count") or "1")

    # ── Security Groups ─────────────────────────────────────────────────────

    # ALB Security Group — public internet traffic
    alb_sg = aws.ec2.SecurityGroup(
        f"alb-sg-{env}",
        vpc_id=vpc.id,
        description="ALB: allow HTTP/HTTPS from internet",
        ingress=[
            aws.ec2.SecurityGroupIngressArgs(
                protocol="tcp", from_port=80, to_port=80,
                cidr_blocks=["0.0.0.0/0"], description="HTTP",
            ),
            aws.ec2.SecurityGroupIngressArgs(
                protocol="tcp", from_port=443, to_port=443,
                cidr_blocks=["0.0.0.0/0"], description="HTTPS",
            ),
        ],
        egress=[
            aws.ec2.SecurityGroupEgressArgs(
                protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"],
            )
        ],
        tags={"Name": f"apartment-manager-alb-sg-{env}", "Environment": env},
    )

    # ECS Task Security Group — only accept from ALB
    ecs_sg = aws.ec2.SecurityGroup(
        f"ecs-sg-{env}",
        vpc_id=vpc.id,
        description="ECS tasks: accept from ALB only",
        ingress=[
            aws.ec2.SecurityGroupIngressArgs(
                protocol="tcp", from_port=app_port, to_port=app_port,
                security_groups=[alb_sg.id], description="From ALB",
            )
        ],
        egress=[
            aws.ec2.SecurityGroupEgressArgs(
                protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"],
            )
        ],
        tags={"Name": f"apartment-manager-ecs-sg-{env}", "Environment": env},
    )

    # ── IAM Roles ────────────────────────────────────────────────────────────

    assume_role_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ecs-tasks.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    })

    # Task Execution Role (pull image, write logs, read secrets)
    execution_role = aws.iam.Role(
        f"ecs-execution-role-{env}",
        name=f"apartment-manager-ecs-execution-{env}",
        assume_role_policy=assume_role_policy,
        tags={"Environment": env},
    )

    aws.iam.RolePolicyAttachment(
        f"ecs-execution-policy-{env}",
        role=execution_role.name,
        policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
    )

    # Allow reading secrets
    secrets_policy = aws.iam.RolePolicy(
        f"ecs-secrets-policy-{env}",
        role=execution_role.id,
        policy=pulumi.Output.all(db_password_secret_arn, app_secret_arn).apply(
            lambda arns: json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "secretsmanager:GetSecretValue",
                        "secretsmanager:DescribeSecret",
                    ],
                    "Resource": arns,
                }],
            })
        ),
    )

    # Task Role (app-level AWS permissions — S3 for uploads, etc.)
    task_role = aws.iam.Role(
        f"ecs-task-role-{env}",
        name=f"apartment-manager-ecs-task-{env}",
        assume_role_policy=assume_role_policy,
        tags={"Environment": env},
    )

    task_s3_policy = aws.iam.RolePolicy(
        f"ecs-task-s3-policy-{env}",
        role=task_role.id,
        policy=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
                    "Resource": f"arn:aws:s3:::apartment-manager-uploads-{env}/*",
                },
                {
                    "Effect": "Allow",
                    "Action": ["s3:ListBucket"],
                    "Resource": f"arn:aws:s3:::apartment-manager-uploads-{env}",
                },
            ],
        }),
    )

    # ── S3 Bucket for uploads ────────────────────────────────────────────────

    uploads_bucket = aws.s3.BucketV2(
        f"uploads-bucket-{env}",
        bucket=f"apartment-manager-uploads-{env}",
        tags={"Environment": env},
    )

    aws.s3.BucketVersioningV2(
        f"uploads-versioning-{env}",
        bucket=uploads_bucket.id,
        versioning_configuration=aws.s3.BucketVersioningV2VersioningConfigurationArgs(
            status="Enabled",
        ),
    )

    aws.s3.BucketServerSideEncryptionConfigurationV2(
        f"uploads-encryption-{env}",
        bucket=uploads_bucket.id,
        rules=[
            aws.s3.BucketServerSideEncryptionConfigurationV2RuleArgs(
                apply_server_side_encryption_by_default=aws.s3.BucketServerSideEncryptionConfigurationV2RuleApplyServerSideEncryptionByDefaultArgs(
                    sse_algorithm="AES256",
                ),
            )
        ],
    )

    # ── CloudWatch Log Group ─────────────────────────────────────────────────

    # dev: 7-day retention (cheaper), prod: 30-day
    log_group = aws.cloudwatch.LogGroup(
        f"ecs-logs-{env}",
        name=f"/ecs/apartment-manager-{env}",
        retention_in_days=7 if not is_prod else 30,
        tags={"Environment": env},
    )

    # ── ECS Cluster ──────────────────────────────────────────────────────────

    cluster = aws.ecs.Cluster(
        f"cluster-{env}",
        name=f"apartment-manager-{env}",
        settings=[
            # Container Insights costs ~$0.35/task/month — disable on dev
            aws.ecs.ClusterSettingArgs(
                name="containerInsights",
                value="enabled" if is_prod else "disabled",
            ),
        ],
        tags={"Environment": env},
    )

    aws.ecs.ClusterCapacityProviders(
        f"cluster-capacity-{env}",
        cluster_name=cluster.name,
        capacity_providers=["FARGATE", "FARGATE_SPOT"],
        default_capacity_provider_strategies=[
            aws.ecs.ClusterCapacityProvidersDefaultCapacityProviderStrategyArgs(
                # dev: FARGATE_SPOT = up to 70% cheaper (can be interrupted, fine for dev)
                # prod: FARGATE on-demand (reliable)
                capacity_provider="FARGATE" if is_prod else "FARGATE_SPOT",
                weight=1,
                base=1,
            )
        ],
    )

    # ── Task Definition ──────────────────────────────────────────────────────

    task_definition = aws.ecs.TaskDefinition(
        f"task-def-{env}",
        family=f"apartment-manager-{env}",
        cpu=cpu,
        memory=memory,
        network_mode="awsvpc",
        requires_compatibilities=["FARGATE"],
        execution_role_arn=execution_role.arn,
        task_role_arn=task_role.arn,
        container_definitions=pulumi.Output.all(
            ecr_repo_url,
            log_group.name,
            database_url,
            db_password_secret_arn,
            app_secret_arn,
            uploads_bucket.bucket,
        ).apply(
            lambda args: json.dumps([
                {
                    "name": "apartment-manager",
                    "image": f"{args[0]}:latest",
                    "portMappings": [
                        {"containerPort": app_port, "protocol": "tcp"}
                    ],
                    "essential": True,
                    "environment": [
                        {"name": "UPLOAD_DIR", "value": "/tmp/uploads"},
                        {"name": "ALGORITHM", "value": "HS256"},
                        {"name": "ACCESS_TOKEN_EXPIRE_MINUTES", "value": "60"},
                        {"name": "REFRESH_TOKEN_EXPIRE_DAYS", "value": "7"},
                        {"name": "CORS_ORIGINS", "value": '["*"]'},
                        {"name": "S3_BUCKET", "value": args[5]},
                        {"name": "AWS_DEFAULT_REGION", "value": "us-east-1"},
                    ],
                    "secrets": [
                        {
                            "name": "DATABASE_URL",
                            "valueFrom": args[2] if isinstance(args[2], str) and args[2].startswith("arn:") else args[3],
                        },
                    ],
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": args[1],
                            "awslogs-region": "us-east-1",
                            "awslogs-stream-prefix": "ecs",
                        },
                    },
                    "healthCheck": {
                        "command": ["CMD-SHELL", f"curl -f http://localhost:{app_port}/health || exit 1"],
                        "interval": 30,
                        "timeout": 5,
                        "retries": 3,
                        "startPeriod": 60,
                    },
                }
            ])
        ),
        tags={"Environment": env},
    )

    # ── Application Load Balancer ────────────────────────────────────────────

    alb = aws.lb.LoadBalancer(
        f"alb-{env}",
        name=f"apartment-manager-{env}",
        internal=False,
        load_balancer_type="application",
        security_groups=[alb_sg.id],
        subnets=[s.id for s in public_subnets],
        enable_deletion_protection=env == "prod",
        tags={"Name": f"apartment-manager-alb-{env}", "Environment": env},
    )

    target_group = aws.lb.TargetGroup(
        f"tg-{env}",
        name=f"apartment-manager-{env}",
        port=app_port,
        protocol="HTTP",
        vpc_id=vpc.id,
        target_type="ip",
        health_check=aws.lb.TargetGroupHealthCheckArgs(
            enabled=True,
            path="/health",
            port="traffic-port",
            protocol="HTTP",
            healthy_threshold=2,
            unhealthy_threshold=3,
            timeout=5,
            interval=30,
            matcher="200",
        ),
        deregistration_delay=30,
        tags={"Environment": env},
    )

    # HTTP listener (redirects to HTTPS in prod, forwards in dev)
    http_listener = aws.lb.Listener(
        f"http-listener-{env}",
        load_balancer_arn=alb.arn,
        port=80,
        protocol="HTTP",
        default_actions=[
            aws.lb.ListenerDefaultActionArgs(
                type="forward",
                target_group_arn=target_group.arn,
            )
        ],
    )

    # ── ECS Service ──────────────────────────────────────────────────────────

    service = aws.ecs.Service(
        f"service-{env}",
        name=f"apartment-manager-{env}",
        cluster=cluster.arn,
        task_definition=task_definition.arn,
        desired_count=desired_count,
        # dev: no launch_type so FARGATE_SPOT capacity provider is used
        launch_type="FARGATE" if is_prod else None,
        capacity_provider_strategies=[] if is_prod else [
            aws.ecs.ServiceCapacityProviderStrategyArgs(
                capacity_provider="FARGATE_SPOT",
                weight=1,
                base=1,
            )
        ],
        network_configuration=aws.ecs.ServiceNetworkConfigurationArgs(
            subnets=[s.id for s in ecs_subnets],
            security_groups=[ecs_sg.id],
            # dev: public subnets + public IP = no NAT needed (free)
            # prod: private subnets, no public IP (NAT handles outbound)
            assign_public_ip=not is_prod,
        ),
        load_balancers=[
            aws.ecs.ServiceLoadBalancerArgs(
                target_group_arn=target_group.arn,
                container_name="apartment-manager",
                container_port=app_port,
            )
        ],
        deployment_circuit_breaker=aws.ecs.ServiceDeploymentCircuitBreakerArgs(
            enable=True,
            rollback=True,
        ),
        deployment_minimum_healthy_percent=50,
        deployment_maximum_percent=200,
        health_check_grace_period_seconds=120,
        enable_execute_command=True,
        tags={"Environment": env},
        opts=pulumi.ResourceOptions(depends_on=[http_listener]),
    )

    # ── Auto Scaling ─────────────────────────────────────────────────────────

    scalable_target = aws.appautoscaling.Target(
        f"ecs-scaling-target-{env}",
        max_capacity=10,
        min_capacity=desired_count,
        resource_id=pulumi.Output.all(cluster.name, service.name).apply(
            lambda args: f"service/{args[0]}/{args[1]}"
        ),
        scalable_dimension="ecs:service:DesiredCount",
        service_namespace="ecs",
    )

    aws.appautoscaling.Policy(
        f"ecs-cpu-scaling-{env}",
        name=f"apartment-manager-cpu-scaling-{env}",
        policy_type="TargetTrackingScaling",
        resource_id=scalable_target.resource_id,
        scalable_dimension=scalable_target.scalable_dimension,
        service_namespace=scalable_target.service_namespace,
        target_tracking_scaling_policy_configuration=aws.appautoscaling.PolicyTargetTrackingScalingPolicyConfigurationArgs(
            target_value=70.0,
            predefined_metric_specification=aws.appautoscaling.PolicyTargetTrackingScalingPolicyConfigurationPredefinedMetricSpecificationArgs(
                predefined_metric_type="ECSServiceAverageCPUUtilization",
            ),
            scale_in_cooldown=300,
            scale_out_cooldown=60,
        ),
    )

    return {
        "cluster": cluster,
        "service": service,
        "alb": alb,
        "alb_dns": alb.dns_name,
        "target_group": target_group,
        "ecs_sg": ecs_sg,
        "uploads_bucket": uploads_bucket,
        "log_group": log_group,
    }
