# syntax=docker/dockerfile:1

FROM python:3.10-slim-buster

WORKDIR /Gold-api

COPY requirements.txt requirements.txt
#COPY .venv/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY pip-packages-new/ /pip-packages

RUN pip install --no-index --find-links=/pip-packages -r requirements.txt
#RUN pip install -r requirements.txt


COPY . /Gold-api
COPY /api /Gold-api/api/
COPY /config /Gold-api/config/
EXPOSE 8000

CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0"]
