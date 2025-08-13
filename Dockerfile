# Usa imagem oficial do Python slim
FROM python:3.10-slim

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libxss1 \
    libasound2 \
    libxtst6 \
    libgtk-3-0 \
    wget \
    unzip \
    curl \
    # Instala Chromium
    chromium-driver chromium \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Define variáveis de ambiente para o Chromium (importante para headless)
ENV CHROME_BIN=/usr/bin/chromium
ENV PATH="${PATH}:/usr/bin/chromium"

# Instala as dependências do Python
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copia o código da app
COPY . /app
WORKDIR /app

# Porta padrão do Streamlit
EXPOSE 8501

# Comando para iniciar a aplicação
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]