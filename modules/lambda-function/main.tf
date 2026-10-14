terraform {
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.67" }
    archive = { source = "hashicorp/archive", version = "~> 2.7" }
  }
}

data "aws_partition" "current" {}

data "aws_iam_policy_document" "trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

locals {
  files = merge(
    { for f in fileset(var.source_dir, "**/*.py") : f => "${var.source_dir}/${f}" },
    var.extra_files,
  )
}

data "archive_file" "this" {
  type        = "zip"
  output_path = "${path.root}/build/${var.name}.zip"

  dynamic "source" {
    for_each = local.files
    content {
      filename = source.key
      content  = file(source.value)
    }
  }

  lifecycle {
    precondition {
      condition     = length(local.files) > 0
      error_message = "No hay archivos .py en source_dir ni en extra_files para empaquetar."
    }
  }
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_iam_role" "this" {
  name                 = var.name
  path                 = var.iam_path
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = var.tags
}

resource "aws_iam_role_policy" "this" {
  name   = "function"
  role   = aws_iam_role.this.id
  policy = var.policy_json
}

data "aws_iam_policy_document" "logs" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }
}

resource "aws_iam_role_policy" "logs" {
  name   = "logs"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.logs.json
}

resource "aws_lambda_function" "this" {
  function_name    = var.name
  role             = aws_iam_role.this.arn
  runtime          = var.runtime
  architectures    = [var.architecture]
  handler          = var.handler
  timeout          = var.timeout
  memory_size      = var.memory_size
  filename         = data.archive_file.this.output_path
  source_code_hash = data.archive_file.this.output_base64sha256
  tags             = var.tags

  environment {
    variables = var.environment
  }

  depends_on = [aws_cloudwatch_log_group.this, aws_iam_role_policy.logs]
}
