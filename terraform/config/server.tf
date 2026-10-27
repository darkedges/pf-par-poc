data "pingfederate_oauth_server_settings" "existing" {}
resource "pingfederate_oauth_server_settings" "par" {
  authorization_code_entropy = data.pingfederate_oauth_server_settings.existing.authorization_code_entropy
  authorization_code_timeout = 60
  refresh_rolling_interval   = data.pingfederate_oauth_server_settings.existing.refresh_rolling_interval
  refresh_token_length       = data.pingfederate_oauth_server_settings.existing.refresh_token_length
  scopes                     = data.pingfederate_oauth_server_settings.existing.scopes
  par_status                 = "ENABLED"
  par_reference_timeout      = 120
  par_reference_length       = 32
  disallow_plain_pkce        = true
}
import {
  to = pingfederate_oauth_server_settings.par
  id = "id"
}
data "pingfederate_server_settings" "existing" {}
resource "pingfederate_server_settings" "local" {
  federation_info = {
    base_url          = var.pf_runtime_url
    saml_2_entity_id  = data.pingfederate_server_settings.existing.federation_info.saml_2_entity_id
    saml_1x_issuer_id = data.pingfederate_server_settings.existing.federation_info.saml_1x_issuer_id
    wsfed_realm       = data.pingfederate_server_settings.existing.federation_info.wsfed_realm
  }
}
import {
  to = pingfederate_server_settings.local
  id = "id"
}
resource "pingfederate_keypairs_ssl_server_key" "local" {
  key_id    = "par-localhost"
  file_data = sensitive(filebase64("${path.module}/../../certs/localhost.p12"))
  format    = "PKCS12"
  password  = var.tls_password
}
resource "pingfederate_keypairs_ssl_server_settings" "local" {
  count                       = var.activate_tls ? 1 : 0
  admin_console_cert_ref      = { id = pingfederate_keypairs_ssl_server_key.local.id }
  active_admin_console_certs  = [{ id = pingfederate_keypairs_ssl_server_key.local.id }]
  runtime_server_cert_ref     = { id = pingfederate_keypairs_ssl_server_key.local.id }
  active_runtime_server_certs = [{ id = pingfederate_keypairs_ssl_server_key.local.id }]
}
import {
  for_each = var.activate_tls ? toset(["existing"]) : toset([])
  to       = pingfederate_keypairs_ssl_server_settings.local[0]
  id       = "existing"
}
