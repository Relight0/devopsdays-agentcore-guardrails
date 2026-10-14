output "gateway_id" {
  value = aws_bedrockagentcore_gateway.this.gateway_id
}

output "gateway_arn" {
  description = "Depende de los targets: las politicas Cedar que lo usen se crean cuando el esquema de herramientas ya existe."
  value       = aws_bedrockagentcore_gateway.this.gateway_arn
  depends_on  = [aws_bedrockagentcore_gateway_target.this]
}

output "gateway_url" {
  description = "Endpoint MCP."
  value       = aws_bedrockagentcore_gateway.this.gateway_url
}

output "policy_engine_id" {
  description = "null si el gateway no es gobernado."
  value       = var.governed ? aws_bedrockagentcore_policy_engine.this[0].policy_engine_id : null
}

output "role_arn" {
  value = aws_iam_role.gateway.arn
}

output "target_names" {
  value = keys(aws_bedrockagentcore_gateway_target.this)
}
