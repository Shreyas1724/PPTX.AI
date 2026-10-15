FROM python:3.12-slim
# Optional: install the headless Office renderer only on workers performing
# independent export checks. This is OFF by default to keep images small.
ARG INSTALL_RENDERING_QA=0
RUN if [ "$INSTALL_RENDERING_QA" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends libreoffice-impress fonts-dejavu-core && \
      rm -rf /var/lib/apt/lists/*; \
    fi
WORKDIR /service
COPY requirements.txt requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt && useradd --uid 10001 --create-home app
COPY --chown=app:app app ./app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--limit-concurrency","100"]
