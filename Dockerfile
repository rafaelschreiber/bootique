ARG BASE_IMAGE_TAG=3-alpine
ARG VERSION

FROM hafen.parlament.gv.at/docker.io/library/python:$BASE_IMAGE_TAG

LABEL "org.opencontainers.image.authors"="rafael.schreiber@parlament.gv.at"
LABEL "org.opencontainers.image.version"="$VERSION"


ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /

RUN apk add bash curl gcompat git tini tzdata
RUN pip install --no-cache-dir -r /requirements.txt

COPY entrypoint.sh /
COPY src /app

EXPOSE 69/udp
EXPOSE 443/tcp

ENTRYPOINT ["/sbin/tini", "--", "/entrypoint.sh"]
