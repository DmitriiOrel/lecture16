# Торговая логика LSTM + GARCH + Kelly + торговые скрипты KuCoin

Репозиторий содержит:

- `notebooks/final_ml_rl_kucoin_demo.ipynb` - учебный ноутбук в стиле лекций (LSTM + GARCH + Kelly), который формирует JSON-состояние для бота.
- `trade_signal_executor_kucoin.py` - CLI-исполнитель стратегии (`shadow`/`live`, policy/force actions).
- `run_trade_signal.py` - универсальный кроссплатформенный раннер (ищет `latest_forecast_signal_*.json` в `Downloads`/`reports` или берет `--state-json`).
- `run_kucoin_trade_signal.ps1` - обертка для Windows PowerShell.
- `run_kucoin_trade_signal.sh` - обертка для macOS/Linux.
- `src/delta_bot/*.py` - ядро (policy, risk engine, execution planner, KuCoin client).
- `config/micro_near_v1_1m.json` - основной профиль для минутного запуска.

## Торговая логика

- LSTM прогнозирует цену `NEAR-USDT` на 1 минуту вперед.
- `ret_hat` = прогнозная лог-доходность из LSTM.
- `sigma_hat` = оценка волатильности через GARCH по доходностям.
- Kelly-сигнал:
  - `z = ret_hat / (sigma_hat^2 + eps)`
  - `z = clip(z, -2, 2)`
- Целевой notional:
  - `target_notional_usdt = 1.5 * 0.5 * z`
- Дальше строится spot-позиция и фьючерсный хедж (`hedge_ratio = -1`).

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

Важно: все команды ниже выполняются из папки репозитория `lecture16`.

## 2) Google Colab (анализ и генерация сигнала)

1. Откройте в Colab: `notebooks/final_ml_rl_kucoin_demo.ipynb`
2. Запустите install-ячейку.
3. Сделайте `Runtime -> Restart runtime`.
4. Запустите ноутбук сверху вниз.
5. В конце ноутбук создает файл:
   - `reports/kucoin_rl/latest_forecast_signal_kucoin_rl.json`
6. Скачайте этот JSON на локальный компьютер (обычно в `Downloads`).

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

## 4) Проверка, что JSON реально есть

### Windows PowerShell

```powershell
Get-ChildItem "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json"
```

### macOS / Linux

```bash
ls -1 ~/Downloads/latest_forecast_signal_kucoin_rl.json
```

Если файла нет в `Downloads`, значит его нужно заново скачать из Colab.

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

### Шаг 2. Тестовый запуск (без отправки ордера)

Windows/macOS/Linux:

```bash
python run_trade_signal.py --mode shadow --config config/micro_near_v1_1m.json --state-json "$HOME/Downloads/latest_forecast_signal_kucoin_rl.json"
```

PowerShell-эквивалент (если удобнее обратные слэши):

```powershell
python run_trade_signal.py --mode shadow --config config/micro_near_v1_1m.json --state-json "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json"
```

### Ошибка `400002 Invalid KC-API-TIMESTAMP`

Причина: время на локальной машине отличается от времени сервера KuCoin.

Решение:

1. Синхронизируйте время Windows:

```powershell
w32tm /resync
```

2. Обновите репозиторий до версии с авто-синхронизацией времени в клиенте:

```powershell
git pull
```

3. Повторите `shadow`-запуск.

### Ошибка `400004 Invalid KC-API-PASSPHRASE`

Причина: неверная `KUCOIN_API_PASSPHRASE` для текущего API-ключа/секрета.

Проверьте, что все три переменные (`KEY`, `SECRET`, `PASSPHRASE`) относятся к одному и тому же API-ключу на KuCoin.

### Шаг 3. Реальный запуск

```bash
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME/Downloads/latest_forecast_signal_kucoin_rl.json"
```

### Шаг 4. Принудительный тест BUY/SELL

```bash
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME/Downloads/latest_forecast_signal_kucoin_rl.json" --force-action BUY_SPOT --spot-qty 0.1
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME/Downloads/latest_forecast_signal_kucoin_rl.json" --force-action SELL_SPOT --spot-qty 0.1
```

Обе ноги одновременно:

```bash
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME/Downloads/latest_forecast_signal_kucoin_rl.json" --force-action BUY_BOTH --spot-qty 0.1 --futures-contracts 1
python run_trade_signal.py --run-real-order --config config/micro_near_v1_1m.json --state-json "$HOME/Downloads/latest_forecast_signal_kucoin_rl.json" --force-action SELL_BOTH --spot-qty 0.1 --futures-contracts 1
```

### Шаг 5. Если не хотите указывать путь руками

Можно дать раннеру авто-поиск в `Downloads`:

```bash
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

## 7) Частая ошибка и быстрое исправление

Ошибка:

```text
State JSON not found: ...\notebooks\reports\kucoin_rl\latest_forecast_signal_kucoin_rl.json
```

Причина: в команде указан путь, которого нет на диске.

Решение:

1. Проверить, где файл реально лежит (обычно `Downloads`):

```powershell
Get-ChildItem "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json"
```

2. Передать этот путь в `--state-json`:

```powershell
python run_trade_signal.py --mode shadow --config config/micro_near_v1_1m.json --state-json "$HOME\Downloads\latest_forecast_signal_kucoin_rl.json"
```

## 8) Безопасность

- Не храните KuCoin API ключи в ноутбуке и в репозитории.
- Используйте только env-переменные: `KUCOIN_API_KEY`, `KUCOIN_API_SECRET`, `KUCOIN_API_PASSPHRASE`.
- Сначала запускайте `shadow`, затем `live`.
- Если ключи были опубликованы, отзовите их и выпустите новые.

## 9) Что исключено из git

В `.gitignore` исключены:

- `venv/`
- `.venv/`
- `logs/`
- `reports/`
- `.runtime/`

## 10) Quick Kelly sizing (NEAR)

Если:

- `ret_hat = 0.0003`
- `sigma_hat = 0.001`

то:

- `z_raw = ret_hat / sigma_hat^2 = 300`
- `z = clip(300, -2, 2) = 2`
- `target_notional = 1.5 * 0.5 * 2 = 1.5 USDT`

Далее бот конвертирует notional в `spot_qty`, строит futures-хедж и выполняет ребаланс.
