param(
    [Parameter(Mandatory)]
    [ValidateSet('help', 'doctor', 'prepare', 'deps', 'init', 'bootstrap', 'deploy', 'plan', 'fmt', 'fmt-check', 'validate', 'test', 'test-live', 'status', 'logs', 'start', 'stop', 'destroy')]
    [string]$Action,
    [string]$ReferenceProject = '../pingfederate-graph-broker',
    [string]$Python = 'python',
    [string]$DockerHost = 'npipe:////./pipe/dockerDesktopLinuxEngine'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = Split-Path -Parent $PSScriptRoot

function Invoke-Checked([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed with exit code $LASTEXITCODE." }
}

function Get-ProjectPython {
    $venvPython = if ($IsWindows) { "$root/.venv/Scripts/python.exe" } else { "$root/.venv/bin/python" }
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }
    return $Python
}

Push-Location -LiteralPath $root
try {
    # Keep Docker CLI and Terraform on the same engine. No Docker Desktop restart.
    $env:DOCKER_HOST = $DockerHost
    $env:TF_VAR_docker_host = $DockerHost
    switch ($Action) {
        'help' {
            @(
                'First run: make doctor prepare deps bootstrap check test-live',
                'Existing environment: make deploy',
                '',
                'doctor      Check required tools and Docker engine connectivity',
                'prepare     Copy reference credentials/TLS and generate demo secrets',
                'deps        Create .venv and install local test dependencies',
                'init        Initialize both Terraform roots',
                'bootstrap   First deployment with local TLS bootstrap',
                'deploy/up   Apply runtime + configuration and build/start the demo',
                'plan        Preview both Terraform roots after initial deployment',
                'fmt         Format Terraform sources',
                'fmt-check   Check Terraform formatting',
                'validate    Validate both initialized Terraform roots',
                'test        Run local mock-provider integration tests',
                'test-live   Run protocol tests against the deployed local PF server',
                'check       Run fmt-check, validate and test in sequence',
                'status      Show this Compose project containers',
                'logs        Show the last 100 log lines from this project',
                'start/stop  Resume or stop this project, retaining state and volume',
                'destroy     Terraform destroy of runtime; normal interactive approval',
                '',
                'Demo: https://localhost:8789 | Test user: par-demo-user',
                'Password file: .local/dev-password (not printed)',
                'Overrides: PWSH, PYTHON, REFERENCE_PROJECT, DOCKER_HOST'
            ) | Write-Output
        }
        'doctor' {
            foreach ($command in @('terraform', 'docker', $Python)) {
                $null = Get-Command $command -ErrorAction Stop
                Write-Output "Found $command"
            }
            Invoke-Checked 'terraform' @('version')
            Invoke-Checked $Python @('--version')
            Invoke-Checked 'docker' @('version', '--format', 'Docker engine: {{.Server.Version}}')
        }
        'prepare' {
            & "$PSScriptRoot/prepare-local.ps1" -ReferenceProject $ReferenceProject
        }
        'deps' {
            $venvPython = if ($IsWindows) { "$root/.venv/Scripts/python.exe" } else { "$root/.venv/bin/python" }
            if (-not (Test-Path -LiteralPath $venvPython)) {
                Invoke-Checked $Python @('-m', 'venv', '.venv')
            }
            if (-not (Test-Path -LiteralPath $venvPython)) { throw 'The .venv Python executable was not created.' }
            Invoke-Checked $venvPython @('-m', 'pip', 'install', '-r', 'demo/requirements.txt')
        }
        'init' {
            Invoke-Checked 'terraform' @('-chdir=terraform/runtime', 'init', '-input=false')
            Invoke-Checked 'terraform' @('-chdir=terraform/config', 'init', '-input=false')
        }
        { $_ -in @('bootstrap', 'deploy') } {
            & "$PSScriptRoot/deploy.ps1" -BootstrapTls:($Action -eq 'bootstrap')
        }
        'plan' {
            . "$PSScriptRoot/config-env.ps1"
            Invoke-Checked 'terraform' @('-chdir=terraform/runtime', 'plan', '-input=false')
            Invoke-Checked 'terraform' @('-chdir=terraform/config', 'plan', '-input=false')
        }
        'fmt' { Invoke-Checked 'terraform' @('fmt', '-recursive', 'terraform') }
        'fmt-check' { Invoke-Checked 'terraform' @('fmt', '-check', '-recursive', 'terraform') }
        'validate' {
            Invoke-Checked 'terraform' @('-chdir=terraform/runtime', 'validate')
            Invoke-Checked 'terraform' @('-chdir=terraform/config', 'validate')
        }
        'test' { Invoke-Checked (Get-ProjectPython) @('-m', 'unittest', 'discover', '-s', 'tests', '-v') }
        'test-live' { Invoke-Checked (Get-ProjectPython) @('scripts/test-live.py') }
        'status' { Invoke-Checked 'docker' @('compose', '--profile', 'demo', 'ps', '--all') }
        'logs' { Invoke-Checked 'docker' @('compose', '--profile', 'demo', 'logs', '--tail', '100') }
        'start' { Invoke-Checked 'docker' @('compose', '--profile', 'demo', 'start', '--wait', '--wait-timeout', '300') }
        'stop' { Invoke-Checked 'docker' @('compose', '--profile', 'demo', 'stop') }
        'destroy' { Invoke-Checked 'terraform' @('-chdir=terraform/runtime', 'destroy') }
    }
}
finally { Pop-Location }
