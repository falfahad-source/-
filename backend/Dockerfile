# trixie: its postgresql-client (17) restores backups made with PostgreSQL 16 (app/seed.py)
FROM python:3.12-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["sh", "start.sh"]
