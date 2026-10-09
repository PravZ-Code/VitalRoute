FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY static ./static
COPY mobile ./mobile
COPY backend/run.py ./

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

CMD ["python", "run.py"]
