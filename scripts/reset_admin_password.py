"""Standalone admin password reset script.

Use this to fix an admin account whose hashed_password column currently holds
plain text (e.g. "password123") instead of a proper bcrypt hash.

Prerequisites (install if not already present):
    pip install passlib[bcrypt] psycopg2-binary

Usage:
    python scripts/reset_admin_password.py

Edit the CONFIG section below before running.
"""

import sys
import psycopg2
import hashlib
import bcrypt

# ── CONFIG ─────────────────────────────────────────────────────────────────
# Update these values before running.

DB_HOST     = "localhost"
DB_PORT     = 5432
DB_NAME     = "egdc_db"          # matches POSTGRES_DB in .env
DB_USER     = "egdc_user"        # matches POSTGRES_USER in .env
DB_PASSWORD = "changeme"         # matches POSTGRES_PASSWORD in .env

ADMIN_EMAIL    = "admin@example.com"
NEW_PASSWORD   = "password123"   # the desired new plain-text password
# ───────────────────────────────────────────────────────────────────────────

def _sha256_hexdigest_bytes(password: str) -> bytes:
    return hashlib.sha256(password.encode('utf-8')).hexdigest().encode('ascii')

def get_password_hash(password: str) -> str:
    prehashed = _sha256_hexdigest_bytes(password)
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(prehashed, salt)
    return hashed.decode('ascii')

def main() -> None:
    print(f"Hashing new password for '{ADMIN_EMAIL}' ...")
    new_hash = get_password_hash(NEW_PASSWORD) # <-- CHANGED THIS LINE
    print(f"Generated bcrypt hash: {new_hash[:30]}...")

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
    except psycopg2.OperationalError as exc:
        print(f"ERROR: Could not connect to database: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    'UPDATE "user" SET hashed_password = %s WHERE email = %s',
                    (new_hash, ADMIN_EMAIL),
                )
                rows_affected = cur.rowcount

        if rows_affected == 1:
            print(f"SUCCESS: Password for '{ADMIN_EMAIL}' has been reset.")
        elif rows_affected == 0:
            print(
                f"WARNING: No user found with email '{ADMIN_EMAIL}'. "
                "Check the email address and try again.",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            print(
                f"WARNING: {rows_affected} rows were updated. "
                "Expected exactly 1. Investigate immediately.",
                file=sys.stderr,
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
