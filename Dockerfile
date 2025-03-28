# syntax=docker/dockerfile:1

FROM python:3.8-slim-buster

WORKDIR /Gold-api

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . /Gold-api
COPY /api /Gold-api/api/
COPY /config /Gold-api/config/
EXPOSE 8000

CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0"]