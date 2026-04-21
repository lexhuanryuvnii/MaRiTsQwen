"""Реализация агента сбора и отправки метрик с независимой отправкой по метрикам."""

import os
import time
from typing import Literal, Dict, List, Tuple, Optional

from cpu_monitor.collector import collect_cpu_metrics
from cpu_monitor.compressor import StreamingCompressor, CompressorName


MetricPoints = Dict[str, List[Tuple[int, float]]]


class MetricStream:
    """
    Управляет потоком одной метрики: буферизация, сжатие и отправка.
    Каждая метрика имеет свой собственный компрессор и может регулировать частоту отправки.
    """
    
    def __init__(
        self,
        metric_name: str,
        compressor_name: CompressorName = "none",
        deviation: float = 0.5,
        auto_dev_factor: float = 0.5,
        ema_alpha: float = 0.3,
        send_threshold: int = 1,  # Количество точек для триггера отправки
    ):
        self.metric_name = metric_name
        self.compressor_name = compressor_name
        self.send_threshold = send_threshold
        
        self._compressor = StreamingCompressor(
            compressor_name=compressor_name,
            deviation=deviation,
            auto_dev_factor=auto_dev_factor,
            ema_alpha=ema_alpha,
        )
        self._pending_points: List[Tuple[int, float]] = []
    
    def add_points(self, points: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
        """
        Добавляет новые точки в поток метрики.
        Возвращает сжатые точки, готовые к отправке.
        """
        # Пропускаем через компрессор
        compressed = self._compressor.add_points(points)
        
        # Буферизуем сжатые точки
        self._pending_points.extend(compressed)
        
        # Проверяем, пора ли отправлять
        ready_to_send = []
        if len(self._pending_points) >= self.send_threshold:
            ready_to_send = self._pending_points[:]
            self._pending_points = []
        
        return ready_to_send
    
    def flush(self) -> List[Tuple[int, float]]:
        """Сбрасывает все накопленные точки для отправки."""
        flushed = self._pending_points[:]
        self._pending_points = []
        return flushed


def run_agent(
    api_url: str,
    interval: float,
    compressor_name: CompressorName = "none",
    deviation: float = 0.5,
    auto_dev_factor: float = 0.5,
    ema_alpha: float = 0.3,
    send_threshold: int = 1,
) -> None:
    print(
        f"Starting CPU monitor with independent metric streams: "
        f"api_url={api_url}, interval={interval}s, "
        f"compressor={compressor_name}, deviation={deviation}, "
        f"auto_dev_factor={auto_dev_factor}, ema_alpha={ema_alpha}"
    )
    
    # Словарь потоков для каждой метрики
    metric_streams: Dict[str, MetricStream] = {}
    
    while True:
        try:
            time.sleep(interval)
            
            # Собираем сырые метрики
            raw_points = collect_cpu_metrics(interval=1.0)
            print(f"Collected raw metrics for {len(raw_points)} metrics")
            
            # Обрабатываем каждую метрику независимо
            for metric_name, points in raw_points.items():
                # Создаём поток для новой метрики при первом появлении
                if metric_name not in metric_streams:
                    metric_streams[metric_name] = MetricStream(
                        metric_name=metric_name,
                        compressor_name=compressor_name,
                        deviation=deviation,
                        auto_dev_factor=auto_dev_factor,
                        ema_alpha=ema_alpha,
                        send_threshold=send_threshold,
                    )
                    print(f"Created stream for metric: {metric_name}")
                
                # Получаем сжатые точки для отправки
                stream = metric_streams[metric_name]
                ready_points = stream.add_points(points)
                
                if ready_points:
                    # Отправляем только эту метрику
                    _send_metric_batch(
                        metric_name=metric_name,
                        points=ready_points,
                        api_url=api_url,
                    )
                    print(
                        f"Sent {len(ready_points)} points for {metric_name}: "
                        f"{ready_points[:3]}..." if len(ready_points) > 3 
                        else f"Sent {len(ready_points)} points for {metric_name}: {ready_points}"
                    )
            
            # Логируем количество активных потоков
            print(f"Active metric streams: {list(metric_streams.keys())}")
            
        except KeyboardInterrupt:
            print("Shutting down agent...")
            # Сбрасываем оставшиеся точки перед выходом
            for metric_name, stream in metric_streams.items():
                remaining = stream.flush()
                if remaining:
                    _send_metric_batch(
                        metric_name=metric_name,
                        points=remaining,
                        api_url=api_url,
                    )
                    print(f"Flushed {len(remaining)} points for {metric_name}")
            break
        except Exception as exc:
            print(f"Agent error: {exc}, continuing...")


def _send_metric_batch(
    metric_name: str,
    points: List[Tuple[int, float]],
    api_url: str,
) -> None:
    """
    Отправляет пакет точек для ОДНОЙ метрики в /metrics/put_batch.
    
    Формат JSON:
      [
        {"metric": "cpu.usage_percent", "value": 42.5, "timestamp": 1711450000},
        ...
      ]
    """
    import requests
    
    endpoint = api_url.rstrip("/") + "/metrics/put_batch"
    
    payload = [
        {
            "metric": metric_name,
            "value": value,
            "timestamp": ts,
        }
        for ts, value in points
    ]
    
    if not payload:
        return
    
    resp = requests.post(endpoint, json=payload, timeout=5.0)
    if not resp.ok:
        raise RuntimeError(
            f"Failed to send metrics batch for {metric_name}: {resp.status_code} {resp.text}"
        )


def main() -> None:
    """CLI‑обёртка, читающая env‑переменные и запускающая run_agent()."""
    
    api_url = os.getenv("METRICS_API_URL", "http://localhost:8000")
    interval = float(os.getenv("CPU_SCRAPE_INTERVAL", "5.0"))
    compressor_name: CompressorName = os.getenv("CPU_COMPRESSOR", "none")  # type: ignore
    deviation = float(os.getenv("COMPRESSOR_DEVIATION", "0.5"))
    auto_dev_factor = float(os.getenv("COMPRESSOR_AUTO_DEV_FACTOR", "0.5"))
    ema_alpha = float(os.getenv("COMPRESSOR_EMA_ALPHA", "0.3"))
    send_threshold = int(os.getenv("SEND_THRESHOLD", "1"))
    
    run_agent(
        api_url=api_url,
        interval=interval,
        compressor_name=compressor_name,
        deviation=deviation,
        auto_dev_factor=auto_dev_factor,
        ema_alpha=ema_alpha,
        send_threshold=send_threshold,
    )


if __name__ == "__main__":
    main()
