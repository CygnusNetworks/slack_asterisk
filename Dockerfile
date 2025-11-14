FROM python:3.12-slim

WORKDIR /usr/src/app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
RUN mkdir /data
COPY slack_asterisk /usr/src/app/slack_asterisk

ENV LISTEN_IP=127.0.0.1
ENV LISTEN_PORT=4574

CMD exec python -m slack_asterisk.main -i "$LISTEN_IP" -p "$LISTEN_PORT"
