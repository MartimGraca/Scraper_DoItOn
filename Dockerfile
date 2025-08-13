FROM python:3.10-slim

RUN apt-get update && apt-get install -y wget

CMD ["python3", "--version"]