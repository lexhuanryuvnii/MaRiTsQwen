"""Реализация агента сбора и отправки метрик с пакетной отправкой и потоковым сжатием."""

import os
import time
import threading
from typing import Literal, Dict, List, Tuple, Optional

from cpu_monitor.collector import collect_cpu_metrics
from cpu_monitor.compressor import StreamingCompressor, CompressorName
from cpu_monitor.sender import send_points_batch


MetricPoints = Dict[str, List[Tuple[int, float]]]


class MetricStream:
    """
    Управляет потоком одной метрики: буферизация, сжатие.
    Каждая метрика имеет свой собственный компрессор.
    """
    
    def __init__(
        self,
        metric_name: str,
        compressor_name: CompressorName = "none",
        deviation: float = 0.5,
        auto_dev_factor: float = 0.5,
        ema_alpha: float = 0.3,
        max_silent_interval: float = 10.0,
    ):
        self.metric_name = metric_name
        self.compressor_name = compressor_name
        
        self._compressor = StreamingCompressor(
            compressor_name=compressor_name,
            deviation=deviation,
            auto_dev_factor=auto_dev_factor,
            ema_alpha=ema_alpha,
            max_silent_interval=max_silent_interval,
        )
        # Буфер сжатых точек, готовых к отправке
        self._compressed_buffer: List[Tuple[int, float]] = []
        self._lock = threading.Lock()
    
    def add_points(self, points: List[Tuple[int, float]]) -> None:
        """
        Добавляет новые точки в поток метрики.
        Сжатые точки помещаются в буфер для последующей отправки.
        """
        with self._lock:
            # Пропускаем через компрессор (heartbeat проверяется внутри)
            compressed = self._compressor.add_points(points)
            # Буферизуем сжатые точки
            self._compressed_buffer.extend(compressed)
    
    def flush_to_send(self) -> List[Tuple[int, float]]:
        """Забирает все накопленные сжатые точки для отправки."""
        with self._lock:
            if not self._compressed_buffer:
                return []
            ready = self._compressed_buffer[:]
            self._compressed_buffer = []
            return ready
    
    def final_flush(self) -> List[Tuple[int, float]]:
        """Сбрасывает все точки включая незавершённые перед остановкой."""
        with self._lock:
            # Забираем буфер
            result = self._compressed_buffer[:]
            self._compressed_buffer = []
            # Добавляем оставшиеся точки из компрессора
            remaining = self._compressor.flush()
            result.extend(remaining)
            return result


def run_agent(
    api_url: str,
    collection_interval: float,
    batch_send_interval: float,
    compressor_name: CompressorName = "none",
    deviation: float = 0.5,
    auto_dev_factor: float = 0.5,
    ema_alpha: float = 0.3,
    max_silent_interval: float = 10.0,
) -> None:
    print(
        f"Starting CPU monitor with batch sending and streaming compression: "
        f"api_url={api_url}, collection_interval={collection_interval}s, "
        f"batch_send_interval={batch_send_interval}s, "
        f"compressor={compressor_name}, deviation={deviation}, "
        f"auto_dev_factor={auto_dev_factor}, ema_alpha={ema_alpha}, "
        f"max_silent_interval={max_silent_interval}s"
    )
    
    # Словарь потоков для каждой метрики
    metric_streams: Dict[str, MetricStream] = {}
    streams_lock = threading.Lock()
    
    # Флаг остановки
    stop_event = threading.Event()
    
    def collect_loop():
        """Цикл сбора данных каждые collection_interval секунд."""
        while not stop_event.is_set():
            try:
                # Собираем сырые метрики (collector сам ждёт interval)
                raw_points = collect_cpu_metrics(interval=collection_interval)
                print(f"Collected raw metrics for {len(raw_points)} metrics")
                
                # Обрабатываем каждую метрику независимо
                with streams_lock:
                    for metric_name, points in raw_points.items():
                        # Создаём поток для новой метрики при первом появлении
                        if metric_name not in metric_streams:
                            metric_streams[metric_name] = MetricStream(
                                metric_name=metric_name,
                                compressor_name=compressor_name,
                                deviation=deviation,
                                auto_dev_factor=auto_dev_factor,
                                ema_alpha=ema_alpha,
                                max_silent_interval=max_silent_interval,
                            )
                            print(f"Created stream for metric: {metric_name}")
                        
                        # Добавляем точки в поток (сжатие происходит внутри)
                        stream = metric_streams[metric_name]
                        stream.add_points(points)
                
            except Exception as exc:
                print(f"Collection error: {exc}, continuing...")
    
    def send_loop():
        """Цикл отправки пакетов каждые batch_send_interval секунд."""
        while not stop_event.is_set():
            try:
                time.sleep(batch_send_interval)
                
                # Собираем все готовые к отправке точки из всех потоков
                batch_to_send: MetricPoints = {}
                
                with streams_lock:
                    for metric_name, stream in metric_streams.items():
                        ready_points = stream.flush_to_send()
                        if ready_points:
                            batch_to_send[metric_name] = ready_points
                        if metric_name == "cpu.freq.current_mhz":
                            print(f"CPU freq mhz to send: {ready_points}")
                
                # Отправляем пакет если есть данные
                if batch_to_send:
                    total_points = sum(len(pts) for pts in batch_to_send.values())
                    send_points_batch(batch_to_send, api_url)
                    print(
                        f"Sent batch with {total_points} points across "
                        f"{len(batch_to_send)} metrics"
                    )
                else:
                    print("No compressed points to send in this batch")
                
            except Exception as exc:
                print(f"Send error: {exc}, continuing...")
    
    # Запускаем потоки
    collector_thread = threading.Thread(target=collect_loop, daemon=True)
    sender_thread = threading.Thread(target=send_loop, daemon=True)
    
    collector_thread.start()
    sender_thread.start()
    
    # Ждём прерывания
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down agent...")
        stop_event.set()
        
        # Даём потокам немного времени на завершение
        collector_thread.join(timeout=2.0)
        sender_thread.join(timeout=2.0)
        
        # Финальная отправка всех оставшихся точек
        print("Flushing remaining points...")
        final_batch: MetricPoints = {}
        with streams_lock:
            for metric_name, stream in metric_streams.items():
                remaining = stream.final_flush()
                if remaining:
                    final_batch[metric_name] = remaining
                    print(f"Flushed {len(remaining)} points for {metric_name}")
        
        if final_batch:
            try:
                send_points_batch(final_batch, api_url)
                print("Final batch sent successfully")
            except Exception as exc:
                print(f"Failed to send final batch: {exc}")
        
        print("Agent stopped")


def main() -> None:
    """CLI‑обёртка, читающая env‑переменные и запускающая run_agent()."""
    
    api_url = os.getenv("METRICS_API_URL", "http://localhost:8000")
    collection_interval = float(os.getenv("CPU_COLLECTION_INTERVAL", "0.5"))
    batch_send_interval = float(os.getenv("BATCH_SEND_INTERVAL", "3.0"))
    compressor_name: CompressorName = os.getenv("CPU_COMPRESSOR", "none")  # type: ignore
    # deviation=1.0 подходит для метрик с небольшим изменением
    # Для частоты CPU (~2000-4000 MHz) используем меньшее значение
    # auto_dev_factor=0.5 включает адаптивное отклонение
    deviation = float(os.getenv("COMPRESSOR_DEVIATION", "1.0"))
    auto_dev_factor = float(os.getenv("COMPRESSOR_AUTO_DEV_FACTOR", "0.5"))
    ema_alpha = float(os.getenv("COMPRESSOR_EMA_ALPHA", "0.3"))
    # max_silent_interval - интервал в секундах, через который отправляется heartbeat
    # для неизменных метрик (чтобы отличить их от отсутствующих)
    max_silent_interval = float(os.getenv("COMPRESSOR_MAX_SILENT_INTERVAL", "10.0"))
    
    run_agent(
        api_url=api_url,
        collection_interval=collection_interval,
        batch_send_interval=batch_send_interval,
        compressor_name=compressor_name,
        deviation=deviation,
        auto_dev_factor=auto_dev_factor,
        ema_alpha=ema_alpha,
        max_silent_interval=max_silent_interval,
    )


if __name__ == "__main__":
    main()
