# The edge service (app/edge.py): webhook receiver for module 14 and external knowledge base for module 09.
# One instance can serve the whole room, each participant on /<WS_PREFIX>.
#   docker build -t orq-edge . && docker run -p 8001:8001 -e WS_WEBHOOK_SECRET=<secret> orq-edge
FROM python:3.12-slim
RUN pip install --no-cache-dir "starlette>=0.40" "uvicorn>=0.30"
WORKDIR /srv
COPY app/edge.py app/edge.py
COPY app/data/kb app/data/kb
ENV PORT=8001
EXPOSE 8001
CMD ["python", "-m", "app.edge"]
