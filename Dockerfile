FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini entrypoint.sh ./
RUN mkdir -p /app/catalog-files /app/diagnostics && chown -R app:app /app && chmod +x /app/entrypoint.sh
USER app
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "app.main"]
