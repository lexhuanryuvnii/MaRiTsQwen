import os
import json
import asyncio
import numpy as np
import pandas as pd
from time import time
from typing import Dict, List, Tuple, Optional

from fastapi import FastAPI, HTTPException, Query, Response, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse


#from src.metrics_client import Client, ClientError
from metrics_client import Client, ClientError
from .models import PutMetricRequest, MetricPoint, PutMetricBatchItem, MetricNamesResponse, MetricSeriesResponse, AnalysisResponse, MetricStat

app = FastAPI(title="Metrics Client API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4000",
        "http://127.0.0.1:4000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#  Перенести в env да
# METRICS_SERVER_HOST = os.getenv("METRICS_SERVER_HOST", "localhost")
METRICS_SERVER_HOST = os.getenv("METRICS_SERVER_HOST", "metrics_server")
METRICS_SERVER_PORT = int(os.getenv("METRICS_SERVER_PORT", "8888"))

client = Client(host=METRICS_SERVER_HOST, port=METRICS_SERVER_PORT, timeout=5)

# Вспомогательная фигня 

def _filter_last_minutes(points: List[tuple[int, float]], minutes: int) -> List[MetricPoint]:
    cutoff = int(time()) - minutes * 60
    result: List[MetricPoint] = []
    for ts, value in points:
        if ts >= cutoff:
            result.append(MetricPoint(timestamp=ts, value=value))
    return result


# Эндпоинты


@app.get("/favicon.ico")
async def favicon():
    return Response(content="", media_type="favicon.ico")


@app.get("/metrics/names", response_model=MetricNamesResponse)
async def get_metric_names():    
    try:
        data = client.get("*")
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    names = sorted(data.keys())
    return MetricNamesResponse(metrics=names)

@app.get("/metrics/stream")
async def metrics_stream(
    request: Request,
    metrics: Optional[str] = Query(None, alias="metrics"),
    interval: int = Query(default=20, ge=5, le=60),
    minutes: int = Query(default=30, ge=1, le=60),
):
    """
    Метод для получения потока метрик в формате Server-Sent Events
    
    Parameters:
    metrics (str): Названия метрик, которые нужно вернуть (через запятую)
    interval (int): Интервал между событиями в секундах (min=5, max=60, default=20)
    minutes (int): Количество минут, за которые нужно вернуть метрики (min=1, max=60, default=30)
    
    Returns:
    StreamingResponse: Поток метрик в формате Server-Sent Events
    """
    first_run = True 
    target_metrics = metrics.split(",") if metrics else None
    print(f'Пришел запрос с параметрами {target_metrics=}\n, {interval=}\n, {minutes=}')

    async def event_generator(first_run):
        while True:

            if await request.is_disconnected():
                break

            if not first_run: await asyncio.sleep(interval)
            first_run = False

            try:
                now = int(time())
                cutoff = now - minutes * 60

                raw_data = await asyncio.to_thread(client.get, target_metrics)

                payload = {}
                for name, points in raw_data.items():
                    # Берем только свежие точки
                    recent = [p for p in points if p[0] >= cutoff]
                    
                    if recent:
                        # --- СГЛАЖИВАНИЕ С ПОМОЩЬЮ PANDAS ---
                        # Если точек достаточно, применяем скользящее среднее
                        # window=3 - среднее по 3 точкам. 
                        # Это уберет резкие пики точёные на графике.
                        
                        df_recent = pd.DataFrame(recent, columns=['timestamp', 'value'])
                        
                        # Скользящее среднее с min_periods=1 (чтобы не терять начало)
                        smoothed_values = df_recent['value'].rolling(window=3, min_periods=1).mean()
                        
                        # Собираем обратно в список словарей
                        # Используем сглаженные значения, но оригинальные timestamp
                        payload[name] = [
                            {"timestamp": int(ts), "value": float(val)} 
                            for ts, val in zip(df_recent['timestamp'], smoothed_values)
                        ]

                if payload:
                    yield f"data: {json.dumps({'timestamp': now, 'metrics': payload}, separators=(',', ':'))}\n\n"
                else:
                    yield ": ping\n\n"
                

            except Exception as exc:
                message = f"data: {json.dumps({'error': str(exc), "code": 500})}\n\n"
                print("ERROR: ", message)
                yield message


    return StreamingResponse(
        event_generator(first_run),
        media_type="text/event-stream",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no", 
        }
    )
                               

@app.get("/metrics/analysis", response_model=AnalysisResponse)
async def get_metrics_analysis(
    metrics: Optional[str] = Query(None, alias="metrics"),
    minutes: int = Query(default=30, ge=1, le=60)
):
    target_metrics = metrics.split(",") if metrics else None
    
    try:
        raw_data = await asyncio.to_thread(client.get, target_metrics)
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    now = int(time())
    cutoff = now - minutes * 60
    result_stats = {}

    for name, points in raw_data.items():
        if not points:
            continue

        # Фильтруем по времени
        recent_points = [(p[0], p[1]) for p in points if p[0] >= cutoff]
        if not recent_points:
            continue

        # --- PANDAS И NUMPY ---
        
        df = pd.DataFrame(recent_points, columns=['timestamp', 'value'])
        
        # Базовая статистика (Pandas)
        mean_val = df['value'].mean()
        std_val = df['value'].std()
        min_val = df['value'].min()
        max_val = df['value'].max()
        last_val = df.iloc[-1]['value']

        # Вычисляем тренд (Numpy - линейная регрессия)
        # Полином 1-й степени (линейная)
        # x - это время, y - значения. slope - наклон.
        if len(df) > 1:
            # Нормализуем время, чтобы избежать переполнения в полиноме
            x_normalized = df['timestamp'] - df['timestamp'].iloc[0]
            slope, intercept = np.polyfit(x_normalized, df['value'], 1)
            trend = slope # Изменение значения в единицу времени (секунду)
        else:
            trend = 0.0

        result_stats[name] = MetricStat(
            mean=round(float(mean_val), 2),
            std=round(float(std_val), 2),
            trend=round(float(trend) * 1000, 4), # Умножаем на 1000 для наглядности (изменение за 1000 сек)
            min_val=round(float(min_val), 2),
            max_val=round(float(max_val), 2),
            last_value=round(float(last_val), 2),
            is_increasing=bool(trend > 0)
        )

    return AnalysisResponse(stats=result_stats)

@app.get("/metrics/{metric_name}", response_model=MetricSeriesResponse)
async def get_metric(
    metric_name: str,
    minutes: int = Query(default=30, ge=1, le=24 * 60)
    ):
    try:
        data = client.get(metric_name)
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    print(f"[metrics] requested={metric_name}")
    print(f"[metrics] raw keys={list(data.keys())}")

    points: List[MetricPoint] = []
    if metric_name in data:
        points = _filter_last_minutes(data[metric_name], minutes)

    return MetricSeriesResponse(metric=metric_name, points=points)


@app.post("/metrics/put", status_code=204)
async def put_metric(payload: PutMetricRequest):
    try:
        client.put(
            metric=payload.metric,
            value=payload.value,
            timestamp=payload.timestamp,
        )
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return  # 204 No Content


@app.post("/metrics/put_batch", status_code=204)
async def put_metrics_batch(items: List[PutMetricBatchItem]):
    """
    Метод для отправки пакета метрик на сервер
    
    Parameters:
    items (List[PutMetricBatchItem]): Список метрик, которые нужно отправить на сервер
    
    Returns:
    204 No Content: Метрики успешно отправлены на сервер
    """
    if not items:
        return

    try:
        for item in items:
            client.put(
                metric=item.metric,
                value=item.value,
                timestamp=item.timestamp,
            )
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return