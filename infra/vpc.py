"""VPC, subnets, internet gateway, route tables.

Cost strategy:
  dev  — NO NAT Gateway (~$32/month saved). ECS tasks run in public subnets
          with assign_public_ip=True. RDS stays private, reachable via SG only.
  prod — NAT Gateway included so ECS tasks stay in private subnets (secure).
"""
import pulumi
import pulumi_aws as aws


def create_vpc(env: str):
    is_prod = env == "prod"

    vpc = aws.ec2.Vpc(
        f"vpc-{env}",
        cidr_block="10.0.0.0/16",
        enable_dns_hostnames=True,
        enable_dns_support=True,
        tags={"Name": f"apartment-manager-vpc-{env}", "Environment": env},
    )

    igw = aws.ec2.InternetGateway(
        f"igw-{env}",
        vpc_id=vpc.id,
        tags={"Name": f"apartment-manager-igw-{env}", "Environment": env},
    )

    azs = aws.get_availability_zones(state="available")

    # Public subnets — ALB always lives here; ECS also lives here on dev
    public_subnet_1 = aws.ec2.Subnet(
        f"public-subnet-1-{env}",
        vpc_id=vpc.id,
        cidr_block="10.0.1.0/24",
        availability_zone=azs.names[0],
        map_public_ip_on_launch=True,
        tags={"Name": f"apartment-manager-public-1-{env}", "Environment": env},
    )

    public_subnet_2 = aws.ec2.Subnet(
        f"public-subnet-2-{env}",
        vpc_id=vpc.id,
        cidr_block="10.0.2.0/24",
        availability_zone=azs.names[1],
        map_public_ip_on_launch=True,
        tags={"Name": f"apartment-manager-public-2-{env}", "Environment": env},
    )

    # Private subnets — RDS always; ECS only in prod
    private_subnet_1 = aws.ec2.Subnet(
        f"private-subnet-1-{env}",
        vpc_id=vpc.id,
        cidr_block="10.0.10.0/24",
        availability_zone=azs.names[0],
        tags={"Name": f"apartment-manager-private-1-{env}", "Environment": env},
    )

    private_subnet_2 = aws.ec2.Subnet(
        f"private-subnet-2-{env}",
        vpc_id=vpc.id,
        cidr_block="10.0.11.0/24",
        availability_zone=azs.names[1],
        tags={"Name": f"apartment-manager-private-2-{env}", "Environment": env},
    )

    # Public route table (IGW) — used by public subnets and dev private subnets
    public_rt = aws.ec2.RouteTable(
        f"public-rt-{env}",
        vpc_id=vpc.id,
        routes=[
            aws.ec2.RouteTableRouteArgs(cidr_block="0.0.0.0/0", gateway_id=igw.id)
        ],
        tags={"Name": f"apartment-manager-public-rt-{env}", "Environment": env},
    )

    aws.ec2.RouteTableAssociation(f"public-rta-1-{env}", subnet_id=public_subnet_1.id, route_table_id=public_rt.id)
    aws.ec2.RouteTableAssociation(f"public-rta-2-{env}", subnet_id=public_subnet_2.id, route_table_id=public_rt.id)

    if is_prod:
        # Prod: NAT Gateway so ECS tasks in private subnets can reach internet
        nat_eip = aws.ec2.Eip(
            f"nat-eip-{env}",
            domain="vpc",
            tags={"Name": f"apartment-manager-nat-eip-{env}", "Environment": env},
        )
        nat_gateway = aws.ec2.NatGateway(
            f"nat-gw-{env}",
            subnet_id=public_subnet_1.id,
            allocation_id=nat_eip.id,
            tags={"Name": f"apartment-manager-nat-{env}", "Environment": env},
            opts=pulumi.ResourceOptions(depends_on=[igw]),
        )
        private_rt = aws.ec2.RouteTable(
            f"private-rt-{env}",
            vpc_id=vpc.id,
            routes=[
                aws.ec2.RouteTableRouteArgs(cidr_block="0.0.0.0/0", nat_gateway_id=nat_gateway.id)
            ],
            tags={"Name": f"apartment-manager-private-rt-{env}", "Environment": env},
        )
    else:
        # Dev: no NAT — private subnets have no outbound internet
        # (RDS doesn't need it; ECS will run in public subnets instead)
        private_rt = aws.ec2.RouteTable(
            f"private-rt-{env}",
            vpc_id=vpc.id,
            tags={"Name": f"apartment-manager-private-rt-{env}", "Environment": env},
        )

    aws.ec2.RouteTableAssociation(f"private-rta-1-{env}", subnet_id=private_subnet_1.id, route_table_id=private_rt.id)
    aws.ec2.RouteTableAssociation(f"private-rta-2-{env}", subnet_id=private_subnet_2.id, route_table_id=private_rt.id)

    return {
        "vpc": vpc,
        "public_subnets": [public_subnet_1, public_subnet_2],
        "private_subnets": [private_subnet_1, private_subnet_2],
        # In dev, ECS should use public subnets (no NAT needed)
        "ecs_subnets": [public_subnet_1, public_subnet_2] if not is_prod else [private_subnet_1, private_subnet_2],
        "is_prod": is_prod,
    }
