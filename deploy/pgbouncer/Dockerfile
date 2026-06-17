FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends pgbouncer gettext-base && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /etc/pgbouncer /var/log/pgbouncer /var/run/pgbouncer && \
    chown -R postgres:postgres /etc/pgbouncer /var/log/pgbouncer /var/run/pgbouncer

COPY pgbouncer.ini.template /etc/pgbouncer/pgbouncer.ini.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER postgres
EXPOSE 6432
ENTRYPOINT ["/entrypoint.sh"]
