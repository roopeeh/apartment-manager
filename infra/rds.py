"""RDS PostgreSQL instance with subnet group, security group, and Secrets Manager."""
import json
import pulumi
import pulumi_aws as aws


def create_rds(env: str, vpc, private_subnets: list, ecs_sg_id, config: pulumi.Config):
    db_name = config.get("db_name") or "apartment_manager"
    db_username = config.get("db_username") or "appadmin"
    db_instance_class = config.get("db_instance_class") or "db.t3.micro"
    db_allocated_storage = int(config.get("db_allocated_storage") or "20")

    # Random password stored in Secrets Manager
    db_password = aws.secretsmanager.Secret(
        f"db-password-secret-{env}",
        name=f"apartment-manager/{env}/db-password",
        description="RDS master password for apartment manager",
        tags={"Environment": env},
    )

    db_password_value = aws.secretsmanager.SecretVersion(
        f"db-password-value-{env}",
        secret_id=db_password.id,
        secret_string=pulumi.Output.secret(
            pulumi.Output.from_input("ApartmentManager2024!")  # Change in production
        ),
    )

    # App secrets (JWT secret key, etc.)
    app_secret = aws.secretsmanager.Secret(
        f"app-secret-{env}",
        name=f"apartment-manager/{env}/app-secrets",
        description="Application secrets for apartment manager",
        tags={"Environment": env},
    )

    app_secret_value = aws.secretsmanager.SecretVersion(
        f"app-secret-value-{env}",
        secret_id=app_secret.id,
        secret_string=pulumi.Output.secret(
            json.dumps({
                "SECRET_KEY": "change-this-to-a-real-secret-key-in-production",
                "ALGORITHM": "HS256",
            })
        ),
    )

    # RDS Security Group
    rds_sg = aws.ec2.SecurityGroup(
        f"rds-sg-{env}",
        vpc_id=vpc.id,
        description="Allow PostgreSQL from anywhere (public access)",
        ingress=[
            aws.ec2.SecurityGroupIngressArgs(
                protocol="tcp",
                from_port=5432,
                to_port=5432,
                cidr_blocks=["0.0.0.0/0"],
                description="PostgreSQL from anywhere",
            )
        ],
        egress=[
            aws.ec2.SecurityGroupEgressArgs(
                protocol="-1",
                from_port=0,
                to_port=0,
                cidr_blocks=["0.0.0.0/0"],
            )
        ],
        tags={"Name": f"apartment-manager-rds-sg-{env}", "Environment": env},
    )

    # DB Subnet Group (using public subnets for public access)
    db_subnet_group = aws.rds.SubnetGroup(
        f"db-subnet-group-public-{env}",
        subnet_ids=[s.id for s in private_subnets],
        tags={"Name": f"apartment-manager-db-subnet-{env}", "Environment": env},
    )

    # RDS Parameter Group
    db_param_group = aws.rds.ParameterGroup(
        f"db-param-group-{env}",
        family="postgres16",
        description="Custom parameter group for apartment manager",
        parameters=[
            aws.rds.ParameterGroupParameterArgs(name="log_connections", value="1"),
            aws.rds.ParameterGroupParameterArgs(name="log_disconnections", value="1"),
        ],
        tags={"Environment": env},
    )

    is_prod = env == "prod"

    # RDS Instance
    db_instance = aws.rds.Instance(
        f"db-public-{env}",
        identifier=f"apartment-manager-public-{env}",
        engine="postgres",
        engine_version="16.3",
        instance_class=db_instance_class,        # db.t3.micro on dev (~$13/mo)
        allocated_storage=db_allocated_storage,   # 20 GB on dev
        max_allocated_storage=0 if not is_prod else 100,  # disable autoscaling on dev
        storage_type="gp2",
        storage_encrypted=True,
        db_name=db_name,
        username=db_username,
        password=db_password_value.secret_string,
        db_subnet_group_name=db_subnet_group.name,
        vpc_security_group_ids=[rds_sg.id],
        parameter_group_name=db_param_group.name,
        # dev: 0-day backups = free, prod: 7-day retention
        backup_retention_period=0 if not is_prod else 7,
        backup_window="03:00-04:00",
        maintenance_window="Mon:04:00-Mon:05:00",
        skip_final_snapshot=not is_prod,
        final_snapshot_identifier=f"apartment-manager-{env}-final" if is_prod else None,
        deletion_protection=is_prod,
        # dev: Single-AZ (Multi-AZ doubles cost: ~$26/mo vs ~$13/mo)
        multi_az=is_prod,
        publicly_accessible=True,
        auto_minor_version_upgrade=True,
        # dev: performance insights off (costs extra)
        performance_insights_enabled=is_prod,
        tags={"Name": f"apartment-manager-db-{env}", "Environment": env},
    )

    # Build DATABASE_URL output
    database_url = pulumi.Output.all(
        db_instance.address,
        db_password_value.secret_string,
        db_name,
        db_username,
    ).apply(
        lambda args: f"postgresql+asyncpg://{args[3]}:{args[1]}@{args[0]}:5432/{args[2]}"
    )

    return {
        "instance": db_instance,
        "security_group": rds_sg,
        "password_secret": db_password,
        "app_secret": app_secret,
        "database_url": database_url,
        "db_username": db_username,
        "db_name": db_name,
        "db_password_secret_arn": db_password.arn,
        "app_secret_arn": app_secret.arn,
    }
