FROM debian:buster-slim as asterisk

WORKDIR /tmp
RUN apt-get -y update && apt-get -y install --no-install-recommends asterisk asterisk-mp3 gettext-base dnsutils && apt-get clean && rm -rf /var/lib/apt/lists/* && \
    mkdir -p /etc/asterisk/pjsip.d /etc/asterisk/sip.d /etc/asterisk/extensions.d /var/run/asterisk /usr/share/asterisk/moh && \
    chown -R asterisk:asterisk /etc/asterisk/pjsip.d /etc/asterisk/sip.d /etc/asterisk/extensions.d /var/run/asterisk /usr/share/asterisk/moh

COPY ./docker_config/*.conf /config/
COPY ./docker-entrypoint.sh /

CMD ["bash", "-x", "/docker-entrypoint.sh"]
EXPOSE 5060/udp 5060/tcp

FROM python:3.9-slim-buster as python

WORKDIR /usr/src/app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
EXPOSE 4574/tcp
