FROM python:3.9-slim

RUN apt-get update && apt-get install -y iputils-ping && rm -rf /var/lib/apt/list/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

EXPOSE 5000

CMD ["python", "app.py"]