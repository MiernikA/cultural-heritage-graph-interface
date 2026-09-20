from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.application import build_application_context  # noqa: E402
from backend.config import get_settings  # noqa: E402
from benchmarks.analyze_graph_ui_coverage import (  # noqa: E402
    analyze_canonicalization,
    analyze_displayable_entities,
    analyze_hidden_categories,
    analyze_information_coverage,
    analyze_inverse_relations,
    analyze_population,
    analyze_rdf_types,
    canonical_fieldnames,
    degree_fieldnames,
    information_fieldnames,
    inverse_fieldnames,
    path_aggregation_fieldnames,
    rdf_type_fieldnames,
    summarize_degrees,
    summarize_path_aggregation,
    write_csv,
)


def main() -> int:
    started = time.perf_counter()
    output_dir = Path(__file__).resolve().parent / "results" / "chapter_6_2_graph_app_context"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Chapter 6.2 graph/UI analysis with application context")
    context = build_application_context(get_settings())
    explorer = context.explorer
    graph = explorer.graph
    semantics = explorer.semantics
    sources = [
        uri
        for uri in sorted(graph.nodes)
        if graph.canonical_uri(uri) == uri and semantics.profile_for(uri)
    ]
    print(f"All URI resources: {len(graph.nodes)}")
    print(f"Displayable canonical entities: {len(sources)}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    files = {
        "population": output_dir / f"chapter_6_2_population_{timestamp}.csv",
        "rdf_types": output_dir / f"chapter_6_2_rdf_types_{timestamp}.csv",
        "hidden": output_dir / f"chapter_6_2_hidden_categories_{timestamp}.csv",
        "canonicalization": output_dir / f"chapter_6_2_canonicalization_{timestamp}.csv",
        "degree": output_dir / f"chapter_6_2_degree_per_entity_{timestamp}.csv",
        "path": output_dir / f"chapter_6_2_ui_relations_{timestamp}.csv",
        "information": output_dir / f"chapter_6_2_information_coverage_{timestamp}.csv",
        "inverse": output_dir / f"chapter_6_2_inverse_relations_{timestamp}.csv",
        "summary": output_dir / f"chapter_6_2_graph_summary_{timestamp}.json",
    }

    population_rows, population_summary = analyze_population(explorer)
    rdf_type_rows = analyze_rdf_types(explorer)
    hidden_rows, hidden_summary = analyze_hidden_categories(explorer)
    canonical_rows, canonical_summary = analyze_canonicalization(explorer)
    degree_rows, path_rows, _examples, expected_by_source, implementation_issues = analyze_displayable_entities(sources, explorer)
    degree_summary_rows, degree_summary = summarize_degrees(degree_rows)
    path_summary = summarize_path_aggregation(path_rows)
    information_rows, information_summary = analyze_information_coverage(explorer, sources, path_rows)
    inverse_rows, inverse_summary = analyze_inverse_relations(expected_by_source)

    relation_origin = {}
    symmetric = {"symmetric": 0, "asymmetric": 0}
    for row in path_rows:
        relation_origin[row["origin_kind"]] = relation_origin.get(row["origin_kind"], 0) + 1
        # Re-resolving would duplicate the expensive pass. Direction labels identify
        # symmetric bridge relations in the generated UI relation rows.
        if row["relation"].startswith("appears in the same") or row["relation"] in {"participated with", "shares classification with", "shares title context with", "is identified with"}:
            symmetric["symmetric"] += 1
        else:
            symmetric["asymmetric"] += 1

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "context": "backend.api.application.build_application_context(get_settings())",
        "population": population_summary,
        "hidden_categories": hidden_summary,
        "canonicalization": canonical_summary,
        "displayable_type_distribution": [
            {
                "semantic_type": key,
                "count": value,
                "percentage_of_displayable": round(value / len(sources) * 100.0, 4) if sources else 0.0,
            }
            for key, value in sorted(population_summary["displayable_semantic_type_distribution"].items())
        ],
        "degree_summary": degree_summary,
        "ui_relations": {
            "total": len(path_rows),
            "origin_kind_distribution": relation_origin,
            "symmetric_estimate_from_display_label": symmetric,
            "path_aggregation_summary": path_summary,
            "implementation_issues": len(implementation_issues),
        },
        "information_coverage": information_summary,
        "inverse_relations": inverse_summary,
        "files": {key: str(value) for key, value in files.items()},
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }

    write_csv(files["population"], population_rows, ("category", "count", "percentage_of_all_uri", "definition"))
    write_csv(files["rdf_types"], rdf_type_rows, rdf_type_fieldnames())
    write_csv(files["hidden"], hidden_rows, ("category", "count", "percentage_of_all_uri", "definition"))
    write_csv(files["canonicalization"], canonical_rows, canonical_fieldnames())
    write_csv(files["degree"], degree_rows, degree_fieldnames())
    write_csv(files["path"], path_rows, path_aggregation_fieldnames())
    write_csv(files["information"], information_rows, information_fieldnames())
    write_csv(files["inverse"], inverse_rows, inverse_fieldnames())
    files["summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
