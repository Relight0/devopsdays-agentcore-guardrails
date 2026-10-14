variable "name" {
  description = "Nombre del gateway (y prefijo del rol y del motor de politicas)."
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9-]{2,60}$", var.name))
    error_message = "Usa letras, digitos y guiones, empezando por letra (3 a 61 caracteres)."
  }
}

variable "description" {
  type    = string
  default = "Gateway MCP gestionado por Terraform."
}

variable "governed" {
  description = "true crea el motor de politicas Cedar y lo conecta al gateway. false = carril sin gobierno (solo para contrastes didacticos)."
  type        = bool
  default     = true
}

variable "policy_engine_mode" {
  description = "ENFORCE aplica; LOG_ONLY solo registra (util para promover politicas nuevas con seguridad)."
  type        = string
  default     = "ENFORCE"

  validation {
    condition     = contains(["ENFORCE", "LOG_ONLY"], var.policy_engine_mode)
    error_message = "Debe ser ENFORCE o LOG_ONLY."
  }
}

variable "interceptor_lambda_arn" {
  description = "Lambda interceptora de REQUEST (p. ej. resuelve atributos reales antes de Cedar). null = sin interceptor."
  type        = string
  default     = null
}

variable "targets" {
  description = "Targets del gateway: nombre => Lambda + herramientas con su esquema."
  type = map(object({
    description = string
    lambda_arn  = string
    tools = list(object({
      name        = string
      description = string
      properties = list(object({
        name        = string
        type        = string
        description = string
        required    = optional(bool, false)
      }))
    }))
  }))
}

variable "exception_level" {
  description = "DEBUG devuelve errores completos (util en demo, no en produccion). null = comportamiento por defecto."
  type        = string
  default     = null
}

variable "iam_path" {
  type    = string
  default = "/"
}

variable "permissions_boundary_arn" {
  type    = string
  default = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
