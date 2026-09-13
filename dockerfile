FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Запускаем Flask
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
#CMD ["python", "-u", "-m", "flask", "run", "--host=0.0.0.0", "--port=5000"]