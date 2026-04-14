# Marimo Dashboard

Интерактивная тетрадка Marimo для анализа и визуализации метрик с двумя панелями графиков.

## Назначение

- Интерактивный анализ исторических данных в реальном времени
- Построение кастомных графиков на двух панелях
- Исследование данных в формате Jupyter-подобной тетрадки
- Отображение статистики метрик (среднее, тренд, мин/макс)

## Структура проекта

```text
marimo_dashboard/
├── Dockerfile
├── README.md
├── pyproject.toml
└── notebooks/
    └── dashboard.py
```

## Зависимости

- Python 3.11+
- marimo>=0.8.0
- requests>=2.31.0
- pandas
- numpy
- plotly

## Конфигурация

Сервис настраивается через переменные окружения:

| Переменная | Описание | Пример | По умолчанию |
|------------|----------|--------|--------------|
| `METRICS_CLIENT_API_HOST` | Хост API клиента метрик | `metrics_client_api` | `localhost` |
| `METRICS_CLIENT_API_PORT` | Порт API клиента метрик | `8000` | `8000` |
| `MARIMO_HOST` | Хост для прослушивания | `0.0.0.0` | `0.0.0.0` |
| `MARIMO_PORT` | Порт для прослушивания | `8080` | `8080` |

---

## Запуск в Docker Compose

### Production режим

Сервис запускается как часть общего compose-файла:

```bash
docker compose up -d marimo_dashboard
```

Конфигурация в `docker-compose.yml`:

```yaml
marimo_dashboard:
  build:
    context: ./services/marimo_dashboard
  container_name: marits-marimo
  volumes:
    - ./services/marimo_dashboard/notebooks:/app/notebooks
  ports:
    - "8080:8080"
  environment:
    METRICS_CLIENT_API_HOST: metrics_client_api
    METRICS_CLIENT_API_PORT: "8000"
  depends_on:
    - metrics_client_api
  networks:
    - metrics-net
  restart: unless-stopped
```

### Debug режим

Запуск с пересборкой и просмотром логов:

```bash
# Пересборка и запуск
docker compose up marimo_dashboard --build

# Просмотр логов
docker compose logs -f marimo_dashboard

# Доступ к тетрадке
# http://localhost:8080
```

---

## Запуск на хосте (без Docker)

### Установка

```bash
cd services/marimo_dashboard

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
export METRICS_CLIENT_API_HOST=localhost
export METRICS_CLIENT_API_PORT=8000

# Запуск marimo в режиме редактирования
marimo edit notebooks/dashboard.py --host 0.0.0.0 --port 8080
```

### Запуск в production режиме

```bash
# Установка переменных окружения
export METRICS_CLIENT_API_HOST=localhost
export METRICS_CLIENT_API_PORT=8000

# Запуск в режиме только для чтения
marimo run notebooks/dashboard.py --host 0.0.0.0 --port 8080
```

---

## Проверка работоспособности

### curl примеры

```bash
# Проверка доступности
curl http://localhost:8080/
```

### Браузер

Откройте в браузере:

```
http://localhost:8080
```

---

## Функционал тетрадки

### Две панели графиков

- **Панель 1**: Отображает первую половину выбранных метрик
- **Панель 2**: Отображает вторую половину выбранных метрик
- Общие оси X для синхронизации по времени
- Интерактивные легенды и hover-эффекты

### Элементы управления

- **Выбор метрик**: Мультивыбор из доступных метрик
- **Временное окно**: Слайдер от 1 до 60 минут
- **Кнопка обновления**: Ручная загрузка данных
- **Таблица статистики**: Среднее, станд. отклонение, тренд, мин/макс, последнее значение

### Визуализация

- Временные ряды с интерактивными графиками Plotly
- Цветовое кодирование для разных метрик
- Unified hover для сравнения значений в один момент времени
- Адаптивная высота графиков

---

## Troubleshooting

### Тетрадка не загружается

1. Проверьте доступность API метрик:
   ```bash
   curl http://localhost:8000/metrics/names
   ```

2. Убедитесь, что порт 8080 свободен:
   ```bash
   netstat -tlnp | grep 8080
   ```

3. Проверьте логи:
   ```bash
   docker compose logs marimo_dashboard
   ```

### Ошибки при загрузке данных

- Проверьте, что сервис `metrics_client_api` запущен
- Убедитесь, что данные доступны за запрашиваемый период
- Проверьте логи тетрадки на наличие ошибок парсинга

### Графики не отображаются

- Выберите метрики в селекторе
- Нажмите кнопку "Обновить данные"
- Убедитесь, что выбранные метрики содержат данные

---

## Разработка

### Редактирование тетрадки

1. Запустите в режиме редактирования:
   ```bash
   marimo edit notebooks/dashboard.py --host 0.0.0.0 --port 8080
   ```

2. Внесите изменения в ячейки кода
3. Сохраните файл (Ctrl+S / Cmd+S)
4. Перезапустите в режиме просмотра для проверки

### Добавление новых панелей

Для добавления третьей панели обновите `make_subplots`:

```python
fig = make_subplots(
    rows=3, cols=1,
    subplot_titles=("Панель 1", "Панель 2", "Панель 3"),
    vertical_spacing=0.08,
    shared_xaxes=True
)
```

### Настройка стилей

Измените параметры `update_layout`:

```python
fig.update_layout(
    height=1000,  # Общая высота
    template="plotly_dark",  # Тема: plotly_white, plotly_dark, ggplot2
    margin=dict(l=60, r=40, t=80, b=60)
)
```

---

## Интеграция

### С Metrics Client API

Тетрадка получает данные через REST API:

```python
import requests
import pandas as pd

API_BASE = f"http://{API_HOST}:{API_PORT}"

def get_metrics(metric_name, minutes=30):
    response = requests.get(
        f"{API_BASE}/metrics/{metric_name}",
        params={"minutes": minutes}
    )
    data = response.json()
    return pd.DataFrame(data["points"])
```

### С Web Dashboard

Оба интерфейса используют одни данные:

- **Web Dashboard** — для мониторинга в реальном времени (SSE поток)
- **Marimo Dashboard** — для глубокого анализа и отчётов по запросу

---

## Мониторинг

### Health Check

```bash
curl http://localhost:8080/
```

Ожидаемый ответ — HTML страница тетрадки.

### Docker Health Check

Автоматическая проверка каждые 30 секунд:

```bash
docker inspect --format='{{.State.Health.Status}}' marits-marimo
```

---

## Отличия от Web Dashboard

| Характеристика | Web Dashboard | Marimo Dashboard |
|----------------|---------------|------------------|
| Тип интерфейса | Статический веб | Интерактивная тетрадка |
| Обновление данных | Автоматическое (SSE, 20 сек) | По запросу (кнопка) |
| Количество панелей | 1 график | 2 панели графиков |
| Кастомизация | Ограниченная | Полная (Python код) |
| Таблица статистики | Нет | Есть |
| Требует знаний | Нет | Базовый Python |

---

## Планы развития

- Добавить автоматическое обновление по таймеру
- Реализовать экспорт данных в CSV/XLSX
- Добавить предопределённые шаблоны отчётов
- Поддержка алертов при превышении порогов
- Экспорт графиков в PNG/SVG
