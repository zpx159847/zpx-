# No RUN or pip install: only the official Python runtime and first-party lab files.
FROM python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54
LABEL org.opencontainers.image.title="Pocket Lab - OWASP training playground" \
      org.opencontainers.image.description="Intentionally vulnerable local training app. OWASP 2025/2021 + business logic." \
      org.opencontainers.image.source="https://github.com/zpx159847/zpx-" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.licenses="MIT"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 LAB_HOST=0.0.0.0 LAB_PORT=8080 LAB_INTERNAL_PORT=9091 LAB_DATA_DIR=/data
WORKDIR /app
COPY --chown=10001:10001 app/ /app/
COPY --chown=10001:10001 data/ /data/
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=4s --start-period=8s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3).read()"]
CMD ["python", "/app/app.py"]
