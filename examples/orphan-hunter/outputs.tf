output "region" {
  value = var.region
}

output "model_id" {
  value = var.model_id
}

output "project_name" {
  value = var.project_name
}

output "gateway_urls" {
  description = "Endpoint MCP de cada carril."
  value = {
    ungoverned = module.gateway_ungoverned.gateway_url
    governed   = module.gateway_governed.gateway_url
  }
}

output "gateway_ids" {
  value = {
    ungoverned = module.gateway_ungoverned.gateway_id
    governed   = module.gateway_governed.gateway_id
  }
}

output "policy_engine_id" {
  value = module.gateway_governed.policy_engine_id
}

output "governed_mode" {
  value = var.governed_mode
}

output "active_policies" {
  description = "Tras un apply con -target puede quedar viejo; la fuente de verdad es terraform.tfvars."
  value       = module.ladder.active_policies
}

output "active_batch_param" {
  value = aws_ssm_parameter.active_batch.name
}

output "trust_ledger_table" {
  value = module.ladder.ledger_table
}

output "notify_topic_arn" {
  value = aws_sns_topic.notify.arn
}

output "quarantine_minutes" {
  value = var.quarantine_minutes
}

output "lambda_log_groups" {
  value = {
    tools_ungoverned = module.tools_ungoverned.log_group_name
    tools_governed   = module.tools_governed.log_group_name
    interceptor      = module.interceptor.log_group_name
  }
}
