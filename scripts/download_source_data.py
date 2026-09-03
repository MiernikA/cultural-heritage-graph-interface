from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


DEFAULT_FILES = (
    "chexrish_onto_prototype2.rdf",
    "complex_entity_to_id_all_cac.pkl",
    "graph_all_cac.tsv",
    "complex_embeddings_all_cac.pkl",
    "hnsw_index_complex_model_all_cac.bin",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download backend source data files.")
    parser.add_argument("--base-url", required=True, help="Base URL containing the source data files.")
    parser.add_argument(
        "--destination",
        default="backend/data/source",
        help="Directory where files should be stored.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite files that already exist.",
    )
    args = parser.parse_args()

    destination = Path(args.destination)
    destination.mkdir(parents=True, exist_ok=True)
    base_url = args.base_url.rstrip("/")

    for filename in DEFAULT_FILES:
        target = destination / filename
        if target.exists() and not args.force:
            print(f"skip {filename}: already exists")
            continue
        download_file(f"{base_url}/{filename}", target)

    return 0


def download_file(url: str, target: Path) -> None:
    tmp_target = target.with_suffix(target.suffix + ".part")
    print(f"download {url}")
    try:
        with urlopen(url) as response, tmp_target.open("wb") as output:
            downloaded = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if downloaded % (64 * 1024 * 1024) < len(chunk):
                    print(f"  {target.name}: {downloaded // (1024 * 1024)} MB")
    except (HTTPError, URLError) as exc:
        tmp_target.unlink(missing_ok=True)
        raise SystemExit(f"failed to download {url}: {exc}") from exc

    tmp_target.replace(target)
    print(f"saved {target}")


if __name__ == "__main__":
    sys.exit(main())
