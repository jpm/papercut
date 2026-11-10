# Test image for the Docker integration tests (docs/integration-testing-plan.md)
FROM python:3.13-slim

# build dependencies for mysqlclient (the MySQLdb module)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt /tmp/
RUN pip install --no-cache-dir --root-user-action=ignore \
        -r /tmp/requirements.txt -r /tmp/requirements-dev.txt aiosmtpd

# the repo is mounted here at run time
WORKDIR /src
ENV PYTHONDONTWRITEBYTECODE=1
