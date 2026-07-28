#!/bin/sh
set -eu

: "${DOMAIN:?DOMAIN must be set in .env}"

domain="$DOMAIN"
live_certificate="/etc/letsencrypt/live/${domain}/fullchain.pem"
live_key="/etc/letsencrypt/live/${domain}/privkey.pem"

if [ -f "$live_certificate" ] && [ -f "$live_key" ]; then
    SSL_CERTIFICATE="$live_certificate"
    SSL_CERTIFICATE_KEY="$live_key"
else
    fallback_dir="/etc/nginx/fallback-certificate"
    SSL_CERTIFICATE="${fallback_dir}/fullchain.pem"
    SSL_CERTIFICATE_KEY="${fallback_dir}/privkey.pem"
    mkdir -p "$fallback_dir"

    if [ ! -f "$SSL_CERTIFICATE" ] || [ ! -f "$SSL_CERTIFICATE_KEY" ]; then
        openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
            -keyout "$SSL_CERTIFICATE_KEY" \
            -out "$SSL_CERTIFICATE" \
            -subj "/CN=${domain}"
    fi
fi

export DOMAIN="$domain" SSL_CERTIFICATE SSL_CERTIFICATE_KEY
envsubst '${DOMAIN} ${SSL_CERTIFICATE} ${SSL_CERTIFICATE_KEY}' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf

(
    while sleep 43200; do
        nginx -s reload
    done
) &

exec nginx -g "daemon off;"
