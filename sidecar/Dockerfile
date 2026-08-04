FROM python:3.12-slim-bookworm

WORKDIR /app
COPY app.py chassis_fan.py parity.py /app/

ENV NC_TOWER_BIND=0.0.0.0 \
    NC_TOWER_PORT=18765 \
    PYTHONUNBUFFERED=1

EXPOSE 18765
CMD ["python", "/app/app.py"]
