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
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.data.graph.constants import (  # noqa: E402
    CIDOC,
    E33_LINGUISTIC_OBJECT,
    E67_BIRTH,
    E69_DEATH,
    P100_WAS_DEATH_OF,
    P102_HAS_TITLE,
    P102I_IS_TITLE_OF,
    P108_HAS_PRODUCED,
    P11_HAD_PARTICIPANT,
    P11I_PARTICIPATED_IN,
    P128_CARRIES,
    P129I_IS_SUBJECT_OF,
    P14_CARRIED_OUT_BY,
    P14I_PERFORMED,
    P1I_IDENTIFIES,
    P2I_IS_TYPE_OF,
    P4I_IS_TIME_SPAN_OF,
    P7I_WITNESSED,
    P94_HAS_CREATED,
    P98_BROUGHT_INTO_LIFE,
)
from backend.data.semantic_catalog import (  # noqa: E402
    TECHNICAL_LOCAL_PREFIXES,
    TECHNICAL_URI_TAIL_PREFIXES,
    USER_FACING_SEMANTIC_TYPES,
)
from backend.data.text import local_class_prefix, normalize_for_search, uri_tail  # noqa: E402
from benchmarks.validate_exploration import (  # noqa: E402
    actual_visible_relations,
    build_explorer_only_context,
    classify_pattern,
    expected_visible_relations,
)


DEFAULT_SEED = 20260903
DEFAULT_MAX_SOURCES = 0
EXAMPLE_LIMIT = 10
SCHEMA_URI_PREFIXES = (
    CIDOC,
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "http://www.w3.org/2000/01/rdf-schema#",
    "http://www.w3.org/2002/07/owl#",
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Analiza pokrycia zrodlowego grafu RDF przez warstwe eksploracji UI."
    )
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "results" / "graph_ui_coverage"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--max-sources",
        type=int,
        default=DEFAULT_MAX_SOURCES,
        help="0 oznacza pelny zbior kanonicznych displayable entities; wartosc >0 losuje probke warstwowa.",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Graph/UI coverage analysis")
    print(f"Project root: {PROJECT_ROOT}")
    print("Loading graph and exploration context...")
    explorer = build_explorer_only_context()
    graph = explorer.graph
    labels = explorer.labels
    semantics = explorer.semantics

    all_displayable = [
        uri
        for uri in sorted(graph.nodes)
        if graph.canonical_uri(uri) == uri and semantics.profile_for(uri)
    ]
    sources = select_sources(all_displayable, args.max_sources, args.seed, semantics)
    full_graph = len(sources) == len(all_displayable)
    print(f"All URI resources: {len(graph.nodes)}")
    print(f"Displayable canonical entities: {len(all_displayable)}")
    print(f"Analyzed displayable entities: {len(sources)}")
    print(f"Scope: {'full graph' if full_graph else 'stratified sample, seed=' + str(args.seed)}")
    print()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    files = {
        "population": output_dir / f"graph_ui_population_summary_{timestamp}.csv",
        "rdf_types": output_dir / f"graph_ui_rdf_types_{timestamp}.csv",
        "degree_per_entity": output_dir / f"graph_ui_degree_per_entity_{timestamp}.csv",
        "degree_summary": output_dir / f"graph_ui_degree_summary_{timestamp}.csv",
        "path_aggregation": output_dir / f"graph_ui_path_aggregation_{timestamp}.csv",
        "information_coverage": output_dir / f"graph_ui_information_coverage_{timestamp}.csv",
        "hidden_categories": output_dir / f"graph_ui_hidden_categories_{timestamp}.csv",
        "canonicalization": output_dir / f"graph_ui_canonicalization_{timestamp}.csv",
        "inverse_relations": output_dir / f"graph_ui_inverse_relations_{timestamp}.csv",
        "examples": output_dir / f"graph_ui_examples_{timestamp}.csv",
        "summary_json": output_dir / f"graph_ui_validation_summary_{timestamp}.json",
    }

    print("Analyzing graph population...")
    population_rows, population_summary = analyze_population(explorer)
    rdf_type_rows = analyze_rdf_types(explorer)
    hidden_rows, hidden_summary = analyze_hidden_categories(explorer)
    canonical_rows, canonical_summary = analyze_canonicalization(explorer)

    print("Analyzing displayable entity degrees and UI relations...")
    (
        degree_rows,
        path_rows,
        examples,
        expected_by_source,
        implementation_issues,
    ) = analyze_displayable_entities(sources, explorer)
    degree_summary_rows, degree_summary = summarize_degrees(degree_rows)
    path_summary = summarize_path_aggregation(path_rows)
    inverse_rows, inverse_summary = analyze_inverse_relations(expected_by_source)

    print("Analyzing raw RDF -> semantic -> UI information categories...")
    information_rows, information_summary = analyze_information_coverage(explorer, sources, path_rows)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "command": command_hint(args),
        "methodology": {
            "scope": "full_graph" if full_graph else "stratified_sample",
            "seed": args.seed,
            "max_sources": args.max_sources,
            "analyzed_displayable_entities": len(sources),
            "displayable_canonical_entities": len(all_displayable),
            "note": (
                "Metryki porownuja strukture zrodlowego grafu RDF z warstwa prezentacji UI. "
                "Odsetek displayable URI jest raportowany jako udzial zasobow dostepnych jako "
                "samodzielne cele eksploracji, nie jako coverage calego grafu."
            ),
        },
        "population": population_summary,
        "rdf_type_top": rdf_type_rows[:30],
        "hidden_categories": hidden_summary,
        "canonicalization": canonical_summary,
        "degree_summary": degree_summary,
        "path_aggregation_summary": path_summary,
        "information_coverage": information_summary,
        "inverse_relations": inverse_summary,
        "implementation_conformance": {
            "expected_visible_relations": sum(len(rows) for rows in expected_by_source.values()),
            "issues": len(implementation_issues),
            "coverage_percent": percent(
                sum(len(rows) for rows in expected_by_source.values()) - len(implementation_issues),
                sum(len(rows) for rows in expected_by_source.values()),
            ),
            "interpretation": "Zgodnosc warstwy eksploracyjnej z zaimplementowanymi regulami.",
        },
        "examples": examples[:EXAMPLE_LIMIT],
        "files": {key: str(value) for key, value in files.items()},
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }

    write_csv(files["population"], population_rows, ("category", "count", "percentage_of_all_uri", "definition"))
    write_csv(files["rdf_types"], rdf_type_rows, rdf_type_fieldnames())
    write_csv(files["degree_per_entity"], degree_rows, degree_fieldnames())
    write_csv(files["degree_summary"], degree_summary_rows, ("metric", "min", "mean", "median", "p25", "p75", "p95", "max"))
    write_csv(files["path_aggregation"], path_rows, path_aggregation_fieldnames())
    write_csv(files["information_coverage"], information_rows, information_fieldnames())
    write_csv(files["hidden_categories"], hidden_rows, ("category", "count", "percentage_of_all_uri", "definition"))
    write_csv(files["canonicalization"], canonical_rows, canonical_fieldnames())
    write_csv(files["inverse_relations"], inverse_rows, inverse_fieldnames())
    write_csv(files["examples"], examples, example_fieldnames())
    files["summary_json"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(summary, population_rows, rdf_type_rows, degree_summary, path_summary, information_rows)
    return 0


def select_sources(uris: list[str], max_sources: int, seed: int, semantics: Any) -> list[str]:
    if max_sources <= 0 or len(uris) <= max_sources:
        return list(uris)
    rng = random.Random(seed)
    by_type: dict[str, list[str]] = defaultdict(list)
    for uri in uris:
        profile = semantics.profile_for(uri)
        by_type[profile.semantic_type if profile else "n/a"].append(uri)
    for values in by_type.values():
        rng.shuffle(values)
    sample: list[str] = []
    while len(sample) < max_sources and any(by_type.values()):
        for semantic_type in sorted(by_type):
            if by_type[semantic_type]:
                sample.append(by_type[semantic_type].pop())
                if len(sample) >= max_sources:
                    break
    rng.shuffle(sample)
    return sample


def analyze_population(explorer: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    graph = explorer.graph
    semantics = explorer.semantics
    total = len(graph.nodes)
    placeholders = [uri for uri in graph.nodes if graph.is_placeholder_reference(uri)]
    mapped_placeholders = [uri for uri in placeholders if graph.canonical_uri(uri) != uri]
    canonical = [uri for uri in graph.nodes if graph.canonical_uri(uri) == uri]
    displayable = [uri for uri in canonical if semantics.profile_for(uri)]
    technical = [uri for uri in graph.nodes if semantics.is_technical_node(uri)]
    schema = [uri for uri in graph.nodes if is_schema_resource(uri)]
    described_no_profile = [
        uri
        for uri in graph.nodes
        if graph.is_described_entity(uri)
        and not semantics.profile_for(uri)
        and not semantics.is_technical_node(uri)
        and not is_schema_resource(uri)
    ]
    rows = [
        row("all_uri_resources", total, total, "Unikalne URI obecne jako subject albo URI object w grafie wczytanym przez KnowledgeGraph."),
        row("canonical_uri_resources", len(canonical), total, "URI, dla ktorych canonical_uri(uri) == uri."),
        row("displayable_canonical_entities", len(displayable), total, "Kanoniczne URI z profile_for(uri), czyli samodzielne cele eksploracji UI."),
        row("technical_entities", len(technical), total, "Wezly, dla ktorych SemanticResolver.is_technical_node(uri) zwraca True."),
        row("ontology_or_schema_resources", len(schema), total, "URI w przestrzeniach CIDOC, RDF, RDFS lub OWL."),
        row("placeholder_references", len(placeholders), total, "URI bez opisu: bez rdf:type i bez krawedzi wychodzacych."),
        row("placeholder_references_mapped_to_canonical_uri", len(mapped_placeholders), total, "Placeholdery, dla ktorych KnowledgeGraph zbudowal mapping do kanonicznego URI."),
        row("described_nontechnical_without_displayable_profile", len(described_no_profile), total, "Opisane, nietechniczne URI bez profilu displayable."),
    ]
    type_distribution = Counter(semantics.profile_for(uri).semantic_type for uri in displayable)
    summary = {
        "all_uri_resources": total,
        "canonical_uri_resources": len(canonical),
        "displayable_canonical_entities": len(displayable),
        "technical_entities": len(technical),
        "ontology_or_schema_resources": len(schema),
        "placeholder_references": len(placeholders),
        "placeholder_references_mapped_to_canonical_uri": len(mapped_placeholders),
        "exploration_target_share_percent": percent(len(displayable), total),
        "displayable_semantic_type_distribution": dict(sorted(type_distribution.items())),
        "user_facing_semantic_types_from_code": sorted(USER_FACING_SEMANTIC_TYPES),
    }
    return rows, summary


def analyze_rdf_types(explorer: Any) -> list[dict[str, Any]]:
    graph = explorer.graph
    semantics = explorer.semantics
    labels = explorer.labels
    rows = []
    for rdf_type, instances in graph.by_type.items():
        displayable = 0
        technical = 0
        no_profile = 0
        for uri in instances:
            canonical = graph.canonical_uri(uri)
            if semantics.profile_for(canonical):
                displayable += 1
            elif semantics.is_technical_node(uri) or semantics.is_technical_node(canonical):
                technical += 1
            else:
                no_profile += 1
        count = len(instances)
        rows.append(
            {
                "rdf_type": rdf_type,
                "rdf_type_label": labels.predicate_label(rdf_type),
                "local_prefix": uri_tail(rdf_type),
                "instance_count": count,
                "displayable_count": displayable,
                "technical_or_intermediate_count": technical,
                "without_displayable_profile_count": no_profile,
                "exploration_target_share_percent": percent(displayable, count),
            }
        )
    rows.sort(key=lambda item: (-int(item["instance_count"]), str(item["rdf_type_label"]), str(item["rdf_type"])))
    return rows


def analyze_displayable_entities(
    sources: list[str],
    explorer: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, list[Any]], list[dict[str, Any]]]:
    graph = explorer.graph
    semantics = explorer.semantics
    relations = explorer.relations
    degree_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    implementation_issues: list[dict[str, Any]] = []
    expected_by_source: dict[str, list[Any]] = {}

    for index, uri in enumerate(sources, start=1):
        if index == 1 or index % 500 == 0 or index == len(sources):
            print(f"Progress: {index}/{len(sources)}")
        profile = semantics.profile_for(uri)
        node = graph.nodes[uri]
        semantic_paths = semantics.semantic_paths_for(uri, explorer.max_relationships)
        grouped_expected, _occurrences = expected_visible_relations(uri, explorer)
        expected_by_source[uri] = grouped_expected
        actual = actual_visible_relations(uri, explorer)
        actual_index = {(item["target_uri"], item["relation"]) for item in actual}
        for expected in grouped_expected:
            if (expected.target_uri, expected.relation) not in actual_index:
                implementation_issues.append(
                    {
                        "source_uri": expected.source_uri,
                        "target_uri": expected.target_uri,
                        "relation": expected.relation,
                        "pattern": expected.pattern,
                    }
                )

        ui_targets = {item["target_uri"] for item in actual}
        raw_total = len(node.outgoing) + len(node.incoming)
        degree_rows.append(
            {
                "uri": uri,
                "label": profile.display_name if profile else explorer.labels.label_for(uri),
                "semantic_type": profile.semantic_type if profile else "",
                "raw_out_degree": len(node.outgoing),
                "raw_in_degree": len(node.incoming),
                "raw_total_degree": raw_total,
                "unique_direct_rdf_neighbors": len(direct_neighbors(uri, explorer)),
                "semantic_path_count": len(semantic_paths),
                "ui_relation_count": len(actual),
                "unique_ui_target_entities": len(ui_targets),
                "ui_to_raw_degree_ratio": round(len(actual) / raw_total, 6) if raw_total else "",
            }
        )

        paths_by_relation: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
        patterns_by_relation: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
        information_by_relation: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
        for semantic_path in semantic_paths:
            target_uri = graph.canonical_uri(semantic_path.target_uri)
            target_profile = semantics.profile_for(target_uri)
            if not profile or not target_profile:
                continue
            resolved = relations.resolve(uri, target_uri, semantic_path.path, profile, target_profile, semantic_path.confidence)
            key = (resolved.category, target_uri, resolved.display_label)
            pattern = classify_pattern(uri, target_uri, semantic_path.hint, semantic_path.path, profile, target_profile, graph)
            paths_by_relation[key].append(semantic_path)
            patterns_by_relation[key][pattern] += 1
            information_by_relation[key][information_category(pattern, semantic_path.hint, semantic_path.path)] += 1

        actual_keys = {(item["category"], item["target_uri"], item["relation"]) for item in actual}
        for key, paths in paths_by_relation.items():
            if key not in actual_keys:
                continue
            category, target_uri, relation = key
            lengths = [len(path.path) for path in paths]
            target_profile = semantics.profile_for(target_uri)
            path_rows.append(
                {
                    "source_uri": uri,
                    "source_label": profile.display_name if profile else explorer.labels.label_for(uri),
                    "source_semantic_type": profile.semantic_type if profile else "",
                    "target_uri": target_uri,
                    "target_label": target_profile.display_name if target_profile else explorer.labels.label_for(target_uri),
                    "target_semantic_type": target_profile.semantic_type if target_profile else "",
                    "category": category,
                    "relation": relation,
                    "information_category": most_common_key(information_by_relation[key]),
                    "semantic_patterns": pipe_counter(patterns_by_relation[key]),
                    "semantic_path_count_aggregated": len(paths),
                    "min_path_length": min(lengths) if lengths else 0,
                    "max_path_length": max(lengths) if lengths else 0,
                    "path_length_distribution": pipe_counter(Counter(lengths)),
                    "origin_kind": origin_kind(lengths),
                    "example_path_readable": readable_path(paths[0].path, explorer) if paths else "",
                    "example_path_signature": path_signature(paths[0].path) if paths else "",
                }
            )

    examples = select_examples(degree_rows, path_rows)
    return degree_rows, path_rows, examples, expected_by_source, implementation_issues


def analyze_information_coverage(explorer: Any, sources: list[str], path_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_counts = raw_information_counts(explorer)
    semantic_counts: Counter[str] = Counter()
    visible_before_dedup: Counter[str] = Counter()
    final_counts: Counter[str] = Counter()

    source_set = set(sources)
    for uri in sources:
        profile = explorer.semantics.profile_for(uri)
        for semantic_path in explorer.semantics.semantic_paths_for(uri, explorer.max_relationships):
            target_uri = explorer.graph.canonical_uri(semantic_path.target_uri)
            target_profile = explorer.semantics.profile_for(target_uri)
            if not profile or not target_profile:
                continue
            pattern = classify_pattern(uri, target_uri, semantic_path.hint, semantic_path.path, profile, target_profile, explorer.graph)
            category = information_category(pattern, semantic_path.hint, semantic_path.path)
            semantic_counts[category] += 1
            visible_before_dedup[category] += 1

    for row_data in path_rows:
        final_counts[str(row_data.get("information_category") or "other")] += 1

    categories = sorted(set(raw_counts) | set(semantic_counts) | set(final_counts))
    rows = []
    for category in categories:
        comparable_semantic_ui = True
        raw = raw_counts[category]
        semantic = semantic_counts[category]
        final = final_counts[category]
        rows.append(
            {
                "information_category": category,
                "raw_rdf_occurrences": raw,
                "semantic_occurrences": semantic,
                "visible_before_ui_dedup": visible_before_dedup[category],
                "final_ui_relations": final,
                "raw_to_semantic_percent": "",
                "semantic_to_ui_percent": percent(final, semantic) if comparable_semantic_ui else "",
                "comparability_note": "raw RDF count is a structural proxy; compare raw counts with semantic/UI counts qualitatively, not as 1:1 retention",
            }
        )
    summary = {row["information_category"]: row for row in rows}
    return rows, summary


def raw_information_counts(explorer: Any) -> Counter[str]:
    graph = explorer.graph
    counts: Counter[str] = Counter()
    for edge in graph.edges:
        if edge.predicate in {P108_HAS_PRODUCED, P94_HAS_CREATED, P14I_PERFORMED, P14_CARRIED_OUT_BY}:
            counts["production_or_creation_creator"] += 1
        elif edge.predicate in {P102_HAS_TITLE, P102I_IS_TITLE_OF}:
            counts["title"] += 1
        elif edge.predicate == P2I_IS_TYPE_OF:
            counts["classification"] += 1
        elif edge.predicate in {P11_HAD_PARTICIPANT, P11I_PARTICIPATED_IN}:
            counts["event_participant"] += 1
        elif edge.predicate in {P128_CARRIES, P129I_IS_SUBJECT_OF}:
            counts["described_context"] += 1
        elif edge.predicate == P1I_IDENTIFIES:
            counts["appellation_identification"] += 1

    for event_uri in graph.by_type.get(E67_BIRTH, set()):
        event = graph.nodes.get(event_uri)
        if not event:
            continue
        people = [graph.edges[index] for index in event.outgoing if graph.edges[index].predicate == P98_BROUGHT_INTO_LIFE and graph.edges[index].target_is_uri]
        places = [graph.edges[index] for index in event.incoming if graph.edges[index].predicate == P7I_WITNESSED]
        times = [graph.edges[index] for index in event.incoming if graph.edges[index].predicate == P4I_IS_TIME_SPAN_OF]
        counts["birth_place"] += len(people) * len(places)
        counts["birth_time"] += len(people) * len(times)

    for event_uri in graph.by_type.get(E69_DEATH, set()):
        event = graph.nodes.get(event_uri)
        if not event:
            continue
        people = [graph.edges[index] for index in event.outgoing if graph.edges[index].predicate == P100_WAS_DEATH_OF and graph.edges[index].target_is_uri]
        places = [graph.edges[index] for index in event.incoming if graph.edges[index].predicate == P7I_WITNESSED]
        times = [graph.edges[index] for index in event.incoming if graph.edges[index].predicate == P4I_IS_TIME_SPAN_OF]
        counts["death_place"] += len(people) * len(places)
        counts["death_time"] += len(people) * len(times)
    return counts


def information_category(pattern: str, hint: str, path: Any) -> str:
    value = f"{pattern} {hint}".lower()
    if "birth_place" in value or "born in" in value or "birthplace" in value:
        return "birth_place"
    if "birth_time" in value or "birth date" in value:
        return "birth_time"
    if "death_place" in value or "died in" in value or "death place" in value:
        return "death_place"
    if "death_time" in value or "death date" in value:
        return "death_time"
    if "production" in value or "creation" in value or "created" in value:
        return "production_or_creation_creator"
    if "title" in value:
        return "title"
    if "classification" in value or "classified" in value or "classifies" in value or "type_" in value:
        return "classification"
    if "participant" in value or "participated" in value:
        return "event_participant"
    if "described" in value or "context" in value or "carries" in value:
        return "described_context"
    if "appellation" in value or "identif" in value:
        return "appellation_identification"
    return "other"


def analyze_hidden_categories(explorer: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    graph = explorer.graph
    semantics = explorer.semantics
    total = len(graph.nodes)
    counts: Counter[str] = Counter(primary_hidden_category(uri, explorer) for uri in graph.nodes)
    definitions = {
        "displayable_exploration_target": "Kanoniczny zasob z profile_for(uri); widoczny jako samodzielny cel eksploracji.",
        "placeholder_canonicalized_to_existing_uri": "Placeholder bez opisu, mapowany przez KnowledgeGraph.canonical_uri do opisanego URI.",
        "placeholder_without_canonical_mapping": "Placeholder bez opisu i bez jednoznacznego mapowania kanonicznego.",
        "ontology_or_schema_resource": "Zasob z przestrzeni CIDOC/RDF/RDFS/OWL.",
        "technical_or_intermediate_entity": "Zasob ukryty przez SemanticResolver.is_technical_node.",
        "canonical_alias_hidden": "Niekanoniczny zasob reprezentowany w UI przez inne URI.",
        "described_without_displayable_profile": "Opisany zasob, ktory nie przechodzi reguly profile_for.",
        "other": "Pozostaly zasob URI niewyrozniony przez aktualna logike.",
    }
    rows = [row(category, count, total, definitions.get(category, "")) for category, count in counts.most_common()]
    return rows, dict(counts)


def primary_hidden_category(uri: str, explorer: Any) -> str:
    graph = explorer.graph
    semantics = explorer.semantics
    if graph.canonical_uri(uri) == uri and semantics.profile_for(uri):
        return "displayable_exploration_target"
    if graph.is_placeholder_reference(uri) and graph.canonical_uri(uri) != uri:
        return "placeholder_canonicalized_to_existing_uri"
    if graph.is_placeholder_reference(uri):
        return "placeholder_without_canonical_mapping"
    if is_schema_resource(uri):
        return "ontology_or_schema_resource"
    if semantics.is_technical_node(uri):
        return "technical_or_intermediate_entity"
    if graph.canonical_uri(uri) != uri:
        return "canonical_alias_hidden"
    if graph.is_described_entity(uri) and not semantics.profile_for(uri):
        return "described_without_displayable_profile"
    return "other"


def analyze_canonicalization(explorer: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    graph = explorer.graph
    labels = explorer.labels
    by_label: dict[str, list[str]] = defaultdict(list)
    for uri in graph.nodes:
        by_label[normalize_for_search(labels.label_for(uri))].append(uri)

    rows = []
    counts = Counter()
    duplicate_relation_uris = 0
    for placeholder in sorted(uri for uri in graph.nodes if graph.is_placeholder_reference(uri)):
        label = normalize_for_search(labels.label_for(placeholder))
        candidates = [
            uri
            for uri in by_label.get(label, [])
            if uri != placeholder and graph.is_described_entity(uri)
        ]
        same_prefix = [uri for uri in candidates if local_class_prefix(uri) == local_class_prefix(placeholder)]
        canonical = graph.canonical_uri(placeholder)
        if canonical != placeholder and len(candidates) == 1:
            status = "mapped_unambiguous_same_label"
        elif canonical != placeholder and len(same_prefix) == 1:
            status = "mapped_by_same_prefix_tie_break"
        elif canonical == placeholder and len(candidates) > 1:
            status = "unmapped_potentially_ambiguous"
        elif canonical == placeholder:
            status = "unmapped_no_candidate"
        else:
            status = "mapped_other"
        counts[status] += 1
        rows.append(
            {
                "placeholder_uri": placeholder,
                "placeholder_label": labels.label_for(placeholder),
                "canonical_uri": canonical if canonical != placeholder else "",
                "canonical_label": labels.label_for(canonical) if canonical != placeholder else "",
                "candidate_count_same_label": len(candidates),
                "same_prefix_candidate_count": len(same_prefix),
                "status": status,
            }
        )

    for uri in graph.nodes:
        node = graph.nodes[uri]
        seen_targets: set[str] = set()
        for edge_index in [*node.outgoing, *node.incoming]:
            edge = graph.edges[edge_index]
            other = edge.target if edge.source == uri else edge.source
            if not edge.target_is_uri and edge.source == uri:
                continue
            canonical_other = graph.canonical_uri(other)
            if canonical_other in seen_targets and canonical_other != other:
                duplicate_relation_uris += 1
            seen_targets.add(canonical_other)

    summary = dict(counts)
    summary.update(
        {
            "placeholder_references": sum(counts.values()),
            "canonical_mappings": len(graph.canonical_uri_by_placeholder),
            "unmapped_placeholders": sum(count for key, count in counts.items() if key.startswith("unmapped")),
            "duplicate_relation_neighbor_hits_after_canonicalization": duplicate_relation_uris,
            "identity_note": "Statusy opisuja deterministyczna regule implementacji, nie zewnetrzna poprawnosc tozsamosci encji.",
        }
    )
    return rows, summary


def analyze_inverse_relations(expected_by_source: dict[str, list[Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_index = {(row.source_uri, row.target_uri, row.relation) for rows in expected_by_source.values() for row in rows}
    inverse_labels = {
        ("created", "created by"),
        ("born in", "birthplace of"),
        ("died in", "death place of"),
        ("has title", "is title of"),
        ("carries", "is carried by"),
        ("describes", "is described in"),
        ("classifies", "is classified as"),
    }
    inverse_map = {a: b for a, b in inverse_labels}
    inverse_map.update({b: a for a, b in inverse_labels})
    rows = []
    missing_by_relation: Counter[str] = Counter()
    required_by_relation: Counter[str] = Counter()
    for rels in expected_by_source.values():
        for item in rels:
            inverse = inverse_map.get(item.relation)
            if not inverse:
                continue
            required_by_relation[item.relation] += 1
            ok = (item.target_uri, item.source_uri, inverse) in expected_index
            if not ok:
                missing_by_relation[item.relation] += 1
            rows.append(
                {
                    "source_uri": item.source_uri,
                    "source_label": item.source_label,
                    "relation": item.relation,
                    "target_uri": item.target_uri,
                    "target_label": item.target_label,
                    "expected_inverse_relation": inverse,
                    "status": "full_pair" if ok else "missing_inverse",
                }
            )
    required = sum(required_by_relation.values())
    missing = sum(missing_by_relation.values())
    summary = {
        "relations_with_expected_inverse": required,
        "full_pairs": required - missing,
        "one_sided_relations": missing,
        "coverage_percent": percent(required - missing, required),
        "missing_by_relation": dict(missing_by_relation.most_common()),
        "required_by_relation": dict(required_by_relation.most_common()),
    }
    return rows, summary


def summarize_degrees(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = [int(row["raw_total_degree"]) for row in rows]
    ui = [int(row["ui_relation_count"]) for row in rows]
    ratios = [float(row["ui_to_raw_degree_ratio"]) for row in rows if row["ui_to_raw_degree_ratio"] != ""]
    summary_rows = [
        {"metric": "raw_total_degree", **distribution(raw)},
        {"metric": "ui_relation_count", **distribution(ui)},
        {"metric": "ui_to_raw_degree_ratio", **distribution(ratios)},
    ]
    summary = {
        "raw_total_degree": distribution(raw),
        "ui_relation_count": distribution(ui),
        "ui_to_raw_degree_ratio": distribution(ratios),
        "ratio_buckets": ratio_buckets(ratios),
    }
    return summary_rows, summary


def summarize_path_aggregation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = [int(row["semantic_path_count_aggregated"]) for row in rows]
    lengths: Counter[int] = Counter()
    origin: Counter[str] = Counter()
    for row in rows:
        origin[str(row["origin_kind"])] += 1
        for part in str(row["path_length_distribution"]).split("|"):
            if not part:
                continue
            key, value = part.split(":", 1)
            lengths[int(key)] += int(value)
    return {
        "ui_relations_analyzed": len(rows),
        "semantic_paths_per_ui_relation": distribution(counts),
        "path_length_distribution": dict(sorted(lengths.items())),
        "origin_kind_distribution": dict(origin.most_common()),
    }


def direct_neighbors(uri: str, explorer: Any) -> set[str]:
    graph = explorer.graph
    node = graph.nodes[uri]
    neighbors: set[str] = set()
    for edge_index in node.outgoing:
        edge = graph.edges[edge_index]
        if edge.target_is_uri:
            neighbors.add(graph.canonical_uri(edge.target))
    for edge_index in node.incoming:
        neighbors.add(graph.canonical_uri(graph.edges[edge_index].source))
    neighbors.discard(uri)
    return neighbors


def select_examples(degree_rows: list[dict[str, Any]], path_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source = defaultdict(list)
    for row in path_rows:
        by_source[row["source_uri"]].append(row)

    examples = []
    categories = [
        (
            "high_raw_low_ui_degree",
            sorted(degree_rows, key=lambda item: (-int(item["raw_total_degree"]), int(item["ui_relation_count"]), str(item["label"]))),
        ),
        (
            "similar_raw_and_ui_degree",
            sorted(
                [row for row in degree_rows if int(row["raw_total_degree"]) > 0],
                key=lambda item: (abs(int(item["raw_total_degree"]) - int(item["ui_relation_count"])), -int(item["ui_relation_count"])),
            ),
        ),
        (
            "relatively_high_ui_degree",
            sorted(degree_rows, key=lambda item: (-int(item["ui_relation_count"]), -int(item["raw_total_degree"]), str(item["label"]))),
        ),
        (
            "many_paths_aggregated_to_one_relation",
            sorted(path_rows, key=lambda item: (-int(item["semantic_path_count_aggregated"]), str(item["source_label"]))),
        ),
    ]
    seen_entities: set[str] = set()
    for category, rows in categories:
        for row_data in rows:
            source_uri = str(row_data.get("uri") or row_data.get("source_uri"))
            if source_uri in seen_entities:
                continue
            seen_entities.add(source_uri)
            relation = by_source.get(source_uri, [{}])[0]
            if "source_uri" in row_data:
                relation = row_data
            examples.append(example_row(category, row_data, relation))
            break
        if len(examples) >= EXAMPLE_LIMIT:
            break

    path_examples = sorted(path_rows, key=lambda item: (-int(item["semantic_path_count_aggregated"]), -int(item["max_path_length"])))
    for relation in path_examples:
        if len(examples) >= EXAMPLE_LIMIT:
            break
        key = f"{relation['source_uri']}->{relation['target_uri']}:{relation['relation']}"
        if key in seen_entities:
            continue
        seen_entities.add(key)
        examples.append(example_row("path_aggregation", relation, relation))
    return examples[:EXAMPLE_LIMIT]


def example_row(category: str, source_row: dict[str, Any], relation_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "example_category": category,
        "source_uri": source_row.get("uri") or relation_row.get("source_uri", ""),
        "source_label": source_row.get("label") or relation_row.get("source_label", ""),
        "source_semantic_type": source_row.get("semantic_type") or relation_row.get("source_semantic_type", ""),
        "raw_total_degree": source_row.get("raw_total_degree", ""),
        "ui_relation_count": source_row.get("ui_relation_count", ""),
        "target_uri": relation_row.get("target_uri", ""),
        "target_label": relation_row.get("target_label", ""),
        "relation": relation_row.get("relation", ""),
        "semantic_paths_aggregated": relation_row.get("semantic_path_count_aggregated", ""),
        "path_length_distribution": relation_row.get("path_length_distribution", ""),
        "example_path_readable": relation_row.get("example_path_readable", ""),
        "example_path_signature": relation_row.get("example_path_signature", ""),
    }


def distribution(values: list[int] | list[float]) -> dict[str, Any]:
    if not values:
        return {"min": None, "mean": None, "median": None, "p25": None, "p75": None, "p95": None, "max": None}
    return {
        "min": round(min(values), 6),
        "mean": round(statistics.fmean(values), 6),
        "median": round(statistics.median(values), 6),
        "p25": round(percentile(values, 25), 6),
        "p75": round(percentile(values, 75), 6),
        "p95": round(percentile(values, 95), 6),
        "max": round(max(values), 6),
    }


def percentile(values: list[int] | list[float], pct: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * pct / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    weight = rank - lower
    return float(ordered[lower]) * (1.0 - weight) + float(ordered[upper]) * weight


def ratio_buckets(values: list[float]) -> dict[str, int]:
    return {
        "0": sum(1 for value in values if value == 0),
        ">0-0.1": sum(1 for value in values if 0 < value <= 0.1),
        ">0.1-0.25": sum(1 for value in values if 0.1 < value <= 0.25),
        ">0.25-0.5": sum(1 for value in values if 0.25 < value <= 0.5),
        ">0.5-1": sum(1 for value in values if 0.5 < value <= 1),
        ">1": sum(1 for value in values if value > 1),
    }


def row(category: str, count: int, total: int, definition: str) -> dict[str, Any]:
    return {
        "category": category,
        "count": count,
        "percentage_of_all_uri": percent(count, total),
        "definition": definition,
    }


def percent(value: int | float, denominator: int | float) -> float:
    return round(float(value) / float(denominator) * 100.0, 4) if denominator else 0.0


def is_schema_resource(uri: str) -> bool:
    return uri.startswith(SCHEMA_URI_PREFIXES)


def pipe_counter(counter: Counter[Any]) -> str:
    return "|".join(f"{key}:{value}" for key, value in sorted(counter.items()))


def most_common_key(counter: Counter[str]) -> str:
    if not counter:
        return "other"
    return counter.most_common(1)[0][0]


def origin_kind(lengths: list[int]) -> str:
    if not lengths:
        return "unknown"
    if max(lengths) == 1:
        return "direct_edge"
    if max(lengths) == 2 and min(lengths) == 2:
        return "two_hop_path"
    if min(lengths) > 2:
        return "longer_path"
    return "mixed_lengths"


def readable_path(path: tuple[Any, ...], explorer: Any) -> str:
    return " -> ".join(explorer.labels.predicate_label(edge.predicate) for edge in path)


def path_signature(path: tuple[Any, ...]) -> str:
    return " || ".join(f"{edge.source} {edge.predicate} {edge.target}" for edge in path)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in rows:
            writer.writerow({field: item.get(field, "") for field in fieldnames})


def rdf_type_fieldnames() -> tuple[str, ...]:
    return (
        "rdf_type",
        "rdf_type_label",
        "local_prefix",
        "instance_count",
        "displayable_count",
        "technical_or_intermediate_count",
        "without_displayable_profile_count",
        "exploration_target_share_percent",
    )


def degree_fieldnames() -> tuple[str, ...]:
    return (
        "uri",
        "label",
        "semantic_type",
        "raw_out_degree",
        "raw_in_degree",
        "raw_total_degree",
        "unique_direct_rdf_neighbors",
        "semantic_path_count",
        "ui_relation_count",
        "unique_ui_target_entities",
        "ui_to_raw_degree_ratio",
    )


def path_aggregation_fieldnames() -> tuple[str, ...]:
    return (
        "source_uri",
        "source_label",
        "source_semantic_type",
        "target_uri",
        "target_label",
        "target_semantic_type",
        "category",
        "relation",
        "information_category",
        "semantic_patterns",
        "semantic_path_count_aggregated",
        "min_path_length",
        "max_path_length",
        "path_length_distribution",
        "origin_kind",
        "example_path_readable",
        "example_path_signature",
    )


def information_fieldnames() -> tuple[str, ...]:
    return (
        "information_category",
        "raw_rdf_occurrences",
        "semantic_occurrences",
        "visible_before_ui_dedup",
        "final_ui_relations",
        "raw_to_semantic_percent",
        "semantic_to_ui_percent",
        "comparability_note",
    )


def canonical_fieldnames() -> tuple[str, ...]:
    return (
        "placeholder_uri",
        "placeholder_label",
        "canonical_uri",
        "canonical_label",
        "candidate_count_same_label",
        "same_prefix_candidate_count",
        "status",
    )


def inverse_fieldnames() -> tuple[str, ...]:
    return (
        "source_uri",
        "source_label",
        "relation",
        "target_uri",
        "target_label",
        "expected_inverse_relation",
        "status",
    )


def example_fieldnames() -> tuple[str, ...]:
    return (
        "example_category",
        "source_uri",
        "source_label",
        "source_semantic_type",
        "raw_total_degree",
        "ui_relation_count",
        "target_uri",
        "target_label",
        "relation",
        "semantic_paths_aggregated",
        "path_length_distribution",
        "example_path_readable",
        "example_path_signature",
    )


def command_hint(args: argparse.Namespace) -> str:
    parts = ["python", "benchmarks/analyze_graph_ui_coverage.py"]
    if args.max_sources:
        parts.extend(["--max-sources", str(args.max_sources)])
    if args.seed != DEFAULT_SEED:
        parts.extend(["--seed", str(args.seed)])
    return " ".join(parts)


def print_report(
    summary: dict[str, Any],
    population_rows: list[dict[str, Any]],
    rdf_type_rows: list[dict[str, Any]],
    degree_summary: dict[str, Any],
    path_summary: dict[str, Any],
    information_rows: list[dict[str, Any]],
) -> None:
    print()
    print("=== Population ===")
    for item in population_rows:
        print(f"{item['category']:<52} {item['count']:>12} {item['percentage_of_all_uri']:>9.4f}%")

    print()
    print("=== Top RDF types ===")
    print(f"{'rdf_type_label':<40} {'instances':>10} {'display':>10} {'tech':>10} {'no_profile':>12} {'target %':>10}")
    for item in rdf_type_rows[:20]:
        print(
            f"{str(item['rdf_type_label'])[:40]:<40} {item['instance_count']:>10} "
            f"{item['displayable_count']:>10} {item['technical_or_intermediate_count']:>10} "
            f"{item['without_displayable_profile_count']:>12} {item['exploration_target_share_percent']:>9.4f}%"
        )

    print()
    print("=== Raw degree vs UI degree ===")
    print(json.dumps(degree_summary, ensure_ascii=False, indent=2))

    print()
    print("=== Path aggregation ===")
    print(json.dumps(path_summary, ensure_ascii=False, indent=2))

    print()
    print("=== Information coverage ===")
    print(f"{'category':<36} {'raw':>12} {'semantic':>12} {'visible':>12} {'ui':>12} {'raw->sem':>10} {'sem->ui':>10}")
    for item in information_rows:
        print(
            f"{item['information_category']:<36} {item['raw_rdf_occurrences']:>12} "
            f"{item['semantic_occurrences']:>12} {item['visible_before_ui_dedup']:>12} "
            f"{item['final_ui_relations']:>12} {str(item['raw_to_semantic_percent']):>10} "
            f"{str(item['semantic_to_ui_percent']):>10}"
        )

    print()
    print("=== Inverse relations ===")
    print(json.dumps(summary["inverse_relations"], ensure_ascii=False, indent=2))

    print()
    print("=== Implementation conformance ===")
    print(json.dumps(summary["implementation_conformance"], ensure_ascii=False, indent=2))

    print()
    print("=== Files ===")
    for key, value in summary["files"].items():
        print(f"{key}: {value}")
    print(f"Runtime seconds: {summary['runtime_seconds']}")


if __name__ == "__main__":
    raise SystemExit(main())
