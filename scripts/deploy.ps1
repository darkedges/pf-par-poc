param([switch]$BootstrapTls)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
. "$PSScriptRoot/config-env.ps1"
function Invoke-Terraform([string[]]$Arguments) {
    & terraform @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Terraform failed: $($Arguments[0]) $($Arguments[1])" }
}
Invoke-Terraform @('-chdir=terraform/runtime', 'init', '-input=false')
Invoke-Terraform @('-chdir=terraform/runtime', 'plan', '-input=false', '-out=runtime.tfplan')
Invoke-Terraform @('-chdir=terraform/runtime', 'apply', '-input=false', 'runtime.tfplan')
# Compose waits for the image's health check, then the admin API must be reachable.
$deadline = [DateTime]::UtcNow.AddMinutes(5)
do {
    $client = [Net.Sockets.TcpClient]::new()
    try { $ready = $client.ConnectAsync('127.0.0.1', 9998).Wait(1000) -and $client.Connected }
    catch { $ready = $false }
    finally { $client.Dispose() }
    if (-not $ready) { Start-Sleep -Seconds 3 }
} until ($ready -or [DateTime]::UtcNow -gt $deadline)
if (-not $ready) { throw 'The new PingFederate admin port did not become ready.' }
Invoke-Terraform @('-chdir=terraform/config', 'init', '-input=false')
if ($BootstrapTls) {
    # First run only: the getting-started profile has an untrusted certificate.
    # Restrict this exception to importing/activating TLS on the new loopback instance.
    try {
        $env:PINGFEDERATE_PROVIDER_INSECURE_TRUST_ALL_TLS = 'true'
        Invoke-Terraform @('-chdir=terraform/config', 'plan', '-input=false', '-var=activate_tls=true', '-target=pingfederate_keypairs_ssl_server_key.local', '-target=pingfederate_keypairs_ssl_server_settings.local', '-out=tls.tfplan')
        Invoke-Terraform @('-chdir=terraform/config', 'apply', '-input=false', 'tls.tfplan')
    } finally { $env:PINGFEDERATE_PROVIDER_INSECURE_TRUST_ALL_TLS = 'false' }
    # PF reads the newly selected listener certificate on restart.
    & docker restart pf-par-poc
    if ($LASTEXITCODE -ne 0) { throw 'Could not restart the dedicated PAR PingFederate container.' }
    $deadline = [DateTime]::UtcNow.AddMinutes(5)
    do {
        try {
            $response = Invoke-WebRequest 'https://127.0.0.1:9998/pf-admin-api/v1/version' -Headers @{'X-XSRF-Header'='PingFederate'} -SkipHttpErrorCheck -TimeoutSec 5
            $ready = $response.StatusCode -in @(200,401)
        } catch { $ready = $false }
        if (-not $ready) { Start-Sleep -Seconds 3 }
    } until ($ready -or [DateTime]::UtcNow -gt $deadline)
    if (-not $ready) { throw 'PF did not restart with trusted HTTPS.' }
}
Invoke-Terraform @('-chdir=terraform/config', 'plan', '-input=false', '-var=activate_tls=true', '-out=config.tfplan')
Invoke-Terraform @('-chdir=terraform/config', 'apply', '-input=false', 'config.tfplan')
Invoke-Terraform @('-chdir=terraform/runtime', 'plan', '-input=false', '-var=start_demo=true', '-out=runtime.tfplan')
Invoke-Terraform @('-chdir=terraform/runtime', 'apply', '-input=false', 'runtime.tfplan')
function Save-StageFlag([string]$Directory, [string]$Name) {
    $file = Join-Path $root "$Directory/terraform.tfvars"
    $content = if (Test-Path -LiteralPath $file) { [IO.File]::ReadAllText($file) } else { '' }
    $pattern = '(?m)^\s*' + [regex]::Escape($Name) + '\s*=\s*(true|false)\s*$'
    if ($content -match $pattern) { $content = [regex]::Replace($content, $pattern, "$Name = true") }
    else { $content = $content.TrimEnd() + "`n$Name = true`n" }
    [IO.File]::WriteAllText($file, $content)
}
Save-StageFlag 'terraform/config' 'activate_tls'
Save-StageFlag 'terraform/runtime' 'start_demo'
Write-Output 'Open https://localhost:8789 and sign in as par-demo-user. Password: .local/dev-password (not printed).'
