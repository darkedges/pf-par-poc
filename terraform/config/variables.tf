variable "pf_admin_url" {
  type    = string
  default = "https://localhost:9998"
  validation {
    condition     = can(regex("^https://(localhost|127[.]0[.]0[.]1):[0-9]+$", var.pf_admin_url))
    error_message = "This development environment requires a loopback HTTPS admin URL."
  }
}
variable "pf_runtime_url" {
  type    = string
  default = "https://localhost:9032"
  validation {
    condition     = can(regex("^https://(localhost|127[.]0[.]0[.]1):[0-9]+$", var.pf_runtime_url))
    error_message = "This development environment requires a loopback HTTPS runtime URL."
  }
}
variable "client_secret" {
  type      = string
  sensitive = true
}
variable "dev_password" {
  type      = string
  sensitive = true
}
variable "tls_password" {
  type      = string
  sensitive = true
}
variable "activate_tls" {
  type    = bool
  default = false
}
