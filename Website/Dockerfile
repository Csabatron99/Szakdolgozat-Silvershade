FROM python:3.13-slim

WORKDIR /app

# Install dependencies before copying source for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# serve.py is the production entry point — a thin reverse proxy to the API.
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8080"]
