FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./
COPY react-ui/dist ./static

ENV USER_DATA_DIR=/data
ENV AUTH_ENABLED=true

VOLUME /data

EXPOSE 57991

CMD ["python", "main.py", "--port", "57991", "--host", "0.0.0.0"]
