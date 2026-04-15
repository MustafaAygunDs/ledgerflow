#!/bin/bash
# PostgreSQL init: ek veritabanları oluştur
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE metabase_db OWNER kobi'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'metabase_db')\gexec

    SELECT 'CREATE DATABASE airflow_db OWNER kobi'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow_db')\gexec
EOSQL
