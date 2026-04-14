# CPU Monitor

Агент для сбора метрик CPU и отправки их в `metrics_client_api`.

## Назначение

- Сбор системных метрик (CPU, память, диск) на хосте
- Отправка метрик в API по HTTP
- Работа в фоновом режиме с настраиваемым интервалом

## Структура проекта

```text
cpu_monitor/
├── Dockerfile
├── pyproject.toml
├── README.md
├── install_agent.bat
├── run_agent.bat
├── install_and_run_agent.bat
├── install_and_run.sh
└── src/
    └── cpu_monitor/
        ├── __init__.py
        ├── main.py
        ├── collector.py
        ├── compressor.py
        └── sender.py
```

## Зависимости

- Python 3.11+
- psutil>=5.0
- requests>=2.0

## Конфигурация

Агент настраивается через переменные окружения:

| Переменная | Описание | Пример | По умолчанию |
|------------|----------|--------|--------------|
| `METRICS_API_URL` | Адрес FastAPI-клиента | `http://localhost:8000` | `http://localhost:8000` |
| `CPU_SCRAPE_INTERVAL` | Интервал сбора метрик (сек) | `5` | `5` |
| `CPU_COMPRESSOR` | Алгоритм сжатия | `none` | `none` |
| `LOG_LEVEL` | Уровень логирования | `INFO` | `INFO` |

---

## Запуск в Docker Compose

### Production режим

Агент запускается как часть общего compose-файла:

```bash
docker compose up -d cpu_monitor
```

Конфигурация в `docker-compose.yml`:

```yaml
cpu_monitor:
  build:
    context: ./services/cpu_monitor
  container_name: marits-cpu-monitor
  depends_on:
    - metrics_client_api
  environment:
    METRICS_API_URL: http://metrics_client_api:8000
    CPU_SCRAPE_INTERVAL: "5"
    CPU_COMPRESSOR: "none"
  networks:
    - metrics-net
  restart: unless-stopped
  # Healthcheck не требуется - агент не имеет сетевого интерфейса
```

**Важно:** Для доступа к метрикам хоста из контейнера может потребоваться дополнительный volume:

```yaml
cpu_monitor:
  volumes:
    - /proc:/host/proc:ro
    - /sys:/host/sys:ro
  environment:
    PROCFS_PATH: /host/proc
    SYSFS_PATH: /host/sys
```

### Debug режим

Запуск с пересборкой и просмотром логов:

```bash
# Пересборка и запуск
docker compose up cpu_monitor --build

# Просмотр логов в реальном времени
docker compose logs -f cpu_monitor

# Выполнение команд внутри контейнера
docker compose exec cpu_monitor bash
```

---

## Запуск на хосте (без Docker)

### Установка

#### Linux / macOS

```bash
cd services/cpu_monitor

# Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate

# Установить зависимости
pip install -e .
```

#### Windows

```bat
cd services/cpu_monitor

:: Создать виртуальное окружение
python -m venv .venv
.venv\Scripts\activate

:: Установить зависимости
pip install -e .
```

### Запуск в режиме разработки (Debug)

#### Linux / macOS

```bash
# Установка переменных окружения
export METRICS_API_URL=http://localhost:8000
export CPU_SCRAPE_INTERVAL=5
export CPU_COMPRESSOR=none
export LOG_LEVEL=DEBUG

# Запуск агента с подробным логированием
python -m cpu_monitor.main
```

#### Windows

```bat
:: Установка переменных окружения
set METRICS_API_URL=http://localhost:8000
set CPU_SCRAPE_INTERVAL=5
set CPU_COMPRESSOR=none
set LOG_LEVEL=DEBUG

:: Запуск агента
python -m cpu_monitor.main
```

Или используйте готовые скрипты:

```bat
:: Установка и запуск одним скриптом
install_and_run_agent.bat

:: Или по отдельности
install_agent.bat
run_agent.bat
```

### Запуск в production режиме

#### Linux (systemd)

Создайте файл `/etc/systemd/system/cpu-monitor.service`:

```ini
[Unit]
Description=CPU Monitor Agent
After=network.target

[Service]
Type=simple
User=monitor
WorkingDirectory=/opt/cpu-monitor
Environment="METRICS_API_URL=http://metrics_client_api:8000"
Environment="CPU_SCRAPE_INTERVAL=5"
Environment="CPU_COMPRESSOR=none"
ExecStart=/opt/cpu-monitor/.venv/bin/python -m cpu_monitor.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cpu-monitor
sudo systemctl start cpu-monitor

# Проверка статуса
sudo systemctl status cpu-monitor

# Просмотр логов
journalctl -u cpu-monitor -f
```

#### Linux (supervisor)

Создайте файл `/etc/supervisor/conf.d/cpu-monitor.conf`:

```ini
[program:cpu-monitor]
directory=/opt/cpu-monitor
command=.venv/bin/python -m cpu_monitor.main
environment=METRICS_API_URL="http://metrics_client_api:8000",CPU_SCRAPE_INTERVAL="5"
autostart=true
autorestart=true
stderr_logfile=/var/log/cpu-monitor.err.log
stdout_logfile=/var/log/cpu-monitor.out.log
```

Запуск:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start cpu-monitor
```

#### Windows (как служба)

Используйте NSSM (Non-Sucking Service Manager):

```bat
:: Скачать NSSM и установить службу
nssm install cpu-monitor "C:\Python314\python.exe" "-m cpu_monitor.main"
nssm set cpu-monitor AppDirectory "C:\cpu-monitor"
nssm set cpu-monitor AppEnvironmentExtra METRICS_API_URL=http://localhost:8000
nssm start cpu-monitor
```

#### Windows (Task Scheduler)

Запуск при загрузке системы через планировщик задач:

```bat
schtasks /Create /TN "CPU Monitor" /TR "python -m cpu_monitor.main" /SC ONSTART /RU SYSTEM
```

---

## Проверка работоспособности

### Проверка логов

```bash
# В Docker
docker compose logs cpu_monitor

# На хосте (Linux systemd)
journalctl -u cpu-monitor -f

# На хосте (Windows)
# Логи выводятся в консоль или в файлы, указанные в конфигурации
```

### Проверка отправки метрик

1. Запустите агент
2. Проверьте логи API:
   ```bash
   docker compose logs metrics_client_api
   ```
3. Проверьте наличие метрик в базе:
   ```python
   from metrics_client import Client
   c = Client("localhost", 8888)
   print(c.get("cpu.usage_percent"))
   ```

---

## Формат отправляемых данных

Агент отправляет метрики в формате JSON:

```json
{
  "metric": "cpu.usage_percent",
  "value": 42.5,
  "timestamp": 1711450000,
  "tags": {
    "host": "server01",
    "core": "all"
  }
}
```

Доступные метрики:

- `cpu.usage_percent` — загрузка CPU в процентах
- `cpu.count` — количество ядер
- `memory.used_percent` — использование памяти
- `disk.usage_percent` — использование диска

---

## Troubleshooting

### Агент не отправляет метрики

1. Проверьте доступность API:
   ```bash
   curl http://localhost:8000/health
   ```

2. Убедитесь, что переменная `METRICS_API_URL` корректна:
   ```bash
   echo $METRICS_API_URL  # Linux
   echo %METRICS_API_URL%  # Windows
   ```

3. Проверьте логи агента на наличие ошибок

### Ошибки доступа к системным метрикам

**Docker:** Добавьте volumes для доступа к `/proc` и `/sys`:

```yaml
volumes:
  - /proc:/host/proc:ro
  - /sys:/host/sys:ro
```

**Linux:** Запустите от имени пользователя с правами чтения `/proc`:

```bash
sudo python -m cpu_monitor.main
```

**Windows:** Запустите от имени администратора

### Высокая нагрузка от агента

Увеличьте интервал сбора:

```bash
export CPU_SCRAPE_INTERVAL=30  # сбор каждые 30 секунд
```

---

## Разработка

### Добавление новых метрик

1. Создайте функцию сбора в `src/cpu_monitor/collector.py`
2. Добавьте отправку в `src/cpu_monitor/main.py`
3. Обновите документацию

Пример:

```python
import psutil

def get_memory_metrics():
    memory = psutil.virtual_memory()
    return {
        "metric": "memory.used_percent",
        "value": memory.percent,
        "timestamp": int(time.time())
    }
```

### Тестирование

```bash
# Запуск тестов (при наличии)
pytest tests/

# Линтинг
flake8 src/cpu_monitor/

# Проверка типов
mypy src/cpu_monitor/
```

---

## Мониторинг самого агента

Агент не предоставляет health check endpoint, но его работоспособность можно проверить:

```bash
# Проверка процесса
ps aux | grep cpu_monitor

# Проверка логов на наличие последних записей
docker compose logs --tail=10 cpu_monitor

# Проверка отправки метрик через логи API
docker compose logs metrics_client_api | grep "received metric"
```

---

## Планы развития

- Поддержка дополнительных метрик (сеть, GPU, процессы)
- Кастомные компрессоры временных рядов
- Буферизация метрик при недоступности API
- Динамическая настройка интервала через API