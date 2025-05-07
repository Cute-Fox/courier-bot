FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pi install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot/main.py"]
