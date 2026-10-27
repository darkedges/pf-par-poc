# Dot-source this before running configuration Terraform commands.
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:TF_VAR_client_secret = [IO.File]::ReadAllText("$projectRoot/.local/client-secret")
$env:TF_VAR_dev_password = [IO.File]::ReadAllText("$projectRoot/.local/dev-password")
$env:TF_VAR_tls_password = [IO.File]::ReadAllText("$projectRoot/.local/tls-password")
$env:PINGFEDERATE_PROVIDER_CA_CERTIFICATE_PEM_FILES = "$projectRoot/certs/ca.pem"
$env:PINGFEDERATE_PROVIDER_INSECURE_TRUST_ALL_TLS = 'false'
# Use project-specific overrides so inherited credentials for another PF server
# cannot accidentally be sent to this new getting-started instance.
$env:PINGFEDERATE_PROVIDER_USERNAME = 'administrator'
$env:PINGFEDERATE_PROVIDER_PASSWORD = '2FederateM0re'
if ($env:PAR_PF_ADMIN_USERNAME) { $env:PINGFEDERATE_PROVIDER_USERNAME = $env:PAR_PF_ADMIN_USERNAME }
if ($env:PAR_PF_ADMIN_PASSWORD) { $env:PINGFEDERATE_PROVIDER_PASSWORD = $env:PAR_PF_ADMIN_PASSWORD }
