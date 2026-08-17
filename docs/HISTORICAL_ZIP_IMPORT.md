# Historical ZIP directory import

The importer reads its directory only from trusted application configuration. It does not accept a path argument.

Configure `.env`:

```env
HISTORICAL_DATA_ALLOWED_IMPORT_ROOT=/historical-data
HISTORICAL_DATA_IMPORT_DIRECTORY=/historical-data/xauusd
HISTORICAL_DATA_BATCH_SIZE=10000
HISTORICAL_DATA_MAXIMUM_UNCOMPRESSED_FILE_SIZE=2147483648
HISTORICAL_DATA_MAXIMUM_ARCHIVE_UNCOMPRESSED_SIZE=4294967296
HISTORICAL_DATA_MAXIMUM_COMPRESSION_RATIO=200
HISTORICAL_DATA_MAXIMUM_ARCHIVE_ENTRIES=100
```

The configured import directory must resolve beneath the allowed root. Symlink resolution is performed before this check.

Run the import manually:

```bash
source .venv312/bin/activate
python import_historical_data.py
```

The command discovers `.zip` files case-insensitively, sorts them by filename, streams every CSV entry without extracting it, ignores TXT and other entries, and writes candles in bounded batches. Results are printed as JSON and stored per CSV in `historical_data_imports`.

Expected HistData-style rows are semicolon- or comma-delimited:

```text
<DATE>;<TIME>;<OPEN>;<HIGH>;<LOW>;<CLOSE>;<TICKVOL>
20250102;120000;2630.10;2631.20;2629.90;2630.80;100
```

Reruns are idempotent through PostgreSQL `ON CONFLICT` for provider `histdata`, symbol `XAUUSD`, timeframe `1m`, and UTC candle time. Candles are stored only in `gold_price_candles`; the importer never writes to the live `prices` table. Previously inserted batches remain recoverable if a later entry or archive fails.
