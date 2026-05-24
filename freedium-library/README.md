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

## Training a zstd dictionary (optional, recommended)

Compression efficiency for Medium GraphQL responses improves ~2-3x with
a trained zstd dictionary that captures the field names, URL prefixes,
and recurring schema constants shared across all responses.

1. Populate the cache first — the trainer needs ≥100 sample docs.
   Either run the PG→Mongo migration (`scripts/migrate_pg_to_mongo.py`)
   or just let the cache fill organically.

2. Run the trainer:

       MONGO_URL=mongodb://localhost:27017 \
       pdm run python -m freedium_library.scripts.train_zstd_dict

   The dictionary is written to
   `src/freedium_library/utils/cache/db/dict_v1.zstd` and is loaded
   automatically by the backend at startup.

3. Restart the backend so the new dictionary is loaded:

       docker compose restart backend

Existing documents remain decompressible (they were tagged `compression="zstd"`
when written; the backend still understands that tag). New writes use the
dictionary and are tagged `"zstd_dict_v1"`.

To regenerate the dictionary later (e.g. after schema changes shift the
distribution), just re-run the trainer — it overwrites `dict_v1.zstd`.
