FROM python:3.13.1-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app

COPY pyproject.toml ./
COPY anomaly ./anomaly
RUN pip install --no-cache-dir . \
 && useradd --system --uid 10003 --no-create-home sentinel \
 && mkdir -p /data && chown sentinel /data

USER sentinel
CMD ["python", "-m", "anomaly"]
