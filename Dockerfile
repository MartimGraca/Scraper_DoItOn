FROM python:3.10-slim

# Instala dependências básicas do sistema
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Instala Google Chrome estável (podes manter; Playwright usará o Chromium próprio)
RUN wget -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get update && \
    apt-get install -y /tmp/google-chrome.deb && \
    rm /tmp/google-chrome.deb

ENV CHROME_BIN=/usr/bin/google-chrome
ENV PYTHONUNBUFFERED=1
# Armazenar browsers do Playwright dentro da imagem/projeto
ENV PLAYWRIGHT_BROWSERS_PATH=0

# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Garante que o pacote playwright existe e instala os browsers necessários
# (se já tiver no requirements.txt, o pip show passa; se não, instala aqui)
RUN python -m pip show playwright >/dev/null 2>&1 || pip install --no-cache-dir playwright
RUN python -m playwright install --with-deps chromium

# Copia a app
COPY . /app
WORKDIR /app

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]