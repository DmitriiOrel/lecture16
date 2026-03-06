from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path


@dataclass
class RuntimeState:
    state_date: str
    peak_equity_usdt: float
    day_start_equity_usdt: float
    api_error_streak: int

    @classmethod
    def initial(cls, equity_usdt: float) -> "RuntimeState":
        today = date.today().isoformat()
        return cls(
            state_date=today,
            peak_equity_usdt=equity_usdt,
            day_start_equity_usdt=equity_usdt,
            api_error_streak=0,
        )

    def roll_day_if_needed(self, equity_usdt: float) -> None:
        today = date.today().isoformat()
        if self.state_date != today:
            self.state_date = today
            self.day_start_equity_usdt = equity_usdt
            self.api_error_streak = 0
        if equity_usdt > self.peak_equity_usdt:
            self.peak_equity_usdt = equity_usdt


class JsonStateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self, default_equity_usdt: float) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState.initial(default_equity_usdt)
        with self.path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return RuntimeState(
            state_date=payload["state_date"],
            peak_equity_usdt=float(payload["peak_equity_usdt"]),
            day_start_equity_usdt=float(payload["day_start_equity_usdt"]),
            api_error_streak=int(payload.get("api_error_streak", 0)),
        )

    def save(self, state: RuntimeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(asdict(state), fh, indent=2)
