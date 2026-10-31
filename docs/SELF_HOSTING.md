# Running EV Share yourself

You need a Linux server (or any machine) with **Docker** and the Docker Compose plugin. EV Share runs as three containers: the app, Postgres, and Redis (for shared login rate limiting across instances).
*(This guide and the Docker image have not been run end to end by the author yet; tell us if a step needs fixing.)*

## 1. Get the files
Download `docker-compose.prod.yml` and `.env.example` from the latest [release](../../releases), then:
```bash
cp .env.example .env
```

## 2. Fill in `.env`
Generate the secrets:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"                                   # EVSHARE_SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"      # EVSHARE_DOCS_ENCRYPTION_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(24))"                                   # POSTGRES_PASSWORD
```
Set at least:
```
EVSHARE_ENV=production
EVSHARE_SECRET_KEY=...
EVSHARE_DOCS_ENCRYPTION_KEY=...
POSTGRES_PASSWORD=...
EVSHARE_STAFF_PATH=/review-<something-random>      # your private reviewer portal address
EVSHARE_PAYMENT_PROVIDER=razorpay                  # production refuses the demo payment provider
EVSHARE_RAZORPAY_KEY_ID=...  EVSHARE_RAZORPAY_KEY_SECRET=...
EVSHARE_OTP_PROVIDER=smtp    EVSHARE_SMTP_HOST=...  EVSHARE_SMTP_FROM=...  (and user/password)
EVSHARE_STORAGE_BACKEND=s3   EVSHARE_S3_BUCKET=...  (or EVSHARE_ALLOW_LOCAL_STORAGE=true to use the server disk)
```
Keep `.env` private and back it up: **losing the encryption key makes stored documents unreadable.**

## 3. Start it
```bash
docker compose -f docker-compose.prod.yml up -d
curl http://localhost:8000/health        # {"status":"ok"}
```
The database tables are created automatically on start.

## 4. Create your first reviewer
```bash
docker compose -f docker-compose.prod.yml exec app python -m scripts.create_admin
```
Reviewers sign in at `https://your-domain/<your EVSHARE_STAFF_PATH>`, not on the public Login.

## 5. HTTPS
Put a reverse proxy in front. With [Caddy](https://caddyserver.com), a `Caddyfile` of
```
ev.example.com {
    reverse_proxy localhost:8000
}
```
gets you automatic HTTPS. Browsers only share the location needed by *Go live* over HTTPS.

## 6. Routine jobs
```bash
# daily: delete identity documents past their retention period
docker compose -f docker-compose.prod.yml exec -T app python -m scripts.purge_documents
# daily or weekly: back up the database
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U evshare evshare > backup-$(date +%F).sql
```
Put these in `cron`.

## Updating
```bash
docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d
```
Database changes are applied automatically on start. Read the release notes first, and take a backup.
