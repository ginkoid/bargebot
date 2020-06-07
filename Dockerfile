FROM python:3.7.5-slim-buster AS build

COPY requirements.txt /app/requirements.txt
WORKDIR /app

RUN apt update && apt install build-essential zlib1g-dev libjpeg-dev git -y && pip install -r /app/requirements.txt

COPY . .

RUN git rev-parse HEAD > /app/version

FROM python:3.7.5-slim-buster AS run

COPY --from=build /usr/local/lib/python3.7/site-packages /usr/local/lib/python3.7/site-packages
COPY --from=build /app /app

WORKDIR /app

CMD ["python", "/app/GearBot/GearBot.py"]
