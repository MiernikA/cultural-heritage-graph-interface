from __future__ import annotations

import argparse
import csv
import ctypes
import json
import math
import os
import platform
import random
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8001/api"
DEFAULT_ITERATIONS = 100
DEFAULT_LIMIT = 25
DEFAULT_RECOMMENDATION_LIMIT = 10
WARMUP_REQUESTS_PER_OPERATION = 5
REQUEST_TIMEOUT_SECONDS = 30

DISCOVERY_SEEDS = (
    "a",
    "e",
    "i",
    "o",
    "m",
    "p",
    "s",
    "w",
    "z",
    "object",
    "person",
    "place",
    "type",
    "fragment",
    "collection",
    "museum",
    "site",
    "artifact",
    "vessel",
    "stone",
    "bronze",
    "ceramic",
    "glass",
    "coin",
)


@dataclass(frozen=True)
class RequestSpec:
    operation: str
    path: str
    query_or_uri: str


@dataclass(frozen=True)
class Measurement:
    operation: str
    query_or_uri: str
    url: str
    status_http: int | None
    elapsed_ms: float
    error: str

    @property
    def ok(self) -> bool:
        return not self.error and self.status_http is not None and 200 <= self.status_http < 300


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark lokalnego backendu Knowledge Graph Explorer.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Bazowy URL API, np. http://127.0.0.1:8001/api")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS, help="Liczba pomiarow dla kazdej operacji.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Limit wynikow dla endpointu /search.")
    parser.add_argument(
        "--recommendation-limit",
        type=int,
        default=DEFAULT_RECOMMENDATION_LIMIT,
        help="Limit wynikow dla endpointu /recommendations.",
    )
    parser.add_argument("--seed", type=int, default=20260902, help="Seed losowania probki.")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "results"),
        help="Katalog wynikow CSV/JSON.",
    )
    args = parser.parse_args()

    if args.iterations < 1:
        raise SystemExit("--iterations musi byc dodatnie")

    rng = random.Random(args.seed)
    base_url = args.base_url.rstrip("/") + "/"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Backend benchmark")
    print(f"API base URL: {base_url.rstrip('/')}")
    print(f"Measurements per operation: {args.iterations}")
    print()

    ensure_backend_available(base_url)
    environment = collect_environment()
    entities = discover_entities(base_url, args.limit)

    if not entities:
        raise SystemExit("Discovery nie znalazlo zadnych encji przez /api/search; benchmark przerwany.")

    by_type: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        by_type.setdefault(str(entity.get("semantic_type") or "Unknown"), []).append(entity)

    print(f"Discovery: {len(entities)} unikalnych encji, typy: {format_type_counts(by_type)}")

    search_specs = build_search_specs(entities, args.iterations, args.limit, rng)
    entity_specs = build_entity_specs(entities, args.iterations, rng)
    recommendation_specs = build_recommendation_specs(entities, args.iterations, args.recommendation_limit, rng)

    print("Warm-up: start")
    run_warmup(base_url, search_specs, entity_specs, recommendation_specs)
    print("Warm-up: zakonczony")
    print()

    measurements: list[Measurement] = []
    for operation, specs in (
        ("entity_search", search_specs),
        ("entity_view", entity_specs),
        ("recommendations", recommendation_specs),
    ):
        print(f"Pomiar: {operation} ({len(specs)} requestow)")
        measurements.extend(measure_specs(base_url, specs))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_csv = output_dir / f"backend_benchmark_raw_{timestamp}.csv"
    summary_json = output_dir / f"backend_benchmark_summary_{timestamp}.json"
    write_raw_csv(raw_csv, measurements)

    summary = build_summary(measurements)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url.rstrip("/"),
        "iterations_per_operation": args.iterations,
        "warmup_requests_per_operation": WARMUP_REQUESTS_PER_OPERATION,
        "environment": environment,
        "discovery": {
            "unique_entities": len(entities),
            "semantic_type_counts": {key: len(value) for key, value in sorted(by_type.items())},
        },
        "summary": summary,
        "raw_measurements_csv": str(raw_csv),
    }
    summary_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(summary, environment, raw_csv, summary_json)
    return 0


def ensure_backend_available(base_url: str) -> None:
    status, _, error = http_get_json(base_url, "health")
    if error or status != 200:
        detail = f" status={status}" if status else ""
        raise SystemExit(f"Backend nie odpowiada na /api/health{detail}: {error or 'unknown error'}")


def discover_entities(base_url: str, limit: int) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for seed in DISCOVERY_SEEDS:
        status, payload, error = http_get_json(base_url, "search?" + urlencode({"q": seed, "limit": min(100, max(limit, 50))}))
        if error or status != 200 or not isinstance(payload, list):
            continue
        for item in payload:
            if isinstance(item, dict) and item.get("uri") and item.get("label"):
                seen.setdefault(str(item["uri"]), item)
    return list(seen.values())


def build_search_specs(
    entities: list[dict[str, Any]],
    iterations: int,
    limit: int,
    rng: random.Random,
) -> list[RequestSpec]:
    queries: list[str] = []
    for entity in entities:
        label = compact(str(entity.get("label") or ""))
        if not label:
            continue
        parts = [part for part in label.replace("_", " ").split() if len(part) >= 2]
        candidates = [label]
        if parts:
            candidates.extend(parts[:2])
            candidates.append(parts[-1])
            candidates.append(parts[0][: min(len(parts[0]), 5)])
        for candidate in candidates:
            candidate = candidate.strip(" ,.;:()[]{}")
            if len(candidate) >= 1:
                queries.append(candidate)

    unique_queries = unique_preserve_order(queries)
    rng.shuffle(unique_queries)
    selected = repeat_to_length(unique_queries, iterations, rng)
    return [
        RequestSpec(
            operation="entity_search",
            path="search?" + urlencode({"q": query, "limit": limit}),
            query_or_uri=query,
        )
        for query in selected
    ]


def build_entity_specs(entities: list[dict[str, Any]], iterations: int, rng: random.Random) -> list[RequestSpec]:
    selected = representative_entities(entities, iterations, rng)
    return [
        RequestSpec(
            operation="entity_view",
            path="entity?" + urlencode({"uri": str(entity["uri"])}),
            query_or_uri=str(entity["uri"]),
        )
        for entity in selected
    ]


def build_recommendation_specs(
    entities: list[dict[str, Any]],
    iterations: int,
    limit: int,
    rng: random.Random,
) -> list[RequestSpec]:
    selected = representative_entities(entities, iterations, rng)
    return [
        RequestSpec(
            operation="recommendations",
            path="recommendations?" + urlencode({"uri": str(entity["uri"]), "limit": limit}),
            query_or_uri=str(entity["uri"]),
        )
        for entity in selected
    ]


def representative_entities(
    entities: list[dict[str, Any]],
    count: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        by_type.setdefault(str(entity.get("semantic_type") or "Unknown"), []).append(entity)
    for values in by_type.values():
        rng.shuffle(values)

    ordered: list[dict[str, Any]] = []
    type_names = sorted(by_type)
    while len(ordered) < min(count, len(entities)):
        progressed = False
        for type_name in type_names:
            values = by_type[type_name]
            if values:
                ordered.append(values.pop())
                progressed = True
                if len(ordered) >= min(count, len(entities)):
                    break
        if not progressed:
            break

    if len(ordered) < count:
        ordered = repeat_to_length(ordered, count, rng)
    return ordered[:count]


def run_warmup(
    base_url: str,
    search_specs: list[RequestSpec],
    entity_specs: list[RequestSpec],
    recommendation_specs: list[RequestSpec],
) -> None:
    for specs in (search_specs, entity_specs, recommendation_specs):
        for spec in specs[:WARMUP_REQUESTS_PER_OPERATION]:
            http_get_json(base_url, spec.path)


def measure_specs(base_url: str, specs: list[RequestSpec]) -> list[Measurement]:
    measurements: list[Measurement] = []
    for spec in specs:
        url = urljoin(base_url, spec.path)
        start = time.perf_counter()
        status, _, error = http_get_json(base_url, spec.path)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        measurements.append(
            Measurement(
                operation=spec.operation,
                query_or_uri=spec.query_or_uri,
                url=url,
                status_http=status,
                elapsed_ms=elapsed_ms,
                error=error,
            )
        )
    return measurements


def http_get_json(base_url: str, path: str) -> tuple[int | None, Any, str]:
    url = urljoin(base_url, path)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "kg-backend-benchmark/1.0"})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read()
            status = int(response.status)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        return int(exc.code), None, f"HTTPError: {body}"
    except URLError as exc:
        return None, None, f"URLError: {exc.reason}"
    except TimeoutError:
        return None, None, "TimeoutError"
    except Exception as exc:
        return None, None, f"{type(exc).__name__}: {exc}"

    if not raw:
        return status, None, ""
    try:
        return status, json.loads(raw.decode("utf-8")), ""
    except json.JSONDecodeError as exc:
        return status, None, f"JSONDecodeError: {exc}"


def build_summary(measurements: list[Measurement]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    operations = sorted({measurement.operation for measurement in measurements})
    for operation in operations:
        operation_measurements = [item for item in measurements if item.operation == operation]
        successful = [item.elapsed_ms for item in operation_measurements if item.ok]
        failed = [item for item in operation_measurements if not item.ok]
        stats = {
            "successful_measurements": len(successful),
            "failed_requests": len(failed),
            "mean_ms": None,
            "median_ms": None,
            "p95_ms": None,
            "min_ms": None,
            "max_ms": None,
        }
        if successful:
            stats.update(
                {
                    "mean_ms": round(statistics.fmean(successful), 3),
                    "median_ms": round(statistics.median(successful), 3),
                    "p95_ms": round(percentile(successful, 95), 3),
                    "min_ms": round(min(successful), 3),
                    "max_ms": round(max(successful), 3),
                }
            )
        summary[operation] = stats
    return summary


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (percentile_value / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def write_raw_csv(path: Path, measurements: list[Measurement]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("operation", "query_or_uri", "url", "status_http", "elapsed_ms", "error"),
        )
        writer.writeheader()
        for measurement in measurements:
            writer.writerow(
                {
                    "operation": measurement.operation,
                    "query_or_uri": measurement.query_or_uri,
                    "url": measurement.url,
                    "status_http": measurement.status_http if measurement.status_http is not None else "",
                    "elapsed_ms": f"{measurement.elapsed_ms:.3f}",
                    "error": measurement.error,
                }
            )


def collect_environment() -> dict[str, Any]:
    return {
        "operating_system": f"{platform.system()} {platform.release()} ({platform.version()})",
        "processor": detect_processor(),
        "logical_cpu_cores": os.cpu_count() or "unavailable",
        "ram": detect_ram(),
        "python_version": platform.python_version(),
    }


def detect_processor() -> str:
    processor = platform.processor().strip()
    if processor:
        return processor
    env_value = os.environ.get("PROCESSOR_IDENTIFIER", "").strip()
    return env_value or "unavailable"


def detect_ram() -> str:
    if platform.system().lower() == "windows":
        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return f"{status.ullTotalPhys / (1024 ** 3):.2f} GiB"
        return "unavailable"

    pages = os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names else None
    page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names else None
    if pages and page_size:
        return f"{pages * page_size / (1024 ** 3):.2f} GiB"
    return "unavailable"


def print_report(summary: dict[str, dict[str, Any]], environment: dict[str, Any], raw_csv: Path, summary_json: Path) -> None:
    print()
    print("=== Environment ===")
    for key, value in environment.items():
        print(f"{key}: {value}")

    print()
    print("=== Results ===")
    print(f"{'operation':<18} {'ok':>5} {'failed':>7} {'mean ms':>10} {'median ms':>10} {'P95 ms':>10} {'min ms':>10} {'max ms':>10}")
    for operation, stats in summary.items():
        print(
            f"{operation:<18} "
            f"{stats['successful_measurements']:>5} "
            f"{stats['failed_requests']:>7} "
            f"{format_number(stats['mean_ms']):>10} "
            f"{format_number(stats['median_ms']):>10} "
            f"{format_number(stats['p95_ms']):>10} "
            f"{format_number(stats['min_ms']):>10} "
            f"{format_number(stats['max_ms']):>10}"
        )

    total_failed = sum(int(stats["failed_requests"]) for stats in summary.values())
    print()
    print(f"Failed requests total: {total_failed}")
    print(f"Raw CSV: {raw_csv}")
    print(f"Summary JSON: {summary_json}")


def format_type_counts(by_type: dict[str, list[dict[str, Any]]]) -> str:
    return ", ".join(f"{key}={len(value)}" for key, value in sorted(by_type.items()))


def format_number(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.3f}"


def compact(value: str) -> str:
    return " ".join(value.split())


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return unique


def repeat_to_length(values: list[Any], length: int, rng: random.Random) -> list[Any]:
    if not values:
        raise SystemExit("Nie mozna zbudowac probki benchmarkowej: brak poprawnych danych discovery.")
    output = list(values)
    while len(output) < length:
        next_batch = list(values)
        rng.shuffle(next_batch)
        output.extend(next_batch)
    return output[:length]


if __name__ == "__main__":
    raise SystemExit(main())
