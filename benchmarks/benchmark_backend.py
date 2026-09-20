from __future__ import annotations

import argparse
import csv
import ctypes
import json
import math
import os
import platform
import random
import shlex
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8001/api"
DEFAULT_ITERATIONS = 100
DEFAULT_LIMIT = 25
DEFAULT_RECOMMENDATION_LIMIT = 10
DEFAULT_WARMUP = 5
DEFAULT_STARTUP_RUNS = 3
REQUEST_TIMEOUT_SECONDS = 60
DISCOVERY_LIMIT = 100

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
    "zzzz-no-results-kg-benchmark",
)


@dataclass(frozen=True)
class RequestSpec:
    operation: str
    path: str
    query_or_uri: str
    source_label: str = ""
    semantic_type: str = ""
    relation_count: int | None = None


@dataclass(frozen=True)
class Measurement:
    operation: str
    iteration: int
    query_or_uri: str
    url: str
    status_http: int | None
    elapsed_ms: float
    response_size_bytes: int | None
    semantic_type: str
    relation_count: int | None
    final_recommendation_count: int | None
    error: str

    @property
    def ok(self) -> bool:
        return not self.error and self.status_http is not None and 200 <= self.status_http < 300


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark lokalnego backendu Knowledge Graph Explorer.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Bazowy URL API, np. http://127.0.0.1:8001/api")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS, help="Liczba pomiarow dla kazdej operacji.")
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP, help="Liczba requestow warm-up dla kazdej operacji.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Limit wynikow dla endpointu /search.")
    parser.add_argument(
        "--recommendation-limit",
        type=int,
        default=DEFAULT_RECOMMENDATION_LIMIT,
        help="Limit wynikow dla endpointu /recommendations.",
    )
    parser.add_argument("--seed", type=int, default=20260912, help="Seed losowania probki.")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "results" / "performance"),
        help="Katalog wynikow CSV/JSON.",
    )
    parser.add_argument(
        "--timestamped",
        action="store_true",
        help="Dodaj timestamp do nazw plikow wynikowych.",
    )
    parser.add_argument(
        "--startup-command",
        default="",
        help="Opcjonalna komenda startu backendu do pomiaru cold start, np. \"py -3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8001\".",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=300.0,
        help="Maksymalny czas oczekiwania na /health podczas pomiaru cold start.",
    )
    parser.add_argument(
        "--startup-runs",
        type=int,
        default=DEFAULT_STARTUP_RUNS,
        help="Liczba powtorzen pomiaru cold start, jesli podano --startup-command.",
    )
    args = parser.parse_args()

    if args.iterations < 1:
        raise SystemExit("--iterations musi byc dodatnie")
    if args.warmup < 0:
        raise SystemExit("--warmup nie moze byc ujemny")
    if args.startup_runs < 1:
        raise SystemExit("--startup-runs musi byc dodatnie")

    rng = random.Random(args.seed)
    base_url = args.base_url.rstrip("/") + "/"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Backend benchmark")
    print(f"API base URL: {base_url.rstrip('/')}")
    print(f"Measurements per operation: {args.iterations}")
    print(f"Warm-up per operation: {args.warmup}")
    print(f"Seed: {args.seed}")
    print()

    startup_summary: dict[str, Any]
    managed_process: subprocess.Popen[str] | None = None
    if args.startup_command:
        startup_summary, managed_process = measure_startups(args.startup_command, base_url, args.startup_timeout, args.startup_runs)
    else:
        ensure_backend_available(base_url)
        startup_summary = {
            "measured": False,
            "reason": "No --startup-command provided; benchmark used an already running backend.",
            "runs": [],
        }

    try:
        environment = collect_environment()
        entities = discover_entities(base_url, args.limit)
        if not entities:
            raise SystemExit("Discovery nie znalazlo zadnych encji przez /api/search; benchmark przerwany.")

        by_type = group_by_type(entities)
        print(f"Discovery: {len(entities)} unikalnych encji, typy: {format_type_counts(by_type)}")

        entity_profiles = profile_entities(base_url, entities, rng)
        recommendation_profiles, recommendation_probe = profile_recommendation_entities(
            base_url,
            entity_profiles,
            args.recommendation_limit,
            rng,
        )
        if recommendation_probe:
            startup_summary["recommendation_probe"] = recommendation_probe

        search_specs = build_search_specs(entities, args.iterations, args.limit, rng)
        entity_specs = build_entity_specs(entity_profiles, args.iterations, rng)
        recommendation_specs = build_recommendation_specs(
            recommendation_profiles or entity_profiles,
            args.iterations,
            args.recommendation_limit,
            rng,
        )

        print("Warm-up: start")
        run_warmup(base_url, search_specs, entity_specs, recommendation_specs, args.warmup)
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

        if managed_process and managed_process.poll() is None:
            benchmark_memory_pid = startup_summary.get("listener_pid") or managed_process.pid
            startup_summary["backend_ram_after_benchmark"] = memory_for_pid(int(benchmark_memory_pid))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{timestamp}" if args.timestamped else ""
        paths = {
            "raw_csv": output_dir / f"backend_performance_raw{suffix}.csv",
            "summary_csv": output_dir / f"backend_performance_summary{suffix}.csv",
            "outliers_csv": output_dir / f"backend_performance_outliers{suffix}.csv",
            "by_type_csv": output_dir / f"backend_performance_by_type{suffix}.csv",
            "startup_csv": output_dir / f"backend_startup{suffix}.csv",
            "summary_json": output_dir / f"backend_performance_summary{suffix}.json",
        }

        summary = build_summary(measurements)
        outliers = build_outliers(measurements)
        by_type_summary = build_by_type_summary(measurements)
        correlations = build_correlations(measurements)
        errors = summarize_errors(measurements)
        ui_request_notes = frontend_request_notes()

        write_raw_csv(paths["raw_csv"], measurements)
        write_summary_csv(paths["summary_csv"], summary)
        write_outliers_csv(paths["outliers_csv"], outliers)
        write_by_type_csv(paths["by_type_csv"], by_type_summary)
        write_startup_csv(paths["startup_csv"], startup_summary)

        summary_payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "base_url": base_url.rstrip("/"),
            "seed": args.seed,
            "iterations_per_operation": args.iterations,
            "warmup_requests_per_operation": args.warmup,
            "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "environment": environment,
            "methodology": {
                "timer": "time.perf_counter() around one HTTP GET request in the benchmark client",
                "endpoints": {
                    "health_check": "GET /api/health",
                    "entity_search": "GET /api/search?q=...&limit=...",
                    "entity_view": "GET /api/entity?uri=...",
                    "recommendations": "GET /api/recommendations?uri=...&limit=...",
                },
                "percentiles": "Linear interpolation over sorted successful latencies: rank=(n-1)*p/100, matching the common inclusive quantile definition used by numpy.percentile default method='linear'.",
                "failed_requests": "excluded from latency statistics and reported separately",
                "selection": "search queries derived from discovered labels plus fixed varied seeds; entity and recommendation cases stratified by semantic_type and relation count when available",
                "warmup": "Warm-up uses the first N prepared request specs for each operation; these requests are executed before measured iterations and excluded from raw results.",
                "frontend_request_notes": ui_request_notes,
            },
            "discovery": {
                "unique_entities": len(entities),
                "profiled_entities": len(entity_profiles),
                "recommendation_profiled_entities": len(recommendation_profiles),
                "semantic_type_counts": {key: len(value) for key, value in sorted(by_type.items())},
            },
            "summary": summary,
            "by_type": by_type_summary,
            "outliers": outliers,
            "correlations": correlations,
            "errors": errors,
            "startup": startup_summary,
            "output_files": {key: str(value) for key, value in paths.items()},
        }
        paths["summary_json"].write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print_report(summary, correlations, errors, environment, startup_summary, paths)
        return 0
    finally:
        if managed_process and managed_process.poll() is None:
            stop_process(managed_process)


def ensure_backend_available(base_url: str) -> None:
    status, _, _, error = http_get_json(base_url, "health")
    if error or status != 200:
        detail = f" status={status}" if status else ""
        raise SystemExit(f"Backend nie odpowiada na /api/health{detail}: {error or 'unknown error'}")


def measure_startups(
    command: str,
    base_url: str,
    timeout_seconds: float,
    runs: int,
) -> tuple[dict[str, Any], subprocess.Popen[str]]:
    run_results: list[dict[str, Any]] = []
    managed_process: subprocess.Popen[str] | None = None
    for run in range(1, runs + 1):
        result, process = measure_startup(command, base_url, timeout_seconds, run)
        run_results.append(result)
        if run < runs:
            stop_process(process)
            time.sleep(1.0)
        else:
            managed_process = process

    values = [float(item["startup_to_health_ms"]) for item in run_results if item.get("startup_to_health_ms") is not None]
    summary = {
        "measured": True,
        "command": command,
        "runs_requested": runs,
        "runs": run_results,
        "startup_to_health_ms": {
            "count": len(values),
            "mean": round(statistics.fmean(values), 3) if values else None,
            "median": round(statistics.median(values), 3) if values else None,
            "min": round(min(values), 3) if values else None,
            "max": round(max(values), 3) if values else None,
        },
        "listener_pid": run_results[-1].get("listener_pid") if run_results else None,
        "ram_after_health": run_results[-1].get("ram_after_health") if run_results else None,
        "peak_ram_during_startup_polling": run_results[-1].get("peak_ram_during_startup_polling") if run_results else None,
        "note": "Each run was measured until /api/health was available. Earlier runs were terminated after measurement; the final run served the benchmark requests.",
    }
    if managed_process is None:
        raise SystemExit("Cold start nie pozostawil dzialajacego procesu backendu.")
    return summary, managed_process


def measure_startup(command: str, base_url: str, timeout_seconds: float, run: int) -> tuple[dict[str, Any], subprocess.Popen[str]]:
    print(f"Cold start {run}: uruchamianie backendu")
    argv = shlex.split(command, posix=False)
    start = time.perf_counter()
    process = subprocess.Popen(
        argv,
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    peak_memory: dict[str, Any] | None = None
    health_status: int | None = None
    health_error = ""
    while True:
        if process.poll() is not None:
            raise SystemExit(f"Backend zakonczyl prace przed /health, exit code={process.returncode}")
        memory = memory_for_pid(process.pid)
        if isinstance(memory.get("working_set_bytes"), int):
            if not peak_memory or int(memory["working_set_bytes"]) > int(peak_memory.get("working_set_bytes", 0)):
                peak_memory = memory
        health_status, _, _, health_error = http_get_json(base_url, "health", timeout=1.0)
        if health_status == 200 and not health_error:
            break
        if time.perf_counter() - start > timeout_seconds:
            process.terminate()
            raise SystemExit(f"Timeout podczas oczekiwania na /api/health: {health_error or health_status}")
        time.sleep(0.25)

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    listener_pid = listener_pid_for_url(base_url)
    memory_after_start = memory_for_pid(listener_pid or process.pid)
    print(f"Cold start {run}: /health gotowe po {elapsed_ms:.1f} ms")
    return (
        {
            "measured": True,
            "run": run,
            "command": command,
            "pid": process.pid,
            "listener_pid": listener_pid,
            "startup_to_health_ms": round(elapsed_ms, 3),
            "health_status": health_status,
            "ram_after_health": memory_after_start,
            "peak_ram_during_startup_polling": peak_memory,
            "note": "Measured until /api/health was available. Recommendation artifacts are loaded lazily on first recommendation request.",
        },
        process,
    )


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()


def discover_entities(base_url: str, limit: int) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for seed in DISCOVERY_SEEDS:
        status, payload, _, error = http_get_json(base_url, "search?" + urlencode({"q": seed, "limit": min(DISCOVERY_LIMIT, max(limit, 50))}))
        if error or status != 200 or not isinstance(payload, list):
            continue
        for item in payload:
            if isinstance(item, dict) and item.get("uri") and item.get("label"):
                seen.setdefault(str(item["uri"]), item)
    return list(seen.values())


def profile_entities(base_url: str, entities: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    ordered = representative_entities(entities, min(len(entities), 180), rng)
    profiles: list[dict[str, Any]] = []
    for entity in ordered:
        uri = str(entity["uri"])
        status, payload, _, error = http_get_json(base_url, "entity?" + urlencode({"uri": uri}))
        if error or status != 200 or not isinstance(payload, dict):
            continue
        relation_count = count_entity_relations(payload)
        raw_degree = len(payload.get("advanced", {}).get("raw_triples", [])) if isinstance(payload.get("advanced"), dict) else None
        profiles.append(
            {
                "uri": uri,
                "label": str(entity.get("label") or payload.get("display_name") or uri),
                "semantic_type": str(payload.get("semantic_type") or entity.get("semantic_type") or "Unknown"),
                "relation_count": relation_count,
                "raw_degree": raw_degree,
            }
        )
    return profiles


def profile_recommendation_entities(
    base_url: str,
    profiles: list[dict[str, Any]],
    limit: int,
    rng: random.Random,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    output: list[dict[str, Any]] = []
    probe_measurements: list[dict[str, Any]] = []
    for profile in representative_entities(profiles, min(len(profiles), 120), rng):
        path = "recommendations?" + urlencode({"uri": str(profile["uri"]), "limit": limit})
        start = time.perf_counter()
        status, payload, size, error = http_get_json(base_url, path)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        probe_measurements.append(
            {
                "uri": profile["uri"],
                "semantic_type": profile.get("semantic_type"),
                "status_http": status,
                "elapsed_ms": round(elapsed_ms, 3),
                "response_size_bytes": size,
                "recommendation_count": len(payload) if isinstance(payload, list) else None,
                "error": error,
            }
        )
        if error or status != 200 or not isinstance(payload, list):
            continue
        enriched = dict(profile)
        enriched["final_recommendation_count"] = len(payload)
        output.append(enriched)
    return output, recommendation_probe_summary(probe_measurements)


def recommendation_probe_summary(probe_measurements: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not probe_measurements:
        return None
    first = probe_measurements[0]
    subsequent = probe_measurements[1:]
    successful_subsequent = [
        float(item["elapsed_ms"])
        for item in subsequent
        if not item.get("error") and item.get("status_http") is not None and 200 <= int(item["status_http"]) < 300
    ]
    return {
        "first_request": first
        | {
            "note": "First recommendation request observed by benchmark; includes lazy recommendation artifact loading if artifacts were not already loaded.",
        },
        "subsequent_requests": {
            "count": len(subsequent),
            "successful_responses": len(successful_subsequent),
            "mean_ms": round(statistics.fmean(successful_subsequent), 3) if successful_subsequent else None,
            "median_ms": round(statistics.median(successful_subsequent), 3) if successful_subsequent else None,
            "p95_ms": round(percentile(successful_subsequent, 95), 3) if successful_subsequent else None,
            "min_ms": round(min(successful_subsequent), 3) if successful_subsequent else None,
            "max_ms": round(max(successful_subsequent), 3) if successful_subsequent else None,
        },
        "sample": probe_measurements[:10],
        "note": "Probe calls are used only to identify entities with available recommendation artifacts and to observe lazy loading before the measured benchmark iterations.",
    }


def build_search_specs(
    entities: list[dict[str, Any]],
    iterations: int,
    limit: int,
    rng: random.Random,
) -> list[RequestSpec]:
    queries = ["a", "museum", "bronze", "ceramic vessel", "nonexistent-query-zzzz-benchmark"]
    for entity in entities:
        label = compact(str(entity.get("label") or ""))
        if not label:
            continue
        parts = [part for part in label.replace("_", " ").split() if len(part) >= 2]
        queries.append(label)
        if parts:
            queries.extend(parts[:2])
            queries.append(parts[-1])
            queries.append(" ".join(parts[: min(3, len(parts))]))

    unique_queries = unique_preserve_order(query for query in queries if len(query.strip()) >= 1)
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


def build_entity_specs(profiles: list[dict[str, Any]], iterations: int, rng: random.Random) -> list[RequestSpec]:
    selected = stratified_by_type_and_degree(profiles, iterations, rng)
    return [
        RequestSpec(
            operation="entity_view",
            path="entity?" + urlencode({"uri": str(profile["uri"])}),
            query_or_uri=str(profile["uri"]),
            source_label=str(profile.get("label") or ""),
            semantic_type=str(profile.get("semantic_type") or ""),
            relation_count=as_int_or_none(profile.get("relation_count")),
        )
        for profile in selected
    ]


def build_recommendation_specs(
    profiles: list[dict[str, Any]],
    iterations: int,
    limit: int,
    rng: random.Random,
) -> list[RequestSpec]:
    selected = stratified_by_type_and_degree(profiles, iterations, rng)
    return [
        RequestSpec(
            operation="recommendations",
            path="recommendations?" + urlencode({"uri": str(profile["uri"]), "limit": limit}),
            query_or_uri=str(profile["uri"]),
            source_label=str(profile.get("label") or ""),
            semantic_type=str(profile.get("semantic_type") or ""),
            relation_count=as_int_or_none(profile.get("relation_count")),
        )
        for profile in selected
    ]


def representative_entities(entities: list[dict[str, Any]], count: int, rng: random.Random) -> list[dict[str, Any]]:
    by_type = group_by_type(entities)
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
    return repeat_to_length(ordered, count, rng) if len(ordered) < count else ordered[:count]


def stratified_by_type_and_degree(profiles: list[dict[str, Any]], count: int, rng: random.Random) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for profile in profiles:
        buckets.setdefault(str(profile.get("semantic_type") or "Unknown"), []).append(profile)
    ordered: list[dict[str, Any]] = []
    for type_name in sorted(buckets):
        values = sorted(buckets[type_name], key=lambda item: as_int_or_none(item.get("relation_count")) or 0)
        if len(values) <= 3:
            chosen = values
        else:
            chosen = [values[0], values[len(values) // 2], values[-1]]
            rest = [item for item in values if item not in chosen]
            rng.shuffle(rest)
            chosen.extend(rest)
        ordered.extend(chosen)
    rng.shuffle(ordered)
    return repeat_to_length(ordered, count, rng)[:count]


def run_warmup(
    base_url: str,
    search_specs: list[RequestSpec],
    entity_specs: list[RequestSpec],
    recommendation_specs: list[RequestSpec],
    warmup: int,
) -> None:
    for specs in (search_specs, entity_specs, recommendation_specs):
        for spec in specs[:warmup]:
            http_get_json(base_url, spec.path)


def measure_specs(base_url: str, specs: list[RequestSpec]) -> list[Measurement]:
    measurements: list[Measurement] = []
    for iteration, spec in enumerate(specs, start=1):
        url = urljoin(base_url, spec.path)
        start = time.perf_counter()
        status, payload, response_size, error = http_get_json(base_url, spec.path)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        semantic_type = spec.semantic_type
        relation_count = spec.relation_count
        final_recommendation_count: int | None = None
        if not error and status and 200 <= status < 300:
            if spec.operation == "entity_search" and isinstance(payload, list):
                final_recommendation_count = None
            elif spec.operation == "entity_view" and isinstance(payload, dict):
                semantic_type = str(payload.get("semantic_type") or semantic_type)
                relation_count = count_entity_relations(payload)
            elif spec.operation == "recommendations" and isinstance(payload, list):
                final_recommendation_count = len(payload)
        measurements.append(
            Measurement(
                operation=spec.operation,
                iteration=iteration,
                query_or_uri=spec.query_or_uri,
                url=url,
                status_http=status,
                elapsed_ms=elapsed_ms,
                response_size_bytes=response_size,
                semantic_type=semantic_type,
                relation_count=relation_count,
                final_recommendation_count=final_recommendation_count,
                error=error,
            )
        )
    return measurements


def http_get_json(base_url: str, path: str, timeout: float = REQUEST_TIMEOUT_SECONDS) -> tuple[int | None, Any, int | None, str]:
    url = urljoin(base_url, path)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "kg-backend-benchmark/2.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = int(response.status)
    except HTTPError as exc:
        body = exc.read()
        detail = body.decode("utf-8", errors="replace")[:500]
        return int(exc.code), None, len(body), f"HTTPError: {detail}"
    except URLError as exc:
        return None, None, None, f"URLError: {exc.reason}"
    except TimeoutError:
        return None, None, None, "TimeoutError"
    except Exception as exc:
        return None, None, None, f"{type(exc).__name__}: {exc}"

    if not raw:
        return status, None, 0, ""
    try:
        return status, json.loads(raw.decode("utf-8")), len(raw), ""
    except json.JSONDecodeError as exc:
        return status, None, len(raw), f"JSONDecodeError: {exc}"


def build_summary(measurements: list[Measurement]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for operation in sorted({measurement.operation for measurement in measurements}):
        operation_measurements = [item for item in measurements if item.operation == operation]
        successful = [item.elapsed_ms for item in operation_measurements if item.ok]
        failed = [item for item in operation_measurements if not item.ok]
        stats: dict[str, Any] = {
            "request_count": len(operation_measurements),
            "successful_responses": len(successful),
            "count": len(successful),
            "errors": len(failed),
            "success_rate": round(len(successful) / len(operation_measurements), 6) if operation_measurements else None,
            "mean_ms": None,
            "median_ms": None,
            "p90_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "min_ms": None,
            "max_ms": None,
            "std_ms": None,
            "coefficient_of_variation": None,
        }
        if successful:
            mean = statistics.fmean(successful)
            std = statistics.stdev(successful) if len(successful) > 1 else 0.0
            stats.update(
                {
                    "mean_ms": round(mean, 3),
                    "median_ms": round(statistics.median(successful), 3),
                    "p90_ms": round(percentile(successful, 90), 3),
                    "p95_ms": round(percentile(successful, 95), 3),
                    "p99_ms": round(percentile(successful, 99), 3),
                    "min_ms": round(min(successful), 3),
                    "max_ms": round(max(successful), 3),
                    "std_ms": round(std, 3),
                    "coefficient_of_variation": round(std / mean, 6) if mean else None,
                }
            )
        summary[operation] = stats
    return summary


def build_by_type_summary(measurements: list[Measurement]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    keys = sorted({(item.operation, item.semantic_type or "n/a") for item in measurements if item.ok})
    for operation, semantic_type in keys:
        values = [item.elapsed_ms for item in measurements if item.ok and item.operation == operation and (item.semantic_type or "n/a") == semantic_type]
        if not values:
            continue
        rows.append(
            {
                "operation": operation,
                "semantic_type": semantic_type,
                "count": len(values),
                "mean_ms": round(statistics.fmean(values), 3),
                "median_ms": round(statistics.median(values), 3),
                "p95_ms": round(percentile(values, 95), 3),
                "min_ms": round(min(values), 3),
                "max_ms": round(max(values), 3),
            }
        )
    return rows


def build_outliers(measurements: list[Measurement], per_operation: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for operation in sorted({item.operation for item in measurements}):
        slowest = sorted([item for item in measurements if item.operation == operation and item.ok], key=lambda item: item.elapsed_ms, reverse=True)
        for rank, item in enumerate(slowest[:per_operation], start=1):
            rows.append(measurement_row(item) | {"rank": rank})
    return rows


def build_correlations(measurements: list[Measurement]) -> dict[str, Any]:
    entity_pairs = [
        (float(item.relation_count), item.elapsed_ms)
        for item in measurements
        if item.ok and item.operation == "entity_view" and item.relation_count is not None
    ]
    recommendation_pairs = [
        (float(item.final_recommendation_count), item.elapsed_ms)
        for item in measurements
        if item.ok and item.operation == "recommendations" and item.final_recommendation_count is not None
    ]
    return {
        "entity_relation_count_to_latency": correlation_summary(entity_pairs),
        "recommendation_count_to_latency": correlation_summary(recommendation_pairs),
    }


def correlation_summary(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    if len(pairs) < 3 or len({x for x, _ in pairs}) < 2 or len({y for _, y in pairs}) < 2:
        return {"count": len(pairs), "pearson": None, "spearman": None, "note": "Too little variation for a meaningful coefficient."}
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    return {
        "count": len(pairs),
        "pearson": round(pearson(xs, ys), 6),
        "spearman": round(pearson(ranks(xs), ranks(ys)), 6),
    }


def pearson(xs: list[float], ys: list[float]) -> float:
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denominator_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denominator_x == 0 or denominator_y == 0:
        return math.nan
    return numerator / (denominator_x * denominator_y)


def ranks(values: list[float]) -> list[float]:
    ordered = sorted((value, index) for index, value in enumerate(values))
    result = [0.0] * len(values)
    position = 0
    while position < len(ordered):
        end = position
        while end + 1 < len(ordered) and ordered[end + 1][0] == ordered[position][0]:
            end += 1
        rank = (position + end + 2) / 2.0
        for _, original_index in ordered[position : end + 1]:
            result[original_index] = rank
        position = end + 1
    return result


def summarize_errors(measurements: list[Measurement]) -> dict[str, Any]:
    total = len(measurements)
    successful = sum(1 for item in measurements if item.ok)
    errors = [item for item in measurements if not item.ok]
    return {
        "total_requests": total,
        "successful_requests": successful,
        "success_rate": round(successful / total, 6) if total else None,
        "timeouts": sum(1 for item in errors if "Timeout" in item.error),
        "http_4xx": sum(1 for item in errors if item.status_http is not None and 400 <= item.status_http < 500),
        "http_5xx": sum(1 for item in errors if item.status_http is not None and 500 <= item.status_http < 600),
        "other_exceptions": sum(1 for item in errors if item.status_http is None and "Timeout" not in item.error),
        "by_operation": {
            operation: {
                "total": sum(1 for item in measurements if item.operation == operation),
                "errors": sum(1 for item in measurements if item.operation == operation and not item.ok),
            }
            for operation in sorted({item.operation for item in measurements})
        },
    }


def percentile(values: list[float], percentile_value: float) -> float:
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
        writer = csv.DictWriter(handle, fieldnames=list(measurement_row(measurements[0]).keys()) if measurements else [])
        writer.writeheader()
        for measurement in measurements:
            writer.writerow(measurement_row(measurement))


def write_summary_csv(path: Path, summary: dict[str, dict[str, Any]]) -> None:
    fieldnames = (
        "operation",
        "request_count",
        "successful_responses",
        "count",
        "errors",
        "success_rate",
        "mean_ms",
        "median_ms",
        "p90_ms",
        "p95_ms",
        "p99_ms",
        "min_ms",
        "max_ms",
        "std_ms",
        "coefficient_of_variation",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for operation, stats in summary.items():
            writer.writerow({"operation": operation, **stats})


def write_outliers_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = (
        "rank",
        "operation",
        "iteration",
        "query_or_uri",
        "url",
        "status_http",
        "elapsed_ms",
        "response_size_bytes",
        "semantic_type",
        "relation_count",
        "final_recommendation_count",
        "error",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_by_type_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ("operation", "semantic_type", "count", "mean_ms", "median_ms", "p95_ms", "min_ms", "max_ms")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_startup_csv(path: Path, startup_summary: dict[str, Any]) -> None:
    fieldnames = (
        "run",
        "startup_to_health_ms",
        "health_status",
        "pid",
        "listener_pid",
        "ram_after_health_working_set_mib",
        "ram_after_health_private_memory_mib",
        "peak_startup_working_set_mib",
    )
    rows = startup_summary.get("runs") if isinstance(startup_summary.get("runs"), list) else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            ram = row.get("ram_after_health") if isinstance(row, dict) else {}
            peak = row.get("peak_ram_during_startup_polling") if isinstance(row, dict) else {}
            writer.writerow(
                {
                    "run": row.get("run"),
                    "startup_to_health_ms": row.get("startup_to_health_ms"),
                    "health_status": row.get("health_status"),
                    "pid": row.get("pid"),
                    "listener_pid": row.get("listener_pid"),
                    "ram_after_health_working_set_mib": ram.get("working_set_mib") if isinstance(ram, dict) else "",
                    "ram_after_health_private_memory_mib": ram.get("private_memory_mib") if isinstance(ram, dict) else "",
                    "peak_startup_working_set_mib": peak.get("working_set_mib") if isinstance(peak, dict) else "",
                }
            )


def measurement_row(measurement: Measurement) -> dict[str, Any]:
    return {
        "operation": measurement.operation,
        "iteration": measurement.iteration,
        "query_or_uri": measurement.query_or_uri,
        "url": measurement.url,
        "status_http": measurement.status_http if measurement.status_http is not None else "",
        "elapsed_ms": f"{measurement.elapsed_ms:.3f}",
        "response_size_bytes": measurement.response_size_bytes if measurement.response_size_bytes is not None else "",
        "semantic_type": measurement.semantic_type,
        "relation_count": measurement.relation_count if measurement.relation_count is not None else "",
        "final_recommendation_count": measurement.final_recommendation_count if measurement.final_recommendation_count is not None else "",
        "error": measurement.error,
    }


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


def memory_for_pid(pid: int) -> dict[str, Any]:
    if platform.system().lower() == "windows":
        try:
            ps_script = (
                f"$root={pid};"
                "$ids=@($root);"
                "do {"
                "  $children=Get-CimInstance Win32_Process | Where-Object { $ids -contains $_.ParentProcessId -and -not ($ids -contains $_.ProcessId) };"
                "  $new=@($children | ForEach-Object { [int]$_.ProcessId });"
                "  if ($new.Count -gt 0) { $ids += $new }"
                "} while ($new.Count -gt 0);"
                "$procs=Get-Process -Id $ids -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,WorkingSet64,PeakWorkingSet64,PrivateMemorySize64;"
                "$procs | ConvertTo-Json -Compress"
            )
            output = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    ps_script,
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except Exception as exc:
            return {"pid": pid, "available": False, "error": f"{type(exc).__name__}: {exc}"}
        if not output:
            return {"pid": pid, "available": False, "error": "process not found"}
        try:
            payload = json.loads(output)
            processes = payload if isinstance(payload, list) else [payload]
            working_set = sum(int(item.get("WorkingSet64") or 0) for item in processes)
            peak_working_set = sum(int(item.get("PeakWorkingSet64") or 0) for item in processes)
            private_memory = sum(int(item.get("PrivateMemorySize64") or 0) for item in processes)
            if working_set < 64 * 1024 * 1024 and private_memory < 64 * 1024 * 1024:
                return {
                    "pid": pid,
                    "available": False,
                    "working_set_mib": round(working_set / (1024.0 ** 2), 3),
                    "private_memory_mib": round(private_memory / (1024.0 ** 2), 3),
                    "process_count": len(processes),
                    "source": "Get-CimInstance process tree + Get-Process WorkingSet64/PrivateMemorySize64",
                    "error": "Measured memory is implausibly low for this backend; omitted as unreliable in this environment.",
                }
            return {
                "pid": pid,
                "available": True,
                "working_set_bytes": working_set,
                "working_set_mib": round(working_set / (1024.0 ** 2), 3),
                "peak_working_set_bytes": peak_working_set,
                "peak_working_set_mib": round(peak_working_set / (1024.0 ** 2), 3),
                "private_memory_bytes": private_memory,
                "private_memory_mib": round(private_memory / (1024.0 ** 2), 3),
                "process_count": len(processes),
                "processes": [
                    {
                        "pid": int(item.get("Id") or 0),
                        "name": str(item.get("ProcessName") or ""),
                        "working_set_mib": round(int(item.get("WorkingSet64") or 0) / (1024.0 ** 2), 3),
                        "private_memory_mib": round(int(item.get("PrivateMemorySize64") or 0) / (1024.0 ** 2), 3),
                    }
                    for item in processes
                ],
                "source": "Get-CimInstance process tree + Get-Process WorkingSet64/PeakWorkingSet64/PrivateMemorySize64",
            }
        except Exception as exc:
            return {"pid": pid, "available": False, "raw": output, "error": f"{type(exc).__name__}: {exc}"}

    status_path = Path(f"/proc/{pid}/status")
    if status_path.exists():
        for line in status_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("VmRSS:"):
                kb = int(line.split()[1])
                return {
                    "pid": pid,
                    "available": True,
                    "working_set_bytes": kb * 1024,
                    "working_set_mib": round(kb / 1024.0, 3),
                    "source": "/proc/<pid>/status VmRSS",
                }
    return {"pid": pid, "available": False, "error": "unsupported platform or process not found"}


def listener_pid_for_url(base_url: str) -> int | None:
    parsed = urlparse(base_url)
    port = parsed.port
    if port is None:
        return None
    if platform.system().lower() == "windows":
        try:
            script = (
                f"$conn=Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
                "Select-Object -First 1 -ExpandProperty OwningProcess;"
                "$conn"
            )
            output = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", script],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            return int(output) if output else None
        except Exception:
            try:
                output = subprocess.check_output(["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL)
            except Exception:
                return None
            marker = f":{port}"
            for line in output.splitlines():
                if marker in line and "LISTENING" in line:
                    parts = line.split()
                    if parts and parts[-1].isdigit():
                        return int(parts[-1])
            return None
    try:
        output = subprocess.check_output(["lsof", "-ti", f":{port}"], text=True, stderr=subprocess.DEVNULL).strip()
        return int(output.splitlines()[0]) if output else None
    except Exception:
        return None


def print_report(
    summary: dict[str, dict[str, Any]],
    correlations: dict[str, Any],
    errors: dict[str, Any],
    environment: dict[str, Any],
    startup_summary: dict[str, Any],
    paths: dict[str, Path],
) -> None:
    print()
    print("=== Environment ===")
    for key, value in environment.items():
        print(f"{key}: {value}")

    print()
    print("=== Results ===")
    print(
        f"{'operation':<18} {'req':>6} {'ok':>6} {'mean':>10} {'median':>10} {'P90':>10} "
        f"{'P95':>10} {'P99':>10} {'min':>10} {'max':>10} {'std':>10}"
    )
    for operation, stats in summary.items():
        print(
            f"{operation:<18} "
            f"{stats['request_count']:>6} "
            f"{stats['successful_responses']:>6} "
            f"{format_number(stats['mean_ms']):>10} "
            f"{format_number(stats['median_ms']):>10} "
            f"{format_number(stats['p90_ms']):>10} "
            f"{format_number(stats['p95_ms']):>10} "
            f"{format_number(stats['p99_ms']):>10} "
            f"{format_number(stats['min_ms']):>10} "
            f"{format_number(stats['max_ms']):>10} "
            f"{format_number(stats['std_ms']):>10}"
        )

    print()
    print(f"Success rate: {format_percent(errors['success_rate'])}")
    if startup_summary.get("measured"):
        print(f"Startup to /health: {startup_summary.get('startup_to_health_ms')} ms")
        print(f"RAM after /health: {startup_summary.get('ram_after_health')}")
    else:
        print(f"Startup: not measured ({startup_summary.get('reason')})")
    print(f"Correlations: {json.dumps(correlations, ensure_ascii=False)}")
    print()
    for key, path in paths.items():
        print(f"{key}: {path}")


def frontend_request_notes() -> list[str]:
    return [
        "Search input calls GET /api/search?q=...&limit=25 after a 350 ms debounce for queries with at least two characters.",
        "Opening an entity view requires GET /api/entity?uri=... for the entity detail payload.",
        "EntityPage also calls GET /api/recommendations?uri=... and GET /api/recommendations/featured?uri=... in parallel after an entity is loaded.",
        "Alias resolution may call /api/search for displayable aliases; it is conditional on aliases and was not included as a core operation.",
    ]


def count_entity_relations(payload: dict[str, Any]) -> int:
    groups = payload.get("connections", [])
    if not isinstance(groups, list):
        return 0
    total = 0
    for group in groups:
        if isinstance(group, dict) and isinstance(group.get("relationships"), list):
            total += len(group["relationships"])
    return total


def group_by_type(entities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        by_type.setdefault(str(entity.get("semantic_type") or "Unknown"), []).append(entity)
    return by_type


def as_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def format_type_counts(by_type: dict[str, list[dict[str, Any]]]) -> str:
    return ", ".join(f"{key}={len(value)}" for key, value in sorted(by_type.items()))


def format_number(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.3f}"


def format_percent(value: Any) -> str:
    return "n/a" if value is None else f"{float(value) * 100.0:.2f}%"


def compact(value: str) -> str:
    return " ".join(value.split())


def unique_preserve_order(values: Any) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        value = compact(str(value))
        key = value.casefold()
        if value and key not in seen:
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
