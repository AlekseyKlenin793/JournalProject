FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir sentence-transformers psycopg2-binary
RUN apt-get update && apt-get install -y ca-certificates && update-ca-certificates
COPY . .
CMD ["python", "bot.py"]