# Development-only OAuth login. This deliberately creates one isolated
# credential validator, HTML Form IdP adapter and persistent-grant mapping.
# Do not enable outside a localhost PF runtime/admin API. The password remains in state.
resource "pingfederate_password_credential_validator" "dev" {
  validator_id = "parDemoPCV"
  name         = "PAR demo DEV-ONLY local user"

  plugin_descriptor_ref = {
    id = "org.sourceid.saml20.domain.SimpleUsernamePasswordCredentialValidator"
  }
  attribute_contract = {}
  configuration = {
    tables = [{
      name = "Users"
      rows = [{
        default_row = false
        fields = [
          { name = "Username", value = "par-demo-user" },
          { name = "Relax Password Requirements", value = "false" },
        ]
        sensitive_fields = [
          { name = "Password", value = var.dev_password },
          { name = "Confirm Password", value = var.dev_password },
        ]
      }]
    }]
  }

}

resource "pingfederate_idp_adapter" "dev" {
  adapter_id = "parDemoHTMLForm"
  name       = "PAR demo DEV-ONLY HTML Form"

  plugin_descriptor_ref = {
    id = "com.pingidentity.adapters.htmlform.idp.HtmlFormIdpAuthnAdapter"
  }
  configuration = {
    fields = [
      { name = "Challenge Retries", value = "3" },
      { name = "Session State", value = "None" },
      { name = "Login Template", value = "html.form.login.template.html" },
      { name = "Allow Password Changes", value = "false" },
      { name = "Enable 'Remember My Username'", value = "false" },
    ]
    tables = [{
      name = "Credential Validators"
      rows = [{
        default_row = false
        fields = [{
          name  = "Password Credential Validator Instance"
          value = pingfederate_password_credential_validator.dev.id
        }]
      }]
    }]
  }
  attribute_contract = {
    core_attributes = [
      { name = "policy.action", pseudonym = false, masked = false },
      { name = "username", pseudonym = true, masked = false },
    ]
    unique_user_key_attribute = "username"
  }
  attribute_mapping = {
    attribute_contract_fulfillment = {
      "policy.action" = { source = { type = "ADAPTER" }, value = "policy.action" }
      username        = { source = { type = "ADAPTER" }, value = "username" }
    }
  }
}

resource "pingfederate_oauth_idp_adapter_mapping" "dev" {
  mapping_id = pingfederate_idp_adapter.dev.id
  attribute_contract_fulfillment = {
    USER_KEY  = { source = { type = "ADAPTER" }, value = "username" }
    USER_NAME = { source = { type = "ADAPTER" }, value = "username" }
  }
}
