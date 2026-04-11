# EGDC Repository Backend

FastAPI + SQLModel + PostgreSQL backend for the EGDC (Environmental Green Data Case Studies) repository.

---

## Table of Contents

1. [Deployment — Required Folder Structure](#deployment--required-folder-structure)
2. [Quick Start (Docker Compose)](#quick-start-docker-compose)
3. [Environment Variables](#environment-variables)
4. [Seeding the Database](#seeding-the-database)
5. [Running Tests](#running-tests)
6. [Admin Password Reset](#admin-password-reset)

---

## Deployment — Required Folder Structure

`docker-compose.yml` builds **three services**: the Postgres database, this backend, and the Next.js frontend. The frontend build context is set to `../Repository-FE` (relative to the backend directory), so **both repositories must be checked out as siblings** under the same parent folder.

```
parent-directory/
├── Repository-BE/          ← this repository
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── .env               ← copy from .env.example and fill in values
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   │   └── seeds/
│   │   │       └── data.json
│   │   ├── models/
│   │   └── schemas/
│   └── scripts/
│       ├── test_search.py
│       ├── reset_admin_password.py
│       └── ...
│
└── Repository-FE/         ← MUST be at this exact sibling path
    ├── Dockerfile
    ├── package.json
    └── ...
```

> **Why is the sibling layout required?**
> The `frontend` service in `docker-compose.yml` uses:
> ```yaml
> build:
>   context: ../Repository-FE
> ```
> Docker resolves `../Repository-FE` relative to the directory that contains
> `docker-compose.yml` (i.e. `Repository-BE/`). If the frontend is placed
> anywhere else, the build will fail with *"context not found"*.

### Uploaded Files (Persistent Volume)

Static file uploads (logos, methodology PDFs, datasets) are stored in the
`app_uploads` named Docker volume, which is mounted at `/app/static/uploads`
inside the backend container. This volume persists across container restarts.
To back up uploads, use `docker cp` or mount the volume to a host directory.

---

## Quick Start (Docker Compose)

```bash
# 1. Clone both repositories as siblings
git clone <backend-repo-url>  Repository-BE
git clone <frontend-repo-url> Repository-FE

# 2. Create and configure the environment file
cd Repository-BE
cp .env.example .env
# Edit .env and set: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB,
#                    SECRET_KEY, NEXT_PUBLIC_API_BASE_URL

# 3. Start all services
docker compose up --build -d

# 4. Seed the database (run once after first start)
curl -X POST http://localhost:3000/api/v1/seed
```

Service ports after startup:

| Service  | Host port | Description            |
|----------|-----------|------------------------|
| backend  | 3000      | FastAPI (REST API)     |
| frontend | 8000      | Next.js                |
| db       | 5432      | PostgreSQL 15          |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all required values.

| Variable                   | Required | Description                                              |
|----------------------------|----------|----------------------------------------------------------|
| `POSTGRES_USER`            | Yes      | PostgreSQL username                                      |
| `POSTGRES_PASSWORD`        | Yes      | PostgreSQL password                                      |
| `POSTGRES_DB`              | Yes      | PostgreSQL database name                                 |
| `DATABASE_URL`             | Yes      | Full async connection string (`postgresql+asyncpg://...`)|
| `SECRET_KEY`               | Yes      | JWT signing key — use a long random string in production |
| `NEXT_PUBLIC_API_BASE_URL` | Yes      | Public URL the frontend uses to reach the backend API    |

---

## Seeding the Database

The seed endpoint drops all tables, recreates them, and inserts reference data,
organisations, and case studies from `app/db/seeds/data.json`.

```bash
# Seed via HTTP (backend must be running)
curl -X POST http://localhost:3000/api/v1/seed

# Or via Docker exec
docker exec -it <backend-container> \
    curl -X POST http://localhost:3000/api/v1/seed
```

Default seed credentials (change immediately in production):

| Email                    | Role       | Password    |
|--------------------------|------------|-------------|
| admin@example.com        | admin      | password123 |
| custodian@example.com    | custodian  | password123 |
| owner@example.com        | data_owner | password123 |

---

## Enabling partial matching and fuzzy search

To enable partial matching and fuzzy search, you need to create the extension `pg_trgm`.

```bash
# Create the extension
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```


## Running Tests

The test suite in `scripts/` uses `pytest` + `requests` and requires the
backend to be running.

```bash
# Install test dependencies
pip install pytest requests

# Run all search regression tests
pytest scripts/test_search.py -v

# Override the base URL if your backend is on a different host/port
EGDC_BASE_URL=http://my-server:3000 pytest scripts/test_search.py -v
```

---

## Admin Password Reset

If an admin account has a plain-text password stored in the `hashed_password`
column, use the provided reset script to fix it without touching the seed data.

```bash
# 1. Install dependencies (if not already installed)
pip install passlib[bcrypt] psycopg2-binary

# 2. Edit the CONFIG section at the top of the script
#    (DB host, port, credentials, target email, new password)
nano scripts/reset_admin_password.py

# 3. Run it
python scripts/reset_admin_password.py
```

The script connects directly to Postgres, generates a fresh bcrypt hash, and
updates only the target user's `hashed_password` column. It prints a clear
success or warning message and exits with a non-zero code on failure, making
it safe to run in automated pipelines.
