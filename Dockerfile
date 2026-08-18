FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    HOST=0.0.0.0 \
    PORT=5000 \
    FLASK_DEBUG=0

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads /app/charts \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000
CMD ["python", "app.py"]
