locals {
  # Nunca env, hold ni owner: el agente no puede reescribir los hechos que lo limitan.
  review_tag_keys = ["orphan-status", "quarantine-until", "quarantined-by"]
}

locals {
  inventory_arns = [
    "arn:${local.partition}:ec2:${var.region}:${local.account_id}:volume/*",
    "arn:${local.partition}:ec2:${var.region}::snapshot/*",
    "arn:${local.partition}:ec2:${var.region}:${local.account_id}:elastic-ip/*",
    "arn:${local.partition}:ec2:${var.region}:${local.account_id}:security-group/*",
    "arn:${local.partition}:ec2:${var.region}:${local.account_id}:network-interface/*",
  ]
  delete_actions = [
    "ec2:DeleteVolume", "ec2:DeleteSnapshot", "ec2:ReleaseAddress",
    "ec2:DeleteSecurityGroup", "ec2:DeleteNetworkInterface",
  ]
  describe_actions = [
    "ec2:DescribeVolumes", "ec2:DescribeSnapshots", "ec2:DescribeAddresses",
    "ec2:DescribeSecurityGroups", "ec2:DescribeNetworkInterfaces",
  ]
}

data "aws_iam_policy_document" "tools_common" {
  statement {
    sid       = "ReadActiveBatch"
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.active_batch.arn]
  }
  statement {
    sid       = "DescribeInventoryAndTrail"
    actions   = concat(local.describe_actions, ["cloudtrail:LookupEvents"])
    resources = ["*"] # Describe* y LookupEvents no soportan resource-level permissions
  }
  statement {
    sid       = "NotifyOwners"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.notify.arn]
  }
}

data "aws_iam_policy_document" "tools_ungoverned" {
  source_policy_documents = [data.aws_iam_policy_document.tools_common.json]

  statement {
    sid       = "DeleteAnyDemoResource"
    actions   = local.delete_actions
    resources = local.inventory_arns
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/project"
      values   = [var.project_name]
    }
  }

  statement {
    sid       = "TagReviewStatus"
    actions   = ["ec2:CreateTags"]
    resources = local.inventory_arns
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/project"
      values   = [var.project_name]
    }
    condition {
      test     = "ForAllValues:StringEquals"
      variable = "aws:TagKeys"
      values   = local.review_tag_keys
    }
  }
}

# Techo IAM del carril gobernado: equivale al nivel 2 de la escalera.
data "aws_iam_policy_document" "tools_governed" {
  source_policy_documents = [data.aws_iam_policy_document.tools_common.json]

  statement {
    sid       = "DeleteReviewedNonProdResources"
    actions   = local.delete_actions
    resources = local.inventory_arns
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/project"
      values   = [var.project_name]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/env"
      values   = ["dev", "staging"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/hold"
      values   = ["false"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/orphan-status"
      values   = ["quarantined", "released"]
    }
  }

  statement {
    sid       = "QuarantineNonProdResources"
    actions   = ["ec2:CreateTags"]
    resources = local.inventory_arns
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/project"
      values   = [var.project_name]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/env"
      values   = ["dev", "staging"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/hold"
      values   = ["false"]
    }
    condition {
      test     = "ForAllValues:StringEquals"
      variable = "aws:TagKeys"
      values   = local.review_tag_keys
    }
  }
}

data "aws_iam_policy_document" "interceptor" {
  statement {
    sid       = "DescribeInventory"
    actions   = local.describe_actions
    resources = ["*"]
  }
}

locals {
  shared_files = { "ec2_inventory.py" = "${path.module}/../../lambdas/shared/ec2_inventory.py" }

  tools_env = {
    PROJECT            = var.project_name
    AGENT_ID           = local.scenario.agent_id
    ACTIVE_BATCH_PARAM = aws_ssm_parameter.active_batch.name
    TOPIC_ARN          = aws_sns_topic.notify.arn
    QUARANTINE_MINUTES = tostring(var.quarantine_minutes)
  }
}

module "tools_ungoverned" {
  source = "../../modules/lambda-function"

  name                     = "${var.project_name}-tools-ungoverned"
  source_dir               = "${path.module}/lambdas/tools"
  extra_files              = local.shared_files
  timeout                  = 60
  policy_json              = data.aws_iam_policy_document.tools_ungoverned.json
  log_retention_days       = var.log_retention_days
  iam_path                 = local.iam_path
  permissions_boundary_arn = var.permissions_boundary_arn
  environment              = merge(local.tools_env, { LANE = "ungoverned" })
}

module "tools_governed" {
  source = "../../modules/lambda-function"

  name                     = "${var.project_name}-tools-governed"
  source_dir               = "${path.module}/lambdas/tools"
  extra_files              = local.shared_files
  timeout                  = 60
  policy_json              = data.aws_iam_policy_document.tools_governed.json
  log_retention_days       = var.log_retention_days
  iam_path                 = local.iam_path
  permissions_boundary_arn = var.permissions_boundary_arn
  environment              = merge(local.tools_env, { LANE = "governed" })
}

module "interceptor" {
  source = "../../modules/lambda-function"

  name                     = "${var.project_name}-interceptor"
  source_dir               = "${path.module}/../../lambdas/attribute_resolver"
  extra_files              = local.shared_files
  timeout                  = 15
  policy_json              = data.aws_iam_policy_document.interceptor.json
  log_retention_days       = var.log_retention_days
  iam_path                 = local.iam_path
  permissions_boundary_arn = var.permissions_boundary_arn

  environment = {
    RESOLVER_CONFIG = jsonencode({
      rules = [
        {
          tools      = ["notify_owner"]
          resolver   = "ec2_resource_facts"
          key_arg    = "resource_id"
          attributes = { owner = "owner" }
          default    = "unknown"
        },
        {
          tools    = ["quarantine_resource", "delete_resource"]
          resolver = "ec2_resource_facts"
          key_arg  = "resource_id"
          attributes = {
            environment = "env"
            hold        = "hold"
            in_use      = "in_use"
            quarantine  = "quarantine"
          }
          default = "unknown"
        },
      ]
    })
  }
}

locals {
  target_description = "Inventario, avisos y limpieza de recursos EC2 huerfanos."
}

module "gateway_ungoverned" {
  source = "../../modules/governed-gateway"

  name                     = "${var.project_name}-ungoverned"
  description              = "Carril sin gobierno del demo (Acto 1)."
  governed                 = false
  exception_level          = "DEBUG"
  iam_path                 = local.iam_path
  permissions_boundary_arn = var.permissions_boundary_arn

  targets = {
    (local.tool_target_name) = {
      description = local.target_description
      lambda_arn  = module.tools_ungoverned.function_arn
      tools       = local.tools
    }
  }
}

module "gateway_governed" {
  source = "../../modules/governed-gateway"

  name                     = "${var.project_name}-governed"
  description              = "Carril gobernado del demo (Actos 2 y 3)."
  governed                 = true
  policy_engine_mode       = var.governed_mode
  interceptor_lambda_arn   = module.interceptor.function_arn
  exception_level          = "DEBUG"
  iam_path                 = local.iam_path
  permissions_boundary_arn = var.permissions_boundary_arn

  targets = {
    (local.tool_target_name) = {
      description = local.target_description
      lambda_arn  = module.tools_governed.function_arn
      tools       = local.tools
    }
  }
}

module "ladder" {
  source = "../../modules/trust-ladder"

  policy_engine_id = module.gateway_governed.policy_engine_id
  gateway_arn      = module.gateway_governed.gateway_arn
  target_name      = local.tool_target_name
  level            = var.trust_level
  ladder           = local.ladder
  policies_dir     = "${path.module}/policies"
  name_prefix      = var.project_name
  validation_mode  = var.policy_validation_mode

}
