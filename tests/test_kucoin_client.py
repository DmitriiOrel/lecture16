from __future__ import annotations

import base64
import hashlib
import hmac
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from delta_bot.kucoin_client import KuCoinCredentials, KuCoinRestClient


class KuCoinClientTests(unittest.TestCase):
    def test_signature_and_passphrase(self) -> None:
        creds = KuCoinCredentials(
            api_key="k",
            api_secret="secret",
            api_passphrase="pass",
            api_key_version="2",
        )
        client = KuCoinRestClient(credentials=creds)

        payload = "123GET/api/v1/accounts"
        sig = client._sign(payload)  # internal deterministic primitive
        expected_sig = base64.b64encode(
            hmac.new(b"secret", payload.encode("utf-8"), hashlib.sha256).digest()
        ).decode("utf-8")
        self.assertEqual(sig, expected_sig)

        expected_pp = base64.b64encode(
            hmac.new(b"secret", b"pass", hashlib.sha256).digest()
        ).decode("utf-8")
        self.assertEqual(client._signed_passphrase(), expected_pp)

    def test_no_auth_mode(self) -> None:
        client = KuCoinRestClient(credentials=None)
        self.assertFalse(client.has_auth)


if __name__ == "__main__":
    unittest.main()
