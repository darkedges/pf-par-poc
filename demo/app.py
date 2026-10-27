"""Local confidential OIDC client demonstrating PAR and S256 PKCE.

Transactions and tokens stay in process memory. Never log URLs or upstream bodies.
"""
import base64
import hashlib
import html
import json
import os
import secrets
import ssl
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener, HTTPSHandler, Request

import jwt

ISSUER = os.environ.get("PF_ISSUER", "https://localhost:9032")
INTERNAL = os.environ.get("PF_INTERNAL_ORIGIN", ISSUER)
ORIGIN = os.environ.get("DEMO_ORIGIN", "https://localhost:8789")
CLIENT = os.environ.get("CLIENT_ID", "par-browser-demo")
SECRET = Path(os.environ.get("CLIENT_SECRET_FILE", ".local/client-secret")).read_text().strip()
CALLBACK = ORIGIN + "/callback"
TLS = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE", "certs/ca.pem"))
TRANSACTIONS = {}
LOCK = threading.Lock()
TTL = 600


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


HTTP = build_opener(HTTPSHandler(context=TLS), NoRedirect())


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def pf_request(url, fields=None, authenticate=False):
    # Only the configured PF origin can receive credentials, including through discovery.
    parsed = urlsplit(url)
    expected = urlsplit(ISSUER)
    if parsed.scheme != "https" or parsed.netloc != expected.netloc or parsed.fragment:
        raise ValueError("Unexpected provider endpoint")
    target = INTERNAL + parsed.path + (("?" + parsed.query) if parsed.query else "")
    headers = {"Accept": "application/json"}
    if authenticate:
        headers["Authorization"] = "Basic " + base64.b64encode((CLIENT + ":" + SECRET).encode()).decode()
    data = None if fields is None else urlencode(fields).encode()
    with HTTP.open(Request(target, data=data, headers=headers), timeout=20) as response:
        return json.load(response)


def discovery():
    result = pf_request(ISSUER + "/.well-known/openid-configuration")
    if result["issuer"] != ISSUER:
        raise ValueError("Issuer does not match configuration")
    for key in ("pushed_authorization_request_endpoint", "authorization_endpoint", "token_endpoint", "jwks_uri"):
        endpoint = urlsplit(result[key])
        if endpoint.scheme != "https" or endpoint.netloc != urlsplit(ISSUER).netloc:
            raise ValueError("Unexpected provider endpoint")
    return result


def validate_id_token(raw, config, transaction, access_token):
    header = jwt.get_unverified_header(raw)
    if header.get("alg") != "RS256":
        raise ValueError("Unexpected ID token signing algorithm")
    keys = pf_request(config["jwks_uri"])["keys"]
    key = next(key for key in keys if key.get("kid") == header.get("kid") and key.get("kty") == "RSA")
    claims = jwt.decode(raw, jwt.PyJWK.from_dict(key).key, algorithms=["RS256"],
                        audience=CLIENT, issuer=ISSUER, leeway=5,
                        options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]})
    if not secrets.compare_digest(claims["nonce"], transaction["nonce"]):
        raise ValueError("Nonce mismatch")
    if claims.get("azp", CLIENT) != CLIENT:
        raise ValueError("Authorized party mismatch")
    if isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and claims.get("azp") != CLIENT:
        raise ValueError("Missing authorized party")
    if "at_hash" in claims:
        expected_hash = b64(hashlib.sha256(access_token.encode()).digest()[:16])
        if not secrets.compare_digest(expected_hash, claims["at_hash"]):
            raise ValueError("Access token hash mismatch")
    return {key: claims[key] for key in ("iss", "sub", "aud", "iat", "exp")}


def page(content):
    return ("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>PingFederate · PAR lab</title>
<style>
:root{color-scheme:dark;font-family:Segoe UI,system-ui,sans-serif;color:#e8edf5;background:#101721}
body{max-width:1040px;margin:0 auto;padding:48px 30px}header{display:flex;justify-content:space-between;align-items:center}
.brand{font-size:15px;font-weight:650;letter-spacing:.08em}.badge{border:1px solid #405366;border-radius:25px;padding:7px 12px;font-size:12px;color:#aebfcf}
h1{font-size:48px;line-height:1.12;letter-spacing:-.04em;margin:60px 0 20px;max-width:720px}p{color:#acbbcc;line-height:1.7;max-width:740px}
.eyebrow{color:#74d9c4;font-size:12px;letter-spacing:.15em;margin-top:65px}.flow{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:38px 0}
.card{background:#172330;border:1px solid #2b3b4b;border-radius:12px;padding:24px}.number{color:#74d9c4;font-family:monospace;font-size:13px}
h2{font-size:18px;font-weight:600}button,.link{display:inline-block;background:#80e0c7;color:#0c2524;border:0;border-radius:7px;padding:15px 24px;font-size:15px;font-weight:650;text-decoration:none;cursor:pointer}
pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#c3d7e7;font-size:14px;line-height:1.7}footer{border-top:1px solid #2b3b4b;margin-top:55px;padding-top:22px;color:#7f93a7;font-size:12px}
.success{color:#80e0c7}.error{color:#ffb9a7}@media(max-width:700px){.flow{grid-template-columns:1fr}h1{font-size:36px}}
a{color:#80e0c7}.walkthrough h2{font-size:24px;margin-top:48px}.code-block{background:#172330;border:1px solid #2b3b4b;border-radius:12px;padding:22px;margin:20px 0;min-width:0}.code-block pre{white-space:pre;overflow-x:auto;padding-bottom:8px}.walkthrough p{max-width:100%}
.shell-switch{position:sticky;top:12px;z-index:2;display:flex;align-items:center;gap:8px;width:fit-content;background:#101721;border:1px solid #405366;border-radius:9px;padding:8px}.shell-switch span{font-size:12px;color:#acbbcc;padding:0 8px}.shell-switch a{padding:9px 14px;border-radius:5px;text-decoration:none}.shell-switch a[aria-current="page"]{background:#80e0c7;color:#0c2524;font-weight:650}.walkthrough h2{scroll-margin-top:88px}
</style><header><div class="brand">PINGFEDERATE / PAR LAB</div><span class="badge">LOCAL DEVELOPMENT</span></header>""" + content +
            "<footer>PingFederate 13.1 · OAuth 2.0 PAR · S256 PKCE · OpenID Connect<br>Tokens remain in server memory. This lab uses a dedicated local test account.</footer></html>").encode()


def curl_guide_source(shell="powershell"):
    filename = {"powershell": "curl-walkthrough.md", "bash": "curl-walkthrough-bash.md"}[shell]
    return Path(__file__).with_name(filename).read_text(encoding="utf-8")


def curl_walkthrough(shell="powershell"):
    """Render our static Markdown guide, escaping all examples and placeholders."""
    source = curl_guide_source(shell)
    sections = [f'<p><a href="/">← Back to demo</a> · <a href="/curl.md?shell={shell}">Markdown source</a></p><main class="walkthrough"><nav class="shell-switch" aria-label="Command shell"><span>Shell</span>']
    for value, label in (("powershell", "PowerShell"), ("bash", "Bash")):
        active = ' aria-current="page"' if value == shell else ""
        sections.append(f'<a href="?shell={value}"{active}>{label}</a>')
    sections.append("</nav>")
    for index, block in enumerate(source.split("```")):
        if index % 2:
            language, _, code = block.partition("\n")
            label = "RESPONSE / HTTP" if language.strip() == "http" else "REQUEST / " + shell.upper()
            sections.append('<div class="code-block"><span class="number">' + label + '</span><pre>' + html.escape(code.rstrip()) + '</pre></div>')
        else:
            for paragraph in block.strip().split("\n\n"):
                if not paragraph:
                    continue
                if paragraph.startswith("# "):
                    sections.append("<h1>" + html.escape(paragraph[2:]) + "</h1>")
                    sections.append('<p>Jump to: <a href="#step-1">Discovery</a> · <a href="#step-2">PAR</a> · <a href="#step-3">Authorization</a> · <a href="#step-4">Login</a> · <a href="#step-5">Consent</a> · <a href="#step-6">Token exchange</a> · <a href="#step-7">Signing keys</a></p>')
                elif paragraph.startswith("## "):
                    title = paragraph[3:]
                    anchor = ' id="step-' + title[0] + '"' if title[:1] in "1234567" else ""
                    sections.append("<h2" + anchor + ">" + html.escape(title) + "</h2>")
                else:
                    sections.append("<p>" + html.escape(paragraph.replace("\n", " ")) + "</p>")
    return "".join(sections) + "</main>"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send(self, status, content=b"", extra=None, content_type="text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "strict-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", f"default-src 'none'; style-src 'unsafe-inline'; form-action 'self' {ISSUER}; frame-ancestors 'none'; base-uri 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if self.path != "/start":
            return self.send(404)
        if self.headers.get("Origin") != ORIGIN:
            return self.send(403, page('<h1>Request rejected</h1><p>Origin check failed.</p>'))
        try:
            config = discovery()
            state, binding, verifier, nonce = (secrets.token_urlsafe(32) for _ in range(4))
            result = pf_request(config["pushed_authorization_request_endpoint"], {
                "client_id": CLIENT, "response_type": "code", "redirect_uri": CALLBACK,
                "scope": "openid", "state": state, "nonce": nonce,
                "code_challenge": b64(hashlib.sha256(verifier.encode()).digest()),
                "code_challenge_method": "S256", "pfidpadapterid": "parDemoHTMLForm",
            }, authenticate=True)
            if not isinstance(result.get("request_uri"), str) or int(result.get("expires_in", 0)) <= 0:
                raise ValueError("Invalid PAR response")
            with LOCK:
                now = time.time()
                for old in [key for key, value in TRANSACTIONS.items() if value["created"] + TTL < now]:
                    del TRANSACTIONS[old]
                if len(TRANSACTIONS) >= 1000:
                    raise ValueError("Too many pending transactions")
                TRANSACTIONS[state] = {"binding": binding, "verifier": verifier, "nonce": nonce, "created": now}
            location = config["authorization_endpoint"] + "?" + urlencode({"client_id": CLIENT, "request_uri": result["request_uri"]})
            self.send(303, extra={"Location": location, "Set-Cookie": "par_tx=" + binding + "; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=600"})
        except Exception:
            self.send(502, page('<h1 class="error">Unable to start login</h1><p>Check PingFederate discovery, TLS trust, and the configured PAR client.</p><a class="link" href="/">Try again</a>'))

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/healthz":
            return self.send(200, b'{"status":"ok"}', content_type="application/json")
        if parsed.path in ("/curl", "/curl.md"):
            shell = parse_qs(parsed.query).get("shell", ["powershell"])[0]
            if shell not in ("powershell", "bash"):
                return self.send(400, page('<h1>Unknown shell</h1><p>Choose powershell or bash.</p>'))
            if parsed.path == "/curl":
                return self.send(200, page(curl_walkthrough(shell)))
            return self.send(200, curl_guide_source(shell).encode(), content_type="text/markdown; charset=utf-8")
        if parsed.path == "/":
            return self.send(200, page('''<div class="eyebrow">A REQUEST, PUSHED FIRST</div><h1>Follow a safer path<br>to authorization.</h1>
<p>Send the authorization payload directly to PingFederate. Your browser carries a short-lived reference, then completes login with a code bound to this client.</p>
<div class="flow"><article class="card"><span class="number">01 / BACK CHANNEL</span><h2>Push the request</h2><p>Authenticate the client and send state, nonce and an S256 challenge to PAR.</p></article>
<article class="card"><span class="number">02 / BROWSER</span><h2>Sign in &amp; consent</h2><p>Use the returned request_uri to continue with your dedicated local account.</p></article>
<article class="card"><span class="number">03 / BACK CHANNEL</span><h2>Exchange &amp; verify</h2><p>Redeem the code with its PKCE verifier. Validate the signed ID token.</p></article></div>
<form method="post" action="/start"><button type="submit">Start PAR login →</button></form><p><a href="/curl">View every request and response in curl →</a></p><p>Test account: <strong>par-demo-user</strong>. Retrieve its password from <code>.local/dev-password</code> in the project.</p>'''))
        if parsed.path != "/callback":
            return self.send(404)
        query = parse_qs(parsed.query)
        clear_cookie = {"Set-Cookie": "par_tx=; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"}
        try:
            if len(query.get("state", [])) != 1:
                raise ValueError("Invalid state")
            state = query["state"][0]
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            binding = cookie["par_tx"].value if "par_tx" in cookie else ""
            with LOCK:
                tx = TRANSACTIONS.get(state)
                if not tx or tx["created"] + TTL < time.time() or not secrets.compare_digest(tx["binding"], binding):
                    raise ValueError("Transaction mismatch")
                del TRANSACTIONS[state]
            if "error" in query or len(query.get("code", [])) != 1:
                raise ValueError("Authorization unsuccessful")
            config = discovery()
            if "iss" in query and query["iss"] != [ISSUER]:
                raise ValueError("Response issuer mismatch")
            tokens = pf_request(config["token_endpoint"], {
                "grant_type": "authorization_code", "code": query["code"][0],
                "redirect_uri": CALLBACK, "code_verifier": tx["verifier"],
            }, authenticate=True)
            if tokens.get("token_type", "").lower() != "bearer" or not tokens.get("access_token"):
                raise ValueError("Unexpected token response")
            claims = validate_id_token(tokens["id_token"], config, tx, tokens["access_token"])
            summary = {"result": "PAR + S256 PKCE completed", "identity": claims,
                       "tokens": {"access_token": "received; value hidden", "id_token": "signature and claims validated", "token_type": tokens["token_type"], "expires_in": tokens.get("expires_in"), "scope": tokens.get("scope")}}
            body = '<div class="eyebrow">ALL THREE STEPS COMPLETE</div><h1 class="success">Authorization verified.</h1><p>The code was exchanged with its PKCE verifier. The ID token passed signature, issuer, audience, expiry and nonce checks.</p><div class="card"><pre>' + html.escape(json.dumps(summary, indent=2)) + '</pre></div><p><a class="link" href="/">Run another login</a></p><p><a href="/curl">View every request and response in curl →</a></p>'
            return self.send(200, page(body), clear_cookie)
        except Exception:
            return self.send(400, page('<h1 class="error">Login could not be verified</h1><p>The transaction expired, was rejected, or failed token validation. Start a new login to retry.</p><a class="link" href="/">Start again</a>'), clear_cookie)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8789), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain("/certs/localhost.pem", "/certs/localhost-key.pem")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print("PAR demo listening on HTTPS port 8789", flush=True)
    server.serve_forever()
