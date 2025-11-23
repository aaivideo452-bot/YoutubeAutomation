FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg gcc libsndfile1 git && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

ENV PORT=5000
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:$PORT"]
