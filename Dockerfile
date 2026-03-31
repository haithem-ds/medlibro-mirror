FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV MEDLIBRO_DATA_DIR=/app/Data
ENV MEDLIBRO_STATE_DIR=/data

WORKDIR /app/medlibro_website_scraper

COPY Data /app/Data
COPY medlibro_website_scraper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY medlibro_website_scraper/ .

RUN mkdir -p /data

EXPOSE 8080

# Render sets PORT; local Docker defaults to 8080
# Single worker: avoids loading the full JSON cache twice (was hitting Render 512MB OOM with --workers 2).
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 2 serve_mirror:app"]
