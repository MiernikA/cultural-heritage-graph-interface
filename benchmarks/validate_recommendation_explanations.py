from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.application import build_application_context
from backend.config import get_settings
from backend.data.graph.constants import CIDOC
from backend.data.schemas import Recommendation
from backend.recommendations.original_pipeline import (
    EVENT_TYPES,
    OriginalCandidate,
    OBJECT_TYPES,
    PLACE_TYPES,
    RetrievedCandidate,
    _dedupe,
    _merge_retrieved,
    _rank_recommendations,
)
from backend.recommendations.service import DEFAULT_CANDIDATE_LIMIT
from backend.recommendations.similarity import query_similar


DEFAULT_SAMPLE_SIZE = 1000
DEFAULT_SEED = 20260903
EXAMPLE_LIMIT = 35
DEFAULT_REJECTION_ANALYSIS_SIZE = 20000
DEFAULT_SPARSE_DEGREE_THRESHOLD = 2
MAX_NEIGHBORS_FOR_SHORT_PATH = 5000
SCHEMA_URI_PREFIXES = (
    CIDOC,
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "http://www.w3.org/2000/01/rdf-schema#",
    "http://www.w3.org/2002/07/owl#",
)


@dataclass(frozen=True, slots=True)
class SourceEntity:
    uri: str
    label: str
    semantic_type: str
    has_embedding: bool


@dataclass(frozen=True, slots=True)
class CandidateTrace:
    source_uri: str
    source_label: str
    source_semantic_type: str
    candidate_uri: str
    candidate_label: str
    candidate_semantic_type: str
    source_embedding_id: int | None
    candidate_embedding_id: int | None
    hnsw_rank: int | None
    distance: float | None
    passed_mapping_filter: bool
    has_semantic_reason: bool
    raw_reason_types: list[str]
    visible_reason_types: list[str]
    semantic_reason_count: int
    visible_reason_count: int
    evidence_path_count: int
    final_decision: str
    rejection_reason: str
    explanation_summary: str
    evidence_descriptions: list[str]
    rdf_evidence: list[str]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Walidacja pokrycia kandydatow HNSW wyjasnieniami semantycznymi z grafu wiedzy."
    )
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE, help="Liczba encji z UI do zbadania.")
    parser.add_argument("--all", action="store_true", help="Zbadaj wszystkie kwalifikujace sie encje z UI.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Seed doboru probki.")
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATE_LIMIT, help="Limit kandydatow HNSW.")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "results"),
        help="Katalog wynikow CSV/JSON.",
    )
    parser.add_argument(
        "--rejection-analysis-size",
        type=int,
        default=DEFAULT_REJECTION_ANALYSIS_SIZE,
        help="Liczba kandydatow no_semantic_reason do dodatkowej diagnostyki.",
    )
    parser.add_argument(
        "--rejection-analysis-all",
        action="store_true",
        help="Analizuj wszystkich kandydatow no_semantic_reason zamiast probki.",
    )
    parser.add_argument(
        "--sparse-degree-threshold",
        type=int,
        default=DEFAULT_SPARSE_DEGREE_THRESHOLD,
        help="Operacyjny prog degree dla kategorii sparse_entity.",
    )
    args = parser.parse_args()

    if args.sample_size < 1 and not args.all:
        raise SystemExit("--sample-size musi byc dodatnie albo uzyj --all")
    if args.candidate_limit < 1:
        raise SystemExit("--candidate-limit musi byc dodatni")

    started = time.perf_counter()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Recommendation explanation validation")
    print(f"Project root: {PROJECT_ROOT}")
    print("Loading application context...")
    context = build_application_context(get_settings())
    service = context.recommendations
    engine = service.original_pipeline
    graph = service.filter.graph

    all_sources = discover_source_entities(service)
    if not all_sources:
        raise SystemExit("Brak kwalifikujacych sie encji displayable w interfejsie.")

    sample = select_sample(all_sources, args.sample_size, args.seed, args.all)
    print(f"Displayable entities: {len(all_sources)}")
    print(f"Sample size: {len(sample)}")
    print(f"Sample semantic types: {format_counter(Counter(entity.semantic_type for entity in sample))}")
    print()

    entity_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    candidate_traces: list[CandidateTrace] = []
    errors: list[dict[str, str]] = []

    for index, source in enumerate(sample, start=1):
        if index == 1 or index % 25 == 0 or index == len(sample):
            print(f"Progress: {index}/{len(sample)}")
        try:
            entity_row, traces = analyze_source(source, service, args.candidate_limit)
        except Exception as exc:
            errors.append({"uri": source.uri, "label": source.label, "error": f"{type(exc).__name__}: {exc}"})
            entity_row = {
                "uri": source.uri,
                "label": source.label,
                "semantic_type": source.semantic_type,
                "has_embedding": source.has_embedding,
                "hnsw_candidate_count": 0,
                "semantic_analysis_candidate_count": 0,
                "candidates_with_semantic_reason": 0,
                "final_recommendation_count": 0,
                "semantic_reason_count": 0,
                "visible_reason_count": 0,
                "evidence_path_count": 0,
                "error": errors[-1]["error"],
            }
            traces = []
        entity_rows.append(entity_row)
        for trace in traces:
            candidate_traces.append(trace)
            candidate_rows.append(candidate_trace_to_row(trace))

    summary = build_summary(sample, entity_rows, candidate_traces, errors, args, all_sources, started)
    reason_distribution = build_reason_distribution(candidate_traces)
    examples = select_examples(candidate_traces, EXAMPLE_LIMIT)
    print()
    print("Analyzing no_semantic_reason candidates...")
    rejection_rows, rejection_summary = analyze_no_semantic_rejections(
        candidate_traces,
        service,
        args.rejection_analysis_size,
        args.rejection_analysis_all,
        args.seed,
        args.sparse_degree_threshold,
    )
    summary["reason_type_distribution"] = reason_distribution
    summary["examples"] = examples
    summary["no_semantic_reason_analysis"] = rejection_summary

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    per_entity_csv = output_dir / f"recommendation_explanations_per_entity_{timestamp}.csv"
    per_candidate_csv = output_dir / f"recommendation_explanations_per_candidate_{timestamp}.csv"
    reason_csv = output_dir / f"recommendation_explanations_reason_types_{timestamp}.csv"
    rejected_csv = output_dir / f"recommendation_explanations_no_semantic_rejections_{timestamp}.csv"
    rejection_categories_csv = output_dir / f"recommendation_explanations_rejection_categories_{timestamp}.csv"
    rejection_types_csv = output_dir / f"recommendation_explanations_rejected_types_{timestamp}.csv"
    summary_json = output_dir / f"recommendation_explanations_summary_{timestamp}.json"

    write_csv(per_entity_csv, entity_rows, entity_fieldnames())
    write_csv(per_candidate_csv, candidate_rows, candidate_fieldnames())
    write_csv(reason_csv, reason_distribution, ("reason_type", "count", "percentage"))
    write_csv(rejected_csv, rejection_rows, rejected_candidate_fieldnames())
    write_csv(rejection_categories_csv, rejection_summary["category_distribution"], ("rejection_category", "count", "percentage"))
    write_csv(rejection_types_csv, rejection_summary["type_distribution_rows"], ("type_kind", "type_value", "count", "percentage"))
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(
        summary,
        per_entity_csv,
        per_candidate_csv,
        reason_csv,
        summary_json,
        rejected_csv,
        rejection_categories_csv,
        rejection_types_csv,
    )
    return 0


def discover_source_entities(service: Any) -> list[SourceEntity]:
    engine = service.original_pipeline
    sources: list[SourceEntity] = []
    for uri in sorted(service.filter.graph.nodes):
        canonical_uri = service.filter.graph.canonical_uri(uri)
        if canonical_uri != uri:
            continue
        profile = service.semantics.profile_for(uri)
        if not profile:
            continue
        sources.append(
            SourceEntity(
                uri=uri,
                label=profile.display_name,
                semantic_type=profile.semantic_type,
                has_embedding=bool(engine.embedding_ids_for_uri(uri)),
            )
        )
    return sources


def select_sample(sources: list[SourceEntity], sample_size: int, seed: int, use_all: bool) -> list[SourceEntity]:
    if use_all or len(sources) <= sample_size:
        return list(sources)

    rng = random.Random(seed)
    by_type: dict[str, list[SourceEntity]] = defaultdict(list)
    for source in sources:
        by_type[source.semantic_type].append(source)
    for values in by_type.values():
        rng.shuffle(values)

    sample: list[SourceEntity] = []
    type_names = sorted(by_type)
    while len(sample) < sample_size:
        progressed = False
        for type_name in type_names:
            values = by_type[type_name]
            if values:
                sample.append(values.pop())
                progressed = True
                if len(sample) >= sample_size:
                    break
        if not progressed:
            break
    rng.shuffle(sample)
    return sample


def analyze_source(source: SourceEntity, service: Any, candidate_limit: int) -> tuple[dict[str, Any], list[CandidateTrace]]:
    engine = service.original_pipeline
    main_uri = service.filter.graph.canonical_uri(source.uri)
    embedding_ids = engine.embedding_ids_for_uri(main_uri)
    if not embedding_ids:
        row = base_entity_row(source)
        return row, []

    target_embedding_ids = set(embedding_ids)
    best_by_uri: dict[str, RetrievedCandidate] = {}
    raw_seen: list[CandidateTrace] = []
    raw_hnsw_candidate_count = 0
    invalid_or_duplicate_count = 0
    invalid_uri_count = 0
    source_entity_count = 0
    duplicate_after_canonicalization_count = 0

    for source_embedding_id in embedding_ids:
        neighbors = query_similar(
            engine.artifacts.index,
            engine.artifacts.embeddings,
            source_embedding_id,
            engine._candidate_count(candidate_limit + len(target_embedding_ids)),
        )
        raw_neighbors = [
            neighbor
            for neighbor in neighbors
            if neighbor.embedding_id not in target_embedding_ids and neighbor.embedding_id in engine.artifacts.embedding_metadata
        ][:candidate_limit]
        raw_hnsw_candidate_count += len(raw_neighbors)
        sorted_neighbors = sorted(raw_neighbors, key=lambda item: item.score)

        for rank, neighbor in enumerate(sorted_neighbors, start=1):
            label, candidate_uri = engine.artifacts.embedding_metadata[neighbor.embedding_id]
            canonical_candidate_uri = service.filter.graph.canonical_uri(candidate_uri)
            passed_mapping = canonical_candidate_uri.startswith("http") and canonical_candidate_uri != main_uri
            if not passed_mapping:
                invalid_or_duplicate_count += 1
                if not canonical_candidate_uri.startswith("http"):
                    invalid_uri_count += 1
                    mapping_rejection_reason = "invalid_uri"
                else:
                    source_entity_count += 1
                    mapping_rejection_reason = "source_entity"
                raw_seen.append(
                    CandidateTrace(
                        source_uri=main_uri,
                        source_label=source.label,
                        source_semantic_type=source.semantic_type,
                        candidate_uri=canonical_candidate_uri,
                        candidate_label=str(label),
                        candidate_semantic_type="n/a",
                        source_embedding_id=source_embedding_id,
                        candidate_embedding_id=int(neighbor.embedding_id),
                        hnsw_rank=rank,
                        distance=float(neighbor.score),
                        passed_mapping_filter=False,
                        has_semantic_reason=False,
                        raw_reason_types=[],
                        visible_reason_types=[],
                        semantic_reason_count=0,
                        visible_reason_count=0,
                        evidence_path_count=0,
                        final_decision="rejected",
                        rejection_reason=mapping_rejection_reason,
                        explanation_summary="",
                        evidence_descriptions=[],
                        rdf_evidence=[],
                    )
                )
                continue
            candidate = RetrievedCandidate(
                embedding_id=int(neighbor.embedding_id),
                uri=canonical_candidate_uri,
                label=engine.label_by_uri.get(canonical_candidate_uri, str(label)),
                distance=float(neighbor.score),
                hnsw_rank=rank,
                source_embedding_id=source_embedding_id,
            )
            if canonical_candidate_uri in best_by_uri:
                invalid_or_duplicate_count += 1
                duplicate_after_canonicalization_count += 1
            best_by_uri[canonical_candidate_uri] = _merge_retrieved(best_by_uri.get(canonical_candidate_uri), candidate)

    semantic_candidate_uris = list(best_by_uri)
    reasons_by_uri, paths_by_uri = engine.recommend_with_semantic_filters(main_uri, semantic_candidate_uris)
    originals = [
        OriginalCandidate(
            embedding_id=candidate.embedding_id,
            uri=candidate.uri,
            label=candidate.label,
            distance=candidate.distance,
            hnsw_rank=candidate.hnsw_rank,
            recommendation_reason=_dedupe(list(reasons_by_uri[candidate.uri])),
            rdf_paths_by_reason={key: _dedupe(list(value)) for key, value in paths_by_uri.get(candidate.uri, {}).items()},
        )
        for candidate in best_by_uri.values()
        if reasons_by_uri.get(candidate.uri)
    ]
    ranked_originals = _rank_recommendations(originals)
    rank_order = {candidate.uri: order for order, candidate in enumerate(ranked_originals, start=1)}

    traces = [trace for trace in raw_seen if not trace.passed_mapping_filter]
    final_recommendations = 0
    semantic_reason_count = 0
    visible_reason_count = 0
    evidence_path_count = 0

    for candidate in sorted(best_by_uri.values(), key=lambda item: (rank_order.get(item.uri, 10**9), item.distance, item.hnsw_rank)):
        raw_reasons = _dedupe(list(reasons_by_uri.get(candidate.uri, [])))
        raw_paths_by_reason = {key: _dedupe(list(value)) for key, value in paths_by_uri.get(candidate.uri, {}).items()}
        raw_path_count = sum(len(paths) for paths in raw_paths_by_reason.values())
        recommendation = None
        if raw_reasons:
            original = OriginalCandidate(
                embedding_id=candidate.embedding_id,
                uri=candidate.uri,
                label=candidate.label,
                distance=candidate.distance,
                hnsw_rank=candidate.hnsw_rank,
                recommendation_reason=raw_reasons,
                rdf_paths_by_reason=raw_paths_by_reason,
            )
            recommendation = service._recommendation_for_original_candidate(main_uri, original)

        visible_reasons = visible_semantic_reason_types(recommendation)
        candidate_profile = service.semantics.profile_for(candidate.uri)
        has_semantic_reason = bool(raw_reasons)
        semantic_reason_count += len(raw_reasons)
        visible_reason_count += len(visible_reasons)
        evidence_path_count += raw_path_count
        if recommendation is not None:
            final_recommendations += 1

        traces.append(
            CandidateTrace(
                source_uri=main_uri,
                source_label=source.label,
                source_semantic_type=source.semantic_type,
                candidate_uri=candidate.uri,
                candidate_label=candidate_profile.display_name if candidate_profile else candidate.label,
                candidate_semantic_type=candidate_profile.semantic_type if candidate_profile else "n/a",
                source_embedding_id=candidate.source_embedding_id,
                candidate_embedding_id=candidate.embedding_id,
                hnsw_rank=candidate.hnsw_rank,
                distance=candidate.distance,
                passed_mapping_filter=True,
                has_semantic_reason=has_semantic_reason,
                raw_reason_types=raw_reasons,
                visible_reason_types=visible_reasons,
                semantic_reason_count=len(raw_reasons),
                visible_reason_count=len(visible_reasons),
                evidence_path_count=raw_path_count,
                final_decision="accepted" if recommendation is not None else "rejected",
                rejection_reason=rejection_reason(raw_reasons, recommendation),
                explanation_summary=recommendation.explanation.summary if recommendation and recommendation.explanation else "",
                evidence_descriptions=evidence_descriptions(recommendation),
                rdf_evidence=[path for paths in raw_paths_by_reason.values() for path in paths],
            )
        )

    entity_row = {
        "uri": main_uri,
        "label": source.label,
        "semantic_type": source.semantic_type,
        "has_embedding": True,
        "hnsw_candidate_count": raw_hnsw_candidate_count,
        "semantic_analysis_candidate_count": len(best_by_uri),
        "candidates_with_semantic_reason": sum(1 for trace in traces if trace.passed_mapping_filter and trace.has_semantic_reason),
        "final_recommendation_count": final_recommendations,
        "semantic_reason_count": semantic_reason_count,
        "visible_reason_count": visible_reason_count,
        "evidence_path_count": evidence_path_count,
        "error": "",
    }
    entity_row["mapping_filtered_or_duplicate_count"] = invalid_or_duplicate_count
    entity_row["invalid_uri_count"] = invalid_uri_count
    entity_row["source_entity_count"] = source_entity_count
    entity_row["duplicate_after_canonicalization_count"] = duplicate_after_canonicalization_count
    return entity_row, traces


def base_entity_row(source: SourceEntity) -> dict[str, Any]:
    return {
        "uri": source.uri,
        "label": source.label,
        "semantic_type": source.semantic_type,
        "has_embedding": False,
        "hnsw_candidate_count": 0,
        "semantic_analysis_candidate_count": 0,
        "candidates_with_semantic_reason": 0,
        "final_recommendation_count": 0,
        "semantic_reason_count": 0,
        "visible_reason_count": 0,
        "evidence_path_count": 0,
        "mapping_filtered_or_duplicate_count": 0,
        "invalid_uri_count": 0,
        "source_entity_count": 0,
        "duplicate_after_canonicalization_count": 0,
        "error": "",
    }


def visible_semantic_reason_types(recommendation: Recommendation | None) -> list[str]:
    if not recommendation:
        return []
    return [reason.type for reason in recommendation.reasons if reason.type not in {"embedding_similarity", "person_or_actor"}]


def evidence_descriptions(recommendation: Recommendation | None) -> list[str]:
    if not recommendation or not recommendation.explanation:
        return []
    return [evidence.description for evidence in recommendation.explanation.evidence]


def rejection_reason(raw_reasons: list[str], recommendation: Recommendation | None) -> str:
    if recommendation is not None:
        return ""
    if not raw_reasons:
        return "no_semantic_reason"
    return "final_recommendation_filter"


def build_summary(
    sample: list[SourceEntity],
    entity_rows: list[dict[str, Any]],
    traces: list[CandidateTrace],
    errors: list[dict[str, str]],
    args: argparse.Namespace,
    all_sources: list[SourceEntity],
    started: float,
) -> dict[str, Any]:
    semantic_traces = [trace for trace in traces if trace.passed_mapping_filter]
    reason_traces = [trace for trace in semantic_traces if trace.has_semantic_reason]
    final_traces = [trace for trace in semantic_traces if trace.final_decision == "accepted"]
    no_semantic = [trace for trace in semantic_traces if trace.rejection_reason == "no_semantic_reason"]
    reason_counts = [trace.semantic_reason_count for trace in reason_traces]
    visible_reason_counts = [trace.visible_reason_count for trace in final_traces]
    evidence_counts = [trace.evidence_path_count for trace in reason_traces]
    final_evidence_counts = [trace.evidence_path_count for trace in final_traces]
    denominator = len(semantic_traces)
    coverage = (len(reason_traces) / denominator * 100.0) if denominator else 0.0

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "command_hint": "python benchmarks/validate_recommendation_explanations.py --sample-size 1000",
        "methodology": {
            "pipeline_basis": "Existing OriginalPipelineEngine.recommend and RecommendationService._recommendation_for_original_candidate.",
            "hnsw_candidates": "Neighbors after source embedding removal and metadata presence check, before URI canonicalization/deduplication.",
            "semantic_analysis_candidates": "Canonical HTTP candidate URIs after deduplication by URI, exactly the URI list passed to recommend_with_semantic_filters.",
            "semantic_reason": "Any raw reason returned by recommend_with_semantic_filters, including filter-only person_or_actor because it is part of the real semantic filter stage.",
            "visible_semantic_reason": "Final recommendation reasons excluding embedding_similarity and person_or_actor.",
            "evidence_paths": "Raw rdf_paths_by_reason strings returned by the existing implementation; no synthetic path reconstruction.",
        },
        "parameters": {
            "sample_size_requested": args.sample_size,
            "used_all": bool(args.all),
            "seed": args.seed,
            "candidate_limit": args.candidate_limit,
        },
        "population": {
            "displayable_entities": len(all_sources),
            "displayable_entities_with_embedding": sum(1 for entity in all_sources if entity.has_embedding),
            "displayable_semantic_type_counts": dict(sorted(Counter(entity.semantic_type for entity in all_sources).items())),
        },
        "sample": {
            "tested_source_entities": len(sample),
            "source_entities_with_embedding": sum(1 for entity in sample if entity.has_embedding),
            "semantic_type_counts": dict(sorted(Counter(entity.semantic_type for entity in sample).items())),
        },
        "global_counts": {
            "tested_source_entities": len(sample),
            "source_entities_with_embedding": sum(1 for entity in sample if entity.has_embedding),
            "hnsw_candidates": sum(int(row.get("hnsw_candidate_count") or 0) for row in entity_rows),
            "semantic_analysis_candidates": len(semantic_traces),
            "candidates_with_semantic_reason": len(reason_traces),
            "candidates_rejected_no_semantic_basis": len(no_semantic),
            "final_recommendations": len(final_traces),
            "semantic_reasons_total": sum(trace.semantic_reason_count for trace in semantic_traces),
            "visible_semantic_reasons_total": sum(trace.visible_reason_count for trace in semantic_traces),
            "evidence_paths_total": sum(trace.evidence_path_count for trace in semantic_traces),
            "errors_or_skipped": len(errors),
        },
        "pre_semantic_filter_rejections": {
            "invalid_uri": sum(int(row.get("invalid_uri_count") or 0) for row in entity_rows),
            "source_entity": sum(int(row.get("source_entity_count") or 0) for row in entity_rows),
            "duplicate_after_canonicalization": sum(int(row.get("duplicate_after_canonicalization_count") or 0) for row in entity_rows),
            "total": sum(int(row.get("mapping_filtered_or_duplicate_count") or 0) for row in entity_rows),
        },
        "metrics": {
            "explanation_candidate_coverage_percent": round(coverage, 4),
            "coverage_numerator_candidates_with_semantic_reason": len(reason_traces),
            "coverage_denominator_semantic_analysis_candidates": denominator,
        },
        "reason_count_stats_raw_candidates_with_reason": describe_distribution(reason_counts),
        "reason_count_stats_final_visible_recommendations": describe_distribution(visible_reason_counts),
        "evidence_path_stats_candidates_with_reason": {
            **describe_distribution(evidence_counts),
            "recommendations_with_at_least_one_path": sum(1 for count in final_evidence_counts if count > 0),
            "final_recommendations_with_at_least_one_path": sum(1 for count in final_evidence_counts if count > 0),
        },
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "errors": errors,
    }


def describe_distribution(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "mean": None, "median": None, "p95": None, "max": None}
    return {
        "count": len(values),
        "min": min(values),
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
        "p95": round(percentile(values, 95), 4),
        "max": max(values),
    }


def percentile(values: list[int], percentile_value: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * percentile_value / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def build_reason_distribution(traces: list[CandidateTrace]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for trace in traces:
        if not trace.passed_mapping_filter:
            continue
        counts.update(trace.raw_reason_types)
    total = sum(counts.values())
    rows = []
    for reason_type, count in counts.most_common():
        rows.append(
            {
                "reason_type": reason_type,
                "count": count,
                "percentage": round(count / total * 100.0, 4) if total else 0.0,
            }
        )
    return rows


def select_examples(traces: list[CandidateTrace], limit: int) -> list[dict[str, Any]]:
    accepted = [trace for trace in traces if trace.final_decision == "accepted"]
    rejected_no_reason = [trace for trace in traces if trace.rejection_reason == "no_semantic_reason"]
    buckets = [
        sorted([trace for trace in accepted if trace.semantic_reason_count == 1], key=example_sort_key),
        sorted([trace for trace in accepted if trace.semantic_reason_count > 1], key=example_sort_key),
        sorted([trace for trace in accepted if trace.evidence_path_count > 1], key=example_sort_key),
        sorted(rejected_no_reason, key=example_sort_key),
        sorted(accepted, key=example_sort_key),
    ]
    selected: list[CandidateTrace] = []
    seen: set[tuple[str, str]] = set()
    bucket_index = 0
    while len(selected) < limit and any(buckets):
        bucket = buckets[bucket_index % len(buckets)]
        bucket_index += 1
        if not bucket:
            continue
        trace = bucket.pop(0)
        key = (trace.source_uri, trace.candidate_uri)
        if key in seen:
            continue
        seen.add(key)
        selected.append(trace)
    return [example_to_dict(trace) for trace in selected[:limit]]


def analyze_no_semantic_rejections(
    traces: list[CandidateTrace],
    service: Any,
    sample_size: int,
    use_all: bool,
    seed: int,
    sparse_degree_threshold: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rejected = [trace for trace in traces if trace.rejection_reason == "no_semantic_reason" and trace.passed_mapping_filter]
    accepted = [trace for trace in traces if trace.final_decision == "accepted" and trace.passed_mapping_filter]
    sampled = select_rejection_sample(rejected, sample_size, use_all, seed)
    rows = [
        classify_no_semantic_rejection(trace, service, sparse_degree_threshold)
        for trace in sampled
    ]
    category_counts = Counter(str(row["rejection_category"]) for row in rows)
    semantic_counts = Counter(str(row["candidate_semantic_type"]) for row in rows)
    rdf_counts: Counter[str] = Counter()
    for row in rows:
        for rdf_type in split_pipe(str(row["candidate_rdf_types"])):
            rdf_counts[rdf_type] += 1

    accepted_degrees = [degree_for_trace(trace, service) for trace in accepted]
    rejected_degrees = [int(row["degree"]) for row in rows]
    technical_or_ontology = category_counts["technical_entity"] + category_counts["ontology_or_schema_resource"]
    displayable_without_reason = category_counts["displayable_entity_without_supported_semantic_rule"]
    sparse = category_counts["sparse_entity"]
    analyzed_count = len(rows)

    summary = {
        "methodology": {
            "sampled": not use_all and len(rejected) > sample_size,
            "sample_size_requested": sample_size,
            "analyzed_no_semantic_reason_candidates": analyzed_count,
            "total_no_semantic_reason_candidates": len(rejected),
            "sampling_seed": seed,
            "sampling_strategy": "Stratified by source semantic type and candidate semantic type, with stable random seed.",
            "sparse_degree_threshold": sparse_degree_threshold,
            "short_path_check": (
                "Direct edge and shared one-hop graph neighbor are checked only when both endpoint neighbor sets "
                f"are at most {MAX_NEIGHBORS_FOR_SHORT_PATH}; no full BFS is performed."
            ),
            "classification_limit": (
                "Categories are mutually exclusive and assigned in this order: ontology_or_schema_resource, "
                "technical_entity, sparse_entity, graph_connected_but_rule_not_matched, "
                "displayable_entity_without_supported_semantic_rule, no_detectable_graph_context, other."
            ),
        },
        "category_distribution": distribution_rows(category_counts, analyzed_count, "rejection_category"),
        "semantic_type_distribution": distribution_rows(semantic_counts, analyzed_count, "semantic_type"),
        "rdf_type_distribution": distribution_rows(rdf_counts, sum(rdf_counts.values()), "rdf_type")[:50],
        "type_distribution_rows": (
            typed_distribution_rows("semantic_type", semantic_counts, analyzed_count)
            + typed_distribution_rows("rdf_type", rdf_counts, sum(rdf_counts.values()))[:100]
        ),
        "source_semantic_type_counts": dict(sorted(Counter(trace.source_semantic_type for trace in sampled).items())),
        "candidate_semantic_type_counts": dict(sorted(semantic_counts.items())),
        "accepted_degree_stats": describe_distribution(accepted_degrees),
        "no_semantic_reason_degree_stats": describe_distribution(rejected_degrees),
        "shares": {
            "technical_or_ontology_percent": round(technical_or_ontology / analyzed_count * 100.0, 4) if analyzed_count else 0.0,
            "displayable_without_supported_semantic_rule_percent": round(displayable_without_reason / analyzed_count * 100.0, 4) if analyzed_count else 0.0,
            "sparse_entity_percent": round(sparse / analyzed_count * 100.0, 4) if analyzed_count else 0.0,
        },
        "examples": rejection_examples(rows, 10),
    }
    return rows, summary


def select_rejection_sample(
    rejected: list[CandidateTrace],
    sample_size: int,
    use_all: bool,
    seed: int,
) -> list[CandidateTrace]:
    if use_all or len(rejected) <= sample_size:
        return list(rejected)
    if sample_size < 1:
        return []
    rng = random.Random(seed)
    strata: dict[tuple[str, str], list[CandidateTrace]] = defaultdict(list)
    for trace in rejected:
        strata[(trace.source_semantic_type, trace.candidate_semantic_type)].append(trace)

    selected: list[CandidateTrace] = []
    remainders: list[tuple[float, tuple[str, str], int]] = []
    total = len(rejected)
    for key, values in strata.items():
        rng.shuffle(values)
        exact = sample_size * len(values) / total
        take = min(len(values), int(math.floor(exact)))
        selected.extend(values[:take])
        remainders.append((exact - take, key, take))

    if len(selected) < sample_size:
        for _remainder, key, already_taken in sorted(remainders, reverse=True):
            values = strata[key]
            if already_taken < len(values):
                selected.append(values[already_taken])
                if len(selected) >= sample_size:
                    break

    if len(selected) < sample_size:
        seen = {(trace.source_uri, trace.candidate_uri, trace.hnsw_rank) for trace in selected}
        leftovers = [trace for trace in rejected if (trace.source_uri, trace.candidate_uri, trace.hnsw_rank) not in seen]
        rng.shuffle(leftovers)
        selected.extend(leftovers[: sample_size - len(selected)])

    rng.shuffle(selected)
    return selected[:sample_size]


def classify_no_semantic_rejection(trace: CandidateTrace, service: Any, sparse_degree_threshold: int) -> dict[str, Any]:
    graph = service.filter.graph
    semantics = service.semantics
    labels = service.labels
    node = graph.nodes.get(trace.candidate_uri)
    source_node = graph.nodes.get(trace.source_uri)
    rdf_types = sorted(node.rdf_types) if node else []
    displayable = bool(semantics.profile_for(trace.candidate_uri))
    technical = bool(node and semantics.is_technical_node(trace.candidate_uri))
    ontology = is_ontology_or_schema_resource(trace.candidate_uri, rdf_types)
    outgoing = len(node.outgoing) if node else 0
    incoming = len(node.incoming) if node else 0
    degree = outgoing + incoming
    direct_edge = has_direct_edge(source_node, trace.candidate_uri, graph) if source_node else False
    shared = shared_context_flags(trace.source_uri, trace.candidate_uri, graph)
    short_path = direct_edge or shared["has_shared_neighbor"]

    if ontology:
        category = "ontology_or_schema_resource"
        justification = "URI or RDF type belongs to CIDOC/RDF/RDFS/OWL schema namespace used as ontology/schema resource."
    elif technical:
        category = "technical_entity"
        justification = "SemanticResolver.is_technical_node returned True for this candidate."
    elif node is not None and degree <= sparse_degree_threshold and not short_path:
        category = "sparse_entity"
        justification = f"Candidate has degree {degree}, at or below sparse threshold {sparse_degree_threshold}, and no cheap graph context was detected."
    elif short_path:
        category = "graph_connected_but_rule_not_matched"
        justification = "A direct edge or shared one-hop graph context exists, but recommend_with_semantic_filters returned no reason."
    elif displayable:
        category = "displayable_entity_without_supported_semantic_rule"
        justification = "Candidate has a SemanticResolver profile/displayable entity, but no implemented semantic recommendation rule matched it."
    elif node is not None:
        category = "no_detectable_graph_context"
        justification = "Candidate exists in graph, but direct/shared one-hop context was not detected by the cheap diagnostic checks."
    else:
        category = "other"
        justification = "Candidate URI passed mapping filter but no graph node was found during rejection diagnostics."

    return {
        "source_uri": trace.source_uri,
        "source_label": trace.source_label,
        "source_semantic_type": trace.source_semantic_type,
        "candidate_uri": trace.candidate_uri,
        "candidate_label": trace.candidate_label,
        "candidate_semantic_type": trace.candidate_semantic_type,
        "candidate_rdf_types": "|".join(rdf_types),
        "candidate_rdf_type_labels": "|".join(labels.predicate_label(type_uri) for type_uri in rdf_types),
        "candidate_is_displayable": displayable,
        "candidate_is_technical": technical,
        "candidate_is_ontology_or_schema": ontology,
        "outgoing_edges": outgoing,
        "incoming_edges": incoming,
        "degree": degree,
        "has_direct_edge_to_source": direct_edge,
        "has_shared_neighbor": shared["has_shared_neighbor"],
        "shared_event": shared["shared_event"],
        "shared_object": shared["shared_object"],
        "shared_place": shared["shared_place"],
        "short_path_length_2_checked": shared["checked"],
        "short_path_length_2_detected": short_path,
        "rejection_category": category,
        "classification_justification": justification,
        "hnsw_rank": trace.hnsw_rank if trace.hnsw_rank is not None else "",
        "distance": f"{trace.distance:.8f}" if trace.distance is not None else "",
    }


def is_ontology_or_schema_resource(uri: str, rdf_types: list[str]) -> bool:
    return uri.startswith(SCHEMA_URI_PREFIXES)


def has_direct_edge(source_node: Any, candidate_uri: str, graph: Any) -> bool:
    for edge_index in source_node.outgoing:
        if graph.canonical_uri(graph.edges[edge_index].target) == candidate_uri:
            return True
    for edge_index in source_node.incoming:
        if graph.canonical_uri(graph.edges[edge_index].source) == candidate_uri:
            return True
    return False


def shared_context_flags(source_uri: str, candidate_uri: str, graph: Any) -> dict[str, bool]:
    source_neighbors = neighbor_uris(source_uri, graph)
    candidate_neighbors = neighbor_uris(candidate_uri, graph)
    checked = source_neighbors is not None and candidate_neighbors is not None
    flags = {
        "checked": checked,
        "has_shared_neighbor": False,
        "shared_event": False,
        "shared_object": False,
        "shared_place": False,
    }
    if not checked:
        return flags
    common = source_neighbors.intersection(candidate_neighbors)
    if not common:
        return flags
    flags["has_shared_neighbor"] = True
    for uri in common:
        node = graph.nodes.get(uri)
        rdf_types = node.rdf_types if node else set()
        if rdf_types.intersection(EVENT_TYPES):
            flags["shared_event"] = True
        if rdf_types.intersection(OBJECT_TYPES):
            flags["shared_object"] = True
        if rdf_types.intersection(PLACE_TYPES):
            flags["shared_place"] = True
        if flags["shared_event"] and flags["shared_object"] and flags["shared_place"]:
            break
    return flags


def neighbor_uris(uri: str, graph: Any) -> set[str] | None:
    node = graph.nodes.get(uri)
    if not node:
        return set()
    degree = len(node.outgoing) + len(node.incoming)
    if degree > MAX_NEIGHBORS_FOR_SHORT_PATH:
        return None
    values: set[str] = set()
    for edge_index in node.outgoing:
        edge = graph.edges[edge_index]
        if edge.target_is_uri:
            values.add(graph.canonical_uri(edge.target))
    for edge_index in node.incoming:
        edge = graph.edges[edge_index]
        values.add(graph.canonical_uri(edge.source))
    return values


def degree_for_trace(trace: CandidateTrace, service: Any) -> int:
    node = service.filter.graph.nodes.get(trace.candidate_uri)
    return len(node.outgoing) + len(node.incoming) if node else 0


def distribution_rows(counter: Counter[str], total: int, key_name: str) -> list[dict[str, Any]]:
    return [
        {
            key_name: key,
            "rejection_category" if key_name == "rejection_category" else "type_value": key,
            "count": count,
            "percentage": round(count / total * 100.0, 4) if total else 0.0,
        }
        for key, count in counter.most_common()
    ]


def typed_distribution_rows(type_kind: str, counter: Counter[str], total: int) -> list[dict[str, Any]]:
    return [
        {
            "type_kind": type_kind,
            "type_value": key,
            "count": count,
            "percentage": round(count / total * 100.0, 4) if total else 0.0,
        }
        for key, count in counter.most_common()
    ]


def split_pipe(value: str) -> list[str]:
    return [item for item in value.split("|") if item]


def rejection_examples(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(rows, key=lambda item: (str(item["rejection_category"]), int(item["degree"]), str(item["candidate_uri"]))):
        by_category[str(row["rejection_category"])].append(row)
    examples: list[dict[str, Any]] = []
    while len(examples) < limit and any(by_category.values()):
        for category in sorted(by_category):
            values = by_category[category]
            if not values:
                continue
            row = values.pop(0)
            examples.append({key: row[key] for key in rejected_candidate_fieldnames() if key in row})
            if len(examples) >= limit:
                break
    return examples


def example_sort_key(trace: CandidateTrace) -> tuple[float, str, str]:
    return (trace.distance if trace.distance is not None else 999999.0, trace.source_uri, trace.candidate_uri)


def example_to_dict(trace: CandidateTrace) -> dict[str, Any]:
    return {
        "source_uri": trace.source_uri,
        "source_label": trace.source_label,
        "source_semantic_type": trace.source_semantic_type,
        "recommended_uri": trace.candidate_uri,
        "recommended_label": trace.candidate_label,
        "reason_types": trace.raw_reason_types,
        "visible_reason_types": trace.visible_reason_types,
        "reason_description": trace.evidence_descriptions[0] if trace.evidence_descriptions else "nie dotyczy / brak w implementacji",
        "rdf_evidence": trace.rdf_evidence[:5] if trace.rdf_evidence else ["nie dotyczy / brak w implementacji"],
        "distance": trace.distance,
        "final_decision": trace.final_decision,
        "rejection_reason": trace.rejection_reason,
        "summary": trace.explanation_summary,
    }


def candidate_trace_to_row(trace: CandidateTrace) -> dict[str, Any]:
    return {
        "source_uri": trace.source_uri,
        "source_label": trace.source_label,
        "source_semantic_type": trace.source_semantic_type,
        "candidate_uri": trace.candidate_uri,
        "candidate_label": trace.candidate_label,
        "candidate_semantic_type": trace.candidate_semantic_type,
        "source_embedding_id": trace.source_embedding_id if trace.source_embedding_id is not None else "",
        "candidate_embedding_id": trace.candidate_embedding_id if trace.candidate_embedding_id is not None else "",
        "hnsw_rank": trace.hnsw_rank if trace.hnsw_rank is not None else "",
        "distance": f"{trace.distance:.8f}" if trace.distance is not None else "",
        "passed_mapping_filter": trace.passed_mapping_filter,
        "has_semantic_reason": trace.has_semantic_reason,
        "raw_reason_types": "|".join(trace.raw_reason_types),
        "visible_reason_types": "|".join(trace.visible_reason_types),
        "semantic_reason_count": trace.semantic_reason_count,
        "visible_reason_count": trace.visible_reason_count,
        "evidence_path_count": trace.evidence_path_count,
        "final_decision": trace.final_decision,
        "rejection_reason": trace.rejection_reason,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def entity_fieldnames() -> tuple[str, ...]:
    return (
        "uri",
        "label",
        "semantic_type",
        "has_embedding",
        "hnsw_candidate_count",
        "mapping_filtered_or_duplicate_count",
        "invalid_uri_count",
        "source_entity_count",
        "duplicate_after_canonicalization_count",
        "semantic_analysis_candidate_count",
        "candidates_with_semantic_reason",
        "final_recommendation_count",
        "semantic_reason_count",
        "visible_reason_count",
        "evidence_path_count",
        "error",
    )


def candidate_fieldnames() -> tuple[str, ...]:
    return (
        "source_uri",
        "source_label",
        "source_semantic_type",
        "candidate_uri",
        "candidate_label",
        "candidate_semantic_type",
        "source_embedding_id",
        "candidate_embedding_id",
        "hnsw_rank",
        "distance",
        "passed_mapping_filter",
        "has_semantic_reason",
        "raw_reason_types",
        "visible_reason_types",
        "semantic_reason_count",
        "visible_reason_count",
        "evidence_path_count",
        "final_decision",
        "rejection_reason",
    )


def rejected_candidate_fieldnames() -> tuple[str, ...]:
    return (
        "source_uri",
        "source_label",
        "source_semantic_type",
        "candidate_uri",
        "candidate_label",
        "candidate_semantic_type",
        "candidate_rdf_types",
        "candidate_rdf_type_labels",
        "candidate_is_displayable",
        "candidate_is_technical",
        "candidate_is_ontology_or_schema",
        "outgoing_edges",
        "incoming_edges",
        "degree",
        "has_direct_edge_to_source",
        "has_shared_neighbor",
        "shared_event",
        "shared_object",
        "shared_place",
        "short_path_length_2_checked",
        "short_path_length_2_detected",
        "rejection_category",
        "classification_justification",
        "hnsw_rank",
        "distance",
    )


def print_report(
    summary: dict[str, Any],
    per_entity_csv: Path,
    per_candidate_csv: Path,
    reason_csv: Path,
    summary_json: Path,
    rejected_csv: Path,
    rejection_categories_csv: Path,
    rejection_types_csv: Path,
) -> None:
    counts = summary["global_counts"]
    metrics = summary["metrics"]
    print()
    print("=== Main results ===")
    print(f"{'metric':<48} {'value':>14}")
    print(f"{'HNSW candidates':<48} {counts['hnsw_candidates']:>14}")
    print(f"{'Semantic analysis candidates':<48} {counts['semantic_analysis_candidates']:>14}")
    print(f"{'Candidates with semantic reason':<48} {counts['candidates_with_semantic_reason']:>14}")
    print(f"{'Final recommendations':<48} {counts['final_recommendations']:>14}")
    print(f"{'Explanation Candidate Coverage':<48} {metrics['explanation_candidate_coverage_percent']:>13.4f}%")

    pre_semantic = summary["pre_semantic_filter_rejections"]
    print()
    print("=== Pre-semantic filtering rejections ===")
    print(f"{'reason':<36} {'count':>10}")
    print(f"{'invalid_uri':<36} {pre_semantic['invalid_uri']:>10}")
    print(f"{'source_entity':<36} {pre_semantic['source_entity']:>10}")
    print(f"{'duplicate_after_canonicalization':<36} {pre_semantic['duplicate_after_canonicalization']:>10}")
    print(f"{'total':<36} {pre_semantic['total']:>10}")

    print()
    print("=== Reason type distribution ===")
    print(f"{'reason_type':<32} {'count':>10} {'percent':>10}")
    for row in summary["reason_type_distribution"]:
        print(f"{row['reason_type']:<32} {row['count']:>10} {row['percentage']:>9.4f}%")

    print()
    print("=== Reason count stats ===")
    print(json.dumps(summary["reason_count_stats_raw_candidates_with_reason"], ensure_ascii=False, indent=2))

    print()
    print("=== Evidence path stats ===")
    print(json.dumps(summary["evidence_path_stats_candidates_with_reason"], ensure_ascii=False, indent=2))

    rejection = summary["no_semantic_reason_analysis"]
    print()
    print("=== No semantic reason rejection categories ===")
    print(f"Analyzed no_semantic_reason candidates: {rejection['methodology']['analyzed_no_semantic_reason_candidates']} / {rejection['methodology']['total_no_semantic_reason_candidates']}")
    print(f"{'rejection_category':<48} {'count':>10} {'percent':>10}")
    for row in rejection["category_distribution"]:
        print(f"{row['rejection_category']:<48} {row['count']:>10} {row['percentage']:>9.4f}%")

    print()
    print("=== Rejected candidate degree comparison ===")
    print("accepted_final_candidates:")
    print(json.dumps(rejection["accepted_degree_stats"], ensure_ascii=False, indent=2))
    print("no_semantic_reason_analyzed:")
    print(json.dumps(rejection["no_semantic_reason_degree_stats"], ensure_ascii=False, indent=2))

    print()
    print("=== Top rejected semantic types ===")
    print(f"{'semantic_type':<32} {'count':>10} {'percent':>10}")
    for row in rejection["semantic_type_distribution"][:20]:
        print(f"{row['semantic_type']:<32} {row['count']:>10} {row['percentage']:>9.4f}%")

    print()
    print("=== Top rejected RDF types ===")
    print(f"{'rdf_type':<72} {'count':>10} {'percent':>10}")
    for row in rejection["rdf_type_distribution"][:20]:
        print(f"{row['rdf_type']:<72} {row['count']:>10} {row['percentage']:>9.4f}%")

    print()
    print("=== No semantic reason examples ===")
    for index, example in enumerate(rejection["examples"], start=1):
        print(f"{index:02d}. {example['source_label']} -> {example['candidate_label']}")
        print(f"    category: {example['rejection_category']}")
        print(f"    candidate type: {example['candidate_semantic_type']} degree: {example['degree']}")
        print(f"    technical: {example['candidate_is_technical']} ontology/schema: {example['candidate_is_ontology_or_schema']} displayable: {example['candidate_is_displayable']}")
        print(f"    reason: {example['classification_justification']}")

    print()
    print("=== Examples ===")
    for index, example in enumerate(summary["examples"], start=1):
        reasons = ", ".join(example["reason_types"]) or "nie dotyczy / brak w implementacji"
        print(f"{index:02d}. {example['source_uri']} -> {example['recommended_uri']}")
        print(f"    source: {example['source_label']}")
        print(f"    recommended: {example['recommended_label']}")
        print(f"    reasons: {reasons}")
        print(f"    description: {example['reason_description']}")
        print(f"    evidence: {example['rdf_evidence'][0] if example['rdf_evidence'] else 'nie dotyczy / brak w implementacji'}")
        print(f"    distance: {example['distance']} decision: {example['final_decision']} {example['rejection_reason']}")

    print()
    print("=== Files ===")
    print(f"Per entity CSV: {per_entity_csv}")
    print(f"Per candidate CSV: {per_candidate_csv}")
    print(f"Reason types CSV: {reason_csv}")
    print(f"No semantic rejections CSV: {rejected_csv}")
    print(f"Rejection categories CSV: {rejection_categories_csv}")
    print(f"Rejected semantic/RDF types CSV: {rejection_types_csv}")
    print(f"Summary JSON: {summary_json}")
    print(f"Errors/skipped: {counts['errors_or_skipped']}")
    print(f"Runtime seconds: {summary['runtime_seconds']}")


def format_counter(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items()))


if __name__ == "__main__":
    raise SystemExit(main())
