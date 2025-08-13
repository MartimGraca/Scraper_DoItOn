FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libglib2.0-0 \
    libnss3 \
    libfontconfig1 \
    libxss1 \
    libasound2 \
    libxtst6 \
    libgtk-3-0 \
    wget \
    unzip \
    curl \
    chromium-browser \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium-browser
ENV PATH="${PATH}:/usr/bin/chromium-browser"

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . /app
WORKDIR /app

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]