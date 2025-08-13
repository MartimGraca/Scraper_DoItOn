FROM python:3.10-slim

RUN apt-get update && apt-get install -y wget

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
WORKDIR /app

CMD ["streamlit","run", "app.py"]  