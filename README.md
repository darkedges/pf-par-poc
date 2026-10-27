# PingFederate PAR proof of concept

An isolated local PingFederate 13.1 environment provisioned with Terraform, following
the separate runtime/configuration-state approach in `pingfederate-graph-broker`.
The browser client demonstrates **PAR → browser login and consent → authorization
code → S256 PKCE token exchange → validated OpenID Connect identity**.

| Service | URL |
| --- | --- |
| Demo | https://localhost:8789 |
| PingFederate admin | https://localhost:9998 |
| PingFederate runtime | https://localhost:9032 |
| PAR | https://localhost:9032/as/par.oauth2 |
| Discovery | https://localhost:9032/.well-known/openid-configuration |

The Compose project and PF container are named `pf-par-poc`; the demo container is
`pf-par-demo`. Only loopback ports are published. PF configuration persists in the
project's own `pingfederate-out` named volume. No Entra configuration is involved.

## Prerequisites and preparation

Install GNU Make (`make`), PowerShell 7 (`pwsh`), Python 3.11 or newer (`python`),
Terraform >= 1.9, and Docker Desktop with Linux containers and Compose support.
Put these commands on PATH and start Docker Desktop before running the steps
below. The Makefile invokes PowerShell scripts, so it works from PowerShell or
Git Bash on this Windows workstation. The providers are pinned to PingFederate
1.9.0 and Docker 4.6.0;
commit both generated `.terraform.lock.hcl` files. The image tag is pinned to
`2606-13.1.0` in `.env.example`.

The Docker provider explicitly uses `npipe:////./pipe/dockerDesktopLinuxEngine`
on Windows; override its `docker_host` variable for another engine. Compose uses
the dedicated `10.233.0.0/24` subnet because this workstation's default Docker
address pools are exhausted. Set `PAR_DOCKER_SUBNET` in `.env` if that subnet
conflicts with another local or VPN route.

## First-time setup and run

Run these commands from the project root. Use `make bootstrap` only for the first
deployment of this dedicated environment; this workspace is already bootstrapped.

```powershell
Set-Location E:\development\projects\ping\pf-par-poc
make doctor
make prepare
make deps
make bootstrap
make check
make test-live
```

`doctor` checks the tools and Docker engine connection. `prepare` sets up local
credentials and certificates from the reference project. `deps` creates an ignored
`.venv` and installs the Python test dependencies. `bootstrap` initializes and
applies both Terraform roots, including first-time TLS setup. `check` runs local
formatting, validation, and integration checks; `test-live` exercises the running
PingFederate endpoints, including local login/consent and PKCE rejection.

The default reference project is the sibling `../pingfederate-graph-broker`. To
use a different checkout:

```powershell
make prepare REFERENCE_PROJECT="E:/development/projects/ping/pingfederate-graph-broker"
```

Preparation copies **only** the reference project's licensed Ping DevOps image
credentials and trusted localhost TLS certificate/key/CA. It generates new secrets
for this OAuth client, the `par-demo-user` account, and the PKCS#12 bundle. Existing
local files are preserved. The reference must already have its licensed `.env`
values and trusted localhost TLS files prepared, as described in that project's
setup guide.
To prepare manually, copy `.env.example` to `.env`, supply image credentials,
place trusted TLS files in `certs/localhost.pem`, `certs/localhost-key.pem`, and
`certs/ca.pem`, and provide the three `.local/` secret files and `certs/localhost.p12`.
The certificate needs a `localhost` SAN; its CA must be trusted by your browser.

The bootstrap script creates the runtime, imports and selects the trusted
localhost TLS certificate, restarts only `pf-par-poc`, applies the OAuth/login configuration,
builds the Python demo image, and starts it. It creates and applies saved Terraform
plans at each step. The first TLS bootstrap deliberately disables provider TLS
verification **only for the targeted certificate import/activation on this new
loopback instance** because the getting-started profile starts with an untrusted
certificate. Subsequent API configuration and all runtime OIDC/PAR/token traffic
verify certificates. Do not use bootstrap against a shared server.

The reference getting-started profile uses the local development administration
account `administrator` / `2FederateM0re`. Override
`PAR_PF_ADMIN_USERNAME` and `PAR_PF_ADMIN_PASSWORD` in the process
environment if needed. These are separate from the new demo user's credentials.

## Run or update an existing environment

For this already bootstrapped workspace, deploy configuration or demo changes with:

```powershell
make deploy
make status
```

`make up` is an alias for `make deploy`. Both initialize Terraform, show and apply
saved plans, and build/reconcile the demo image. A successful deployment saves the
enabled stages in ignored tfvars files for later plans. To inspect changes without
applying them after the first deployment, use `make plan`.

Open https://localhost:8789, select **Start PAR login**, and sign in as
`par-demo-user`. Retrieve the generated password locally:

```powershell
Get-Content .local/dev-password
```

Approve the consent screen. The result shows the subject, issuer, audience,
expiry, and token metadata. Access and ID token values stay on the demo server and
are discarded after verification; they are not rendered or logged.

`make stop` pauses the containers. `make start` resumes those same containers and
waits for them to be ready. Use `make deploy` to create missing containers or apply
source/configuration changes. Start a new browser login after restarting the demo.

## Make commands

Run `make` or `make help` to list the available commands.

| Command | Purpose |
| --- | --- |
| `make doctor` | Check required tools and the selected Docker engine |
| `make prepare` | Copy reference image credentials/TLS and generate local demo secrets |
| `make deps` | Create `.venv` and install host-side Python test dependencies |
| `make init` | Initialize both Terraform roots without deploying |
| `make bootstrap` | First deployment, including the dedicated local TLS bootstrap |
| `make deploy` / `make up` | Deploy/update the configured environment and demo |
| `make plan` | Preview both Terraform roots after initial deployment |
| `make fmt` / `make fmt-check` | Format Terraform / check formatting |
| `make validate` | Validate both initialized Terraform roots |
| `make test` | Run local mock-provider integration tests |
| `make test-live` | Exercise the deployed PF PAR/login/code flow |
| `make check` | Run formatting, Terraform validation, and local tests in sequence |
| `make status` / `make logs` | Show project containers / their last 100 log lines |
| `make stop` / `make start` | Pause / resume this project's existing containers |
| `make destroy` | Remove the Terraform-managed runtime with interactive Terraform approval |

The recipes stop on a failed command. Lifecycle operations remain sequential with
`make -j`. Test targets use `.venv` automatically when present; activation is not
required. `make deps` uses `PYTHON` to create it. Executable overrides are available:

```powershell
make doctor PWSH=pwsh PYTHON=python
make status DOCKER_HOST=npipe:////./pipe/dockerDesktopLinuxEngine
```

`DOCKER_HOST` is applied to both the Docker CLI and the Terraform Docker provider.
The Docker engine default and provisioning scripts target this Windows workstation;
the Bash switch in the curl guide selects request syntax independently.

## Curl request and response walkthrough

Open [the curl walkthrough](https://localhost:8789/curl) from the home or success
page, or read [the Markdown guide](demo/curl-walkthrough.md). It shows discovery,
authenticated PAR, authorization, local-user login, consent, code-to-token
exchange, JWKS retrieval, and the demo's start/callback requests, with the
corresponding response statuses and abbreviated bodies. Examples use placeholders
for sensitive values and explain the transaction-specific form fields and cookies.
Use the **PowerShell / Bash** switch to choose command syntax. The URL flag is
`?shell=powershell` (default) or `?shell=bash`; the Markdown source link follows
the selected shell. Bash examples use curl and OpenSSL for PKCE preparation.
The walkthrough also distinguishes manually redeeming a curl-created code from
letting the browser demo redeem its own code and private PKCE verifier.

## What Terraform manages

- `terraform/runtime`: Docker Compose lifecycle and the demo image build.
- `terraform/config`: imported server/OAuth/SSL singleton settings, localhost TLS
  key, Simple PCV test account, HTML Form adapter, OAuth adapter mapping, reference
  access-token manager and mapping, OIDC policy, and confidential OAuth client.
- Server `par_status = "ENABLED"`; client
  `require_pushed_authorization_requests = true` and
  `require_proof_key_for_code_exchange = true`. Plain PKCE is disabled globally on
  this dedicated instance. The PAR reference expires after 120 seconds.
- The client has only `AUTHORIZATION_CODE`, the `openid` scope, and the exact
  `https://localhost:8789/callback` redirect. No refresh-token grant is enabled.

The application sends the authorization payload over authenticated PAR. The
browser redirect carries only `client_id` and `request_uri`. State is bound to an
HttpOnly/Secure/SameSite cookie and a ten-minute in-memory transaction. The callback
exchanges the code with the original verifier, then checks the ID token's RS256
signature, issuer, audience, expiry, nonce, and access-token hash when present.
Restarting the demo clears pending transactions; start a new login afterwards.

## Validation

```powershell
make deps
make init
make check
# After deployment, also run:
make test-live
```

The local mock-provider tests exercise HTTP transaction/cookie binding, cross-origin
rejection, reference-only redirects with S256, successful signed-token verification,
expired transactions, callback replay, and invalid signature/nonce/issuer/audience/expiry.
The live tests check discovery, authenticated PAR, mandatory PAR, missing PKCE,
invalid client authentication, and rejection of a wrong PKCE verifier after a real
local login/consent/code issuance. A browser login verifies the full user journey.

## State and lifecycle

This is a workstation development setup. `.env`, `.local/`, TLS keys/bundles,
Terraform state, saved plans, and private tfvars are ignored. Terraform state and
plans contain credentials and private key material even when outputs are marked
sensitive. Keep them private; use encrypted, access-controlled remote state before
adapting this outside a disposable local environment.

For manual configuration commands, dot-source `scripts/config-env.ps1` first.
Successful deployment saves `activate_tls = true` and `start_demo = true` to the
respective ignored `terraform.tfvars` files, so later ordinary plans retain the
deployed stages. For a partially completed deployment, pass
`-var=activate_tls=true` for configuration and `-var=start_demo=true` for runtime
as appropriate. These flags default to false only for the initial setup.

Stop only this environment while keeping the persistent volume and Terraform state:

```powershell
make stop
```

To remove its containers and network through Terraform (the named volume remains):

```powershell
make destroy
```

This removes runtime containers and the project network while retaining the named
PF volume and local Terraform/configuration files. Use `make deploy` to recreate
the runtime from the retained configuration. There is no Make target that deletes
the PF volume, credentials, certificates, or Terraform state.

Keep the configuration state together with its PF volume. Destroy configuration
resources while PF is still running if deliberately rebuilding; do not delete
state files as a workaround for partial applies. No command here restarts Docker
Desktop or other projects.

References: [PingFederate PAR endpoint](https://docs.pingidentity.com/pingfederate/13.1/developers_reference_guide/pf_pushed_authoriz_request_endpoint.html),
[Terraform OAuth client](https://registry.terraform.io/providers/pingidentity/pingfederate/1.9.0/docs/resources/oauth_client),
[RFC 9126](https://www.rfc-editor.org/rfc/rfc9126).
