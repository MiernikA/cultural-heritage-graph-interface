from __future__ import annotations

import argparse
import csv
import json
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
from backend.data.text import is_uri
from backend.recommendations.original_pipeline import (
    OriginalCandidate,
    RetrievedCandidate,
    _dedupe,
    _merge_retrieved,
    _rank_recommendations,
)
from backend.recommendations.service import DEFAULT_CANDIDATE_LIMIT
from backend.recommendations.similarity import query_similar


DEFAULT_SAMPLE_SIZE = 1000
DEFAULT_SEED = 20260903
TOP_N_FOR_RANKING = 10
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


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Walidacja dostepnosci i przeplywu kandydatow w mechanizmie rekomendacyjnym."
    )
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--all", action="store_true", help="Analizuj wszystkie displayable entities.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "results" / "recommendations"))
    args = parser.parse_args()

    if args.sample_size < 1 and not args.all:
        raise SystemExit("--sample-size musi byc dodatnie albo uzyj --all")
    if args.candidate_limit < 1:
        raise SystemExit("--candidate-limit musi byc dodatni")

    started = time.perf_counter()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Recommendation pipeline validation")
    print(f"Project root: {PROJECT_ROOT}")
    print("Loading application context and recommendation artifacts...")
    context = build_application_context(get_settings())
    service = context.recommendations
    engine = service.original_pipeline

    all_sources = discover_sources(service)
    sources = select_sample(all_sources, args.sample_size, args.seed, args.all)
    print(f"Displayable canonical entities: {len(all_sources)}")
    print(f"Sample size: {len(sources)}")
    print(f"Sample method: {'full graph' if len(sources) == len(all_sources) else 'stratified by semantic type'}")
    print(f"Sample semantic types: {format_counter(Counter(source.semantic_type for source in sources))}")
    print()

    entity_rows: list[dict[str, Any]] = []
    recommendation_rows: list[dict[str, Any]] = []
    source_type_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for index, source in enumerate(sources, start=1):
        if index == 1 or index % 25 == 0 or index == len(sources):
            print(f"Progress: {index}/{len(sources)}")
        try:
            entity_row, rec_rows = trace_recommendation_pipeline(source, service, args.candidate_limit)
        except Exception as exc:
            errors.append({"source_uri": source.uri, "source_label": source.label, "error": f"{type(exc).__name__}: {exc}"})
            entity_row = base_error_row(source, f"{type(exc).__name__}: {exc}")
            rec_rows = []
        entity_rows.append(entity_row)
        recommendation_rows.extend(rec_rows)
        source_type_rows.append(
            {
                "source_uri": source.uri,
                "source_label": source.label,
                "source_semantic_type": source.semantic_type,
                "has_embedding": source.has_embedding,
            }
        )

    summary = build_summary(entity_rows, recommendation_rows, source_type_rows, errors, args, started)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    per_entity_csv = output_dir / f"recommendations_per_entity_{timestamp}.csv"
    per_recommendation_csv = output_dir / f"recommendations_per_final_recommendation_{timestamp}.csv"
    funnel_csv = output_dir / f"recommendations_candidate_funnel_{timestamp}.csv"
    type_distribution_csv = output_dir / f"recommendations_type_distribution_{timestamp}.csv"
    source_target_type_csv = output_dir / f"recommendations_source_to_target_types_{timestamp}.csv"
    summary_json = output_dir / f"recommendations_validation_summary_{timestamp}.json"
    summary["files"] = {
        "per_source_entity_csv": str(per_entity_csv),
        "per_final_recommendation_csv": str(per_recommendation_csv),
        "candidate_funnel_csv": str(funnel_csv),
        "type_distribution_csv": str(type_distribution_csv),
        "source_to_recommended_type_csv": str(source_target_type_csv),
        "summary_json": str(summary_json),
    }

    write_csv(per_entity_csv, entity_rows, entity_fieldnames())
    write_csv(per_recommendation_csv, recommendation_rows, recommendation_fieldnames())
    write_csv(funnel_csv, summary["candidate_funnel"], funnel_fieldnames())
    write_csv(type_distribution_csv, summary["recommendation_type_distribution"], type_distribution_fieldnames())
    write_csv(source_target_type_csv, summary["source_to_recommended_type_distribution"], source_target_fieldnames())
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(summary, per_entity_csv, per_recommendation_csv, funnel_csv, type_distribution_csv, source_target_type_csv, summary_json)
    return 0


def discover_sources(service: Any) -> list[SourceEntity]:
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

    import random

    rng = random.Random(seed)
    by_type: dict[str, list[SourceEntity]] = defaultdict(list)
    for source in sources:
        by_type[source.semantic_type].append(source)
    for values in by_type.values():
        rng.shuffle(values)

    sample: list[SourceEntity] = []
    while len(sample) < sample_size and any(by_type.values()):
        for semantic_type in sorted(by_type):
            if by_type[semantic_type]:
                sample.append(by_type[semantic_type].pop())
                if len(sample) >= sample_size:
                    break
    rng.shuffle(sample)
    return sample


def trace_recommendation_pipeline(source: SourceEntity, service: Any, candidate_limit: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    graph = service.filter.graph
    engine = service.original_pipeline
    main_uri = graph.canonical_uri(source.uri)
    embedding_ids = engine.embedding_ids_for_uri(main_uri)
    if not embedding_ids:
        row = base_entity_row(source)
        row["error"] = ""
        return row, []

    target_embedding_ids = set(embedding_ids)
    best_by_uri: dict[str, RetrievedCandidate] = {}
    raw_hnsw_returned = 0
    raw_after_self_metadata = 0
    invalid_uri_count = 0
    source_entity_count = 0
    duplicate_count = 0
    missing_metadata_count = 0
    self_embedding_count = 0

    for source_embedding_id in embedding_ids:
        neighbors = query_similar(
            engine.artifacts.index,
            engine.artifacts.embeddings,
            source_embedding_id,
            engine._candidate_count(candidate_limit + len(target_embedding_ids)),
        )
        raw_hnsw_returned += len(neighbors)
        for neighbor in neighbors:
            if neighbor.embedding_id in target_embedding_ids:
                self_embedding_count += 1
            elif neighbor.embedding_id not in engine.artifacts.embedding_metadata:
                missing_metadata_count += 1

        raw_neighbors = [
            neighbor
            for neighbor in neighbors
            if neighbor.embedding_id not in target_embedding_ids and neighbor.embedding_id in engine.artifacts.embedding_metadata
        ][:candidate_limit]
        raw_after_self_metadata += len(raw_neighbors)
        sorted_neighbors = sorted(raw_neighbors, key=lambda item: item.score)

        for rank, neighbor in enumerate(sorted_neighbors, start=1):
            label, candidate_uri = engine.artifacts.embedding_metadata[neighbor.embedding_id]
            canonical_uri = graph.canonical_uri(candidate_uri)
            if not canonical_uri.startswith("http"):
                invalid_uri_count += 1
                continue
            if canonical_uri == main_uri:
                source_entity_count += 1
                continue
            candidate = RetrievedCandidate(
                embedding_id=int(neighbor.embedding_id),
                uri=canonical_uri,
                label=engine.label_by_uri.get(canonical_uri, str(label)),
                distance=float(neighbor.score),
                hnsw_rank=rank,
                source_embedding_id=int(source_embedding_id),
            )
            if canonical_uri in best_by_uri:
                duplicate_count += 1
            best_by_uri[canonical_uri] = _merge_retrieved(best_by_uri.get(canonical_uri), candidate)

    semantic_input_uris = list(best_by_uri)
    reasons_by_uri, paths_by_uri = engine.recommend_with_semantic_filters(main_uri, semantic_input_uris)
    semantic_passed = [candidate for candidate in best_by_uri.values() if reasons_by_uri.get(candidate.uri)]
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
        for candidate in semantic_passed
    ]
    ranked_originals = _rank_recommendations(originals)

    dedup_distance_order = {
        candidate.uri: index
        for index, candidate in enumerate(sorted(best_by_uri.values(), key=lambda item: (item.distance, item.hnsw_rank, item.label.casefold())), start=1)
    }
    semantic_distance_order = {
        candidate.uri: index
        for index, candidate in enumerate(sorted(originals, key=lambda item: (item.distance, item.hnsw_rank, item.label.casefold())), start=1)
    }

    recommendation_rows: list[dict[str, Any]] = []
    final_recommendations = []
    final_filter_rejections = Counter()
    ranking_deltas: list[int] = []
    moved_count = 0
    top_n_from_beyond = 0

    for final_rank, original in enumerate(ranked_originals, start=1):
        recommendation = service._recommendation_for_original_candidate(main_uri, original)
        if recommendation is None:
            final_filter_rejections[classify_final_filter_rejection(original.uri, main_uri, service)] += 1
            continue
        raw_rank = dedup_distance_order.get(original.uri)
        semantic_raw_rank = semantic_distance_order.get(original.uri)
        delta = (semantic_raw_rank or final_rank) - final_rank
        ranking_deltas.append(abs(delta))
        if semantic_raw_rank != final_rank:
            moved_count += 1
        if final_rank <= TOP_N_FOR_RANKING and semantic_raw_rank and semantic_raw_rank > TOP_N_FOR_RANKING:
            top_n_from_beyond += 1

        evidence_path_count = sum(len(paths) for paths in original.rdf_paths_by_reason.values())
        non_filter_reasons = [reason for reason in original.recommendation_reason if reason != "person_or_actor"]
        final_recommendations.append(recommendation)
        recommendation_rows.append(
            {
                "source_uri": main_uri,
                "source_label": source.label,
                "source_semantic_type": source.semantic_type,
                "recommendation_uri": recommendation.uri,
                "recommendation_label": recommendation.label,
                "recommendation_semantic_type": recommendation.semantic_type,
                "final_rank": final_rank,
                "hnsw_rank": original.hnsw_rank,
                "dedup_distance_rank": raw_rank,
                "semantic_distance_rank": semantic_raw_rank,
                "rank_delta_from_semantic_distance": delta,
                "distance": f"{original.distance:.8f}",
                "score": recommendation.score,
                "semantic_reason_count": len(original.recommendation_reason),
                "non_filter_reason_count": len(non_filter_reasons),
                "semantic_reasons": "|".join(original.recommendation_reason),
                "evidence_path_count": evidence_path_count,
                "reason_tags": "|".join(recommendation.reason_tags),
            }
        )

    final_types = Counter(recommendation.semantic_type for recommendation in final_recommendations)
    row = {
        "uri": main_uri,
        "label": source.label,
        "semantic_type": source.semantic_type,
        "has_embedding": True,
        "embedding_id_count_used": len(embedding_ids),
        "raw_hnsw_returned": raw_hnsw_returned,
        "raw_hnsw_candidates": raw_after_self_metadata,
        "after_mapping_valid_uri": raw_after_self_metadata - invalid_uri_count,
        "after_canonicalization_non_source": raw_after_self_metadata - invalid_uri_count - source_entity_count,
        "after_deduplication": len(best_by_uri),
        "semantic_filtering_input": len(semantic_input_uris),
        "semantic_filtering_passed": len(semantic_passed),
        "no_semantic_reason": len(semantic_input_uris) - len(semantic_passed),
        "final_recommendations": len(final_recommendations),
        "user_available_recommendations": len(final_recommendations),
        "final_recommendation_types": "|".join(f"{key}:{value}" for key, value in sorted(final_types.items())),
        "self_embedding_removed": self_embedding_count,
        "missing_metadata_removed": missing_metadata_count,
        "invalid_uri_removed": invalid_uri_count,
        "source_entity_removed": source_entity_count,
        "duplicate_after_canonicalization_removed": duplicate_count,
        "final_filter_rejected": sum(final_filter_rejections.values()),
        "final_filter_rejection_reasons": "|".join(f"{key}:{value}" for key, value in sorted(final_filter_rejections.items())),
        "ranking_moved_candidates": moved_count,
        "ranking_avg_abs_position_delta": round(statistics.mean(ranking_deltas), 4) if ranking_deltas else 0.0,
        "ranking_top10_from_beyond_hnsw_top10": top_n_from_beyond,
        "error": "",
    }
    return row, recommendation_rows


def classify_final_filter_rejection(uri: str, current_uri: str, service: Any) -> str:
    graph = service.filter.graph
    canonical_uri = graph.canonical_uri(uri)
    if canonical_uri == current_uri:
        return "source_entity"
    if not is_uri(canonical_uri):
        return "invalid_uri"
    if canonical_uri.startswith(SCHEMA_URI_PREFIXES):
        return "ontology_or_schema_resource"
    node = graph.nodes.get(canonical_uri)
    if not node:
        return "missing_graph_node"
    if service.semantics.is_technical_node(canonical_uri):
        return "technical_entity"
    profile = service.semantics.profile_for(canonical_uri)
    if not profile:
        return "no_displayable_profile"
    if not profile.display_name or profile.display_name == canonical_uri:
        return "missing_display_label"
    return "other"


def base_entity_row(source: SourceEntity) -> dict[str, Any]:
    return {
        "uri": source.uri,
        "label": source.label,
        "semantic_type": source.semantic_type,
        "has_embedding": False,
        "embedding_id_count_used": 0,
        "raw_hnsw_returned": 0,
        "raw_hnsw_candidates": 0,
        "after_mapping_valid_uri": 0,
        "after_canonicalization_non_source": 0,
        "after_deduplication": 0,
        "semantic_filtering_input": 0,
        "semantic_filtering_passed": 0,
        "no_semantic_reason": 0,
        "final_recommendations": 0,
        "user_available_recommendations": 0,
        "final_recommendation_types": "",
        "self_embedding_removed": 0,
        "missing_metadata_removed": 0,
        "invalid_uri_removed": 0,
        "source_entity_removed": 0,
        "duplicate_after_canonicalization_removed": 0,
        "final_filter_rejected": 0,
        "final_filter_rejection_reasons": "",
        "ranking_moved_candidates": 0,
        "ranking_avg_abs_position_delta": 0.0,
        "ranking_top10_from_beyond_hnsw_top10": 0,
        "error": "",
    }


def base_error_row(source: SourceEntity, error: str) -> dict[str, Any]:
    row = base_entity_row(source)
    row["has_embedding"] = source.has_embedding
    row["error"] = error
    return row


def build_summary(
    entity_rows: list[dict[str, Any]],
    recommendation_rows: list[dict[str, Any]],
    source_type_rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    args: Any,
    started: float,
) -> dict[str, Any]:
    total = len(entity_rows)
    with_embedding = sum(1 for row in entity_rows if row["has_embedding"])
    without_embedding = total - with_embedding
    with_final = sum(1 for row in entity_rows if int(row["final_recommendations"]) > 0)
    with_embedding_no_final = sum(1 for row in entity_rows if row["has_embedding"] and int(row["final_recommendations"]) == 0)
    counts = [int(row["final_recommendations"]) for row in entity_rows]

    funnel_counts = {
        "raw_hnsw_returned": sum_int(entity_rows, "raw_hnsw_returned"),
        "raw_hnsw_candidates": sum_int(entity_rows, "raw_hnsw_candidates"),
        "after_mapping_valid_uri": sum_int(entity_rows, "after_mapping_valid_uri"),
        "after_canonicalization_non_source": sum_int(entity_rows, "after_canonicalization_non_source"),
        "after_deduplication": sum_int(entity_rows, "after_deduplication"),
        "semantic_filtering_input": sum_int(entity_rows, "semantic_filtering_input"),
        "semantic_filtering_passed": sum_int(entity_rows, "semantic_filtering_passed"),
        "after_recommendation_filter": sum_int(entity_rows, "final_recommendations"),
        "final_recommendations": sum_int(entity_rows, "final_recommendations"),
    }
    candidate_funnel = funnel_rows(funnel_counts)

    type_counter = Counter(row["recommendation_semantic_type"] for row in recommendation_rows)
    source_target_counter = Counter((row["source_semantic_type"], row["recommendation_semantic_type"]) for row in recommendation_rows)
    technical_rejections = {
        "self_embedding_removed": sum_int(entity_rows, "self_embedding_removed"),
        "missing_metadata_removed": sum_int(entity_rows, "missing_metadata_removed"),
        "invalid_uri_removed": sum_int(entity_rows, "invalid_uri_removed"),
        "source_entity_removed": sum_int(entity_rows, "source_entity_removed"),
        "duplicate_after_canonicalization_removed": sum_int(entity_rows, "duplicate_after_canonicalization_removed"),
        "final_filter_rejected": sum_int(entity_rows, "final_filter_rejected"),
        "final_filter_rejection_reasons": aggregate_reason_pairs(entity_rows, "final_filter_rejection_reasons"),
    }
    semantic_filtering = {
        "candidates_admitted": funnel_counts["semantic_filtering_input"],
        "candidates_with_semantic_reason": funnel_counts["semantic_filtering_passed"],
        "no_semantic_reason": sum_int(entity_rows, "no_semantic_reason"),
        "semantic_pass_rate_percent": percent(funnel_counts["semantic_filtering_passed"], funnel_counts["semantic_filtering_input"]),
    }
    ranking = {
        "final_recommendations_compared": len(recommendation_rows),
        "candidates_changed_position": sum(1 for row in recommendation_rows if int(row["rank_delta_from_semantic_distance"]) != 0),
        "avg_abs_position_delta_per_entity": round(statistics.mean([float(row["ranking_avg_abs_position_delta"]) for row in entity_rows if row["has_embedding"]]), 4) if with_embedding else 0.0,
        "top10_from_beyond_semantic_distance_top10": sum_int(entity_rows, "ranking_top10_from_beyond_hnsw_top10"),
        "ranking_rule": (
            "OriginalPipelineEngine najpierw zachowuje 2 najblizsze kandydaty embeddingowe, "
            "potem dobiera 2 kandydaty z najwieksza liczba powodow semantycznych i evidence paths, "
            "a reszte uklada wedlug dystansu HNSW."
        ),
    }

    return {
        "methodology": {
            "sample_size": total,
            "sample_seed": args.seed,
            "sample_mode": "full_graph" if args.all else "stratified_sample",
            "candidate_limit": args.candidate_limit,
            "ground_truth_note": "Nie liczono Precision@K ani Recall@K; metryki opisuja dostepnosc i przeplyw pipeline'u.",
            "pipeline_order": [
                "displayable canonical source",
                "embedding_ids_for_uri returns last canonical embedding id",
                "HNSW knn_query",
                "remove source embedding and missing metadata, slice candidate_limit",
                "canonicalize URI/ref",
                "remove invalid URI and source entity",
                "deduplicate by canonical URI using lower distance",
                "recommend_with_semantic_filters",
                "_rank_recommendations",
                "RecommendationFilter.build_recommendation_for_uri",
            ],
            "source_sample_distribution": type_distribution_from_source_rows(source_type_rows),
        },
        "availability": {
            "eligible_source_entities": total,
            "sources_with_embedding": with_embedding,
            "sources_without_embedding": without_embedding,
            "sources_with_final_recommendation": with_final,
            "sources_with_embedding_but_no_final_recommendation": with_embedding_no_final,
            "recommendation_coverage_percent": percent(with_final, total),
            "embedding_coverage_percent": percent(with_embedding, total),
            "without_embedding_percent": percent(without_embedding, total),
            "with_embedding_but_no_final_percent": percent(with_embedding_no_final, total),
        },
        "candidate_funnel": candidate_funnel,
        "recommendations_per_entity": {
            "min": min(counts) if counts else 0,
            "mean": round(statistics.mean(counts), 4) if counts else 0.0,
            "median": round(statistics.median(counts), 4) if counts else 0.0,
            "p95": percentile(counts, 95),
            "max": max(counts) if counts else 0,
            "buckets": recommendation_count_buckets(counts),
        },
        "recommendation_type_distribution": distribution_rows(type_counter, len(recommendation_rows), "semantic_type"),
        "source_to_recommended_type_distribution": source_target_rows(source_target_counter, len(recommendation_rows)),
        "technical_filtering": technical_rejections,
        "semantic_filtering": semantic_filtering,
        "ranking": ranking,
        "examples": select_examples(entity_rows, recommendation_rows),
        "errors": {
            "count": len(errors),
            "examples": errors[:10],
        },
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }


def funnel_rows(counts: dict[str, int]) -> list[dict[str, Any]]:
    rows = []
    previous = None
    raw = counts.get("raw_hnsw_returned", 0)
    for stage, count in counts.items():
        rows.append(
            {
                "stage": stage,
                "count": count,
                "percent_of_raw_hnsw_returned": percent(count, raw),
                "percent_of_previous_stage": percent(count, previous) if previous is not None else 100.0,
            }
        )
        previous = count
    return rows


def select_examples(entity_rows: list[dict[str, Any]], recommendation_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in recommendation_rows:
        by_source[row["source_uri"]].append(row)

    selected: list[dict[str, Any]] = []
    categories = [
        ("many_recommendations", lambda row: int(row["final_recommendations"]) > 10),
        ("few_recommendations", lambda row: 1 <= int(row["final_recommendations"]) <= 2),
        ("no_recommendations", lambda row: int(row["final_recommendations"]) == 0),
        ("semantic_filter_strongly_reduces", lambda row: int(row["semantic_filtering_input"]) >= 50 and int(row["semantic_filtering_passed"]) <= max(1, int(row["semantic_filtering_input"]) // 10)),
        ("semantic_ranking_changes_order", lambda row: int(row["ranking_moved_candidates"]) > 0),
    ]
    seen = set()
    for category, predicate in categories:
        matches = [row for row in entity_rows if predicate(row) and row["uri"] not in seen]
        if not matches:
            continue
        row = sorted(matches, key=lambda item: (-int(item["final_recommendations"]), item["label"]))[0]
        seen.add(row["uri"])
        selected.append(
            {
                "category": category,
                "source_uri": row["uri"],
                "source_label": row["label"],
                "source_semantic_type": row["semantic_type"],
                "raw_hnsw_candidates": row["raw_hnsw_candidates"],
                "semantic_filtering_input": row["semantic_filtering_input"],
                "semantic_filtering_passed": row["semantic_filtering_passed"],
                "final_recommendations": row["final_recommendations"],
                "top_recommendations": [
                    {
                        "rank": rec["final_rank"],
                        "label": rec["recommendation_label"],
                        "uri": rec["recommendation_uri"],
                        "semantic_type": rec["recommendation_semantic_type"],
                        "distance": rec["distance"],
                        "hnsw_rank": rec["hnsw_rank"],
                        "semantic_reasons": rec["semantic_reasons"],
                    }
                    for rec in sorted(by_source.get(row["uri"], []), key=lambda item: int(item["final_rank"]))[:5]
                ],
            }
        )
    return selected


def type_distribution_from_source_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter = Counter(row["source_semantic_type"] for row in rows)
    return distribution_rows(counter, len(rows), "source_semantic_type")


def distribution_rows(counter: Counter[str], total: int, key_name: str) -> list[dict[str, Any]]:
    return [
        {key_name: key, "count": count, "percentage": percent(count, total)}
        for key, count in counter.most_common()
    ]


def source_target_rows(counter: Counter[tuple[str, str]], total: int) -> list[dict[str, Any]]:
    return [
        {
            "source_semantic_type": source_type,
            "recommendation_semantic_type": target_type,
            "count": count,
            "percentage": percent(count, total),
        }
        for (source_type, target_type), count in counter.most_common()
    ]


def recommendation_count_buckets(counts: list[int]) -> dict[str, int]:
    return {
        "0": sum(1 for count in counts if count == 0),
        "1": sum(1 for count in counts if count == 1),
        "2-5": sum(1 for count in counts if 2 <= count <= 5),
        "6-10": sum(1 for count in counts if 6 <= count <= 10),
        ">10": sum(1 for count in counts if count > 10),
    }


def aggregate_reason_pairs(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        for part in str(row.get(field, "")).split("|"):
            if not part or ":" not in part:
                continue
            key, value = part.rsplit(":", 1)
            try:
                counter[key] += int(value)
            except ValueError:
                continue
    return dict(counter)


def percentile(values: list[int], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((pct / 100) * (len(ordered) - 1)))
    return float(ordered[index])


def sum_int(rows: list[dict[str, Any]], field: str) -> int:
    return sum(int(row.get(field, 0) or 0) for row in rows)


def percent(value: int | float, denominator: int | float) -> float:
    return round((float(value) / float(denominator) * 100.0), 4) if denominator else 0.0


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
        "embedding_id_count_used",
        "raw_hnsw_returned",
        "raw_hnsw_candidates",
        "after_mapping_valid_uri",
        "after_canonicalization_non_source",
        "after_deduplication",
        "semantic_filtering_input",
        "semantic_filtering_passed",
        "no_semantic_reason",
        "final_recommendations",
        "user_available_recommendations",
        "final_recommendation_types",
        "self_embedding_removed",
        "missing_metadata_removed",
        "invalid_uri_removed",
        "source_entity_removed",
        "duplicate_after_canonicalization_removed",
        "final_filter_rejected",
        "final_filter_rejection_reasons",
        "ranking_moved_candidates",
        "ranking_avg_abs_position_delta",
        "ranking_top10_from_beyond_hnsw_top10",
        "error",
    )


def recommendation_fieldnames() -> tuple[str, ...]:
    return (
        "source_uri",
        "source_label",
        "source_semantic_type",
        "recommendation_uri",
        "recommendation_label",
        "recommendation_semantic_type",
        "final_rank",
        "hnsw_rank",
        "dedup_distance_rank",
        "semantic_distance_rank",
        "rank_delta_from_semantic_distance",
        "distance",
        "score",
        "semantic_reason_count",
        "non_filter_reason_count",
        "semantic_reasons",
        "evidence_path_count",
        "reason_tags",
    )


def funnel_fieldnames() -> tuple[str, ...]:
    return ("stage", "count", "percent_of_raw_hnsw_returned", "percent_of_previous_stage")


def type_distribution_fieldnames() -> tuple[str, ...]:
    return ("semantic_type", "count", "percentage")


def source_target_fieldnames() -> tuple[str, ...]:
    return ("source_semantic_type", "recommendation_semantic_type", "count", "percentage")


def print_report(
    summary: dict[str, Any],
    per_entity_csv: Path,
    per_recommendation_csv: Path,
    funnel_csv: Path,
    type_distribution_csv: Path,
    source_target_type_csv: Path,
    summary_json: Path,
) -> None:
    availability = summary["availability"]
    print()
    print("=== Recommendation availability ===")
    print(f"Eligible sources: {availability['eligible_source_entities']}")
    print(f"Sources with embedding: {availability['sources_with_embedding']} ({availability['embedding_coverage_percent']:.4f}%)")
    print(f"Sources without embedding: {availability['sources_without_embedding']} ({availability['without_embedding_percent']:.4f}%)")
    print(f"Sources with final recommendation: {availability['sources_with_final_recommendation']}")
    print(f"Recommendation Coverage: {availability['recommendation_coverage_percent']:.4f}%")
    print(f"With embedding but no final recommendation: {availability['sources_with_embedding_but_no_final_recommendation']} ({availability['with_embedding_but_no_final_percent']:.4f}%)")

    print()
    print("=== Candidate funnel ===")
    print(f"{'stage':<42} {'count':>12} {'raw %':>10} {'prev %':>10}")
    for row in summary["candidate_funnel"]:
        print(f"{row['stage']:<42} {row['count']:>12} {row['percent_of_raw_hnsw_returned']:>9.4f}% {row['percent_of_previous_stage']:>9.4f}%")

    print()
    print("=== Recommendations per entity ===")
    print(json.dumps(summary["recommendations_per_entity"], ensure_ascii=False, indent=2))

    print()
    print("=== Recommendation semantic types ===")
    print(f"{'semantic_type':<28} {'count':>10} {'percent':>10}")
    for row in summary["recommendation_type_distribution"]:
        print(f"{row['semantic_type']:<28} {row['count']:>10} {row['percentage']:>9.4f}%")

    print()
    print("=== Technical/filtering impact ===")
    print(json.dumps(summary["technical_filtering"], ensure_ascii=False, indent=2))

    print()
    print("=== Semantic filtering ===")
    print(json.dumps(summary["semantic_filtering"], ensure_ascii=False, indent=2))

    print()
    print("=== Ranking ===")
    print(json.dumps(summary["ranking"], ensure_ascii=False, indent=2))

    print()
    print("=== Examples ===")
    for index, example in enumerate(summary["examples"], start=1):
        print(f"{index:02d}. {example['category']}: {example['source_label']} ({example['source_semantic_type']})")
        print(f"    HNSW={example['raw_hnsw_candidates']} semantic_input={example['semantic_filtering_input']} semantic_passed={example['semantic_filtering_passed']} final={example['final_recommendations']}")
        for rec in example["top_recommendations"]:
            print(f"    #{rec['rank']} {rec['label']} [{rec['semantic_type']}] distance={rec['distance']} hnsw_rank={rec['hnsw_rank']}")

    print()
    print("=== Files ===")
    print(f"Per source entity CSV: {per_entity_csv}")
    print(f"Per final recommendation CSV: {per_recommendation_csv}")
    print(f"Candidate funnel CSV: {funnel_csv}")
    print(f"Type distribution CSV: {type_distribution_csv}")
    print(f"Source-to-target type CSV: {source_target_type_csv}")
    print(f"Summary JSON: {summary_json}")
    print(f"Errors: {summary['errors']['count']}")
    print(f"Runtime seconds: {summary['runtime_seconds']}")


def format_counter(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items()))


if __name__ == "__main__":
    raise SystemExit(main())
