# --- ЭТАП 1: Сборка (Builder) ---
FROM python:3.14-alpine as builder

RUN apk add --no-cache \
    build-base \
    libffi-dev \
    netcat-openbsd

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel build

COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

# --- ЭТАП 2: Финальный образ ---
FROM python:3.14-alpine

LABEL project.name="Metrics CPU monitor" \
      project.owner="Lex Huan Ryu" \
      version="0.1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH"

WORKDIR /app

COPY --from=builder /install /usr/local

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

RUN chown -R appuser:appgroup /app

USER appuser

CMD ["python", "-m", "cpu_monitor.main"]

