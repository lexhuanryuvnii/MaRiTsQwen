# --- ЭТАП 1: Сборка (Builder) ---
FROM python:3.12-alpine as builder

RUN apk add --no-cache \
    build-base \
    libffi-dev \
    netcat-openbsd

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel build
RUN pip install --no-cache-dir --prefix=/install .

# --- ЭТАП 2: Финальный образ ---
FROM python:3.12-alpine

LABEL project.name="Metrics marimo dashboard" \
      project.owner="Lex Huan Ryu" \
      version="0.1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH"

RUN apk add --no-cache libstdc++ curl netcat-openbsd

WORKDIR /app

COPY --from=builder /install /usr/local
COPY notebooks ./notebooks

RUN addgroup -S appgroup && adduser -S appuser -G appgroup
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD echo "ping" | timeout 2 nc -w 1 localhost 8080 >/dev/null 2>&1 || exit 1

CMD ["marimo", "run", "notebooks/dashboard.py", "--host", "0.0.0.0", "--port", "8080"]
