FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python3 -c "
   with open('requirements.txt', 'rb') as f:
       raw = f.read()
   if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
       text = raw.decode('utf-16')
       with open('requirements.txt', 'w', encoding='utf-8') as f:
           f.write(text)
   " && pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
