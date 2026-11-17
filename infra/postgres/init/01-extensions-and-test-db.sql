-- Runs once, on first initialisation of the Postgres volume.
-- Extensions are also created by the first Alembic migration (idempotent), so the schema
-- doesn't depend on this script. This script exists to create the separate test database.

CREATE DATABASE tie_test;

\connect tie
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;

\connect tie_test
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
