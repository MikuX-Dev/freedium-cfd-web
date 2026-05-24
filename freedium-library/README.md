# freedium-library

## Migrating from the legacy PostgreSQL cache

The legacy stack stored rendered-post GraphQL responses in a Postgres
`cache(key, value)` table. The current backend uses a Mongo collection
with zstd-compressed values. To migrate:

1. Install the optional migration deps:

       pdm install -G migrate

2. Run the script with both connection strings in env:

       PG_DSN=postgres://user:pass@host/db \
       MONGO_URL=mongodb://localhost:27017 \
       pdm run python -m freedium_library.scripts.migrate_pg_to_mongo

   Optional env: `MONGO_DB`, `MONGO_COLLECTION`, `BATCH_SIZE`, `DRY_RUN=1`.

The script is idempotent: re-running re-applies every row, but
duplicates are upserted on `_id`. Progress is logged every 1000 rows.
