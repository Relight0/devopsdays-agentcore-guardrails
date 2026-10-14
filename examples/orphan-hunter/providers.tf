provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project    = var.project_name
      managed_by = "terraform"
      repository = var.repository
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  az         = var.availability_zone
  iam_path   = "/${var.project_name}/"

  scenario   = jsondecode(file("${path.module}/data/scenario.json"))
  tools      = jsondecode(file("${path.module}/data/tools.json"))
  ladder_cfg = jsondecode(file("${path.module}/data/ladder.json"))
  ladder     = { for level, cfg in local.ladder_cfg.levels : level => cfg.policies }

  tool_target_name = "resources"
}
