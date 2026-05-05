ARG BASE_IMAGE_TAG=3-alpine
ARG VERSION

FROM hafen.parlament.gv.at/registry-1.docker.io/library/python:$BASE_IMAGE_TAG

LABEL org.opencontainers.image.title="bootique" \
      org.opencontainers.image.authors="Rafael Schreiber <rafael.schreiber@parlament.gv.at>" \
      org.opencontainers.image.description="Declare machines running RHEL-based distributions and kickstart them" \
      org.opencontainers.image.url="https://gitlab.parlament.gv.at/container/bootique" \
      org.opencontainers.image.source="https://gitlab.parlament.gv.at/container/bootique" \
      org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.revision=$VCS_REF

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /

RUN apk add bash curl gcompat git tini tzdata
RUN pip install --no-cache-dir -r /requirements.txt

COPY entrypoint.sh /
COPY src /app

EXPOSE 80/tcp

ENTRYPOINT ["/sbin/tini", "--", "/entrypoint.sh"]
