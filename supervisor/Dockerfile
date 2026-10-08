# Superviseur : bibliothèque standard Python uniquement.
FROM python:3.13.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY supervisor.py ./
# pip retiré : bibliothèque standard uniquement, rien à installer à l'exécution.
RUN pip uninstall -y -q pip \
 && useradd --system --uid 10004 --no-create-home sentinel

USER sentinel
EXPOSE 8090
CMD ["python", "supervisor.py"]
