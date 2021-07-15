#!/bin/bash

echo starting entrypoint

# run as user asterisk by default
ASTERISK_USER=${ASTERISK_USER:-asterisk}
ASTERISK_GROUP=${ASTERISK_GROUP:-${ASTERISK_USER}}

if [ "$1" = "" ]; then
  COMMAND="/usr/sbin/asterisk -T -W -U ${ASTERISK_USER} -p -vvvdddf"
else
  COMMAND="$@"
fi

if [ "${ASTERISK_UID}" != "" ] && [ "${ASTERISK_GID}" != "" ]; then
  # recreate user and group for asterisk
  # if they've sent as env variables (i.e. to macth with host user to fix permissions for mounted folders

  deluser asterisk && \
  addgroup -g ${ASTERISK_GID} ${ASTERISK_GROUP} && \
  adduser -D -H -u ${ASTERISK_UID} -G ${ASTERISK_GROUP} ${ASTERISK_USER} \
  || exit
fi

if test -d "/config"; then
  FILES=$(find /config -name \*.conf)
  for file in $FILES; do
    echo "Copying Asterisk configfile from ${file} to /etc/asterisk/${file#/config/}"
    dir=$(dirname ${file#/config/})
    if test "${dir}" != "."; then
      echo "creating config dir /etc/asterisk/${dir}"
      mkdir -p /etc/asterisk/${dir}
    fi
    cp $file /etc/asterisk/${file#/config/}
  done
fi

ln -sf /usr/share/zoneinfo/Europe/Berlin /etc/localtime

DIR=/docker-entrypoint.d
if test -d "$DIR"; then
  /bin/run-parts --verbose "$DIR"
fi

chown -R ${ASTERISK_USER}: /var/log/asterisk \
                           /etc/asterisk \
                           /var/lib/asterisk \
                           /var/run/asterisk \
                           /var/spool/asterisk; \

echo Starting Asterisk
exec ${COMMAND}
