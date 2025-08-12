FROM python:3.10-slim

# Instala Chromium e o driver
RUN apt-get update && \
    apt-get install -y chromium chromium-driver && \
    rm -rf /var/lib/apt/lists/*

# Define o caminho do Chromium para o scraper
ENV CHROME_BINARY=/usr/bin/chromium

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Arranca o Streamlit na porta esperada pelo Render ($PORT) e aceita conexões externas
CMD ["bash", "-c", "streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0"]