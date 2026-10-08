FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py /app/bot.py
COPY config.py /app/config.py
COPY db.py /app/db.py
COPY keys.py /app/keys.py
COPY ccs.py /app/ccs.py
RUN useradd -r -u 1001 adalikm && mkdir -p /data && chown -R adalikm:adalikm /data
USER adalikm
VOLUME ["/data"]
ENV DB_PATH=/data/AdalikM.db STORAGE_DIR=/data/storage
CMD ["python", "/app/bot.py"]
