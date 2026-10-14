terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  # bucket y region llegan por -backend-config (backend.hcl o variables del workflow).
  backend "s3" {
    key          = "orphan-hunter/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
