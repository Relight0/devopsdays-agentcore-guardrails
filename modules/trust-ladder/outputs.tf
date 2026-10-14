output "active_policies" {
  description = "Politicas vigentes en el nivel actual."
  value       = sort(tolist(local.active_policies))
}

output "ledger_table" {
  value = aws_dynamodb_table.ledger.name
}

output "ledger_table_arn" {
  value = aws_dynamodb_table.ledger.arn
}
