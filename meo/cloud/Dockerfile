FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEO_BIND_HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

COPY meo/cloud/requirements.txt /tmp/meo-cloud-requirements.txt
RUN pip install --no-cache-dir -r /tmp/meo-cloud-requirements.txt \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin meocloud

COPY meo /app/meo

USER 10001:10001
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()"

CMD ["python", "-m", "meo.cloud.server"]
