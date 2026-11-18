#!/usr/bin/env bash
# Inicia PostgreSQL local y crea el usuario y las bases de desarrollo y pruebas si no existen.
set -euo pipefail

if ! command -v psql >/dev/null; then
  apt-get update -qq && apt-get install -y -qq postgresql >/dev/null
fi
service postgresql start >/dev/null

as_pg() { su postgres -c "$1"; }
as_pg "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='app'\"" | grep -q 1 \
  || as_pg "psql -qc \"CREATE USER app WITH PASSWORD 'app' CREATEDB;\""
for db in employer_buddy employer_buddy_test; do
  as_pg "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='$db'\"" | grep -q 1 \
    || as_pg "createdb -O app $db"
done
echo "PostgreSQL listo: employer_buddy y employer_buddy_test"
