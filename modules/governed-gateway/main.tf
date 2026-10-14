terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.67" }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  partition   = data.aws_partition.current.partition
  engine_name = replace("${var.name}_engine", "-", "_") # Cedar: solo letras, digitos y _

  invokable_lambdas = concat(
    [for t in var.targets : t.lambda_arn],
    var.interceptor_lambda_arn == null ? [] : [var.interceptor_lambda_arn],
  )
}

data "aws_iam_policy_document" "trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

data "aws_iam_policy_document" "role" {
  statement {
    sid       = "InvokeTargetsAndInterceptor"
    actions   = ["lambda:InvokeFunction"]
    resources = local.invokable_lambdas
  }

  dynamic "statement" {
    for_each = var.governed ? [1] : []
    content {
      sid = "EvaluatePolicies"
      actions = [
        "bedrock-agentcore:AuthorizeAction",
        "bedrock-agentcore:PartiallyAuthorizeActions",
        "bedrock-agentcore:GetPolicyEngine",
      ]
      resources = ["*"]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name                 = "${var.name}-gateway"
  path                 = var.iam_path
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy" "gateway" {
  name   = "gateway"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.role.json
}

resource "aws_bedrockagentcore_policy_engine" "this" {
  count = var.governed ? 1 : 0

  name        = local.engine_name
  description = "Politicas Cedar de ${var.name}."
}

resource "aws_bedrockagentcore_gateway" "this" {
  name            = var.name
  description     = var.description
  role_arn        = aws_iam_role.gateway.arn
  authorizer_type = "AWS_IAM"
  protocol_type   = "MCP"
  exception_level = var.exception_level

  dynamic "policy_engine_configuration" {
    for_each = var.governed ? [1] : []
    content {
      arn  = aws_bedrockagentcore_policy_engine.this[0].policy_engine_arn
      mode = var.policy_engine_mode
    }
  }

  dynamic "interceptor_configuration" {
    for_each = var.interceptor_lambda_arn == null ? [] : [1]
    content {
      interception_points = ["REQUEST"]

      interceptor {
        lambda {
          arn = var.interceptor_lambda_arn
        }
      }

      input_configuration {
        pass_request_headers = false
      }
    }
  }

  tags       = var.tags
  depends_on = [aws_iam_role_policy.gateway]
}

resource "aws_bedrockagentcore_gateway_target" "this" {
  for_each = var.targets

  name               = each.key
  gateway_identifier = aws_bedrockagentcore_gateway.this.gateway_id
  description        = each.value.description

  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    mcp {
      lambda {
        lambda_arn = each.value.lambda_arn

        tool_schema {
          dynamic "inline_payload" {
            for_each = each.value.tools
            content {
              name        = inline_payload.value.name
              description = inline_payload.value.description

              input_schema {
                type = "object"

                dynamic "property" {
                  for_each = inline_payload.value.properties
                  content {
                    name        = property.value.name
                    type        = property.value.type
                    description = property.value.description
                    required    = property.value.required ? true : null
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
