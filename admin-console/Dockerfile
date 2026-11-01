FROM python:3.12.8-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# La console tourne sous un compte non privilégié ; le service "init"
# (même image) s'exécute en root pour écrire dans les volumes partagés.
RUN useradd --system --uid 10001 kibare && mkdir /data && chown kibare /data
EXPOSE 8090
CMD ["sh", "-c", "exec su kibare -s /bin/sh -c 'uvicorn app.main:app --host 0.0.0.0 --port 8090 --proxy-headers'"]
