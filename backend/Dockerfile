FROM python:3.13.1-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . \
 && useradd --system --uid 10001 --no-create-home sentinel

USER sentinel
EXPOSE 8000

# Seul Caddy atteint le backend (aucun port publié) : on fait confiance à son X-Forwarded-For.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
