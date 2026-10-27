param([string]$ReferenceProject = 'E:\development\projects\ping\pingfederate-graph-broker')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force "$root/.local", "$root/certs" | Out-Null
if (-not (Test-Path "$root/.env")) {
    $reference = @{}
    foreach ($line in [IO.File]::ReadAllLines("$ReferenceProject/.env")) {
        if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') { $reference[$matches[1]] = $matches[2].Trim('"') }
    }
    $template = [IO.File]::ReadAllText("$root/.env.example")
    foreach ($name in @('PING_IDENTITY_DEVOPS_USER','PING_IDENTITY_DEVOPS_KEY')) {
        if (-not $reference[$name]) { throw "Missing $name in reference .env" }
        $template = $template.Replace("$name=REPLACE_ME", "$name=$($reference[$name])")
    }
    [IO.File]::WriteAllText("$root/.env", $template)
}
foreach ($item in @(@('portal.pem','localhost.pem'), @('portal-key.pem','localhost-key.pem'), @('ca/mkcert-rootCA.pem','ca.pem'))) {
    if (-not (Test-Path "$root/certs/$($item[1])")) {
        Copy-Item -LiteralPath "$ReferenceProject/certs/$($item[0])" -Destination "$root/certs/$($item[1])"
    }
}
foreach ($name in @('client-secret', 'dev-password', 'tls-password')) {
    if (-not (Test-Path "$root/.local/$name")) {
        [IO.File]::WriteAllText("$root/.local/$name", 'Par!' + [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24)))
    }
}
if (-not (Test-Path "$root/certs/localhost.p12")) {
    $cert = [Security.Cryptography.X509Certificates.X509Certificate2]::CreateFromPemFile("$root/certs/localhost.pem", "$root/certs/localhost-key.pem")
    try {
        if ($cert.NotAfter.ToUniversalTime() -le [DateTime]::UtcNow) { throw 'The reference TLS certificate has expired.' }
        [IO.File]::WriteAllBytes("$root/certs/localhost.p12", $cert.Export([Security.Cryptography.X509Certificates.X509ContentType]::Pkcs12, [IO.File]::ReadAllText("$root/.local/tls-password")))
    } finally { $cert.Dispose() }
}
Write-Output 'Local image credentials, trusted localhost TLS files, and new demo credentials are ready. No secret values were printed.'
