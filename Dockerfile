FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev \
      netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

COPY run.sh /app/run.sh
COPY requirements.txt /app/requirements.txt
COPY . /app

RUN chmod +x /app/run.sh

RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir flask-login psycopg2-binary \
 && pip install --no-cache-dir -r /app/requirements.txt

RUN mkdir -p /app/results
VOLUME ["/app/results"]

EXPOSE 5000

ENTRYPOINT ["/app/run.sh"]
# Change default CMD to --run so run.sh will start the server by default, not pass --config
CMD ["--run"]
