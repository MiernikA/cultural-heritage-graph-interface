from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

from scripts.download_source_data import DEFAULT_FILES, download_file


def main() -> int:
    maybe_download_source_data()
    uvicorn.run(
        "backend.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "7860")),
    )
    return 0


def maybe_download_source_data() -> None:
    base_url = os.getenv("KG_SOURCE_DATA_BASE_URL")
    if not base_url:
        return

    destination = Path(os.getenv("KG_SOURCE_DATA_DIR", "backend/data/source"))
    destination.mkdir(parents=True, exist_ok=True)
    base_url = base_url.rstrip("/")

    missing_files = [filename for filename in DEFAULT_FILES if not (destination / filename).exists()]
    if not missing_files:
        print(f"source data already present in {destination}")
        return

    for filename in missing_files:
        download_file(f"{base_url}/{filename}", destination / filename)


if __name__ == "__main__":
    sys.exit(main())
