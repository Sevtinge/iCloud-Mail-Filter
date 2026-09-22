FROM python:3.12-slim

WORKDIR /app

COPY filter.py /app/filter.py

RUN mkdir -p /data

CMD ["python", "-u", "/app/filter.py"]
