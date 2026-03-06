# Торговая логика LSTM + GARCH + Kelly + торговые скрипты KuCoin

Репозиторий содержит:

- `notebooks/final_ml_rl_kucoin_demo.ipynb` - учебный ноутбук (в стиле лекций) для расчета LSTM-прогноза, GARCH-волатильности, Kelly-сигнала и выгрузки JSON.
- `trade_signal_executor_kucoin.py` - CLI-исполнитель стратегии (`POLICY` / `FORCED` действия, `shadow` / `live`).
- `run_trade_signal.py` - универсальный кроссплатформенный раннер (автопоиск `latest_forecast_signal_*.json` в `Downloads` / `reports`).
- `run_kucoin_trade_signal.ps1` - обертка для Windows PowerShell.
- `run_kucoin_trade_signal.sh` - обертка для macOS / Linux.
- `src/delta_bot/*.py` - ядро логики сигнала, risk engine, policy, execution, KuCoin REST client.
- `config/micro_near_v1_1m.json` - основной профиль минутного запуска.

## Торговая логика LSTM + GARCH + Kelly

- LSTM прогнозирует цену `NEAR-USDT` на 1 минуту вперед.
- `ret_hat` считается как прогнозная лог-доходность из LSTM.
- `sigma_hat` считается через GARCH по доходностям.
- Kelly-сигнал:
  - `z = ret_hat / (sigma_hat^2 + eps)`
  - `z = clip(z, -2, 2)`
- Размер входа в notional:
  - `target_notional_usdt = 1.5 * 0.5 * z`
- Далее строится spot-позиция и фьючерсный хедж (`target_hedge_ratio = -1`).

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

Откройте или загрузите `notebooks/final_ml_rl_kucoin_demo.ipynb` в Google Colab.

Запуск:

1. Запустите первую install-ячейку.
2. После первой установки сделайте `Runtime -> Restart runtime`.
3. Запустите ноутбук сверху вниз.
4. Ноутбук сохраняет JSON с последним сигналом в:

`reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json`

Дальше скачайте этот файл на локальную машину (обычно в `Downloads`).

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
$env:KUCOIN_API_KEY = "69aab5455b3822000122365c"
$env:KUCOIN_API_SECRET = "cad1d5be-f09c-4638-9035-222523dea8d1"
$env:KUCOIN_API_PASSPHRASE = "Lecture16Kucoin6March!!"
$env:KUCOIN_KEY_VERSION = "2"
```

Запуск (основной режим, непрерывно каждую минуту):

```powershell
$env:PYTHONPATH = "src"
python -m delta_bot.live --mode live --config config/micro_near_v1_1m.json --state-file .runtime\bot_state.json --expected-slippage-bps 3 --loop --sleep-seconds 60
```

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

## 10) Quick Kelly sizing example (NEAR)

Если:

- `ret_hat = 0.0003`
- `sigma_hat = 0.001`

то:

- `z_raw = ret_hat / sigma_hat^2 = 300`
- `z = clip(300, -2, 2) = 2`
- `target_notional = 1.5 * 0.5 * 2 = 1.5 USDT`

Дальше бот переводит notional в `spot_qty`, строит futures-хедж и выполняет ребаланс.
