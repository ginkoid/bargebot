FROM python:3.8.6-slim-buster AS build

COPY requirements.txt /app/requirements.txt
WORKDIR /app

RUN apt update && apt install git -y && pip install -r /app/requirements.txt

COPY . .

RUN git rev-parse HEAD > /app/version

FROM python:3.8.6-slim-buster AS run

COPY --from=build /usr/local/lib/python3.8/site-packages /usr/local/lib/python3.8/site-packages
COPY --from=build /app /app

WORKDIR /app

CMD ["python", "/app/GearBot/GearBot.py"]
