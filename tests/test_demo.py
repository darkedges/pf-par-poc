"""Exercise transaction binding and OIDC validation with a local mock provider."""
import base64
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("demo_app", ROOT / "demo/app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key())) | {"kid": "test-key"}
CONFIG = {"issuer": app.ISSUER, "jwks_uri": app.ISSUER + "/pf/JWKS",
          "token_endpoint": app.ISSUER + "/as/token.oauth2",
          "authorization_endpoint": app.ISSUER + "/as/authorization.oauth2",
          "pushed_authorization_request_endpoint": app.ISSUER + "/as/par.oauth2"}


class FlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        app.TRANSACTIONS.clear()

    def request(self, method, path, headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        client.request(method, path, headers=headers or {})
        response = client.getresponse()
        result = response.status, dict(response.getheaders()), response.read().decode()
        client.close()
        return result

    def test_cross_origin_start_is_rejected_without_provider_request(self):
        with patch.object(app, "pf_request") as upstream:
            status, _, _ = self.request("POST", "/start", {"Origin": "https://other.example"})
            self.assertEqual(status, 403)
            upstream.assert_not_called()

    def test_curl_guide_covers_flow_without_loading_credentials_into_examples(self):
        with patch.object(app, "pf_request") as upstream:
            status, _, body = self.request("GET", "/curl")
            self.assertEqual(status, 200)
            for endpoint in ("/.well-known/openid-configuration", "/as/par.oauth2", "/as/authorization.oauth2", "/as/token.oauth2", "/pf/JWKS", "/callback"):
                self.assertIn(endpoint, body)
            self.assertIn("pf.oauth.authz.consent=allow", body)
            self.assertIn("&lt;OPAQUE_REFERENCE_ACCESS_TOKEN&gt;", body)
            self.assertFalse(app.SECRET in body, "curl guide contains a client credential")
            upstream.assert_not_called()

    def test_curl_markdown_can_be_retrieved(self):
        status, headers, body = self.request("GET", "/curl.md")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/markdown"))
        self.assertIn("code_verifier=$Verifier", body)

    def test_bash_flag_switches_commands_and_markdown_together(self):
        status, _, body = self.request("GET", "/curl?shell=bash")
        self.assertEqual(status, 200)
        self.assertIn('href="?shell=bash" aria-current="page"', body)
        self.assertIn('/curl.md?shell=bash', body)
        self.assertIn("REQUEST / BASH", body)
        self.assertNotIn("curl.exe", body)
        self.assertNotIn("Get-Content", body)
        status, _, source = self.request("GET", "/curl.md?shell=bash")
        self.assertEqual(status, 200)
        self.assertIn('curl "${CurlCommon[@]}"', source)
        self.assertIn("openssl dgst -sha256 -binary", source)
        self.assertNotIn("```powershell", source)

    def test_unknown_shell_is_rejected(self):
        self.assertEqual(self.request("GET", "/curl?shell=unknown")[0], 400)
        self.assertEqual(self.request("GET", "/curl.md?shell=unknown")[0], 400)

    def test_start_pushes_pkce_and_redirects_with_reference_only(self):
        with patch.object(app, "discovery", return_value=CONFIG), patch.object(app, "pf_request", return_value={"request_uri": "urn:test:reference", "expires_in": 120}) as upstream:
            status, headers, _ = self.request("POST", "/start", {"Origin": app.ORIGIN})
            self.assertEqual(status, 303)
            self.assertIn("request_uri=urn%3Atest%3Areference", headers["Location"])
            self.assertNotIn("code_challenge", headers["Location"])
            self.assertIn("Secure; HttpOnly; SameSite=Lax", headers["Set-Cookie"])
            self.assertEqual(headers["Referrer-Policy"], "strict-origin")
            self.assertIn("form-action 'self' " + app.ISSUER, headers["Content-Security-Policy"])
            fields = upstream.call_args.args[1]
            tx = app.TRANSACTIONS[fields["state"]]
            self.assertEqual(fields["code_challenge"], app.b64(hashlib.sha256(tx["verifier"].encode()).digest()))
            self.assertEqual(fields["code_challenge_method"], "S256")
            self.assertTrue(upstream.call_args.kwargs["authenticate"])

    def transaction(self):
        tx = {"binding": "browser-cookie", "verifier": "verifier", "nonce": "nonce", "created": time.time()}
        app.TRANSACTIONS["state"] = tx
        return tx

    def token(self, **changes):
        claims = {"iss": app.ISSUER, "aud": app.CLIENT, "sub": "par-demo-user", "iat": int(time.time()), "exp": int(time.time()) + 300, "nonce": "nonce"} | changes
        return jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": "test-key"})

    def test_cookie_mismatch_does_not_redeem_or_consume_code(self):
        self.transaction()
        with patch.object(app, "pf_request") as upstream:
            status, _, _ = self.request("GET", "/callback?state=state&code=secret-code", {"Cookie": "par_tx=wrong"})
            self.assertEqual(status, 400)
            upstream.assert_not_called()
            self.assertIn("state", app.TRANSACTIONS)

    def test_callback_validates_signed_id_token_hides_tokens_and_rejects_replay(self):
        self.transaction()
        raw = self.token()
        def provider(url, fields=None, authenticate=False):
            if url == CONFIG["jwks_uri"]:
                return {"keys": [JWK]}
            self.assertEqual(fields["code_verifier"], "verifier")
            self.assertTrue(authenticate)
            return {"access_token": "private-access-token", "id_token": raw, "token_type": "Bearer", "expires_in": 300}
        with patch.object(app, "discovery", return_value=CONFIG), patch.object(app, "pf_request", side_effect=provider):
            status, headers, body = self.request("GET", "/callback?state=state&code=secret-code", {"Cookie": "par_tx=browser-cookie"})
            self.assertEqual(status, 200)
            self.assertIn("Authorization verified", body)
            self.assertNotIn("private-access-token", body)
            self.assertNotIn(raw, body)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(self.request("GET", "/callback?state=state&code=secret-code", {"Cookie": "par_tx=browser-cookie"})[0], 400)

    def test_wrong_nonce_issuer_audience_expiry_and_signature_are_rejected(self):
        tx = self.transaction()
        with patch.object(app, "pf_request", return_value={"keys": [JWK]}):
            for change in ({"nonce": "wrong"}, {"iss": "https://wrong.example"}, {"aud": "wrong-client"}, {"exp": 1}):
                with self.subTest(change=change), self.assertRaises(Exception):
                    app.validate_id_token(self.token(**change), CONFIG, tx, "access")
            other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            forged = jwt.encode({"iss": app.ISSUER}, other_key, algorithm="RS256", headers={"kid": "test-key"})
            with self.assertRaises(jwt.InvalidSignatureError):
                app.validate_id_token(forged, CONFIG, tx, "access")

    def test_expired_transaction_is_rejected(self):
        self.transaction()["created"] = time.time() - app.TTL - 1
        with patch.object(app, "pf_request") as upstream:
            self.assertEqual(self.request("GET", "/callback?state=state&code=code", {"Cookie": "par_tx=browser-cookie"})[0], 400)
            upstream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
