region                   = "us-east-1"
availability_zone        = "us-east-1a"
project_name             = "orphan-hunter-demo"
repository               = "Relight0/devopsdays-agentcore-guardrails"
model_id                 = "us.anthropic.claude-sonnet-4-6"
governed_mode            = "ENFORCE"
policy_validation_mode   = "FAIL_ON_ANY_FINDINGS"
quarantine_minutes       = 3
notify_email             = "josem.vanegasa@gmail.com"
log_retention_days       = 7
permissions_boundary_arn = null

trust_level = 2
