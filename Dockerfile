FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
# Armazenar browsers do Playwright dentro do container/projeto
ENV PLAYWRIGHT_BROWSERS_PATH=0

# Dependências de sistema necessárias para o Chromium/Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    wget \
    gnupg \
    xdg-utils \
    fonts-liberation \
    fonts-unifont \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-6 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxrender1 \
    libxkbcommon0 \
    libxshmfence1 \
    libcairo2 \
    libpango-1.0-0 \
 && rm -rf /var/lib/apt/lists/*

# (Opcional) Google Chrome — podes manter, mas o Playwright usará o seu Chromium
RUN wget -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get update && apt-get install -y /tmp/google-chrome.deb && rm /tmp/google-chrome.deb
ENV CHROME_BIN=/usr/bin/google-chrome

# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Garante playwright instalado e baixa o Chromium (sem --with-deps)
RUN python -m pip show playwright >/dev/null 2>&1 || pip install --no-cache-dir playwright
RUN python -m playwright install chromium

# Copia a app
COPY . /app
WORKDIR /app

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]