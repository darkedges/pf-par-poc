resource "pingfederate_oauth_access_token_manager" "par" {
  manager_id = "parDemoATM"
  name       = "PAR demo reference tokens"
  plugin_descriptor_ref = {
    id = "org.sourceid.oauth20.token.plugin.impl.ReferenceBearerAccessTokenManagementPlugin"
  }
  configuration = { fields = [
    { name = "Token Length", value = "56" },
    { name = "Token Lifetime", value = "5" },
  ] }
  attribute_contract      = { extended_attributes = [{ name = "sub" }, { name = "iss" }, { name = "aud" }] }
  access_control_settings = { restrict_clients = false }
}
resource "pingfederate_oauth_access_token_mapping" "par" {
  context                  = { type = "DEFAULT" }
  access_token_manager_ref = { id = pingfederate_oauth_access_token_manager.par.id }
  attribute_contract_fulfillment = {
    sub = { source = { type = "OAUTH_PERSISTENT_GRANT" }, value = "USER_KEY" }
    iss = { source = { type = "TEXT" }, value = var.pf_runtime_url }
    aud = { source = { type = "TEXT" }, value = "par-browser-demo" }
  }
}
resource "pingfederate_openid_connect_policy" "par" {
  policy_id                = "parDemoOIDC"
  name                     = "PAR browser demonstration"
  access_token_manager_ref = { id = pingfederate_oauth_access_token_manager.par.id }
  attribute_contract       = { extended_attributes = [] }
  attribute_mapping = {
    attribute_contract_fulfillment = {
      sub = { source = { type = "TOKEN" }, value = "sub" }
    }
  }
  allow_id_token_introspection = false
}
resource "pingfederate_oauth_client" "par" {
  client_id                                = "par-browser-demo"
  name                                     = "Local PAR + PKCE browser demo"
  enabled                                  = true
  client_auth                              = { type = "SECRET", secret = var.client_secret }
  grant_types                              = ["AUTHORIZATION_CODE"]
  redirect_uris                            = ["https://localhost:8789/callback"]
  require_pushed_authorization_requests    = true
  require_proof_key_for_code_exchange      = true
  restrict_scopes                          = true
  restricted_scopes                        = ["openid"]
  bypass_approval_page                     = false
  default_access_token_manager_ref         = { id = pingfederate_oauth_access_token_manager.par.id }
  restrict_to_default_access_token_manager = true
  oidc_policy = {
    policy_group               = { id = pingfederate_openid_connect_policy.par.id }
    id_token_signing_algorithm = "RS256"
  }
  depends_on = [pingfederate_oauth_server_settings.par, pingfederate_oauth_idp_adapter_mapping.dev]
}
output "demo_url" { value = "https://localhost:8789" }
output "par_endpoint" { value = "${var.pf_runtime_url}/as/par.oauth2" }
output "client_id" { value = pingfederate_oauth_client.par.id }
output "test_username" { value = "par-demo-user" }
