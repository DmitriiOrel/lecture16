# Торговая логика Basis Z-Score + Delta-Neutral + торговые скрипты KuCoin

Репозиторий содержит:

- `notebooks/lecture16_basis_rl_colab.ipynb` - учебный Colab-ноутбук: OHLCV, basis z-score, baseline, RL (PPO), экспорт JSON.
- `trade_signal_executor_kucoin.py` - CLI-исполнитель стратегии (`POLICY` / `FORCED` действия, `shadow` / `live`).
- `run_trade_signal.py` - универсальный кроссплатформенный раннер (автопоиск `latest_forecast_signal_*.json` в `Downloads` / `reports`).
- `run_kucoin_trade_signal.ps1` - обертка для Windows PowerShell.
- `run_kucoin_trade_signal.sh` - обертка для macOS / Linux.
- `src/delta_bot/*.py` - ядро логики сигнала, risk engine, policy, execution, KuCoin REST client.
- `config/micro_near_v1_1m.json` - основной профиль минутного запуска.

## Торговая логика Basis Z-Score + Delta-Neutral

- Signal: `basis = (F - S) / S` + rolling `z-score`.
- Entry: `z > entry_z` -> `BUY spot` + `SELL futures`.
- Exit: `|z| < exit_z` -> close both legs.
- Target: keep `spot_qty + futures_base_qty ? 0`.
- Strategy is delta-neutral and trades basis mean reversion.

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

Важно: все команды ниже выполняются из папки `lecture16`.

## 2) Google Colab (анализ и генерация сигнала)

Откройте `notebooks/lecture16_basis_rl_colab.ipynb` в Google Colab:

- https://colab.research.google.com/github/DmitriiOrel/lecture16/blob/master/notebooks/lecture16_basis_rl_colab.ipynb

Запуск:

1. Запустите install-ячейку.
2. При необходимости сделайте `Runtime -> Restart runtime`.
3. Запустите ноутбук сверху вниз.
4. В конце ноутбук формирует JSON:

`/content/latest_forecast_signal_kucoin_rl.json`

5. Скачайте файл в `Downloads`.

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
python -c "import requests; import arch; print('OK')"
```

## 4) Проверка, что JSON действительно сохранен

### Windows PowerShell

```powershell
Get-ChildItem "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json"
```

### macOS / Linux

```bash
ls -1 ~/Downloads/latest_forecast_signal_kucoin_rl.json
```

## 5) Универсальный запуск торговой логики (рекомендуется)

### Шаг 1. Тестовый запуск без отправки ордеров (рекомендуется)

```powershell
python run_trade_signal.py --mode shadow --config config/micro_near_v1_1m.json --state-json "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json"
```

Примечание: `shadow` не отправляет реальные ордера.

### Шаг 2. Реальный запуск

Сначала задайте API-переменные:

```powershell
$env:KUCOIN_API_KEY = "YOUR_KUCOIN_API_KEY"
$env:KUCOIN_API_SECRET = "YOUR_KUCOIN_API_SECRET"
$env:KUCOIN_API_PASSPHRASE = "YOUR_KUCOIN_API_PASSPHRASE"
$env:KUCOIN_KEY_VERSION = "2"
```

Запуск (основной режим, непрерывно каждую минуту):

```powershell
$env:PYTHONPATH = "src"
python -m delta_bot.live --mode live --config config/micro_near_v1_1m.json --state-file .runtime\bot_state.json --expected-slippage-bps 3 --loop --sleep-seconds 60
```

Запуск именно PPO-агента (RL decisions в live):

```powershell
$env:PYTHONPATH = "src"
python -m delta_bot.live --mode live --config config/micro_near_v1_1m.json --state-file .runtime\bot_state.json --expected-slippage-bps 3 --loop --sleep-seconds 60 --decision-mode rl --rl-model-path "$HOME\Downloads\ppo_delta_neutral_near_1m.zip"
```

Примечание: `ppo_delta_neutral_near_1m.zip` сначала нужно обучить и скачать из Colab-ноутбука.

Остановить цикл: `Ctrl + C`.

Единоразовый `live`-прогон (опционально, для ручной проверки):

```powershell
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json"
```

### Шаг 3. Принудительный тест BUY/SELL

Покупка/продажа spot отдельно:

```powershell
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json" --force-action BUY_SPOT --spot-qty 0.1
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json" --force-action SELL_SPOT --spot-qty 0.1
```

Покупка/продажа futures отдельно:

```powershell
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json" --force-action BUY_FUTURES --futures-contracts 1
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json" --force-action SELL_FUTURES --futures-contracts 1
```

Обе ноги одновременно:

```powershell
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json" --force-action BUY_BOTH --spot-qty 0.1 --futures-contracts 1
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json" --force-action SELL_BOTH --spot-qty 0.1 --futures-contracts 1
```

Если JSON лежит в нестандартной папке:

```powershell
python run_trade_signal.py --mode shadow --config config/micro_near_v1_1m.json --state-json "C:\Users\your_user\Downloads\latest_forecast_signal_kucoin_rl.json"
```

Если не хотите указывать путь к JSON вручную:

```powershell
python run_trade_signal.py --mode shadow --config config/micro_near_v1_1m.json --search-downloads-only
```

## 6) Запуск через платформенные обертки (опционально)

### Windows PowerShell

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_kucoin_trade_signal.ps1 -StateJson "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json"
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_kucoin_trade_signal.ps1 -RunRealOrder -StateJson "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json" -ForceAction BUY_SPOT -SpotQty 0.1
```

### macOS / Linux

```bash
./run_kucoin_trade_signal.sh --state-json "$HOME/Downloads/latest_forecast_signal_kucoin_rl.json"
./run_kucoin_trade_signal.sh --run-real-order --state-json "$HOME/Downloads/latest_forecast_signal_kucoin_rl.json" --force-action BUY_SPOT --spot-qty 0.1
```

## 7) Частые ошибки и быстрые решения

### Ошибка: `State JSON not found`

Проверьте наличие файла:

```powershell
Get-ChildItem "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json"
```

И передайте корректный путь через `--state-json`.

### Ошибка: `400002 Invalid KC-API-TIMESTAMP`

Синхронизируйте время Windows:

```powershell
w32tm /resync
```

И обновите репозиторий:

```powershell
git pull
```

### Ошибка: `400004 Invalid KC-API-PASSPHRASE`

Проверьте, что `KEY`, `SECRET`, `PASSPHRASE` относятся к одному и тому же API-ключу на KuCoin.

## 8) Безопасность

- Не храните KuCoin API ключи в ноутбуке и репозитории.
- Используйте переменные окружения `KUCOIN_API_KEY`, `KUCOIN_API_SECRET`, `KUCOIN_API_PASSPHRASE`.
- Всегда сначала запускайте `shadow`, потом `live`.
- Если ключ был опубликован, отзовите его и выпустите новый.

## 9) Что исключено из git

В `.gitignore` исключены:

- `venv/`
- `.venv/`
- `logs/`
- `reports/`
- `.runtime/`

## 10) Quick Basis Z-Score example (NEAR)

Example:

- `spot = 1.25`, `futures = 1.28`
- `basis = (1.28 - 1.25) / 1.25 = 0.024`
- `mean_basis = 0.010`, `std_basis = 0.006`
- `z = (0.024 - 0.010) / 0.006 = 2.33`

Since `z > entry_z`, strategy opens pair:

- `BUY spot`
- `SELL futures`

Then it waits for `|z| < exit_z` and closes both legs.
