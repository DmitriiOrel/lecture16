#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_EXE="${PROJECT_DIR}/venv/bin/python"
if [[ ! -x "$PYTHON_EXE" ]]; then
  PYTHON_EXE="${PYTHON_EXE_OVERRIDE:-python3}"
fi

RUNNER_SCRIPT="${PROJECT_DIR}/run_trade_signal.py"
STATE_JSON="${PROJECT_DIR}/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json"
CONFIG_PATH="${PROJECT_DIR}/config/micro_near_v1_1m.json"
RUN_REAL_ORDER=0
ALLOW_SHORT=0
FORCE_ACTION=""
SPOT_QTY="0.1"
FUTURES_CONTRACTS="1"

usage() {
  cat <<'EOF'
Usage: ./run_kucoin_trade_signal.sh [options]

Options:
  --state-json PATH
  --config PATH
  --python PATH
  --run-real-order
  --allow-short
  --force-action BUY|SELL|HOLD|BUY_BOTH|SELL_BOTH|BUY_SPOT|SELL_SPOT|BUY_FUTURES|SELL_FUTURES
  --spot-qty QTY
  --futures-contracts N
  -h, --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --state-json) STATE_JSON="$2"; shift 2 ;;
    --config) CONFIG_PATH="$2"; shift 2 ;;
    --python) PYTHON_EXE="$2"; shift 2 ;;
    --run-real-order) RUN_REAL_ORDER=1; shift ;;
    --allow-short) ALLOW_SHORT=1; shift ;;
    --force-action)
      FORCE_ACTION="${2^^}"
      if [[ "$FORCE_ACTION" != "BUY" && "$FORCE_ACTION" != "SELL" && "$FORCE_ACTION" != "HOLD" && "$FORCE_ACTION" != "BUY_BOTH" && "$FORCE_ACTION" != "SELL_BOTH" && "$FORCE_ACTION" != "BUY_SPOT" && "$FORCE_ACTION" != "SELL_SPOT" && "$FORCE_ACTION" != "BUY_FUTURES" && "$FORCE_ACTION" != "SELL_FUTURES" ]]; then
        echo "Invalid --force-action: $FORCE_ACTION" >&2
        exit 2
      fi
      shift 2
      ;;
    --spot-qty) SPOT_QTY="$2"; shift 2 ;;
    --futures-contracts) FUTURES_CONTRACTS="$2"; shift 2 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ ! -f "$RUNNER_SCRIPT" ]]; then
  echo "Runner script not found: $RUNNER_SCRIPT" >&2
  exit 2
fi

mkdir -p "${PROJECT_DIR}/logs"
LOG_PATH="${PROJECT_DIR}/logs/kucoin_trade_signal_$(date +%Y%m%d_%H%M%S).log"

ARGS=(
  "$RUNNER_SCRIPT"
  "--state-json" "$STATE_JSON"
  "--config" "$CONFIG_PATH"
)

if [[ $RUN_REAL_ORDER -eq 1 ]]; then
  ARGS+=("--run-real-order")
else
  ARGS+=("--mode" "shadow")
fi
if [[ $ALLOW_SHORT -eq 1 ]]; then
  ARGS+=("--allow-short")
fi
if [[ -n "$FORCE_ACTION" ]]; then
  ARGS+=("--force-action" "$FORCE_ACTION")
  ARGS+=("--spot-qty" "$SPOT_QTY")
  ARGS+=("--futures-contracts" "$FUTURES_CONTRACTS")
fi

echo "Python       : $PYTHON_EXE"
echo "Runner script: $RUNNER_SCRIPT"
echo "State JSON   : $STATE_JSON"
echo "Config       : $CONFIG_PATH"
echo "RunRealOrder : $RUN_REAL_ORDER"
echo "AllowShort   : $ALLOW_SHORT"
echo "ForceAction  : ${FORCE_ACTION:-<none>}"
if [[ -n "$FORCE_ACTION" ]]; then
  echo "SpotQty      : $SPOT_QTY"
  echo "FutContracts : $FUTURES_CONTRACTS"
fi
echo "Log file     : $LOG_PATH"

"$PYTHON_EXE" "${ARGS[@]}" 2>&1 | tee "$LOG_PATH"
STATUS=${PIPESTATUS[0]}

if [[ $STATUS -ne 0 ]]; then
  echo "run_trade_signal.py finished with exit code $STATUS" >&2
  exit $STATUS
fi

echo "Done. ExitCode=0"
