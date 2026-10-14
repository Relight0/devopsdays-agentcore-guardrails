variable "policy_engine_id" {
  description = "ID del motor de politicas del gateway gobernado."
  type        = string
}

variable "gateway_arn" {
  description = "ARN del gateway: se inyecta en las plantillas Cedar como $${gateway_arn}."
  type        = string
}

variable "target_name" {
  description = "Nombre del target: prefijo de las acciones Cedar (<target>___<tool>), $${target} en las plantillas."
  type        = string
}

variable "level" {
  description = "Nivel actual de confianza. Debe ser una clave de var.ladder."
  type        = number

  validation {
    condition     = var.level >= 0 && floor(var.level) == var.level
    error_message = "level debe ser un entero >= 0."
  }
}

variable "ladder" {
  description = "Nivel => lista de nombres de politica (archivos <nombre>.cedar en policies_dir). Cada nivel debe incluir lo del anterior."
  type        = map(list(string))

  validation {
    condition     = length(var.ladder) > 0
    error_message = "ladder no puede estar vacio."
  }
}

variable "policies_dir" {
  description = "Carpeta con las plantillas .cedar."
  type        = string
}

variable "template_vars" {
  description = "Variables extra para las plantillas Cedar."
  type        = map(string)
  default     = {}
}

variable "name_prefix" {
  description = "Prefijo de nombres. Cedar solo admite letras, digitos y _ (los guiones se convierten)."
  type        = string
}

variable "validation_mode" {
  description = "Validacion de Cedar al crear politicas."
  type        = string
  default     = "FAIL_ON_ANY_FINDINGS"

  validation {
    condition     = contains(["FAIL_ON_ANY_FINDINGS", "IGNORE_ALL_FINDINGS"], var.validation_mode)
    error_message = "Debe ser FAIL_ON_ANY_FINDINGS o IGNORE_ALL_FINDINGS."
  }
}

variable "ledger_pitr" {
  description = "Recuperacion a un punto en el tiempo del libro de confianza."
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
