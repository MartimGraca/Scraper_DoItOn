FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y wget gnupg2 && \
    wget -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' && \
    apt-get update && \
    apt-get install -y google-chrome-stable chromium-driver && \
    rm -rf /var/lib/apt/lists/*

ENV CHROME_BINARY=/usr/bin/google-chrome

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash", "-c", "streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0"]