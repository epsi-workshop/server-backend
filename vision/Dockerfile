FROM python:3.13.1-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    STREAM_HOST=0.0.0.0 SNAPSHOT_DIR=/snapshots
WORKDIR /app

COPY pyproject.toml ./
COPY vision ./vision
RUN pip install --no-cache-dir . \
 && useradd --system --uid 10002 --no-create-home sentinel \
 && mkdir -p /snapshots && chown sentinel /snapshots

USER sentinel
# Port 8081 (flux annoté) : réseau interne Docker uniquement, jamais publié.
EXPOSE 8081
CMD ["python", "-m", "vision"]
