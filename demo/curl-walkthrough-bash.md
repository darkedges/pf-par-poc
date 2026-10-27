# The access-token flow, in curl

Each step pairs a curl command with its HTTP response. Status codes and field names were checked against this local PingFederate environment. Bodies are abbreviated, and secrets, cookies, request references, authorization codes and tokens use placeholders. This page is a representation, not a live transaction log.

The commands use Bash, curl, OpenSSL and standard Unix text tools (cat and tr). Run from the project root. The browser-facing requests share a cookie jar; the PAR and token requests authenticate the confidential client with HTTP Basic. TLS verification stays enabled.

## Prepare one transaction

Generate state, nonce and an S256 PKCE verifier/challenge before sending PAR. The same verifier must be used at the token endpoint. This is local preparation, with no HTTP request.

```bash
Issuer='https://localhost:9032'
ClientId='par-browser-demo'
RedirectUri='https://localhost:8789/callback'
ClientSecret=$(cat .local/client-secret)
DevPassword=$(cat .local/dev-password)
Cookies='.local/curl-cookies.txt'
Ca='certs/ca.pem'
CurlCommon=(--silent --show-error --include --ipv4
    --connect-timeout 5 --max-time 30 --cacert "$Ca")

base64url() {
    openssl base64 -A | tr '+/' '-_' | tr -d '='
}
Verifier=$(openssl rand 32 | base64url)
Challenge=$(printf '%s' "$Verifier" | openssl dgst -sha256 -binary | base64url)
State=$(openssl rand 32 | base64url)
Nonce=$(openssl rand 32 | base64url)
```

These Bash examples use the supplied local CA for certificate-chain and hostname verification. In Git Bash on Windows, if curl --version reports Schannel, add --ssl-revoke-best-effort to CurlCommon to tolerate the development certificate's missing revocation distribution point.

For a manual curl transaction, start with a fresh cookie jar. Commands deliberately omit --location so every response and redirect stays visible. Assign variables such as $RequestUri and the form action URLs from that transaction's preceding response. curl prints raw responses locally, including token values at the token step; the examples here are redacted.

## 1. Discover the endpoints

Client server → PingFederate. The demo sends this GET at the start and again during the callback, before the code exchange.

```bash
curl "${CurlCommon[@]}" "$Issuer/.well-known/openid-configuration"
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "issuer": "https://localhost:9032",
  "authorization_endpoint": "https://localhost:9032/as/authorization.oauth2",
  "token_endpoint": "https://localhost:9032/as/token.oauth2",
  "jwks_uri": "https://localhost:9032/pf/JWKS",
  "pushed_authorization_request_endpoint": "https://localhost:9032/as/par.oauth2",
  "require_pushed_authorization_requests": false
}
```

Other discovery fields are omitted above. PAR is enabled globally, and this individual client requires PAR even though the discovery flag does not require it for every client.

## 2. Push the authorization request

Client server → PingFederate. --user sends Authorization: Basic with the client ID and client secret. Login credentials are not sent to PAR.

```bash
curl "${CurlCommon[@]}" "$Issuer/as/par.oauth2" \
    --user "${ClientId}:$ClientSecret" \
    --data-urlencode "client_id=$ClientId" \
    --data-urlencode 'response_type=code' \
    --data-urlencode "redirect_uri=$RedirectUri" \
    --data-urlencode 'scope=openid' \
    --data-urlencode "state=$State" \
    --data-urlencode "nonce=$Nonce" \
    --data-urlencode "code_challenge=$Challenge" \
    --data-urlencode 'code_challenge_method=S256' \
    --data-urlencode 'pfidpadapterid=parDemoHTMLForm'
```

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "expires_in": 120,
  "request_uri": "urn:ietf:params:oauth:request_uri:<PAR_REFERENCE>"
}
```

Set $RequestUri to the returned request_uri. Continue promptly: the reference expires after 120 seconds. Only the reference and client ID are carried to the authorization endpoint; state, nonce and the challenge were already pushed over the back channel.

## 3. Open the authorization endpoint

Browser → PingFederate. curl represents the browser here, saving the PF cookies needed for the following forms.

```bash
RequestUri='<request_uri returned by step 2>'
curl "${CurlCommon[@]}" --cookie-jar $Cookies --cookie $Cookies \
    --get "$Issuer/as/authorization.oauth2" \
    --data-urlencode "client_id=$ClientId" \
    --data-urlencode "request_uri=$RequestUri"
```

```http
HTTP/1.1 200 OK
Content-Type: text/html;charset=utf-8
Set-Cookie: <PF_SESSION_COOKIE>; Secure; HttpOnly

<html>
  <!-- Sign On page; surrounding markup omitted -->
  <form method="post" action="<LOGIN_FORM_ACTION>">
    <input name="pf.username" type="text">
    <input name="pf.pass" type="password">
    <input name="pf.ok" type="hidden" value="">
    <input name="pf.cancel" type="hidden" value="">
    <input name="pf.adapterId" type="hidden" value="<ADAPTER_FIELD_VALUE>">
  </form>
</html>
```

Copy the exact form action and all hidden values from the returned HTML. Resolve relative action URLs against the current PF page. The form action and adapter field are transaction-specific; do not substitute a previous flow's values.

## 4. Submit the local user's login

Browser → PingFederate. This is an HTML Form adapter submission, not an OAuth password grant. Preserve the cookie jar and hidden fields from step 3.

```bash
LoginAction='<absolute login form action from step 3>'
AdapterField='<pf.adapterId value from step 3>'
curl "${CurlCommon[@]}" --cookie-jar $Cookies --cookie $Cookies \
    "$LoginAction" \
    --data-urlencode 'pf.username=par-demo-user' \
    --data-urlencode "pf.pass=$DevPassword" \
    --data-urlencode 'pf.ok=clicked' \
    --data-urlencode 'pf.cancel=' \
    --data-urlencode "pf.adapterId=$AdapterField"
```

```http
HTTP/1.1 200 OK
Content-Type: text/html;charset=utf-8

<html>
  <!-- Request for Approval page; surrounding markup omitted -->
  <form method="post" action="<CONSENT_FORM_ACTION>">
    <input type="hidden" name="check-user-approved-scope" value="true">
    <input type="checkbox" name="scope" value="openid" checked>
    <input type="hidden" name="cSRFToken" value="<CSRF_TOKEN>">
    <input type="hidden" name="pf.oauth.authz.consent" value="">
  </form>
</html>
```

The fresh-session test returned the consent page directly with HTTP 200. If PF returns a redirect in another session, make a separate GET to its Location with the same cookies and inspect that response before continuing. Use the scope value or values actually returned by the consent form.

## 5. Submit consent and receive the authorization code

Browser → PingFederate. The Allow control sets pf.oauth.authz.consent=allow. Preserve the exact case of cSRFToken and its current value.

```bash
ConsentAction='<absolute consent form action from step 4>'
CsrfToken='<cSRFToken value from step 4>'
curl "${CurlCommon[@]}" --cookie-jar $Cookies --cookie $Cookies \
    "$ConsentAction" \
    --data-urlencode 'check-user-approved-scope=true' \
    --data-urlencode 'scope=openid' \
    --data-urlencode "cSRFToken=$CsrfToken" \
    --data-urlencode 'pf.oauth.authz.consent=allow'
```

```http
HTTP/1.1 302 Found
Location: https://localhost:8789/callback?code=<AUTHORIZATION_CODE>&state=<ORIGINAL_STATE>
```

Validate that state matches the value generated for this transaction. The code is short-lived and single-use. It is not the access token. For a standalone curl exchange, capture and URL-decode code from Location, then go directly to step 6 without following the callback redirect.

## 6. Exchange the code for tokens

Client server → PingFederate. This step uses the same client authentication and exact redirect URI as before, plus the original PKCE verifier. The user password is not sent to the token endpoint.

```bash
Code='<URL-decoded code from step 5>'
curl "${CurlCommon[@]}" "$Issuer/as/token.oauth2" \
    --user "${ClientId}:$ClientSecret" \
    --data-urlencode 'grant_type=authorization_code' \
    --data-urlencode "code=$Code" \
    --data-urlencode "redirect_uri=$RedirectUri" \
    --data-urlencode "code_verifier=$Verifier"
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "access_token": "<OPAQUE_REFERENCE_ACCESS_TOKEN>",
  "id_token": "<SIGNED_RS256_ID_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 299
}
```

The access token in this environment is an opaque reference token, not a JWT. The ID token is a signed JWT. The observed response omitted scope and did not include a refresh token; this client enables only the authorization-code grant. expires_in is an example remaining lifetime, not a fixed response value.

## 7. Retrieve signing keys and validate the ID token

Client server → PingFederate. Use jwks_uri from discovery; /pf/JWKS is its value in this environment. No client secret or access token is required for this GET.

```bash
curl "${CurlCommon[@]}" "$Issuer/pf/JWKS"
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "keys": [
    {
      "kty": "RSA",
      "kid": "<SIGNING_KEY_ID>",
      "use": "sig",
      "alg": "RS256",
      "n": "<RSA_MODULUS>",
      "e": "AQAB"
    }
  ]
}
```

The key set is abbreviated. curl retrieves the keys but does not validate a JWT. The demo selects the RSA key matching kid and validates the RS256 signature, issuer, audience, expiry, nonce, authorized party, and at_hash when present. The nonce must match the value pushed in step 2. These checks are local computation and produce no additional HTTP requests.

## How the browser demo wraps these requests

The demo initially serves its home page with GET / → HTTP 200 HTML. Selecting Start PAR login sends this browser request to the demo server:

```bash
curl "${CurlCommon[@]}" --cookie-jar $Cookies --cookie $Cookies \
    'https://localhost:8789/start' \
    --header 'Origin: https://localhost:8789' \
    --data ''
```

```http
HTTP/1.0 303 See Other
Set-Cookie: par_tx=<BROWSER_TRANSACTION_BINDING>; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=600
Location: https://localhost:9032/as/authorization.oauth2?client_id=par-browser-demo&request_uri=<URL_ENCODED_PAR_REFERENCE>
```

Before returning that 303, the demo performs steps 1 and 2 and stores its own state, nonce, verifier and browser-cookie binding in server memory. The browser then performs steps 3–5. PF's 302 redirects it to the callback:

```bash
# Representation of the browser callback for a demo-created transaction.
curl "${CurlCommon[@]}" --cookie-jar $Cookies --cookie $Cookies \
    --get 'https://localhost:8789/callback' \
    --data-urlencode 'code=<AUTHORIZATION_CODE>' \
    --data-urlencode 'state=<ORIGINAL_STATE>'
```

```http
HTTP/1.0 200 OK
Content-Type: text/html; charset=utf-8
Cache-Control: no-store
Set-Cookie: par_tx=; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=0

<html>
  <!-- Authorization verified. -->
  <!-- Identity claims and token metadata; token values hidden. -->
</html>
```

The callback holds its response while the demo validates state and the cookie, repeats discovery, exchanges the code (step 6), retrieves the JWKS (step 7), and validates the ID token. The browser never makes the token request or receives the token values.

A manually constructed PAR transaction has no matching demo-side state or cookie binding, so do not replay its callback against the demo. Redeem that code directly with curl instead. Conversely, a demo-created transaction uses a private server-side verifier: let the demo finish its exchange. A code already redeemed by either path cannot be exchanged a second time.
