terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.67" }
  }
}

data "aws_caller_identity" "current" {}

locals {
  account_id      = data.aws_caller_identity.current.account_id
  cedar_prefix    = replace(var.name_prefix, "-", "_")
  active_policies = toset(var.ladder[tostring(var.level)])
}

# Cambiar de nivel crea o destruye politicas; el gateway no se toca.
resource "aws_bedrockagentcore_policy" "this" {
  for_each = local.active_policies

  name             = "${local.cedar_prefix}_${each.key}"
  policy_engine_id = var.policy_engine_id
  description      = "Politica de la escalera: ${each.key}"
  validation_mode  = var.validation_mode

  definition {
    cedar {
      statement = templatefile("${var.policies_dir}/${each.key}.cedar", merge(var.template_vars, {
        gateway_arn = var.gateway_arn
        target      = var.target_name
        account_id  = local.account_id
      }))
    }
  }
}

resource "aws_dynamodb_table" "ledger" {
  name         = "${var.name_prefix}-trust-ledger"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "agent_id"
  range_key    = "ts"

  attribute {
    name = "agent_id"
    type = "S"
  }

  attribute {
    name = "ts"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.ledger_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = var.tags
}
