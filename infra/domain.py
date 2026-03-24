"""
Custom domain + HTTPS for the ALB.

Since manato.in is on Hostinger (no Pulumi provider), DNS is managed manually.
This module handles everything on the AWS side:
  1. ACM certificate (DNS-validated)
  2. CertificateValidation — Pulumi waits here until cert is ISSUED
  3. HTTPS :443 listener on ALB → forward to target group
  4. HTTP :80 listener rule → redirect to HTTPS

Workflow:
  Step 1 — pulumi up  (cert created, outputs CNAME records, Pulumi waits)
  Step 2 — Add the two CNAME records in Hostinger
  Step 3 — pulumi up  (cert now ISSUED, HTTPS listener created)
"""
import pulumi
import pulumi_aws as aws


def create_domain(
    env: str,
    alb: aws.lb.LoadBalancer,
    target_group: aws.lb.TargetGroup,
    http_listener: aws.lb.Listener,
    config: pulumi.Config,
):
    domain = config.get("custom_domain")
    if not domain:
        pulumi.log.info("custom_domain not set — skipping domain/HTTPS setup")
        return {}

    # ── ACM Certificate ───────────────────────────────────────────────────────
    cert = aws.acm.Certificate(
        f"cert-{env}",
        domain_name=domain,
        validation_method="DNS",
        tags={"Environment": env},
    )

    # Export the CNAME records you must add in Hostinger
    pulumi.export(
        "acm_validation_cname_name",
        cert.domain_validation_options.apply(
            lambda opts: opts[0].resource_record_name if opts else "pending"
        ),
    )
    pulumi.export(
        "acm_validation_cname_value",
        cert.domain_validation_options.apply(
            lambda opts: opts[0].resource_record_value if opts else "pending"
        ),
    )

    # ── Wait for cert to be ISSUED before touching the ALB ───────────────────
    # Pulumi blocks here until ACM reports the cert as ISSUED.
    # Add the Hostinger CNAME first, then re-run pulumi up.
    cert_validation = aws.acm.CertificateValidation(
        f"cert-validation-{env}",
        certificate_arn=cert.arn,
        opts=pulumi.ResourceOptions(
            custom_timeouts=pulumi.CustomTimeouts(create="10m"),
        ),
    )

    # ── HTTPS Listener ────────────────────────────────────────────────────────
    https_listener = aws.lb.Listener(
        f"https-listener-{env}",
        load_balancer_arn=alb.arn,
        port=443,
        protocol="HTTPS",
        ssl_policy="ELBSecurityPolicy-TLS13-1-2-2021-06",
        certificate_arn=cert_validation.certificate_arn,
        default_actions=[
            aws.lb.ListenerDefaultActionArgs(
                type="forward",
                target_group_arn=target_group.arn,
            )
        ],
        opts=pulumi.ResourceOptions(depends_on=[cert_validation]),
    )

    # ── HTTP → HTTPS Redirect ─────────────────────────────────────────────────
    aws.lb.ListenerRule(
        f"http-redirect-{env}",
        listener_arn=http_listener.arn,
        priority=1,
        conditions=[
            aws.lb.ListenerRuleConditionArgs(
                host_header=aws.lb.ListenerRuleConditionHostHeaderArgs(
                    values=[domain],
                )
            )
        ],
        actions=[
            aws.lb.ListenerRuleActionArgs(
                type="redirect",
                redirect=aws.lb.ListenerRuleActionRedirectArgs(
                    protocol="HTTPS",
                    port="443",
                    status_code="HTTP_301",
                ),
            )
        ],
    )

    pulumi.export("custom_domain", domain)
    pulumi.export("api_base_url_https", f"https://{domain}/api/v1")

    return {
        "cert": cert,
        "cert_validation": cert_validation,
        "https_listener": https_listener,
    }
