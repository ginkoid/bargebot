FROM python:3.9.0-slim-buster AS build

WORKDIR /app
COPY requirements.txt .

RUN apt update && apt install build-essential git -y && pip install -r /app/requirements.txt

COPY . .

RUN git rev-parse HEAD > /app/version

FROM python:3.9.0-slim-buster AS run

COPY --from=build /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=build /app /app

WORKDIR /app

CMD ["python", "/app/GearBot/GearBot.py"]
