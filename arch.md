# Архитектура платформы метрик

## Обзор архитектуры

Платформа представляет собой микросервисную систему для сбора, хранения и визуализации системных метрик. Все сервисы контейнеризированы и управляются через Docker Compose.

---

## Общая схема архитектуры

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   cpu_monitor   │────▶│  metrics_client_api  │────▶│  metrics_server │
│   (агент на     │     │   (FastAPI + TCP     │     │   (TCP server   │
│    хостах)      │     │    client bridge)    │     │    + InfluxDB)  │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
                                                  ┌─────────────────┐
                                                  │    influxdb     │
                                                  │  (time-series   │
                                                  │     storage)    │
                                                  └─────────────────┘
                                                         │
                        ┌────────────────────────────────┘
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
┌─────────────────┐           ┌─────────────────┐
│ web_dashboard   │           │ marimo_dashboard│
│ (веб-фронтенд   │           │ (интерактивная  │
│  с SSE)         │           │  тетрадка)      │
└─────────────────┘           └─────────────────┘
```

---

## Детальное описание сервисов

### 1. CPU Monitor

**Назначение**: Агент сбора системных метрик, устанавливаемый на клиентские машины.

**Принцип работы**:
- Периодический сбор метрик CPU и памяти (интервал настраивается, по умолчанию 0.5 сек)
- Потоковое сжатие данных алгоритмом Sausage Links
- Heartbeat-механизм для неизменных метрик
- Пакетная отправка на сервер (интервал настраивается, по умолчанию 3 сек)

**Ключевые особенности**:
- **StreamingCompressor**: Каждая метрика имеет собственный компрессор с буфером
- **Heartbeat**: Если метрика не менялась дольше `max_silent_interval` (10 сек), отправляется последняя известная точка как keepalive-сигнал
- **Адаптивное сжатие**: Параметры `deviation`, `auto_dev_factor`, `ema_alpha` регулируют степень сжатия

**Формат отправки**:
```json
[
  {"metric": "cpu.usage_percent", "value": 42.5, "timestamp": 1711450000},
  {"metric": "cpu.freq.current_mhz", "value": 2300.0, "timestamp": 1711450000}
]
```

**Конфигурация**:
| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `METRICS_API_URL` | `http://localhost:8000` | URL API клиента |
| `CPU_COLLECTION_INTERVAL` | `0.5` | Интервал сбора (сек) |
| `BATCH_SEND_INTERVAL` | `3.0` | Интервал отправки (сек) |
| `CPU_COMPRESSOR` | `none` | Тип компрессора |
| `COMPRESSOR_MAX_SILENT_INTERVAL` | `10.0` | Heartbeat интервал (сек) |

**Файлы**:
- `services/cpu_monitor/info.md` — подробная документация

---

### 2. Metrics Client API

**Назначение**: HTTP-шлюз между клиентами и сервером метрик. Преобразует HTTP-запросы в TCP-команды.

**Основные эндпоинты**:
- `GET /metrics/names` — список всех метрик
- `GET /metrics/{metric_name}` — данные метрики за период
- `GET /metrics/stream` — SSE поток real-time обновлений
- `GET /metrics/analysis` — статистика по метрикам (среднее, тренды)
- `POST /metrics/put_batch` — пакетная запись метрик (от cpu_monitor)

**Технологии**: FastAPI, асинхронные TCP-клиенты

**Конфигурация**:
| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `METRICS_SERVER_HOST` | `metrics_server` | Хост TCP сервера |
| `METRICS_SERVER_PORT` | `8888` | Порт TCP сервера |
| `METRICS_CLIENT_API_HOST` | `0.0.0.0` | Хост для bind |
| `METRICS_CLIENT_API_PORT` | `8000` | Порт для bind |

---

### 3. Metrics Server

**Назначение**: Центральный сервер приёма и записи метрик в InfluxDB.

**Принцип работы**:
- Приём метрик по TCP от клиентов
- Парсинг протокола (команды `put`, `get`, `list`)
- Запись данных в InfluxDB через её API
- Кэширование последних значений для быстрых запросов

**Протокол**:
```
put metric_name value timestamp\n
get metric_name minutes\n
list\n
```

**Конфигурация**:
| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `METRICS_SERVER_HOST` | `0.0.0.0` | Хост для bind |
| `METRICS_SERVER_PORT` | `8888` | Порт TCP сервера |
| `INFLUX_URL` | `http://influxdb:8086` | URL InfluxDB |
| `INFLUX_TOKEN` | — | Токен аутентификации |
| `INFLUX_ORG` | `myorg` | Организация |
| `INFLUX_BUCKET` | `metrics` | Bucket для записи |

---

### 4. InfluxDB

**Назначение**: Хранилище временных рядов для метрик.

**Конфигурация**:
| Переменная | Описание |
|------------|----------|
| `DOCKER_INFLUXDB_INIT_MODE` | `setup` для авто-инициализации |
| `DOCKER_INFLUXDB_INIT_USERNAME` | Имя пользователя admin |
| `DOCKER_INFLUXDB_INIT_PASSWORD` | Пароль администратора |
| `DOCKER_INFLUXDB_INIT_ORG` | Организация |
| `DOCKER_INFLUXDB_INIT_BUCKET` | Bucket по умолчанию |
| `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN` | Токен администратора |

**Доступ**: http://localhost:8086

---

### 5. Web Dashboard

**Назначение**: Веб-интерфейс для визуализации метрик в реальном времени.

**Принцип работы**:
- Подключение к SSE потоку `/metrics/stream` для real-time обновлений
- Накопление точек в `metricsDataStore` для построения графиков
- Отрисовка графиков через Chart.js с временной осью Luxon
- Загрузка аналитики (статистика, тренды) через `/metrics/analysis`

**Архитектура frontend**:
- **Веб-компонент** `<metrics-dashboard>` с инкапсулированной логикой
- **Хранилище данных**: Map для каждой метрики с накоплением точек
- **Debounce механизм**: Предотвращение частых переподключений (3 сек)
- **Heartbeat обработка**: Корректное отображение стабильных метрик

**Ключевые особенности**:
- **Real-time обновления**: Server-Sent Events обеспечивают низкую задержку
- **Интерактивность**: Выбор метрик, настройка интервала и глубины истории
- **Аналитика**: Таблица со средним, мин/макс, последним значением и трендом
- **Визуальное отличие состояний**:
  - Метрика стабильна: горизонтальная линия с heartbeat-точками
  - Метрика не отслеживается: отсутствие новых точек

**Конфигурация компонента**:
```html
<metrics-dashboard 
    server-url="http://localhost:8000"
    interval="10" 
    minutes="10">
</metrics-dashboard>
```

| Параметр | Диапазон | По умолчанию |
|----------|----------|--------------|
| `interval` | 1-300 сек | 20 сек |
| `minutes` | 1-1440 мин | 30 мин |

**Файлы**:
- `services/web_dashboard/info.md` — подробная документация

---

### 6. Marimo Dashboard

**Назначение**: Интерактивная Jupyter-подобная тетрадка для углублённого анализа.

**Особенности**:
- Две панели графиков
- Выполнение Python-кода в браузере
- Интеграция с Metrics Client API

**Доступ**: http://localhost:8080

---

## Изменения в архитектуре (обновление от 2024)

### Проблема различения состояний метрик

**До изменений**:
- Компрессор `cpu_monitor` отправлял только изменяющиеся значения
- Стабильные метрики не передавались после первого значения
- **Проблема**: Невозможно отличить "метрика не меняется" от "метрика не отслеживается"

**Решение**: Внедрён heartbeat-механизм

### Обновлённая архитектура cpu_monitor

**Компоненты**:
1. **StreamingCompressor** с heartbeat:
   - `_last_sent_timestamp`: Время последней отправки
   - `_last_sent_value`: Последнее отправленное значение
   - `max_silent_interval`: Максимальный интервал молчания (10 сек)
   
2. **Алгоритм heartbeat**:
   ```python
   if time_since_last_send >= max_silent_interval:
       heartbeat_point = (current_time, last_sent_value)
       send(heartbeat_point)  # Keepalive-сигнал
   ```

3. **Логирование**: `[COMPRESSOR] Heartbeat sent: (timestamp, value)`

### Обновлённая архитектура web_dashboard

**Изменения**:
1. **Обработка heartbeat-точек**:
   - Точки с одинаковыми значениями добавляются в график
   - Визуально: горизонтальная линия с точками через равные интервалы

2. **Отличие состояний**:
   - **Стабильная метрика**: Новые точки появляются каждые `max_silent_interval` сек с тем же значением
   - **Отсутствие метрики**: Нет новых точек в течение `interval * 2+` секунд

3. **Аналитика**: Статистика учитывает heartbeat-точки (среднее, тренды)

### Преимущества новой архитектуры

1. **Надёжность мониторинга**: Чёткое различие между стабильностью и потерей данных
2. **Эффективность**: Сжатие сохраняется, но добавлены редкие heartbeat-сигналы
3. **Визуальная ясность**: Пользователь видит разницу на графиках
4. **Гибкая настройка**: `COMPRESSOR_MAX_SILENT_INTERVAL` регулирует частоту heartbeat

---

## Сценарии развёртывания

### Production (Docker Compose)

```bash
docker compose up -d --build
```

Все сервисы запускаются в изолированных контейнерах с сетью `metrics-net`.

### Development (локальный запуск)

```bash
# Терминал 1: InfluxDB в Docker
docker run -d --name influxdb -p 8086:8086 ... influxdb:2.7-alpine

# Терминал 2: Metrics Server
cd services/metrics_server && python -m server.main

# Терминал 3: Metrics Client API
cd services/metrics_client_api && uvicorn metrics_client_api.main:app --reload

# Терминал 4: CPU Monitor
cd services/cpu_monitor && python -m cpu_monitor.main

# Терминал 5: Web Dashboard
cd services/web_dashboard && python -m web_dashboard.server
```

### Hybrid (частично Docker, частично на хосте)

```bash
# Запустить только инфраструктуру в Docker
docker compose up -d influxdb metrics_server

# Остальные сервисы запустить локально для отладки
```

---

## Диагностика и мониторинг

### Health Check endpoints

```bash
curl http://localhost:8000/metrics/names          # API
curl http://localhost:4000                         # Web Dashboard
curl http://localhost:8086/health                  # InfluxDB
```

### Проверка heartbeat

1. Запустите cpu_monitor с включённым компрессором:
   ```bash
   export CPU_COMPRESSOR=sausage_links
   export COMPRESSOR_MAX_SILENT_INTERVAL=5.0
   python -m cpu_monitor.main
   ```

2. Наблюдайте логи компрессора:
   ```
   [COMPRESSOR] Heartbeat sent: (1711450123, 42.5)
   ```

3. В web_dashboard проверьте график стабильной метрики:
   - Должны быть видны точки через равные интервалы (~5 сек)
   - Значения одинаковые (горизонтальная линия)

### Логи сервисов

```bash
docker compose logs -f cpu_monitor
docker compose logs -f metrics_client_api
docker compose logs -f web_dashboard
```

---

## Будущие улучшения

1. **Динамический heartbeat**: Адаптивный интервал в зависимости от волатильности метрики
2. **Компрессия на стороне сервера**: Дополнительное сжатие перед записью в InfluxDB
3. **Alerting**: Уведомления при отсутствии heartbeat от критичных метрик
4. **Multi-agent support**: Поддержка множества cpu_monitor агентов с разными hostnames
5. **WebSocket вместо SSE**: Двусторонняя связь для управления агентами из дашборда
