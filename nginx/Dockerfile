FROM nginx:1.27-alpine

RUN apk add --no-cache gettext openssl

COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.sh /usr/local/bin/dashboard-nginx-entrypoint

RUN chmod +x /usr/local/bin/dashboard-nginx-entrypoint

ENTRYPOINT ["/usr/local/bin/dashboard-nginx-entrypoint"]
