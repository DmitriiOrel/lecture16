# lecture16: LSTM + GARCH + Kelly Delta-Hedge (KuCoin)

Проект для минутной торговли `NEAR-USDT` (spot) + `NEARUSDTM` (futures) на KuCoin.

Логика:
- `LSTM` прогнозирует цену на **1 минуту вперед**.
- `GARCH` считает `sigma_hat` по **доходностям** (returns), не по цене.
- Размер позиции: **Kelly**
  - `z = ret_hat / (sigma_hat^2 + eps)`
  - `notional = 1.5 * 0.5 * clip(z, -2, 2)`
- После целевого spot бот строит хедж во futures (`hedge_ratio = -1`).

## Основные файлы

- `notebooks/final_ml_rl_kucoin_demo.ipynb` — Colab/Notebook пайплайн с кириллицей.
- `src/delta_bot/signal.py` — LSTM+GARCH сигнал.
- `src/delta_bot/policy.py` — Kelly sizing + target spot/futures.
- `trade_signal_executor_kucoin.py` — исполнение state JSON -> ордера KuCoin.
- `run_trade_signal.py` — удобный launcher.
- `config/micro_near_v1_1m.json` — минутный торговый конфиг.

## Colab

- https://colab.research.google.com/github/DmitriiOrel/lecture16/blob/master/notebooks/final_ml_rl_kucoin_demo.ipynb

## Установка

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
# source venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 1) Получить JSON сигнала из ноутбука

После выполнения ноутбука создается:
- `notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json`

## 2) Проверка в shadow-режиме

```bash
python run_trade_signal.py --mode shadow --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json
```

## 3) Live-торговля

```bash
# Windows PowerShell
$env:KUCOIN_API_KEY="YOUR_KEY"
$env:KUCOIN_API_SECRET="YOUR_SECRET"
$env:KUCOIN_API_PASSPHRASE="YOUR_PASSPHRASE"

python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json
```

## Ручные команды (интеграционные)

```bash
# Покупка только spot NEAR
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json --force-action BUY_SPOT --spot-qty 0.1

# Покупка обеих ног
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json --force-action BUY_BOTH --spot-qty 0.1 --futures-contracts 1
```

## Тесты

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## Безопасность

- Не храните API-ключи в репозитории.
- Сначала запускайте `shadow`, потом `live`.
- Если ключи были опубликованы, сразу перевыпустите их в KuCoin.
