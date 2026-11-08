FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt backend/constraints.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY .nimbus-root ./
COPY backend backend
COPY frontend frontend
COPY data/demo data/demo
COPY data/snapshot data/snapshot
# backend/models (ONNX) and data/demo/evidence (chips, persistence) ship with the image.
ENV PORT=8741
EXPOSE 8741
CMD ["python", "backend/app.py"]
