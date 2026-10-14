variable "region" {
  description = "Region del demo; debe soportar AgentCore Gateway y Policy Engine."
  type        = string

  validation {
    condition     = contains(["us-east-1", "us-west-2", "eu-central-1", "ap-southeast-2"], var.region)
    error_message = "Usa una de: us-east-1, us-west-2, eu-central-1, ap-southeast-2."
  }
}

variable "project_name" {
  description = "Prefijo de nombres y valor del tag project."
  type        = string

  validation {
    # Con 24 caracteres el nombre de policy mas largo (<prefijo>_find_probable_owner) queda en 44.
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.project_name))
    error_message = "De 3 a 24 caracteres: minusculas, digitos o guiones, empezando por letra."
  }
}

variable "repository" {
  description = "Repositorio de origen, para el tag repository."
  type        = string
}

variable "availability_zone" {
  description = "AZ de los volumenes del inventario."
  type        = string
}

variable "model_id" {
  description = "Inference profile de Bedrock que usa el agente."
  type        = string
}

variable "governed_mode" {
  description = "Modo del Policy Engine en el carril gobernado."
  type        = string

  validation {
    condition     = contains(["ENFORCE", "LOG_ONLY"], var.governed_mode)
    error_message = "Debe ser ENFORCE o LOG_ONLY."
  }
}

variable "trust_level" {
  description = "Nivel actual de la escalera. Lo actualiza scripts/ladder.py."
  type        = number

  validation {
    condition     = contains([0, 1, 2], var.trust_level)
    error_message = "Los niveles validos son 0, 1 y 2 (data/ladder.json)."
  }
}

variable "policy_validation_mode" {
  description = "Validacion de Cedar al crear las policies."
  type        = string

  validation {
    condition     = contains(["FAIL_ON_ANY_FINDINGS", "IGNORE_ALL_FINDINGS"], var.policy_validation_mode)
    error_message = "Debe ser FAIL_ON_ANY_FINDINGS o IGNORE_ALL_FINDINGS."
  }
}

variable "quarantine_minutes" {
  description = "Duracion de la cuarentena. En produccion serian dias; en el demo, minutos."
  type        = number

  validation {
    condition     = var.quarantine_minutes >= 1
    error_message = "Minimo 1 minuto."
  }
}

variable "notify_email" {
  description = "Correo que recibe los avisos a los duenos. null = sin suscripcion."
  type        = string
  nullable    = true
}

variable "log_retention_days" {
  description = "Retencion de los log groups de las Lambdas."
  type        = number
}

variable "permissions_boundary_arn" {
  description = "Permissions boundary para todos los roles. null si la cuenta no usa uno."
  type        = string
  nullable    = true
}
