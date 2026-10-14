variable "name" {
  description = "Nombre de la funcion (tambien del rol y del log group)."
  type        = string
}

variable "source_dir" {
  description = "Carpeta con el codigo; se empaquetan sus archivos .py."
  type        = string
}

variable "extra_files" {
  description = "Archivos extra para el zip: nombre_en_el_zip => ruta local (p. ej. modulos Python compartidos)."
  type        = map(string)
  default     = {}
}

variable "handler" {
  description = "Handler, p. ej. handler.handler."
  type        = string
  default     = "handler.handler"
}

variable "runtime" {
  type    = string
  default = "python3.13"
}

variable "architecture" {
  type    = string
  default = "arm64"

  validation {
    condition     = contains(["arm64", "x86_64"], var.architecture)
    error_message = "architecture debe ser arm64 o x86_64."
  }
}

variable "timeout" {
  type    = number
  default = 15
}

variable "memory_size" {
  type    = number
  default = 256
}

variable "environment" {
  description = "Variables de entorno (sin secretos)."
  type        = map(string)
  default     = {}
}

variable "policy_json" {
  description = "Politica IAM inline con los permisos de la funcion. Obligatoria: no hay permisos por defecto."
  type        = string
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "iam_path" {
  type    = string
  default = "/"
}

variable "permissions_boundary_arn" {
  description = "Permissions boundary opcional (techo organizacional)."
  type        = string
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
