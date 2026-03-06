# Торговая логика LSTM + GARCH + Kelly + торговые скрипты KuCoin

Репозиторий содержит:

- `notebooks/final_ml_rl_kucoin_demo.ipynb` - учебный ноутбук (в стиле лекций), где считаются LSTM-прогноз, GARCH-волатильность, Kelly-сигнал и формируется JSON для терминального бота.
- `trade_signal_executor_kucoin.py` - CLI-исполнитель стратегии (POLICY / FORCED actions).
- `run_trade_signal.py` - универсальный кроссплатформенный Python-раннер (автопоиск `latest_forecast_signal_*.json` в `Downloads` / `reports`).
- `run_kucoin_trade_signal.ps1` - обертка для Windows PowerShell.
- `run_kucoin_trade_signal.sh` - обертка для macOS / Linux.
- `src/delta_bot/*.py` - ядро логики сигнала, risk engine, policy, execution, KuCoin REST client.
- `config/micro_near_v1_1m.json` - профиль для минутного запуска (основной).
- `config/micro_near_v1.json` - профиль для 15m сценария.

## Торговая логика LSTM + GARCH + Kelly

- LSTM прогнозирует цену `NEAR-USDT` на 1 минуту вперед.
- `ret_hat` считается как лог-доходность из прогноза LSTM.
- `sigma_hat` считается через GARCH строго по доходностям `returns = log(P_t / P_{t-1})`.
- Kelly-сигнал:
  - `z = ret_hat / (sigma_hat^2 + eps)`
  - `z` ограничивается: `clip(-2, 2)`
- Размер входа в notional:
  - `target_notional_usdt = 1.5 * 0.5 * z`
- После расчета целевой spot-позиции строится futures-хедж (`target_hedge_ratio = -1`).

## 1) Клонирование репозитория

```bash
git clone https://github.com/DmitriiOrel/lecture16.git
cd lecture16
```

Если `git pull` показывает другой репозиторий или `unrelated histories`, сделайте чистый reclone:

```powershell
cd $HOME
Remove-Item -Recurse -Force .\lecture16
git clone https://github.com/DmitriiOrel/lecture16.git
cd .\lecture16
```

## 2) Google Colab (анализ и генерация сигнала)

1. Откройте в Google Colab:
   - `notebooks/final_ml_rl_kucoin_demo.ipynb`
2. Запустите первую install-ячейку.
3. После первой установки сделайте `Runtime -> Restart runtime`.
4. Запустите ноутбук сверху вниз.
5. Ноутбук сохраняет JSON с последним сигналом в:
   - `reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json`

## 3) Локальная установка (Windows / macOS / Linux)

### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
chmod +x run_kucoin_trade_signal.sh
```

Проверка импорта:

```bash
python -c "import tensorflow as tf; import arch; print('OK')"
```

## 4) Проверка, что JSON действительно сохранен

### Windows PowerShell

```powershell
Get-ChildItem $HOME\Downloads\latest_forecast_signal_*.json
Get-ChildItem .\reports\kucoin_rl\latest_forecast_signal_*.json
Get-ChildItem .\notebooks\reports\kucoin_rl\latest_forecast_signal_*.json
```

### macOS / Linux

```bash
ls -1 ~/Downloads/latest_forecast_signal_*.json
ls -1 ./reports/kucoin_rl/latest_forecast_signal_*.json
ls -1 ./notebooks/reports/kucoin_rl/latest_forecast_signal_*.json
```

## 5) Универсальный запуск торговой логики (рекомендуется)

### Шаг 1. Задайте API переменные

Windows PowerShell:

```powershell
$env:KUCOIN_API_KEY = "YOUR_KEY"
$env:KUCOIN_API_SECRET = "YOUR_SECRET"
$env:KUCOIN_API_PASSPHRASE = "YOUR_PASSPHRASE"
$env:KUCOIN_KEY_VERSION = "2"
```

macOS / Linux:

```bash
export KUCOIN_API_KEY="YOUR_KEY"
export KUCOIN_API_SECRET="YOUR_SECRET"
export KUCOIN_API_PASSPHRASE="YOUR_PASSPHRASE"
export KUCOIN_KEY_VERSION="2"
```

### Шаг 2. Тестовый запуск без отправки ордера

```bash
python run_trade_signal.py --mode shadow --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json
```

### Шаг 3. Реальный запуск

```bash
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json
```

### Шаг 4. Принудительный тест BUY/SELL

```bash
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json --force-action BUY_SPOT --spot-qty 0.1
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json --force-action SELL_SPOT --spot-qty 0.1

# обе ноги одновременно
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json --force-action BUY_BOTH --spot-qty 0.1 --futures-contracts 1
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json --force-action SELL_BOTH --spot-qty 0.1 --futures-contracts 1
```

Если JSON лежит в нестандартной папке:

```bash
python run_trade_signal.py --config config/micro_near_v1_1m.json --state-json "C:/Users/your_user/Downloads/latest_forecast_signal_kucoin_rl.json"
```

## 6) Запуск через платформенные обертки (опционально)

### Windows PowerShell

```powershell
$env:KUCOIN_API_KEY = "YOUR_KEY"
$env:KUCOIN_API_SECRET = "YOUR_SECRET"
$env:KUCOIN_API_PASSPHRASE = "YOUR_PASSPHRASE"

powershell -NoProfile -ExecutionPolicy Bypass -File .\run_kucoin_trade_signal.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_kucoin_trade_signal.ps1 -RunRealOrder -ForceAction BUY_SPOT -SpotQty 0.1
```

### macOS / Linux

```bash
export KUCOIN_API_KEY="YOUR_KEY"
export KUCOIN_API_SECRET="YOUR_SECRET"
export KUCOIN_API_PASSPHRASE="YOUR_PASSPHRASE"

./run_kucoin_trade_signal.sh
./run_kucoin_trade_signal.sh --run-real-order --force-action BUY_SPOT --spot-qty 0.1
```

## 7) Низкоуровневый запуск исполнителя (опционально)

```bash
python trade_signal_executor_kucoin.py --mode shadow --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json

python trade_signal_executor_kucoin.py --mode live --run-real-order --config config/micro_near_v1_1m.json --state-json notebooks/reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json
```

## 8) Безопасность

- Не храните KuCoin API ключи в ноутбуке и репозитории.
- Используйте только переменные окружения `KUCOIN_API_KEY`, `KUCOIN_API_SECRET`, `KUCOIN_API_PASSPHRASE`.
- По умолчанию сначала запускайте `shadow`, потом `live`.
- Если ключи были где-то опубликованы, отзовите их и выпустите новые.

## 9) Что исключено из git

В `.gitignore` исключены:

- `venv/`
- `.venv/`
- `logs/`
- `reports/`
- `.runtime/`

## 10) Quick Kelly-hedge sizing example (NEAR)

Если из LSTM/GARCH получили:

- `ret_hat = 0.0003`
- `sigma_hat = 0.001`

то:

- `z_raw = ret_hat / sigma_hat^2 = 0.0003 / 0.000001 = 300`
- `z = clip(300, -2, 2) = 2`
- `target_notional = 1.5 * 0.5 * 2 = 1.5 USDT`

Дальше бот переводит notional в `spot_qty`, строит futures-хедж и отправляет ребаланс-ордера.
