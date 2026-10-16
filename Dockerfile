FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app

LABEL org.opencontainers.image.source="https://github.com/nilsee1/literotica-scraper"
LABEL org.opencontainers.image.title="literotica-scraper"
LABEL org.opencontainers.image.description="Literotica to EPUB Scraper & Generator"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

