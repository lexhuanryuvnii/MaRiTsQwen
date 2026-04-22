"""Модуль сжатия метрик с использованием библиотеки SausageLinks."""

from typing import Literal, Dict, List, Tuple, Generator, Iterator, Optional
import sausage_links as sl

CompressorName = Literal["none", "sausage_links"] 

MetricPoints = Dict[str, List[Tuple[int, float]]]


def _sausage_links(
    source: Iterator[Tuple[int, float]],
    deviation: float = 0.1,
    max_len: float = 0,
    auto_dev_factor: float = 0,
    ema_alpha: float = 0.3,
) -> Generator[Tuple[int, float], None, None]:
    """
    Обёртка над библиотекой sausage_links для совместимости с существующим API.
    """
    yield from sl.sausage_links(
        source,
        deviation=deviation,
        max_len=max_len,
        auto_dev_factor=auto_dev_factor,
        ema_alpha=ema_alpha,
    )


class StreamingCompressor:
    """
    Потоковый компрессор для одной метрики.
    Поддерживает буферизацию точек и постепенное сжатие через Sausage Links.
    
    Для корректной работы потокового сжатия используется подход с накоплением
    и пересжатием всех точек при каждом добавлении новых данных.
    
    Алгоритм отправляет только первую точку и точки, где произошло значимое
    отклонение. Последняя точка ("открытый сегмент") не отправляется до тех
    пор, пока не появится новое значимое отклонение или не будет вызван flush().
    
    Для решения проблемы отличия "отсутствия отслеживания" от "неизменности метрики"
    реализован механизм heartbeat: если метрика не отправлялась дольше max_silent_interval,
    последняя точка отправляется принудительно как keepalive-сигнал.
    """
    
    def __init__(
        self,
        compressor_name: CompressorName = "none",
        deviation: float = 0.5,
        auto_dev_factor: float = 0.5,
        ema_alpha: float = 0.3,
        max_silent_interval: float = 10.0,  # Максимальный интервал молчания в секундах
    ):
        self.compressor_name = compressor_name
        self.deviation = deviation
        self.auto_dev_factor = auto_dev_factor
        self.ema_alpha = ema_alpha
        self.max_silent_interval = max_silent_interval
        
        # Буфер всех сырых точек для этой метрики
        self._all_points: List[Tuple[int, float]] = []
        # Множество timestamp'ов уже отправленных точек
        self._sent_timestamps: set = set()
        # Timestamp последней отправленной точки (для heartbeat)
        self._last_sent_timestamp: int = 0
        # Последнее отправленное значение (для heartbeat)
        self._last_sent_value: Optional[float] = None
    
    def add_points(self, points: List[Tuple[int, float]], current_time: Optional[int] = None) -> List[Tuple[int, float]]:
        """
        Добавляет новые точки в буфер и возвращает сжатые точки для отправки.
        
        При использовании Sausage Links происходит пересжатие всех накопленных
        точек. Возвращаются только те сжатые точки, которые ещё не были отправлены.
        
        Для постоянных метрик это означает, что будет отправлена только первая точка,
        а затем ничего, пока значение не изменится значительно.
        
        Реализует механизм heartbeat: если прошло больше max_silent_interval секунд
        с последней отправки, последняя известная точка отправляется повторно как
        keepalive-сигнал (чтобы отличить "метрика неизменна" от "метрика не отслеживается").
        
        Parameters:
        points: Список новых точек (timestamp, value)
        current_time: Текущий timestamp для проверки heartbeat (по умолчанию берется из последней точки)
        
        Returns:
        Список точек для отправки (может включать heartbeat-точку)
        """
        if self.compressor_name == "none":
            return points
        
        # Добавляем новые точки в общий буфер
        self._all_points.extend(points)
        
        # Сжимаем все точки заново
        compressed = self._compress_all()
        
        # Фильтруем точки: оставляем только те, чьи timestamp ещё не отправлены
        # ИСКЛЮЧАЯ последнюю точку (открытый сегмент)
        new_points_to_send = []
        
        # Проверяем все точки кроме последней (она всегда открытый сегмент)
        check_up_to = len(compressed) - 1 if len(compressed) > 0 else 0
        
        for i in range(check_up_to):
            ts, val = compressed[i]
            if ts not in self._sent_timestamps:
                new_points_to_send.append((ts, val))
                self._sent_timestamps.add(ts)
                # Обновляем информацию о последней отправке
                self._last_sent_timestamp = ts
                self._last_sent_value = val
        
        # Если есть новые точки для отправки, обновляем last_sent для последней из них
        if new_points_to_send:
            last_ts, last_val = new_points_to_send[-1]
            self._last_sent_timestamp = last_ts
            self._last_sent_value = last_val
        
        # Проверка heartbeat: если давно не отправляли и есть последнее значение
        if (self._last_sent_value is not None and 
            self._all_points and 
            current_time is None):
            # Берем текущее время из последней сырой точки
            current_time = self._all_points[-1][0]
        
        if (self._last_sent_value is not None and 
            current_time is not None and
            self.max_silent_interval > 0):
            time_since_last_send = current_time - self._last_sent_timestamp
            if time_since_last_send >= self.max_silent_interval:
                # Отправляем heartbeat - последнюю известную точку с текущим timestamp
                heartbeat_point = (current_time, self._last_sent_value)
                # Не добавляем в _sent_timestamps, так как это повторяющееся значение
                # Но обновляем timestamp последней отправки
                self._last_sent_timestamp = current_time
                new_points_to_send.append(heartbeat_point)
                print(f"[COMPRESSOR] Heartbeat sent: {heartbeat_point}")
        
        # DEBUG: Print for frequency metric
        print(f"[COMPRESSOR] Iteration: raw_added={len(points)}, total_raw={len(self._all_points)}")
        print(f"[COMPRESSOR] Compressed ({len(compressed)}): {compressed}")
        print(f"[COMPRESSOR] Points to send ({len(new_points_to_send)}): {new_points_to_send}")
        print(f"[COMPRESSOR] Sent timestamps count: {len(self._sent_timestamps)}")
        
        return new_points_to_send
    
    def _compress_all(self) -> List[Tuple[int, float]]:
        """Сжимает все накопленные точки."""
        return list(_sausage_links(
            iter(self._all_points),
            deviation=self.deviation,
            auto_dev_factor=self.auto_dev_factor,
            ema_alpha=self.ema_alpha,
        ))
    
    def flush(self) -> List[Tuple[int, float]]:
        """
        Сбрасывает все оставшиеся точки из компрессора.
        Вызывается перед финальной отправкой.
        
        Возвращает все точки включая последнюю ("открытый сегмент"),
        так как это финальная отправка и новых данных не ожидается.
        """
        if self.compressor_name == "none":
            # Отправляем все неотправленные сырые точки
            return [p for p in self._all_points if p[0] not in self._sent_timestamps]
        
        compressed = self._compress_all()
        # При финальном flush отправляем ВСЕ точки включая последнюю
        # Но только те, что ещё не были отправлены
        
        result = []
        for ts, val in compressed:
            if ts not in self._sent_timestamps:
                result.append((ts, val))
        
        return result
    
    @property
    def total_raw_points(self) -> int:
        """Общее количество сырых точек."""
        return len(self._all_points)
    
    @property
    def total_compressed_points(self) -> int:
        """Общее количество сжатых точек."""
        if self.compressor_name == "none":
            return len(self._all_points)
        return len(self._compress_all())
    
    @property
    def compression_ratio(self) -> float:
        """Коэффициент сжатия (сколько раз уменьшился объём)."""
        if not self._all_points:
            return 1.0
        compressed_count = self.total_compressed_points
        if compressed_count == 0:
            return 1.0
        return len(self._all_points) / compressed_count


def compress_points(
    points: MetricPoints,
    compressor_name: CompressorName = "none",
) -> MetricPoints:
    """
    Сжимает точки метрик using streaming compression.
    Структура: {metric_name: [(ts, value), ...], ...}
    """
    if compressor_name == "none":
        return points
    
    result: MetricPoints = {}
    
    for metric_name, metric_points in points.items():
        compressor = StreamingCompressor(compressor_name=compressor_name)
        compressed = compressor.add_points(metric_points)
        if compressed:
            result[metric_name] = compressed
    
    return result