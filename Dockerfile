FROM python:3.7.5-slim-buster

ADD . /app

RUN apt update && apt install build-essential zlib1g-dev libjpeg-dev -y && pip install -r /app/requirements.txt

WORKDIR /app

CMD ["sh", "/app/Bootloader.sh"]
