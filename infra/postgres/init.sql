-- Enable TimescaleDB extension
-- This runs once when the database is first created.
-- After this, we can use create_hypertable() in our migrations.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Useful for generating UUIDs
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
