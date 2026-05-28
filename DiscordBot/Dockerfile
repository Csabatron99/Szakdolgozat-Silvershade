FROM python:3.13-slim

WORKDIR /app

# Install dependencies before copying source for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
