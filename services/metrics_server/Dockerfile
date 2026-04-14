# --- ЭТАП 1: Сборка (Builder) ---
FROM python:3.14-alpine as builder

RUN apk add --no-cache \
    build-base \
    libffi-dev \
    netcat-openbsd

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel build

COPY server ./server
RUN pip install --no-cache-dir --prefix=/install .

# --- ЭТАП 2: Финальный образ ---
FROM python:3.14-alpine

LABEL project.name="Metrics TCP server" \
      project.owner="Lex Huan Ryu" \
      version="0.1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH"

RUN apk add --no-cache netcat-openbsd

WORKDIR /app

COPY --from=builder /install /usr/local

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD echo "ping" | timeout 2 nc -w 1 localhost 8888 >/dev/null 2>&1 || exit 1

CMD ["python", "-m", "server.main"]