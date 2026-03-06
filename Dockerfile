FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python3 -c 'import codecs; raw = open("requirements.txt", "rb").read(); text = raw.decode("utf-16") if raw.startswith(b"\xff\xfe") or b"\x00" in raw else raw.decode("utf-8"); open("requirements.txt", "w", encoding="utf-8").write(text)' && pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
