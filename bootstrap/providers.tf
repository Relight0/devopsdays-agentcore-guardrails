provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project    = "${var.github_repo}-bootstrap"
      managed_by = "terraform"
      repository = "${var.github_owner}/${var.github_repo}"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  partition    = data.aws_partition.current.partition
  repo         = "${var.github_owner}/${var.github_repo}"
  oidc_host    = "token.actions.githubusercontent.com"
  state_bucket = "${var.state_bucket_prefix}-${local.account_id}"
}
