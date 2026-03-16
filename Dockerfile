FROM python:3.12-alpine

RUN apk add --no-cache dcron

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY entrypoint.sh .
COPY crontab /etc/crontabs/root

RUN chmod +x entrypoint.sh

VOLUME ["/data"]

ENTRYPOINT ["./entrypoint.sh"]
