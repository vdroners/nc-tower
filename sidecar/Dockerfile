FROM python:3.12-slim-bookworm

# iproute2 is a fallback for `ip` when nsenter into the host namespaces is not
# available; the primary path runs the host's ip via nsenter (see _host_ns_argv).
RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py chassis_fan.py parity.py inventory.py /app/

ENV NC_TOWER_BIND=0.0.0.0 \
    NC_TOWER_PORT=18765 \
    PYTHONUNBUFFERED=1

EXPOSE 18765
CMD ["python", "/app/app.py"]
