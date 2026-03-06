# ML/RL Delta-Hedging на KuCoin + торговые скрипты

Репозиторий содержит:
- `notebooks/final_ml_rl_kucoin_demo.ipynb` - учебный ноутбук (в стиле lecture15): анализ OHLCV, ARIMA/GARCH, RL-блок, экспорт `latest_forecast_signal_kucoin_rl.json`.
- `trade_signal_executor_kucoin.py` - CLI-исполнитель: читает JSON состояния, рассчитывает target/hedge, отправляет ордера на KuCoin (`shadow` / `live`).
- `run_trade_signal.py` - универсальный кроссплатформенный раннер (автопоиск `latest_forecast_signal_*.json` в `Downloads` / `reports`).
- `run_kucoin_trade_signal.ps1` - обертка для Windows PowerShell.
- `run_kucoin_trade_signal.sh` - обертка для macOS / Linux.
- `src/delta_bot/*.py` - ядро ML/RL policy, risk engine, execution planner, KuCoin client.
- `config/micro_near_v1.json` - базовый профиль (15m).
- `config/micro_near_v1_1m.json` - профиль для минутного теста роботорговли (1m).

## Торговая логика `ML + RL + Delta-Hedge`

- Ноутбук формирует **последнее состояние рынка** (ret/sigma/price/target) и сохраняет JSON.
- Терминальный раннер читает этот JSON и передает его в исполнитель.
- Исполнитель:
  - рассчитывает целевые позиции spot/futures,
  - прогоняет risk engine,
  - режет объемы на чанки,
  - в `live` отправляет market-ордера на KuCoin.
- Есть принудительные команды для интеграционного теста: `--force-action BUY|SELL|HOLD`.

## 1) Клонирование репозитория

```bash
git clone https://github.com/<your-user>/lecture16.git
cd lecture16
```

## 2) Jupyter Notebook (анализ и генерация state JSON)

1. Откройте `notebooks/final_ml_rl_kucoin_demo.ipynb`.
2. Запустите ноутбук сверху вниз.
3. В конце ноутбука сохраняется файл:
   - `reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json`
4. Также файл копируется в `Downloads` / `Загрузки` (если папка существует).

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

Проверка:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## 4) Проверка, что JSON действительно сохранен

### Windows PowerShell

```powershell
Get-ChildItem $HOME\Downloads\latest_forecast_signal_*.json
Get-ChildItem .\reports\kucoin_rl\latest_forecast_signal_*.json
```

### macOS / Linux

```bash
ls -1 ~/Downloads/latest_forecast_signal_*.json
ls -1 ./reports/kucoin_rl/latest_forecast_signal_*.json
```

## 5) Универсальный запуск торговой логики (рекомендуется)

### Шаг 1. Задайте API переменные

Windows PowerShell:

```powershell
$env:PYTHONPATH="src"
$env:KUCOIN_API_KEY="YOUR_KEY"
$env:KUCOIN_API_SECRET="YOUR_SECRET"
$env:KUCOIN_API_PASSPHRASE="YOUR_PASSPHRASE"
$env:KUCOIN_KEY_VERSION="2"
```

macOS / Linux:

```bash
export PYTHONPATH=src
export KUCOIN_API_KEY="YOUR_KEY"
export KUCOIN_API_SECRET="YOUR_SECRET"
export KUCOIN_API_PASSPHRASE="YOUR_PASSPHRASE"
export KUCOIN_KEY_VERSION="2"
```

### Шаг 2. Тестовый запуск без отправки ордера

```bash
python run_trade_signal.py --config config/micro_near_v1_1m.json
```

### Шаг 3. Реальный запуск

```bash
python run_trade_signal.py --config config/micro_near_v1_1m.json --run-real-order
```

### Шаг 4. Принудительные команды BUY/SELL

```bash
python run_trade_signal.py --config config/micro_near_v1_1m.json --run-real-order --force-action BUY
python run_trade_signal.py --config config/micro_near_v1_1m.json --run-real-order --force-action SELL
python run_trade_signal.py --config config/micro_near_v1_1m.json --force-action HOLD
```

Парные и раздельные команды (одновременные/отдельные ордера):

```bash
# Купить spot+futures одновременно
python run_trade_signal.py --config config/micro_near_v1_1m.json --run-real-order --force-action BUY_BOTH --spot-qty 0.1 --futures-contracts 1

# Продать spot+futures одновременно
python run_trade_signal.py --config config/micro_near_v1_1m.json --run-real-order --force-action SELL_BOTH --spot-qty 0.1 --futures-contracts 1

# Купить/продать только spot
python run_trade_signal.py --config config/micro_near_v1_1m.json --run-real-order --force-action BUY_SPOT --spot-qty 0.1
python run_trade_signal.py --config config/micro_near_v1_1m.json --run-real-order --force-action SELL_SPOT --spot-qty 0.1

# Купить/продать только futures
python run_trade_signal.py --config config/micro_near_v1_1m.json --run-real-order --force-action BUY_FUTURES --futures-contracts 1
python run_trade_signal.py --config config/micro_near_v1_1m.json --run-real-order --force-action SELL_FUTURES --futures-contracts 1
```

Если нужен расчет short-цели policy (не ручной force-action):

```bash
python run_trade_signal.py --config config/micro_near_v1_1m.json --run-real-order --allow-short --force-action SELL
```

### Если JSON лежит в нестандартной папке

```bash
python run_trade_signal.py --state-json "C:/Users/your_user/Downloads/latest_forecast_signal_kucoin_rl.json" --config config/micro_near_v1_1m.json
```

## 6) Запуск через платформенные обертки (опционально)

### Windows PowerShell

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_kucoin_trade_signal.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_kucoin_trade_signal.ps1 -RunRealOrder -ForceAction BUY
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_kucoin_trade_signal.ps1 -RunRealOrder -ForceAction SELL
```

### macOS / Linux

```bash
./run_kucoin_trade_signal.sh
./run_kucoin_trade_signal.sh --run-real-order --force-action BUY
./run_kucoin_trade_signal.sh --run-real-order --force-action SELL
```

## 7) Прямой запуск low-level исполнителя (опционально)

```bash
python trade_signal_executor_kucoin.py \
  --state-json reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json \
  --config config/micro_near_v1_1m.json \
  --mode shadow

python trade_signal_executor_kucoin.py \
  --state-json reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json \
  --config config/micro_near_v1_1m.json \
  --mode live \
  --run-real-order
```

## 8) Безопасность

- Не храните ключи KuCoin в ноутбуках и в репозитории.
- Используйте только переменные окружения.
- Сначала `shadow`, только потом `live`.
- Если ключ был опубликован, сразу отзовите его и выпустите новый.

## 9) Что исключено из git

В `.gitignore` исключены:
- `__pycache__/`
- `*.pyc`
- `.runtime/`
- `venv/`
- `.venv/`
- `.vendor/`
- `reports/`
- `logs/`

## 10) Публикация на GitHub

```bash
git init
git add .
git commit -m "lecture16: notebook->json->kucoin executor + force-action CLI"
git branch -M main
git remote add origin https://github.com/<your-user>/lecture16.git
git push -u origin main
```
