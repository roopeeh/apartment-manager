"""Build and push Docker image to ECR using Pulumi Docker provider."""
import pulumi
import pulumi_docker as docker
import pulumi_aws as aws


def build_and_push_image(env: str, ecr_repo, context_path: str = ".."):
    """
    Build Docker image and push to ECR.
    
    Args:
        env: Environment name (dev/prod)
        ecr_repo: ECR repository resource
        context_path: Path to Docker build context (relative to infra/)
    
    Returns:
        Docker image resource with full image name
    """
    
    # Get ECR authorization token
    ecr_auth_token = aws.ecr.get_authorization_token()
    
    # Build and push Docker image
    image = docker.Image(
        f"apartment-manager-image-{env}",
        build=docker.DockerBuildArgs(
            context=context_path,
            dockerfile=f"{context_path}/Dockerfile",
            platform="linux/amd64",
        ),
        image_name=ecr_repo.repository_url.apply(lambda url: f"{url}:latest"),
        registry=docker.RegistryArgs(
            server=ecr_repo.repository_url,
            username="AWS",
            password=pulumi.Output.secret(ecr_auth_token.password),
        ),
    )
    
    return image
