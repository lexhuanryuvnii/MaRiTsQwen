# Web Dashboard

Веб-интерфейс для визуализации системных метрик в реальном времени.

## Назначение

- Отображение метрик CPU, памяти и диска в реальном времени
- Построение графиков исторических данных
- Предоставление удобного UI для мониторинга системы

## Структура проекта

```text
web_dashboard/
├── Dockerfile
├── pyproject.toml
├── README.md
└── src/
    └── web_dashboard/
        ├── __init__.py
        ├── main.py
        ├── static/
        │   ├── css/
        │   └── js/
        └── templates/
            └── index.html
```

## Зависимости

- Python 3.11+
- fastapi>=0.115.0
- uvicorn[standard]>=0.30.0
- aiohttp (для запросов к API)
- jinja2 (для шаблонов)

## Конфигурация

Сервис настраивается через переменные окружения:

| Переменная | Описание | Пример | По умолчанию |
|------------|----------|--------|--------------|
| `METRICS_API_BASE` | URL базового API метрик | `http://metrics_client_api:8000` | `http://localhost:8000` |
| `WEB_DASHBOARD_HOST` | Хост для прослушивания | `0.0.0.0` | `0.0.0.0` |
| `WEB_DASHBOARD_PORT` | Порт для прослушивания | `4000` | `4000` |

---

## Запуск в Docker Compose

### Production режим

Сервис запускается как часть общего compose-файла:

```bash
docker compose up -d web_dashboard
```

Конфигурация в `docker-compose.yml`:

```yaml
web_dashboard:
  build:
    context: ./services/web_dashboard
  container_name: marits-web-ui
  ports:
    - "4000:4000"
  environment:
    METRICS_API_BASE: http://metrics_client_api:8000
    WEB_DASHBOARD_HOST: 0.0.0.0
    WEB_DASHBOARD_PORT: "4000"
  depends_on:
    - metrics_client_api
  networks:
    - metrics-net
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:4000/health"]
    interval: 10s
    timeout: 5s
    retries: 3
```

### Debug режим

Запуск с пересборкой и hot-reload:

```bash
# Пересборка и запуск
docker compose up web_dashboard --build

# Просмотр логов в реальном времени
docker compose logs -f web_dashboard

# Доступ к дашборду
# http://localhost:4000
```

Для включения hot-reload раскомментируйте в `docker-compose.yml`:

```yaml
web_dashboard:
  volumes:
    - ./services/web_dashboard/src:/app/src
  command: ["uvicorn", "web_dashboard.main:app", "--host", "0.0.0.0", "--port", "4000", "--reload"]
```

---

## Запуск на хосте (без Docker)

### Установка

```bash
cd services/web_dashboard

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
export METRICS_API_BASE=http://localhost:8000
export WEB_DASHBOARD_HOST=0.0.0.0
export WEB_DASHBOARD_PORT=4000

# Запуск с auto-reload
uvicorn web_dashboard.main:app --host 0.0.0.0 --port 4000 --reload
```

### Запуск в production режиме

```bash
# Установка переменных окружения
export METRICS_API_BASE=http://metrics_client_api:8000
export WEB_DASHBOARD_HOST=0.0.0.0
export WEB_DASHBOARD_PORT=4000

# Запуск с несколькими workers
uvicorn web_dashboard.main:app --host 0.0.0.0 --port 4000 --workers 4
```

---

## Проверка работоспособности

### curl примеры

```bash
# Проверка health
curl http://localhost:4000/health

# Проверка главной страницы
curl http://localhost:4000/
```

### Браузер

Откройте в браузере:

```
http://localhost:4000
```

---

## Функционал

### Главная страница

- График загрузки CPU в реальном времени
- График использования памяти
- Статистика по дисковым операциям

### Обновление данных

Данные обновляются автоматически каждые 5 секунд через JavaScript fetch API.

### Адаптивный дизайн

Интерфейс адаптируется под разные размеры экрана (desktop, tablet, mobile).

---

## Troubleshooting

### Дашборд не загружается

1. Проверьте доступность API метрик:
   ```bash
   curl http://localhost:8000/health
   ```

2. Убедитесь, что переменная `METRICS_API_BASE` корректна:
   ```bash
   docker compose exec web_dashboard env | grep METRICS
   ```

3. Проверьте логи:
   ```bash
   docker compose logs web_dashboard
   ```

### Данные не обновляются

- Откройте консоль разработчика в браузере (F12)
- Проверьте наличие ошибок JavaScript
- Убедитесь, что API возвращает данные в ожидаемом формате

### Проблемы с CORS

Если видите ошибки CORS, убедитесь, что API настроен на разрешение запросов с вашего домена.

---

## Разработка

### Добавление новых графиков

1. Создайте новый шаблон в `src/web_dashboard/templates/`
2. Добавьте endpoint в `src/web_dashboard/main.py`
3. Напишите JavaScript для обновления данных

### Кастомизация стилей

Стили находятся в `src/web_dashboard/static/css/`. Основные файлы:

- `style.css` — основные стили
- `charts.css` — стили для графиков

### Тестирование

```bash
# Линтинг
flake8 src/web_dashboard/

# Проверка типов
mypy src/web_dashboard/
```

---

## Интеграция

### С Metrics Client API

Дашборд получает данные через REST API:

```javascript
async function fetchMetrics() {
  const response = await fetch(`${API_BASE}/metrics/cpu.usage_percent`);
  const data = await response.json();
  updateChart(data);
}
```

### С Marimo Dashboard

Оба дашборда используют одни и те же данные из API, но предоставляют разный интерфейс:

- **Web Dashboard** — статический веб-интерфейс
- **Marimo Dashboard** — интерактивная тетрадка для анализа

---

## Мониторинг

### Health Check

```bash
curl http://localhost:4000/health
```

Ожидаемый ответ:

```json
{"status": "ok"}
```

### Метрики самого сервиса

Планируется добавить endpoint для сбора метрик о работе дашборда:
- Количество активных подключений
- Время загрузки страницы
- Частота обновления данных
