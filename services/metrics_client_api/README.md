# Metrics Client API

HTTP-обёртка (FastAPI) для работы с сервером метрик. Предоставляет REST API для приёма и отправки метрик.

## Назначение

- Предоставление HTTP API для работы с метриками
- Преобразование HTTP-запросов в вызовы TCP-клиента
- Валидация и сериализация данных метрик
- Интеграция с другими сервисами платформы

## Структура проекта

```text
metrics_client_api/
├── Dockerfile
├── pyproject.toml
├── README.md
├── src/
│   └── metrics_client_api/
│       ├── __init__.py
│       ├── main.py
│       ├── models.py
│       └── client.py
└── tests/
    └── test_api.py
```

## Зависимости

- Python 3.11+
- fastapi>=0.115.0
- uvicorn[standard]>=0.30.0
- pydantic_settings
- pandas
- numpy

## Конфигурация

Сервис настраивается через переменные окружения:

| Переменная | Описание | Пример | По умолчанию |
|------------|----------|--------|--------------|
| `METRICS_SERVER_HOST` | Хост сервера метрик | `metrics_server` | `localhost` |
| `METRICS_SERVER_PORT` | Порт сервера метрик | `8888` | `8888` |
| `HOST` | Хост для прослушивания API | `0.0.0.0` | `0.0.0.0` |
| `PORT` | Порт для прослушивания API | `8000` | `8000` |

---

## Запуск в Docker Compose

### Production режим

Сервис запускается как часть общего compose-файла:

```bash
docker compose up -d metrics_client_api
```

Конфигурация в `docker-compose.yml`:

```yaml
metrics_client_api:
  build:
    context: ./services/metrics_client_api
  container_name: marits-metrics-api
  environment:
    METRICS_SERVER_HOST: metrics_server
    METRICS_SERVER_PORT: "8888"
  ports:
    - "8000:8000"
  depends_on:
    - metrics_server
  networks:
    - metrics-net
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 10s
    timeout: 5s
    retries: 3
```

### Debug режим

Запуск с пересборкой и hot-reload:

```bash
# Пересборка и запуск
docker compose up metrics_client_api --build

# Просмотр логов в реальном времени
docker compose logs -f metrics_client_api

# Доступ к Swagger UI
# http://localhost:8000/docs
```

Для включения hot-reload раскомментируйте в `docker-compose.yml`:

```yaml
metrics_client_api:
  command: ["uvicorn", "metrics_client_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
  volumes:
    - ./services/metrics_client_api/src:/app/src
```

---

## Запуск на хосте (без Docker)

### Установка

```bash
cd services/metrics_client_api

# Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# или .venv\Scripts\activate  # Windows

# Установить зависимости
pip install -e .
```

### Запуск в режиме разработки (Debug)

```bash
# Установка переменных окружения
export METRICS_SERVER_HOST=localhost
export METRICS_SERVER_PORT=8888

# Запуск с auto-reload
uvicorn metrics_client_api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Запуск в production режиме

```bash
# Установка переменных окружения
export METRICS_SERVER_HOST=metrics_server
export METRICS_SERVER_PORT=8888

# Запуск с несколькими workers
uvicorn metrics_client_api.main:app --host 0.0.0.0 --port 8000 --workers 4

# Или через gunicorn
gunicorn metrics_client_api.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## API Endpoints

### Swagger UI

После запуска откройте в браузере:

```
http://localhost:8000/docs
```

### Основные endpoints

#### GET `/health`

Проверка работоспособности сервиса.

**Ответ:**
```json
{"status": "ok"}
```

#### POST `/metrics/`

Отправка одной или нескольких метрик.

**Тело запроса:**
```json
{
  "metric": "cpu.usage_percent",
  "value": 42.5,
  "timestamp": 1711450000
}
```

Или массив метрик:
```json
[
  {"metric": "cpu.usage_percent", "value": 42.5, "timestamp": 1711450000},
  {"metric": "memory.used_bytes", "value": 1073741824, "timestamp": 1711450001}
]
```

**Ответ:**
```json
{"status": "ok", "received": 1}
```

#### GET `/metrics/{metric_name}`

Получение значений метрики за период.

**Параметры:**
- `metric_name` — имя метрики
- `start` — начало периода (timestamp)
- `end` — конец периода (timestamp)

**Пример:**
```
GET /metrics/cpu.usage_percent?start=1711450000&end=1711460000
```

**Ответ:**
```json
{
  "metric": "cpu.usage_percent",
  "data": [
    {"timestamp": 1711450000, "value": 42.5},
    {"timestamp": 1711450005, "value": 43.1}
  ]
}
```

#### GET `/metrics/`

Получение списка всех доступных метрик.

**Ответ:**
```json
{
  "metrics": ["cpu.usage_percent", "memory.used_bytes", "disk.io_read"]
}
```

---

## Проверка работоспособности

### curl примеры

```bash
# Проверка health
curl http://localhost:8000/health

# Отправка метрики
curl -X POST http://localhost:8000/metrics/ \
  -H "Content-Type: application/json" \
  -d '{"metric": "test.metric", "value": 42.0, "timestamp": '$(date +%s)'}'

# Получение метрики
curl "http://localhost:8000/metrics/test.metric"
```

### Python примеры

```python
import requests

# Проверка health
response = requests.get("http://localhost:8000/health")
print(response.json())

# Отправка метрики
response = requests.post(
    "http://localhost:8000/metrics/",
    json={"metric": "cpu.usage", "value": 42.5, "timestamp": 1711450000}
)
print(response.json())

# Получение метрики
response = requests.get("http://localhost:8000/metrics/cpu.usage")
print(response.json())
```

---

## Troubleshooting

### Сервис не подключается к metrics_server

1. Проверьте доступность сервера метрик:
   ```bash
   nc -zv metrics_server 8888
   ```

2. Убедитесь, что переменные окружения корректны:
   ```bash
   docker compose exec metrics_client_api env | grep METRICS
   ```

3. Проверьте логи:
   ```bash
   docker compose logs metrics_client_api
   ```

### Ошибки валидации данных

- Убедитесь, что формат JSON соответствует схеме
- Проверьте типы данных (value должен быть числом)
- Timestamp должен быть в секундах (Unix time)

### Проблемы с производительностью

- Увеличьте количество workers в production режиме
- Проверьте нагрузку на сервер метрик
- Рассмотрите кэширование частых запросов

---

## Разработка

### Добавление новых endpoints

1. Создайте новую функцию в `src/metrics_client_api/main.py`
2. Добавьте модель данных в `src/metrics_client_api/models.py`
3. Обновите документацию OpenAPI (автоматически генерируется FastAPI)

### Тестирование

```bash
# Запуск тестов
pytest tests/

# Запуск с покрытием
pytest tests/ --cov=metrics_client_api

# Линтинг
flake8 src/metrics_client_api/
```

---

## Мониторинг

### Health Check

```bash
curl http://localhost:8000/health
```

### Метрики самого сервиса

Планируется добавить endpoint `/metrics/service` для сбора метрик о работе API:
- Количество запросов в секунду
- Время обработки запросов
- Ошибки подключения к серверу метрик

---

## Интеграция с другими сервисами

### CPU Monitor

Агент отправляет метрики через этот API:

```bash
METRICS_API_URL=http://metrics_client_api:8000
```

### Web Dashboard

Фронтенд получает данные через REST API:

```javascript
fetch('http://localhost:8000/metrics/cpu.usage_percent')
  .then(r => r.json())
  .then(data => console.log(data));
```

### Marimo Dashboard

Тетрадка использует API для получения исторических данных:

```python
import requests
data = requests.get("http://metrics_client_api:8000/metrics/cpu.usage_percent").json()
```
