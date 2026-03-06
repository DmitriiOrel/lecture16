# lecture16: KuCoin RL bot (stable shadow run)

This README intentionally contains only the flow that is reproducible every time.
It runs the bot in `shadow` mode (no real orders).

## 1) Clone

```powershell
cd $HOME
if (Test-Path .\lecture16) { Remove-Item -Recurse -Force .\lecture16 }
git clone https://github.com/DmitriiOrel/lecture16.git
cd .\lecture16
```

## 2) Create venv and install

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

## 3) Check deps

```powershell
python -c "import tensorflow as tf; import arch; print('OK')"
```

Expected: `OK`

## 4) Check JSON from Colab

```powershell
Get-ChildItem "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json"
```

If file is missing, export/download it from:

- `notebooks/final_ml_rl_kucoin_demo.ipynb`

## 5) Force clean shadow mode (always)

Important: clear KuCoin env vars before shadow run.
This removes dependency on API auth and prevents passphrase/timestamp errors.

```powershell
Remove-Item Env:KUCOIN_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:KUCOIN_API_SECRET -ErrorAction SilentlyContinue
Remove-Item Env:KUCOIN_API_PASSPHRASE -ErrorAction SilentlyContinue
Remove-Item Env:KUCOIN_KEY_VERSION -ErrorAction SilentlyContinue
```

Run:

```powershell
python run_trade_signal.py --mode shadow --config config/micro_near_v1_1m.json --state-json "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json"
```

Expected in output:

- `Mode            : shadow`
- `Risk            : True - OK` (or a clear risk reason)
- `Sent orders     : 0`
- `Report saved    : ...\reports\kucoin_rl\strategy_state_kucoin.json`

## 6) If JSON path changes

Use auto-search in Downloads:

```powershell
python run_trade_signal.py --mode shadow --config config/micro_near_v1_1m.json --search-downloads-only
```

## 7) What this guarantees

- No real orders are sent.
- No dependency on API key/passphrase validity.
- No failure from KuCoin auth errors in shadow mode.

## 8) Live trading

Live commands are intentionally excluded from this README to keep this guide 100% reproducible.
