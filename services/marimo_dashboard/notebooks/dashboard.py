import marimo

__generated_with = "0.8.0"
app = marimo.App()


@app.cell
def _(marimo, os):
    """
    Конфигурация подключения к API
    """
    # Адрес API сервиса метрик
    API_HOST = os.getenv("METRICS_CLIENT_API_HOST", "metrics_client_api")
    API_PORT = int(os.getenv("METRICS_CLIENT_API_PORT", "8000"))
    API_BASE_URL = f"http://{API_HOST}:{API_PORT}"
    
    import requests
    import pandas as pd
    import numpy as np
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from datetime import datetime
    import time
    
    return


@app.cell
def _(marimo):
    """
    Элементы управления дашбордом
    """
    # Выбор метрик для отображения
    metrics_selector = marimo.ui.multiselect(
        label="Выберите метрики для отображения",
        options=[],  # Будет заполнено динамически
        value=[]
    )
    
    # Выбор временного окна (минуты)
    time_window = marimo.ui.slider(
        label="Временное окно (минут)",
        start=1,
        stop=60,
        step=1,
        value=30
    )
    
    # Интервал обновления (секунды)
    refresh_interval = marimo.ui.slider(
        label="Интервал обновления (секунд)",
        start=5,
        stop=60,
        step=5,
        value=20
    )
    
    # Кнопка ручного обновления
    refresh_btn = marimo.ui.button(label="Обновить данные")
    
    return metrics_selector, time_window, refresh_interval, refresh_btn


@app.cell
def _(API_BASE_URL, requests):
    """
    Получение списка доступных метрик
    """
    def get_metric_names():
        try:
            response = requests.get(f"{API_BASE_URL}/metrics/names", timeout=5)
            response.raise_for_status()
            data = response.json()
            return data.get("metrics", [])
        except Exception as e:
            print(f"Ошибка получения списка метрик: {e}")
            return []
    
    available_metrics = get_metric_names()
    return available_metrics, get_metric_names


@app.cell
def _(marimo, available_metrics, metrics_selector):
    """
    Обновление опций селектора метрик
    """
    # Динамическое обновление опций селектора
    if available_metrics:
        marimo.moi.update(metrics_selector, options=available_metrics)
    return


@app.cell
def _(API_BASE_URL, time_window, metrics_selector, requests, pd):
    """
    Получение данных метрик и статистики
    """
    def fetch_metrics_data(metrics_list, minutes):
        """Получает данные метрик и статистику"""
        if not metrics_list:
            return None, None
        
        metrics_str = ",".join(metrics_list)
        
        try:
            # Получаем временные ряды
            series_data = {}
            for metric in metrics_list:
                resp = requests.get(
                    f"{API_BASE_URL}/metrics/{metric}",
                    params={"minutes": minutes},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    points = data.get("points", [])
                    if points:
                        df = pd.DataFrame(points)
                        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
                        series_data[metric] = df
            
            # Получаем статистику
            stats_data = {}
            resp = requests.get(
                f"{API_BASE_URL}/metrics/analysis",
                params={"metrics": metrics_str, "minutes": minutes},
                timeout=10
            )
            if resp.status_code == 200:
                analysis = resp.json()
                stats_data = analysis.get("stats", {})
            
            return series_data, stats_data
            
        except Exception as e:
            print(f"Ошибка получения данных: {e}")
            return None, None
    
    return fetch_metrics_data


@app.cell
def _(refresh_btn, fetch_metrics_data, metrics_selector, time_window):
    """
    Загрузка данных при нажатии кнопки обновления
    """
    if refresh_btn:
        selected_metrics = metrics_selector.value if hasattr(metrics_selector, 'value') else []
        minutes = time_window.value if hasattr(time_window, 'value') else 30
        
        series_data, stats_data = fetch_metrics_data(selected_metrics, minutes)
    else:
        series_data, stats_data = None, None
    
    return series_data, stats_data


@app.cell
def _(series_data, stats_data, go, make_subplots, pd, np):
    """
    Построение графиков на двух панелях
    """
    if series_data is None or not series_data:
        marimo.md("**Нет данных для отображения.** Выберите метрики и нажмите 'Обновить данные'")
    else:
        # Создаем фигуру с двумя подграфиками (панелями)
        num_metrics = len(series_data)
        
        if num_metrics == 0:
            marimo.md("**Нет данных для выбранных метрик**")
        else:
            # Разделяем метрики на две панели
            metrics_list = list(series_data.keys())
            first_panel_metrics = metrics_list[:len(metrics_list)//2 + len(metrics_list)%2]
            second_panel_metrics = metrics_list[len(metrics_list)//2 + len(metrics_list)%2:]
            
            # Создаем сабплоты: 2 ряда, 1 колонка
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=("Панель 1: Временные ряды", "Панель 2: Временные ряды"),
                vertical_spacing=0.12,
                shared_xaxes=True
            )
            
            # Цвета для линий
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
                     '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
            
            # Добавляем графики на первую панель
            for i, metric in enumerate(first_panel_metrics):
                df = series_data[metric]
                color = colors[i % len(colors)]
                
                fig.add_trace(
                    go.Scatter(
                        x=df["timestamp"],
                        y=df["value"],
                        mode="lines",
                        name=metric,
                        line=dict(color=color, width=2),
                        hovertemplate=f"<b>{metric}</b><br>Время: %{{x|%Y-%m-%d %H:%M:%S}}<br>Значение: %{{y:.2f}}<extra></extra>"
                    ),
                    row=1, col=1
                )
            
            # Добавляем графики на вторую панель
            for i, metric in enumerate(second_panel_metrics):
                df = series_data[metric]
                color = colors[(i + len(first_panel_metrics)) % len(colors)]
                
                fig.add_trace(
                    go.Scatter(
                        x=df["timestamp"],
                        y=df["value"],
                        mode="lines",
                        name=metric,
                        line=dict(color=color, width=2),
                        showlegend=False if i > 0 else True,
                        hovertemplate=f"<b>{metric}</b><br>Время: %{{x|%Y-%m-%d %H:%M:%S}}<br>Значение: %{{y:.2f}}<extra></extra>"
                    ),
                    row=2, col=1
                )
            
            # Обновляем layout
            fig.update_layout(
                height=800,
                title_text="Дашборд метрик",
                title_font_size=20,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified",
                template="plotly_white",
                margin=dict(l=60, r=40, t=80, b=60)
            )
            
            # Обновляем оси
            fig.update_xaxes(title_text="Время", row=2, col=1)
            fig.update_yaxes(title_text="Значение", row=1, col=1)
            fig.update_yaxes(title_text="Значение", row=2, col=1)
            
            # Отображаем график
            fig
            
            # Если есть статистика, отображаем её в виде таблицы
            if stats_data:
                stats_rows = []
                for metric, stats in stats_data.items():
                    stats_rows.append({
                        "Метрика": metric,
                        "Среднее": round(stats.get("mean", 0), 2),
                        "Стд. откл.": round(stats.get("std", 0), 2),
                        "Тренд": round(stats.get("trend", 0), 4),
                        "Мин": round(stats.get("min_val", 0), 2),
                        "Макс": round(stats.get("max_val", 0), 2),
                        "Последнее": round(stats.get("last_value", 0), 2),
                        "Растет": "↑" if stats.get("is_increasing", False) else "↓"
                    })
                
                if stats_rows:
                    stats_df = pd.DataFrame(stats_rows)
                    marimo.md("### Статистика метрик")
                    stats_df


@app.cell
def _():
    """
    Автоматическое обновление (опционально)
    """
    # Для автоматического обновления можно использовать marimo.ui.refresh
    # или настроить периодический запуск через внешний триггер
    return


if __name__ == "__main__":
    app.run()
