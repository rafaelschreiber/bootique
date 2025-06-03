FROM hafen.parlament.gv.at/docker.io/library/python:3-alpine

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /

RUN apk add bash curl gcompat git tini tzdata
RUN pip install --no-cache-dir -r /requirements.txt

COPY entrypoint.sh /
COPY src /app

ENTRYPOINT ["/sbin/tini", "--", "/entrypoint.sh"]
