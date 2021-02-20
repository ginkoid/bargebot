FROM python:3.9.0-slim-buster AS build

WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install build-essential -y && pip install -r requirements.txt

FROM python:3.9.0-slim-buster

WORKDIR /app
COPY --from=build /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY . .

CMD ["python", "GearBot/GearBot.py"]
