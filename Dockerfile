FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY app/ ./app/
RUN pip install --upgrade pip && pip install .

EXPOSE 8000
CMD ["python", "-m", "app.container"]
