"""Read-only runtime checks against the dedicated local PF PAR client.

Successful PAR creates an expiring request reference; no server configuration changes.
Prints test names only, never credentials, tokens, or request references.
"""
import base64
import hashlib
import http.cookiejar
import json
from pathlib import Path
import secrets
import ssl
import unittest
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit, urljoin
from urllib.request import HTTPSHandler, HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
ISSUER = "https://localhost:9032"
CLIENT = "par-browser-demo"
SECRET = (ROOT / ".local/client-secret").read_text().strip()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


HTTP = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=str(ROOT / "certs/ca.pem"))), NoRedirect())


def request(path, fields=None, secret=SECRET):
    headers = {"Accept": "application/json"}
    if fields is not None:
        headers["Authorization"] = "Basic " + base64.b64encode((CLIENT + ":" + secret).encode()).decode()
    req = Request(ISSUER + path, data=None if fields is None else urlencode(fields).encode(), headers=headers)
    try:
        with HTTP.open(req, timeout=20) as res:
            return res.status, dict(res.headers), res.read()
    except HTTPError as res:
        return res.code, dict(res.headers), res.read()


def payload():
    verifier = secrets.token_urlsafe(32)
    return {"client_id": CLIENT, "response_type": "code", "scope": "openid", "redirect_uri": "https://localhost:8789/callback", "state": secrets.token_urlsafe(32), "nonce": secrets.token_urlsafe(32), "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode(), "code_challenge_method": "S256", "pfidpadapterid": "parDemoHTMLForm"}


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {"action": attrs.get("action", ""), "fields": {}}
            self.forms.append(self.current)
        elif tag == "input" and self.current is not None and attrs.get("name"):
            self.current["fields"][attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


class LocalBrowserRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != "https":
            raise ValueError("Unexpected browser redirect scheme")
        if target.netloc == "localhost:8789" and target.path == "/callback":
            return None  # Capture the code for the deliberately invalid exchange.
        if target.netloc != "localhost:9032":
            raise ValueError("Unexpected browser redirect host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def authorization_code_for_negative_test(test):
    data = payload()
    status, _, body = request("/as/par.oauth2", data)
    test.assertEqual(status, 201)
    url = ISSUER + "/as/authorization.oauth2?" + urlencode({"client_id": CLIENT, "request_uri": json.loads(body)["request_uri"]})
    browser = build_opener(
        HTTPSHandler(context=ssl.create_default_context(cafile=str(ROOT / "certs/ca.pem"))),
        HTTPCookieProcessor(http.cookiejar.CookieJar()), LocalBrowserRedirect(),
    )
    with browser.open(url, timeout=20) as response:
        url, body = response.url, response.read().decode()
    parser = FormParser()
    parser.feed(body)
    form = next(form for form in parser.forms if "pf.pass" in form["fields"])
    form["fields"].update({"pf.username": "par-demo-user", "pf.pass": (ROOT / ".local/dev-password").read_text().strip(), "pf.ok": "clicked"})
    action = urljoin(url, form["action"])
    test.assertEqual(urlsplit(action).netloc, "localhost:9032")
    with browser.open(Request(action, data=urlencode(form["fields"]).encode()), timeout=20) as response:
        url, body = response.url, response.read().decode()
    parser = FormParser()
    parser.feed(body)
    form = next(form for form in parser.forms if "pf.oauth.authz.consent" in form["fields"])
    form["fields"]["pf.oauth.authz.consent"] = "allow"
    action = urljoin(url, form["action"])
    test.assertEqual(urlsplit(action).netloc, "localhost:9032")
    try:
        browser.open(Request(action, data=urlencode(form["fields"]).encode()), timeout=20)
        raise AssertionError("Expected authorization-code redirect")
    except HTTPError as response:
        test.assertIn(response.code, (302, 303))
        callback = urlsplit(response.headers["Location"])
        test.assertEqual(callback.netloc, "localhost:8789")
        query = parse_qs(callback.query)
        test.assertEqual(query["state"], [data["state"]])
        return query["code"][0]


class LiveTests(unittest.TestCase):
    def test_code_exchange_rejects_wrong_pkce_verifier(self):
        code = authorization_code_for_negative_test(self)
        status, _, body = request("/as/token.oauth2", {
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": "https://localhost:8789/callback", "code_verifier": secrets.token_urlsafe(32),
        })
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid_grant")

    def test_discovery_advertises_par(self):
        status, _, body = request("/.well-known/openid-configuration")
        self.assertEqual(status, 200)
        config = json.loads(body)
        self.assertEqual(config["issuer"], ISSUER)
        self.assertEqual(config["pushed_authorization_request_endpoint"], ISSUER + "/as/par.oauth2")

    def test_authenticated_par_returns_expiring_reference(self):
        status, _, body = request("/as/par.oauth2", payload())
        self.assertEqual(status, 201)
        data = json.loads(body)
        self.assertTrue(data["request_uri"].startswith("urn:"))
        self.assertGreater(data["expires_in"], 0)
        self.assertLessEqual(data["expires_in"], 120)

    def test_par_rejects_bad_client_secret(self):
        status, _, body = request("/as/par.oauth2", payload(), secret="invalid-secret")
        self.assertIn(status, (400, 401))
        self.assertEqual(json.loads(body)["error"], "invalid_client")

    def test_par_rejects_missing_pkce(self):
        data = payload()
        del data["code_challenge"]
        del data["code_challenge_method"]
        status, _, body = request("/as/par.oauth2", data)
        self.assertEqual(status, 400)
        self.assertIn(json.loads(body)["error"], ("invalid_request", "invalid_request_object"))

    def test_client_cannot_bypass_par(self):
        status, headers, body = request("/as/authorization.oauth2?" + urlencode(payload()))
        if status in (302, 303):
            target = urlsplit(headers["Location"])
            self.assertEqual(target.netloc, "localhost:8789")
            self.assertIn("error", parse_qs(target.query))
        else:
            self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
