"""ECR repository for Docker images."""
import json
import pulumi
import pulumi_aws as aws


def create_ecr(env: str):
    repo = aws.ecr.Repository(
        f"ecr-repo-{env}",
        name=f"apartment-manager-{env}",
        image_tag_mutability="MUTABLE",
        image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
            scan_on_push=True,
        ),
        encryption_configuration=aws.ecr.RepositoryEncryptionConfigurationArgs(
            encryption_type="AES256",
        ),
        force_delete=env != "prod",
        tags={"Name": f"apartment-manager-{env}", "Environment": env},
    )

    # Lifecycle policy: keep last 10 images
    lifecycle_policy = aws.ecr.LifecyclePolicy(
        f"ecr-lifecycle-{env}",
        repository=repo.name,
        policy=json.dumps({
            "rules": [
                {
                    "rulePriority": 1,
                    "description": "Keep last 10 images",
                    "selection": {
                        "tagStatus": "tagged",
                        "tagPrefixList": ["v"],
                        "countType": "imageCountMoreThan",
                        "countNumber": 10,
                    },
                    "action": {"type": "expire"},
                },
                {
                    "rulePriority": 2,
                    "description": "Remove untagged images older than 7 days",
                    "selection": {
                        "tagStatus": "untagged",
                        "countType": "sinceImagePushed",
                        "countUnit": "days",
                        "countNumber": 7,
                    },
                    "action": {"type": "expire"},
                },
            ]
        }),
    )

    return {
        "repository": repo,
        "repository_url": repo.repository_url,
    }
