FROM python:3.10-slim

# Instala dependências do sistema e Google Chrome
RUN apt-get update && \
    apt-get install -y wget gnupg2 fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 \
    libdbus-1-3 libdrm2 libnspr4 libnss3 libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libgtk-3-0 libpango-1.0-0 libpangocairo-1.0-0 libatspi2.0-0 libxshmfence1 libxkbcommon0 && \
    wget -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto do código
COPY . /app
WORKDIR /app

# Comando para correr a tua app (ajusta conforme usas)
CMD ["streamlit", "run", "app.py", "--server.port=8000"]