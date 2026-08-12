FROM python:3.11-alpine

WORKDIR /app

RUN pip install --no-cache-dir wsgidav cheroot requests

COPY server.py /app/server.py

CMD ["python", "server.py"]
