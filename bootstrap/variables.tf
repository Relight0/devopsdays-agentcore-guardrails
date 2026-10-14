variable "region" {
  description = "Region del bucket de estado y del demo."
  type        = string
}

variable "github_owner" {
  description = "Usuario u organizacion de GitHub dueno del repo."
  type        = string
}

variable "github_repo" {
  description = "Nombre del repo en GitHub."
  type        = string
}

variable "github_environment" {
  description = "Environment de GitHub que puede asumir el rol de deploy."
  type        = string
}

variable "project_name" {
  description = "Mismo project_name del stack; acota los roles IAM que el deploy puede administrar."
  type        = string
}

variable "state_bucket_prefix" {
  description = "Prefijo del bucket de estado; se le agrega el account ID."
  type        = string
}

variable "state_noncurrent_days" {
  description = "Dias que se conservan las versiones anteriores del estado."
  type        = number
}

variable "create_oidc_provider" {
  description = "false si la cuenta ya tiene el OIDC provider de GitHub (solo puede haber uno)."
  type        = bool
}
