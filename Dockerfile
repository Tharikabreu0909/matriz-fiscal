FROM python:3.13-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHECKFISCAL_DATA_DIR=/data

COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY app.py database.py ./
COPY readers ./readers
COPY services ./services
COPY static ./static

RUN mkdir -p /data

EXPOSE 8145

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8145", "--no-access-log"]
