from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.application import build_application_context
from backend.config import get_settings
from backend.data.semantic_catalog import semantic_type_for


ROOT = Path(__file__).resolve().parents[1]
RECOMMENDATION_PER_ENTITY = ROOT / "benchmarks" / "results" / "recommendations" / "recommendations_per_entity_20260912_211902.csv"
RECOMMENDATION_PER_FINAL = ROOT / "benchmarks" / "results" / "recommendations" / "recommendations_per_final_recommendation_20260912_211902.csv"
EXPLANATION_PER_CANDIDATE = ROOT / "benchmarks" / "results" / "recommendation_explanations_20260912" / "recommendation_explanations_per_candidate_20260912_212047.csv"
GRAPH_SUMMARY = ROOT / "benchmarks" / "results" / "chapter_6_2_graph_app_context" / "chapter_6_2_graph_summary_20260912_212459.json"
OUTPUT = ROOT / "benchmarks" / "results" / "chapter_6_2_summary_20260912.json"


def main() -> int:
    per_entity = read_csv(RECOMMENDATION_PER_ENTITY)
    final = read_csv(RECOMMENDATION_PER_FINAL)
    candidates = read_csv(EXPLANATION_PER_CANDIDATE)
    graph = json.loads(GRAPH_SUMMARY.read_text(encoding="utf-8"))
    context = build_application_context(get_settings())
    semantic_type_coverage = semantic_type_coverage_rows(context.explorer)

    counts = [int(row["final_recommendations"]) for row in per_entity]
    target_types = Counter(row["recommendation_semantic_type"] for row in final)
    target_uris = {row["recommendation_uri"] for row in final}
    final_total = len(final)
    probabilities = [count / final_total for count in target_types.values()]

    by_source_type: dict[str, Counter[str]] = defaultdict(Counter)
    unique_by_source_type: dict[str, set[str]] = defaultdict(set)
    for row in final:
        source_type = row["source_semantic_type"]
        by_source_type[source_type][row["recommendation_semantic_type"]] += 1
        unique_by_source_type[source_type].add(row["recommendation_uri"])

    accepted = [row for row in candidates if row["final_decision"] == "accepted"]
    with_path = [
        row for row in accepted
        if int(row["evidence_path_count"] or 0) > 0
    ]
    filter_only = [
        row for row in accepted
        if row["raw_reason_types"] == "person_or_actor"
    ]
    no_path = [
        row for row in accepted
        if int(row["evidence_path_count"] or 0) == 0
    ]

    summary = {
        "recommendation_count_stats": distribution(counts),
        "semantic_type_coverage": semantic_type_coverage,
        "unique_recommended_targets": len(target_uris),
        "potential_recommendable_entities": graph["population"]["displayable_canonical_entities"],
        "unique_target_share_of_displayable_percent": percent(len(target_uris), graph["population"]["displayable_canonical_entities"]),
        "target_type_distribution": [
            {"semantic_type": key, "count": count, "percentage": percent(count, final_total)}
            for key, count in target_types.most_common()
        ],
        "concentration": {
            "largest_type": target_types.most_common(1)[0][0],
            "largest_type_share_percent": percent(target_types.most_common(1)[0][1], final_total),
            "top3_type_share_percent": percent(sum(count for _key, count in target_types.most_common(3)), final_total),
            "semantic_type_count": len(target_types),
            "entropy_bits": round(-sum(p * math.log2(p) for p in probabilities), 6),
        },
        "by_source_type": [
            {
                "source_semantic_type": source_type,
                "final_recommendations": sum(counter.values()),
                "unique_targets": len(unique_by_source_type[source_type]),
                "target_distribution": [
                    {"target_semantic_type": key, "count": count, "percentage_within_source_type": percent(count, sum(counter.values()))}
                    for key, count in counter.most_common()
                ],
            }
            for source_type, counter in sorted(by_source_type.items())
        ],
        "explanations": {
            "final_recommendations": len(accepted),
            "with_at_least_one_explicit_rdf_evidence_path": len(with_path),
            "with_at_least_one_explicit_rdf_evidence_path_percent": percent(len(with_path), len(accepted)),
            "filter_only_person_or_actor": len(filter_only),
            "filter_only_person_or_actor_percent": percent(len(filter_only), len(accepted)),
            "without_explicit_rdf_evidence_path": len(no_path),
            "without_explicit_rdf_evidence_path_percent": percent(len(no_path), len(accepted)),
        },
    }
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def semantic_type_coverage_rows(explorer) -> list[dict[str, int | float | str]]:
    graph = explorer.graph
    semantics = explorer.semantics
    graph_counts: Counter[str] = Counter()
    displayable_counts: Counter[str] = Counter()
    for uri in graph.nodes:
        if graph.canonical_uri(uri) != uri or not graph.is_described_entity(uri):
            continue
        node = graph.nodes[uri]
        semantic_type = semantic_type_for(node.rdf_types, uri).label
        graph_counts[semantic_type] += 1
        if semantics.profile_for(uri):
            displayable_counts[semantic_type] += 1
    return [
        {
            "semantic_type": semantic_type,
            "graph_described_canonical_count": graph_counts[semantic_type],
            "displayable_count": displayable_counts[semantic_type],
            "displayable_percent": percent(displayable_counts[semantic_type], graph_counts[semantic_type]),
        }
        for semantic_type in sorted(graph_counts)
    ]


def distribution(values: list[int]) -> dict[str, float | int]:
    return {
        "min": min(values),
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
        "p5": round(percentile(values, 5), 4),
        "p25": round(percentile(values, 25), 4),
        "p75": round(percentile(values, 75), 4),
        "p95": round(percentile(values, 95), 4),
        "max": max(values),
    }


def percentile(values: list[int], pct: float) -> float:
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    weight = rank - lower
    return float(ordered[lower]) * (1.0 - weight) + float(ordered[upper]) * weight


def percent(value: int | float, denominator: int | float) -> float:
    return round(float(value) / float(denominator) * 100.0, 4) if denominator else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
