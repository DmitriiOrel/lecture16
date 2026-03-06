from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def configure_console_utf8() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-platform launcher for trade_signal_executor_kucoin.py. "
            "Finds latest_forecast_signal_*.json in Downloads/reports and runs execution CLI."
        )
    )
    parser.add_argument("--state-json", default="", help="Path to state JSON (optional)")
    parser.add_argument(
        "--config",
        default="config/micro_near_v1_1m.json",
        help="Bot config path (default: 1m config).",
    )
    parser.add_argument(
        "--mode",
        choices=["shadow", "live"],
        default="shadow",
        help="Executor mode.",
    )
    parser.add_argument(
        "--run-real-order",
        action="store_true",
        help="Allow real order sending (forces live mode).",
    )
    parser.add_argument(
        "--force-action",
        choices=[
            "BUY",
            "SELL",
            "HOLD",
            "BUY_BOTH",
            "SELL_BOTH",
            "BUY_SPOT",
            "SELL_SPOT",
            "BUY_FUTURES",
            "SELL_FUTURES",
        ],
        default="",
        help="Force BUY/SELL/HOLD for integration testing.",
    )
    parser.add_argument(
        "--spot-qty",
        type=float,
        default=0.1,
        help="Spot order size for manual force actions.",
    )
    parser.add_argument(
        "--futures-contracts",
        type=int,
        default=1,
        help="Futures contracts size for manual force actions.",
    )
    parser.add_argument(
        "--allow-short",
        action="store_true",
        help="Allow short target calculation in policy (spot short may still be blocked).",
    )
    parser.add_argument(
        "--expected-slippage-bps",
        type=float,
        default=3.0,
        help="Expected slippage used by risk engine.",
    )
    parser.add_argument(
        "--search-downloads-only",
        action="store_true",
        help="Search state JSON only in Downloads folders.",
    )
    parser.add_argument("--python-exe", default=sys.executable, help="Python executable to use")
    parser.add_argument("--show-command", action="store_true", help="Print exact underlying command")
    return parser.parse_args()


def candidate_dirs(repo_root: Path, downloads_only: bool) -> list[Path]:
    home = Path.home()
    dirs = []
    if not downloads_only:
        dirs.append(repo_root / "reports")
    for name in ("Downloads", "downloads", "Загрузки"):
        d = home / name
        if d.exists():
            dirs.append(d)
    out = []
    seen = set()
    for d in dirs:
        key = str(d.resolve()) if d.exists() else str(d)
        if key not in seen:
            out.append(d)
            seen.add(key)
    return out


def find_latest_state_json(repo_root: Path, downloads_only: bool) -> Path | None:
    found: list[Path] = []
    for base in candidate_dirs(repo_root, downloads_only):
        if not base.exists():
            continue
        try:
            found.extend(base.rglob("latest_forecast_signal_*.json"))
        except Exception:
            continue
    if not found:
        return None
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0]


def main() -> int:
    configure_console_utf8()
    args = parse_args()

    repo_root = Path(__file__).resolve().parent
    executor = repo_root / "trade_signal_executor_kucoin.py"
    if not executor.exists():
        print(f"Executor script not found: {executor}", file=sys.stderr)
        return 2

    state_json: Path
    if args.state_json:
        state_json = Path(args.state_json).expanduser()
        if not state_json.is_absolute():
            state_json = (Path.cwd() / state_json).resolve()
        if not state_json.exists():
            print(f"State JSON not found: {state_json}", file=sys.stderr)
            return 2
    else:
        auto = find_latest_state_json(repo_root, downloads_only=args.search_downloads_only)
        if auto is None:
            print(
                "No state JSON found. Put latest_forecast_signal_*.json in Downloads or repo/reports,\n"
                "or pass --state-json <path>.",
                file=sys.stderr,
            )
            return 2
        state_json = auto

    mode = "live" if args.run_real_order else args.mode

    cmd = [
        str(Path(args.python_exe)),
        str(executor),
        "--state-json",
        str(state_json),
        "--config",
        str(args.config),
        "--mode",
        mode,
        "--expected-slippage-bps",
        str(args.expected_slippage_bps),
    ]
    if args.run_real_order:
        cmd.append("--run-real-order")
    if args.force_action:
        cmd.extend(["--force-action", args.force_action])
        cmd.extend(["--spot-qty", str(args.spot_qty)])
        cmd.extend(["--futures-contracts", str(args.futures_contracts)])
    if args.allow_short:
        cmd.append("--allow-short")

    print("Python      :", Path(args.python_exe))
    print("Executor    :", executor)
    print("State JSON  :", state_json)
    print("Mode        :", mode)
    print("ForceAction :", args.force_action or "(none)")
    if args.force_action:
        print("SpotQty     :", args.spot_qty)
        print("FutContracts:", args.futures_contracts)
    print("AllowShort  :", bool(args.allow_short))
    print("Config      :", args.config)
    if args.show_command:
        print("Command     :", " ".join(cmd))

    completed = subprocess.run(cmd, env=os.environ.copy())
    return int(completed.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
