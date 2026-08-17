"""Trusted CLI entry point for configured historical ZIP imports."""

import json
from dataclasses import asdict

from src.historical_zip_importer import HistoricalZipImporter


if __name__ == "__main__":
    print(json.dumps(asdict(HistoricalZipImporter().run()), indent=2))
