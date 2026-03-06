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

    def test_retry_on_invalid_timestamp(self) -> None:
        class _FakeResponse:
            def __init__(self, status_code: int, payload: dict, text: str = ""):
                self.status_code = status_code
                self._payload = payload
                self.text = text or str(payload)

            def json(self):
                return self._payload

        class _FakeSession:
            def __init__(self):
                self.request_calls = 0
                self.get_calls = 0

            def request(self, **kwargs):
                self.request_calls += 1
                if self.request_calls == 1:
                    return _FakeResponse(
                        400,
                        {"code": "400002", "msg": "Invalid KC-API-TIMESTAMP"},
                        text='{"code":"400002","msg":"Invalid KC-API-TIMESTAMP"}',
                    )
                return _FakeResponse(
                    200,
                    {"code": "200000", "data": [{"available": "1.0", "holds": "0.0"}]},
                )

            def get(self, **kwargs):
                self.get_calls += 1
                return _FakeResponse(200, {"code": "200000", "data": 1700000000000})

        creds = KuCoinCredentials(
            api_key="k",
            api_secret="secret",
            api_passphrase="pass",
            api_key_version="2",
        )
        client = KuCoinRestClient(credentials=creds)
        fake = _FakeSession()
        client._session = fake  # inject fake transport
        balance = client.get_spot_account_balance("USDT", account_type="trade")
        self.assertEqual(balance, 1.0)
        self.assertEqual(fake.request_calls, 2)
        self.assertGreaterEqual(fake.get_calls, 1)


if __name__ == "__main__":
    unittest.main()
