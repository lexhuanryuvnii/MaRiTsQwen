# Metrics Server

Сервер для приёма и хранения метрик. Принимает данные по TCP-сокету и записывает их в InfluxDB.

## Назначение

- Приём метрик от клиентов по TCP
- Агрегация и запись данных в InfluxDB
- Предоставление API для чтения исторических данных

## Структура проекта

```text
metrics_server/
├── Dockerfile
├── pyproject.toml
├── README.md
└── server/
    ├── __init__.py
    ├── main.py
    └── handler.py
```

## Зависимости

- Python 3.11+
- influxdb-client>=1.38.0

## Конфигурация

Сервер настраивается через переменные окружения:

| Переменная | Описание | Пример |
|------------|----------|--------|
| `INFLUX_URL` | URL подключения к InfluxDB | `http://influxdb:8086` |
| `INFLUX_TOKEN` | Токен аутентификации | `my_token` |
| `INFLUX_ORG` | Организация в InfluxDB | `myorg` |
| `INFLUX_BUCKET` | Имя бакета для записи | `metrics` |
| `METRICS_HOST` | Хост для прослушивания TCP | `0.0.0.0` |
| `METRICS_PORT` | Порт для прослушивания TCP | `8888` |

---

## Запуск в Docker Compose

### Production режим

Сервер запускается как часть общего compose-файла:

```bash
docker compose up -d metrics_server
```

Конфигурация в `docker-compose.yml`:

```yaml
metrics_server:
  build:
    context: ./services/metrics_server
  container_name: marits-metrics-server
  depends_on:
    influxdb:
      condition: service_healthy
  ports:
    - "8888:8888"
  environment:
    - INFLUX_URL=http://influxdb:8086
    - INFLUX_TOKEN=${INFLUX_TOKEN}
    - INFLUX_ORG=${INFLUX_ORG}
    - INFLUX_BUCKET=${INFLUX_BUCKET}
  networks:
    - metrics-net
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "python", "-c", "import socket; s=socket.socket(); s.connect(('localhost', 8888)); s.close()"]
    interval: 10s
    timeout: 5s
    retries: 3
```

### Debug режим

Запуск с пересборкой и просмотром логов:

```bash
# Пересборка и запуск
docker compose up metrics_server --build

# Просмотр логов в реальном времени
docker compose logs -f metrics_server

# Выполнение команд внутри контейнера
docker compose exec metrics_server bash
```

---

## Запуск на хосте (без Docker)

### Установка

```bash
cd services/metrics_server

# Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# или .venv\Scripts\activate  # Windows

# Установить зависимости
pip install -e .
```

### Запуск в режиме разработки

```bash
# Установка переменных окружения
export INFLUX_URL=http://localhost:8086
export INFLUX_TOKEN=my_token
export INFLUX_ORG=myorg
export INFLUX_BUCKET=metrics

# Запуск сервера
python -m server.main
```

### Запуск в production режиме

Для production рекомендуется использовать процесс-менеджер (systemd, supervisor):

```bash
# Через systemd сервис
sudo systemctl start metrics-server
```

---

## Проверка работоспособности

### Тестирование через Python-клиент

```python
from metrics_client import Client

# Подключение к серверу
c = Client("localhost", 8888)

# Отправка метрики
c.put("cpu.usage", 42.5)
c.put("memory.used", 1024.0)

# Чтение метрики
print(c.get("cpu.usage"))
```

### Тестирование через TCP

```bash
# Отправка данных через netcat
echo "test.metric 42.0 $(date +%s)" | nc localhost 8888

# Проверка подключения
telnet localhost 8888
```

### Проверка логов

```bash
# В Docker
docker compose logs metrics_server

# На хосте
journalctl -u metrics-server -f  # если используется systemd
```

---

## Протокол обмена данными

Клиент отправляет метрики в формате:

```
<metric_name> <value> <timestamp>
```

Пример:

```
cpu.usage_percent 42.5 1711450000
memory.used_bytes 1073741824 1711450001
```

Сервер отвечает:

- `OK` — успешная запись
- `ERROR: <message>` — ошибка записи

---

## Troubleshooting

### Сервер не подключается к InfluxDB

1. Проверьте доступность InfluxDB:
   ```bash
   curl http://localhost:8086/health
   ```

2. Убедитесь в корректности токена и параметров подключения

3. Проверьте логи InfluxDB:
   ```bash
   docker compose logs influxdb
   ```

### Проблемы с подключением клиентов

1. Убедитесь, что порт 8888 открыт:
   ```bash
   netstat -tlnp | grep 8888
   ```

2. Проверьте firewall:
   ```bash
   sudo ufw allow 8888/tcp
   ```

### Ошибки записи метрик

- Проверьте, что бакет существует в InfluxDB
- Убедитесь, что токен имеет права на запись
- Проверьте логи сервера на наличие ошибок

---

## Разработка

### Добавление новых обработчиков метрик

1. Создайте новый класс-обработчик в `server/handler.py`
2. Зарегистрируйте обработчик в главном цикле сервера
3. Обновите тесты

### Тестирование

```bash
# Запуск тестов (при наличии)
pytest tests/

# Линтинг
flake8 server/
```

---

## Мониторинг

### Health Check

Сервер поддерживает проверку здоровья через TCP:

```bash
# Проверка доступности порта
nc -zv localhost 8888
```

### Метрики самого сервера

Планируется добавить endpoint для сбора метрик о работе сервера:
- Количество обработанных запросов
- Время обработки
- Ошибки записи в InfluxDB
