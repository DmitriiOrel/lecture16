from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests


class KuCoinApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class KuCoinCredentials:
    api_key: str
    api_secret: str
    api_passphrase: str
    api_key_version: str = "2"


class KuCoinRestClient:
    def __init__(
        self,
        credentials: Optional[KuCoinCredentials] = None,
        spot_base_url: str = "https://api.kucoin.com",
        futures_base_url: str = "https://api-futures.kucoin.com",
        timeout_s: int = 15,
    ):
        self.credentials = credentials
        self.spot_base_url = spot_base_url.rstrip("/")
        self.futures_base_url = futures_base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._session = requests.Session()

    @classmethod
    def from_env(cls) -> "KuCoinRestClient":
        key = os.getenv("KUCOIN_API_KEY", "")
        secret = os.getenv("KUCOIN_API_SECRET", "")
        passphrase = os.getenv("KUCOIN_API_PASSPHRASE", "")
        version = os.getenv("KUCOIN_KEY_VERSION", "2")
        creds = None
        if key and secret and passphrase:
            creds = KuCoinCredentials(
                api_key=key,
                api_secret=secret,
                api_passphrase=passphrase,
                api_key_version=version,
            )
        return cls(credentials=creds)

    @property
    def has_auth(self) -> bool:
        return self.credentials is not None

    def _sign(self, payload: str) -> str:
        if self.credentials is None:
            raise KuCoinApiError("Authenticated endpoint requested but credentials are missing")
        digest = hmac.new(
            self.credentials.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _signed_passphrase(self) -> str:
        if self.credentials is None:
            raise KuCoinApiError("Authenticated endpoint requested but credentials are missing")
        if self.credentials.api_key_version != "2":
            return self.credentials.api_passphrase
        digest = hmac.new(
            self.credentials.api_secret.encode("utf-8"),
            self.credentials.api_passphrase.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _request(
        self,
        *,
        base_url: str,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        auth: bool = False,
    ) -> Dict[str, Any]:
        method_u = method.upper()
        query = ""
        if params:
            query = urlencode(params, doseq=True)
        path_with_query = endpoint if not query else f"{endpoint}?{query}"
        url = f"{base_url}{path_with_query}"

        body_str = ""
        if body is not None:
            body_str = json.dumps(body, separators=(",", ":"))

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if auth:
            if self.credentials is None:
                raise KuCoinApiError("Authenticated endpoint requested but credentials are missing")
            ts = str(int(time.time() * 1000))
            payload = f"{ts}{method_u}{path_with_query}{body_str}"
            headers.update(
                {
                    "KC-API-KEY": self.credentials.api_key,
                    "KC-API-SIGN": self._sign(payload),
                    "KC-API-TIMESTAMP": ts,
                    "KC-API-PASSPHRASE": self._signed_passphrase(),
                    "KC-API-KEY-VERSION": self.credentials.api_key_version,
                }
            )

        response = self._session.request(
            method=method_u,
            url=url,
            params=None,
            data=body_str if body is not None else None,
            headers=headers,
            timeout=self.timeout_s,
        )
        if response.status_code >= 400:
            raise KuCoinApiError(f"HTTP {response.status_code}: {response.text}")

        payload = response.json()
        if payload.get("code") != "200000":
            raise KuCoinApiError(str(payload))
        return payload

    # Public data
    def get_spot_candles(
        self,
        symbol: str,
        candle_type: str,
        start_at: Optional[int] = None,
        end_at: Optional[int] = None,
    ) -> List[List[Any]]:
        params: Dict[str, Any] = {"symbol": symbol, "type": candle_type}
        if start_at is not None:
            params["startAt"] = int(start_at)
        if end_at is not None:
            params["endAt"] = int(end_at)
        payload = self._request(
            base_url=self.spot_base_url,
            method="GET",
            endpoint="/api/v1/market/candles",
            params=params,
            auth=False,
        )
        return payload["data"]

    def get_futures_candles(
        self,
        symbol: str,
        granularity: int,
        from_ts_ms: Optional[int] = None,
        to_ts_ms: Optional[int] = None,
    ) -> List[List[Any]]:
        params: Dict[str, Any] = {"symbol": symbol, "granularity": int(granularity)}
        if from_ts_ms is not None:
            params["from"] = int(from_ts_ms)
        if to_ts_ms is not None:
            params["to"] = int(to_ts_ms)
        payload = self._request(
            base_url=self.futures_base_url,
            method="GET",
            endpoint="/api/v1/kline/query",
            params=params,
            auth=False,
        )
        return payload["data"]

    def get_spot_ticker(self, symbol: str) -> Dict[str, Any]:
        payload = self._request(
            base_url=self.spot_base_url,
            method="GET",
            endpoint="/api/v1/market/orderbook/level1",
            params={"symbol": symbol},
            auth=False,
        )
        return payload["data"]

    def get_futures_ticker(self, symbol: str) -> Dict[str, Any]:
        payload = self._request(
            base_url=self.futures_base_url,
            method="GET",
            endpoint="/api/v1/ticker",
            params={"symbol": symbol},
            auth=False,
        )
        return payload["data"]

    # Private data
    def get_spot_account_balance(self, currency: str, account_type: str = "trade") -> float:
        payload = self._request(
            base_url=self.spot_base_url,
            method="GET",
            endpoint="/api/v1/accounts",
            params={"currency": currency, "type": account_type},
            auth=True,
        )
        rows = payload["data"]
        if not rows:
            return 0.0
        available = float(rows[0].get("available", 0.0))
        holds = float(rows[0].get("holds", 0.0))
        return available + holds

    def get_futures_position_contracts(self, symbol: str) -> int:
        try:
            payload = self._request(
                base_url=self.futures_base_url,
                method="GET",
                endpoint="/api/v1/position",
                params={"symbol": symbol},
                auth=True,
            )
            data = payload.get("data") or {}
            return int(float(data.get("currentQty", 0)))
        except KuCoinApiError:
            payload = self._request(
                base_url=self.futures_base_url,
                method="GET",
                endpoint="/api/v1/positions",
                auth=True,
            )
            rows = payload.get("data", [])
            for row in rows:
                if row.get("symbol") == symbol:
                    return int(float(row.get("currentQty", 0)))
            return 0

    def get_futures_account_equity(self, currency: str = "USDT") -> float:
        payload = self._request(
            base_url=self.futures_base_url,
            method="GET",
            endpoint="/api/v1/account-overview",
            params={"currency": currency},
            auth=True,
        )
        data = payload.get("data") or {}
        for key in ("accountEquity", "marginBalance"):
            if key in data:
                return float(data[key])
        return 0.0

    # Order placement
    def place_spot_market_order(self, symbol: str, side: str, size: float) -> Dict[str, Any]:
        body = {
            "clientOid": uuid.uuid4().hex,
            "symbol": symbol,
            "side": side,
            "type": "market",
            "size": f"{size:.8f}".rstrip("0").rstrip("."),
        }
        payload = self._request(
            base_url=self.spot_base_url,
            method="POST",
            endpoint="/api/v1/orders",
            body=body,
            auth=True,
        )
        return payload["data"]

    def place_futures_market_order(
        self,
        symbol: str,
        side: str,
        contracts: int,
        leverage: str = "1",
        margin_mode: str = "CROSS",
    ) -> Dict[str, Any]:
        body = {
            "clientOid": uuid.uuid4().hex,
            "symbol": symbol,
            "side": side,
            "type": "market",
            "size": int(contracts),
            "leverage": str(leverage),
            "marginMode": margin_mode,
        }
        payload = self._request(
            base_url=self.futures_base_url,
            method="POST",
            endpoint="/api/v1/orders",
            body=body,
            auth=True,
        )
        return payload["data"]
