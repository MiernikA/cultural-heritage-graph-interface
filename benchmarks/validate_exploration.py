from __future__ import annotations

import argparse
import csv
import json
import random
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

from backend.config import get_settings
from backend.data.graph.constants import (
    E12_PRODUCTION,
    E33_LINGUISTIC_OBJECT,
    E35_TITLE,
    E41_APPELLATION,
    E65_CREATION,
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
    P14I_PERFORMED,
    P14_CARRIED_OUT_BY,
    P1I_IDENTIFIES,
    P2I_IS_TYPE_OF,
    P4I_IS_TIME_SPAN_OF,
    P7I_WITNESSED,
    P94_HAS_CREATED,
    P98_BROUGHT_INTO_LIFE,
    TECHNICAL_TYPES,
)
from backend.data.semantic_catalog import TECHNICAL_LOCAL_PREFIXES, TECHNICAL_URI_TAIL_PREFIXES
from backend.data.graph.knowledge_graph import load_graph_from_tsv
from backend.data.label_resolver import LabelResolver
from backend.data.ontology.loader import load_ontology, ontology_label_triples
from backend.data.semantic_resolver import SemanticResolver
from backend.data.text import local_class_prefix, normalize_for_search, uri_tail
from backend.exploration.relation_resolver import RelationResolver
from backend.exploration.service import ExplorerService


DEFAULT_SEED = 20260903
DEFAULT_MAX_SOURCES = 0
EXAMPLE_LIMIT = 10
LEAK_EXAMPLE_LIMIT = 50


@dataclass(frozen=True, slots=True)
class ExpectedRelation:
    source_uri: str
    source_label: str
    source_type: str
    target_uri: str
    target_label: str
    target_type: str
    pattern: str
    relation: str
    direction: str
    category: str
    confidence: int
    path_signature: str
    path_predicates: str
    path_readable: str


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Walidacja eksploracji grafu: RDF/CIDOC -> relacje semantyczne UI."
    )
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "results" / "exploration"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--max-sources",
        type=int,
        default=DEFAULT_MAX_SOURCES,
        help="0 oznacza pelny zbior encji displayable; wartosc >0 losuje probke warstwowa.",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Exploration validation")
    print(f"Project root: {PROJECT_ROOT}")
    print("Loading exploration context...")
    explorer = build_explorer_only_context()
    graph = explorer.graph
    labels = explorer.labels
    semantics = explorer.semantics
    relations = explorer.relations

    all_sources = [
        uri
        for uri in sorted(graph.nodes)
        if graph.canonical_uri(uri) == uri and semantics.profile_for(uri)
    ]
    sources = select_sources(all_sources, args.max_sources, args.seed, semantics)
    full_graph = len(sources) == len(all_sources)

    print(f"Displayable canonical entities: {len(all_sources)}")
    print(f"Validated source entities: {len(sources)}")
    print(f"Method: {'full graph' if full_graph else 'stratified sample, fixed seed=' + str(args.seed)}")
    print()

    source_occurrences = Counter()
    expected_by_source: dict[str, list[ExpectedRelation]] = {}
    expected_rows: list[dict[str, Any]] = []
    actual_rows: list[dict[str, Any]] = []
    issue_rows: list[dict[str, Any]] = []
    correct_examples: list[dict[str, Any]] = []

    for index, uri in enumerate(sources, start=1):
        if index == 1 or index % 500 == 0 or index == len(sources):
            print(f"Progress: {index}/{len(sources)}")

        grouped_expected, occurrence_counts = expected_visible_relations(uri, explorer)
        source_occurrences.update(occurrence_counts)
        expected_by_source[uri] = grouped_expected
        expected_rows.extend(expected_relation_to_row(item) for item in grouped_expected)

        actual = actual_visible_relations(uri, explorer)
        actual_rows.extend(actual_relation_to_row(uri, item) for item in actual)
        actual_index = {(item["target_uri"], item["relation"]) for item in actual}

        for expected in grouped_expected:
            key = (expected.target_uri, expected.relation)
            ok = key in actual_index
            row = expected_relation_to_row(expected)
            row["status"] = "correct" if ok else "missing_or_changed"
            if ok and len(correct_examples) < EXAMPLE_LIMIT:
                correct_examples.append(row)
            if not ok:
                issue_rows.append(row)

    raw_requested_counts = scan_requested_raw_patterns(explorer)
    summary_rows = build_relation_summary(expected_rows, issue_rows, source_occurrences, raw_requested_counts)
    inverse_summary, inverse_issues = validate_inverse_relations(expected_by_source, explorer)
    issue_rows.extend(inverse_issues)
    technical_summary, technical_rows = validate_technical_filtering(sources, expected_by_source, explorer)
    canonical_summary, canonical_rows = validate_canonicalization(graph, labels, semantics)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    per_case_csv = output_dir / f"exploration_cases_{timestamp}.csv"
    summary_csv = output_dir / f"exploration_summary_by_relation_{timestamp}.csv"
    issues_csv = output_dir / f"exploration_issues_{timestamp}.csv"
    actual_csv = output_dir / f"exploration_actual_relationships_{timestamp}.csv"
    technical_csv = output_dir / f"exploration_technical_filtering_{timestamp}.csv"
    canonical_csv = output_dir / f"exploration_canonicalization_{timestamp}.csv"
    summary_json = output_dir / f"exploration_validation_summary_{timestamp}.json"

    write_csv(per_case_csv, expected_rows, case_fieldnames())
    write_csv(summary_csv, summary_rows, summary_fieldnames())
    write_csv(issues_csv, issue_rows, issue_fieldnames())
    write_csv(actual_csv, actual_rows, actual_fieldnames())
    write_csv(technical_csv, technical_rows, technical_fieldnames())
    write_csv(canonical_csv, canonical_rows, canonical_fieldnames())

    summary = {
        "methodology": {
            "expected_relation_definition": (
                "Relacja oczekiwana to relacja po SemanticResolver.semantic_paths_for, "
                "RelationResolver.resolve, filtrowaniu profile_for/is_displayable_entity oraz "
                "deduplikacji ExplorerService po kategorii i kanonicznym target URI."
            ),
            "source_rdf_occurrences_definition": (
                "Liczba sciezek semantycznych z RDF przed deduplikacja UI; nie jest mianownikiem coverage."
            ),
            "full_graph": full_graph,
            "seed": args.seed,
            "max_sources": args.max_sources,
            "validated_sources": len(sources),
            "displayable_canonical_entities": len(all_sources),
            "max_relationships_per_entity": explorer.max_relationships,
            "limitation": (
                "Kanonizacja jest walidowana wzgledem deterministycznych regul implementacji "
                "dla placeholderow i etykiet, bez sztucznego ground truth dla realnej tozsamosci encji."
            ),
        },
        "tested_patterns": [row["pattern"] for row in summary_rows],
        "raw_requested_pattern_scan": raw_requested_counts,
        "relation_summary": summary_rows,
        "inverse_relations": inverse_summary,
        "technical_filtering": technical_summary,
        "canonicalization": canonical_summary,
        "examples_correct": correct_examples,
        "example_issues": issue_rows[:EXAMPLE_LIMIT],
        "files": {
            "cases_csv": str(per_case_csv),
            "summary_csv": str(summary_csv),
            "issues_csv": str(issues_csv),
            "actual_relationships_csv": str(actual_csv),
            "technical_filtering_csv": str(technical_csv),
            "canonicalization_csv": str(canonical_csv),
            "summary_json": str(summary_json),
        },
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print_report(summary, per_case_csv, summary_csv, issues_csv)
    return 0


def build_explorer_only_context() -> ExplorerService:
    settings = get_settings()
    ontology = load_ontology(settings.ontology_rdf_path)
    graph = load_graph_from_tsv(settings.graph_tsv_path)
    for subject, predicate, obj in ontology_label_triples(ontology):
        if subject not in graph.nodes:
            graph.add_triple(subject, predicate, obj)
    labels = LabelResolver(graph, ontology)
    resolved_labels = labels.all_resolved_labels()
    graph.build_placeholder_aliases(resolved_labels)
    graph.build_search_index(resolved_labels)
    semantics = SemanticResolver(graph, labels)
    relations = RelationResolver(labels)
    return ExplorerService(
        graph,
        labels,
        semantics,
        relations,
        max_relationships=settings.max_relationships_per_direction,
    )


def select_sources(uris: list[str], max_sources: int, seed: int, semantics: Any) -> list[str]:
    if max_sources <= 0 or len(uris) <= max_sources:
        return uris
    rng = random.Random(seed)
    by_type: dict[str, list[str]] = defaultdict(list)
    for uri in uris:
        profile = semantics.profile_for(uri)
        by_type[profile.semantic_type if profile else "n/a"].append(uri)
    for values in by_type.values():
        rng.shuffle(values)
    sample: list[str] = []
    while len(sample) < max_sources and any(by_type.values()):
        for key in sorted(by_type):
            if by_type[key]:
                sample.append(by_type[key].pop())
                if len(sample) >= max_sources:
                    break
    rng.shuffle(sample)
    return sample


def expected_visible_relations(uri: str, explorer: Any) -> tuple[list[ExpectedRelation], Counter[str]]:
    graph = explorer.graph
    semantics = explorer.semantics
    relations = explorer.relations
    source_profile = semantics.profile_for(uri)
    if not source_profile:
        return [], Counter()

    candidates: list[ExpectedRelation] = []
    occurrences: Counter[str] = Counter()
    for semantic_path in semantics.semantic_paths_for(uri, explorer.max_relationships):
        target_uri = graph.canonical_uri(semantic_path.target_uri)
        target_profile = semantics.profile_for(target_uri)
        if not target_profile:
            continue
        resolved = relations.resolve(uri, target_uri, semantic_path.path, source_profile, target_profile, semantic_path.confidence)
        pattern = classify_pattern(uri, target_uri, semantic_path.hint, semantic_path.path, source_profile, target_profile, graph)
        occurrences[pattern] += 1
        candidates.append(
            ExpectedRelation(
                source_uri=uri,
                source_label=source_profile.display_name,
                source_type=source_profile.semantic_type,
                target_uri=target_uri,
                target_label=target_profile.display_name,
                target_type=target_profile.semantic_type,
                pattern=pattern,
                relation=resolved.display_label,
                direction=resolved.direction,
                category=resolved.category,
                confidence=resolved.confidence,
                path_signature=path_signature(semantic_path.path),
                path_predicates="|".join(edge.predicate for edge in semantic_path.path),
                path_readable=" -> ".join(explorer.labels.predicate_label(edge.predicate) for edge in semantic_path.path),
            )
        )

    grouped: dict[str, dict[str, ExpectedRelation]] = defaultdict(dict)
    for candidate in candidates:
        existing = grouped[candidate.category].get(candidate.target_uri)
        if existing and path_len(existing) <= path_len(candidate):
            continue
        grouped[candidate.category][candidate.target_uri] = candidate
    return [item for category in sorted(grouped) for item in grouped[category].values()], occurrences


def actual_visible_relations(uri: str, explorer: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in explorer._connection_groups(uri):
        for relationship in group.relationships:
            rows.append(
                {
                    "category": group.label,
                    "target_uri": relationship.target.uri,
                    "target_label": relationship.target.label,
                    "target_type": relationship.target.semantic_type,
                    "relation": relationship.relation,
                    "direction": relationship.direction,
                    "symmetric": relationship.symmetric,
                    "path_len": len(relationship.rdf_path),
                }
            )
    return rows


def classify_pattern(source_uri: str, target_uri: str, hint: str, path: tuple[Any, ...], source_profile: Any, target_profile: Any, graph: Any) -> str:
    predicates = [edge.predicate for edge in path]
    types_by_node = {edge.source: graph.nodes.get(edge.source).rdf_types if graph.nodes.get(edge.source) else set() for edge in path}
    types_by_node.update({edge.target: graph.nodes.get(edge.target).rdf_types if graph.nodes.get(edge.target) else set() for edge in path if edge.target_is_uri})
    has_birth = any(E67_BIRTH in rdf_types for rdf_types in types_by_node.values())
    has_death = any(E69_DEATH in rdf_types for rdf_types in types_by_node.values())
    has_linguistic = any(E33_LINGUISTIC_OBJECT in rdf_types for rdf_types in types_by_node.values())

    if P98_BROUGHT_INTO_LIFE in predicates and P7I_WITNESSED in predicates:
        return "birth_place_inverse" if source_profile.semantic_type == "Place" else "birth_place"
    if P98_BROUGHT_INTO_LIFE in predicates and P4I_IS_TIME_SPAN_OF in predicates:
        return "birth_time"
    if P100_WAS_DEATH_OF in predicates and P7I_WITNESSED in predicates:
        return "death_place_inverse" if source_profile.semantic_type == "Place" else "death_place"
    if P100_WAS_DEATH_OF in predicates and P4I_IS_TIME_SPAN_OF in predicates:
        return "death_time"
    if P108_HAS_PRODUCED in predicates and source_profile.semantic_type == "Object" and target_profile.semantic_type in {"Person", "Actor", "Institution"}:
        return "object_to_person_via_production"
    if P14I_PERFORMED in predicates and P108_HAS_PRODUCED in predicates:
        return "person_to_object_via_production"
    if P128_CARRIES in predicates and P94_HAS_CREATED in predicates and (P14I_PERFORMED in predicates or P14_CARRIED_OUT_BY in predicates) and has_linguistic:
        if source_profile.semantic_type == "Object" and target_profile.semantic_type in {"Person", "Actor", "Institution"}:
            return "carried_object_to_creator_via_linguistic_object"
        return "creation_linguistic_object_to_carried_object"
    if P94_HAS_CREATED in predicates and (P14I_PERFORMED in predicates or P14_CARRIED_OUT_BY in predicates):
        return "creation_created_object"
    if P11_HAD_PARTICIPANT in predicates or P11I_PARTICIPATED_IN in predicates:
        return "event_participant_counterpart"
    if hint in {"studied", "worked as", "earned degree", "field of study", "professional role"}:
        return "typed_activity_" + hint.replace(" ", "_")
    if P102_HAS_TITLE in predicates or P102I_IS_TITLE_OF in predicates:
        return "title_relation"
    if P1I_IDENTIFIES in predicates:
        return "appellation_identification"
    if P129I_IS_SUBJECT_OF in predicates and len(path) > 1:
        return "shared_described_context_subject"
    if P128_CARRIES in predicates and len(path) > 1:
        return "shared_described_context_carrier"
    if P2I_IS_TYPE_OF in predicates:
        return "type_classification"
    if len(path) == 1:
        return "direct_edge_" + uri_tail(path[0].predicate).replace(" ", "_")
    if has_birth:
        return "other_birth_event_path"
    if has_death:
        return "other_death_event_path"
    return "other_semantic_path"


def validate_inverse_relations(expected_by_source: dict[str, list[ExpectedRelation]], explorer: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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

    required = 0
    correct = 0
    one_sided = 0
    issues: list[dict[str, Any]] = []
    for rows in expected_by_source.values():
        for row in rows:
            inverse = inverse_map.get(row.relation)
            if not inverse:
                continue
            required += 1
            if (row.target_uri, row.source_uri, inverse) in expected_index:
                correct += 1
            else:
                one_sided += 1
                issue = expected_relation_to_row(row)
                issue["status"] = "missing_inverse"
                issue["expected_inverse_relation"] = inverse
                issues.append(issue)
    coverage = round(correct / required * 100.0, 4) if required else 0.0
    return {
        "relations_requiring_inverse": required,
        "correct_pairs": correct,
        "one_sided": one_sided,
        "inverse_relation_coverage_percent": coverage,
        "inverse_mapping_used": inverse_map,
    }, issues


def validate_technical_filtering(sources: list[str], expected_by_source: dict[str, list[ExpectedRelation]], explorer: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    graph = explorer.graph
    semantics = explorer.semantics
    technical_nodes = [uri for uri in graph.nodes if semantics.is_technical_node(uri)]
    user_relation_uris = {
        value
        for rels in expected_by_source.values()
        for row in rels
        for value in (row.source_uri, row.target_uri)
    }
    technical_set = set(technical_nodes)
    rows: list[dict[str, Any]] = []
    leaks = 0
    for uri in technical_nodes:
        profile = semantics.profile_for(uri)
        in_user_relation = uri in user_relation_uris
        # ExplorerService.search explicitly skips SemanticResolver.is_technical_node(uri),
        # so a technical node with a profile would be the relevant search leak signal.
        reachable_by_search = bool(profile)
        if in_user_relation or profile or reachable_by_search:
            leaks += 1
            if len(rows) < LEAK_EXAMPLE_LIMIT:
                node = graph.nodes.get(uri)
                rows.append(
                    {
                        "uri": uri,
                        "label": explorer.labels.label_for(uri),
                        "rdf_types": "|".join(sorted(node.rdf_types)) if node else "",
                        "local_prefix": local_class_prefix(uri),
                        "profile_available": bool(profile),
                        "appears_in_user_relation": in_user_relation,
                        "reachable_by_basic_search": reachable_by_search,
                    }
                )
    return {
        "technical_type_uris": sorted(TECHNICAL_TYPES),
        "technical_local_prefixes": sorted(TECHNICAL_LOCAL_PREFIXES),
        "technical_uri_tail_prefixes": sorted(TECHNICAL_URI_TAIL_PREFIXES),
        "technical_nodes": len(technical_nodes),
        "technical_leaks_detected": leaks,
        "technical_search_leaks_detected": sum(1 for row in rows if row["reachable_by_basic_search"]),
    }, rows


def validate_canonicalization(graph: Any, labels: Any, semantics: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    correct = 0
    ambiguous = 0
    wrong = 0
    by_label: dict[str, list[str]] = defaultdict(list)
    for uri in graph.nodes:
        by_label[normalize_for_search(labels.label_for(uri))].append(uri)

    for placeholder, canonical in sorted(graph.canonical_uri_by_placeholder.items()):
        placeholder_label = normalize_for_search(labels.label_for(placeholder))
        candidates = [
            uri
            for uri in by_label.get(placeholder_label, [])
            if uri != placeholder and graph.is_described_entity(uri)
        ]
        same_prefix = [uri for uri in candidates if local_class_prefix(uri) == local_class_prefix(placeholder)]
        expected = ""
        status = "ambiguous"
        if len(candidates) == 1:
            expected = candidates[0]
            status = "correct" if canonical == expected else "wrong"
        elif len(same_prefix) == 1:
            expected = same_prefix[0]
            status = "correct" if canonical == expected else "wrong"
        if status == "correct":
            correct += 1
        elif status == "wrong":
            wrong += 1
        else:
            ambiguous += 1
        rows.append(
            {
                "placeholder_uri": placeholder,
                "placeholder_label": labels.label_for(placeholder),
                "canonical_uri": canonical,
                "canonical_label": labels.label_for(canonical),
                "candidate_count_same_label": len(candidates),
                "same_prefix_candidate_count": len(same_prefix),
                "expected_by_implementation": expected,
                "status": status,
                "canonical_profile_available": bool(semantics.profile_for(canonical)),
            }
        )

    duplicate_label_groups = sum(1 for values in by_label.values() if len(values) > 1)
    placeholders = [uri for uri in graph.nodes if graph.is_placeholder_reference(uri)]
    return {
        "placeholder_references": len(placeholders),
        "canonical_mappings": len(graph.canonical_uri_by_placeholder),
        "cases_subject_to_canonicalization": len(rows),
        "correctly_resolved_by_implementation_rule": correct,
        "ambiguous_without_external_ground_truth": ambiguous,
        "wrong_against_implementation_rule": wrong,
        "duplicate_normalized_label_groups": duplicate_label_groups,
    }, rows


def scan_requested_raw_patterns(explorer: Any) -> dict[str, dict[str, int]]:
    graph = explorer.graph
    semantics = explorer.semantics
    counts: dict[str, Counter[str]] = defaultdict(Counter)

    def add(pattern: str, source_uri: str, target_uri: str) -> None:
        source_canonical = graph.canonical_uri(source_uri)
        target_canonical = graph.canonical_uri(target_uri)
        counts[pattern]["source_rdf_occurrences"] += 1
        if semantics.profile_for(source_canonical) and semantics.profile_for(target_canonical):
            counts[pattern]["visible_by_filters_before_ui_dedup"] += 1

    for edge in graph.edges:
        if edge.predicate != P14I_PERFORMED or not edge.target_is_uri:
            continue
        performer = edge.source
        activity = graph.nodes.get(edge.target)
        if not activity:
            continue
        for out_index in activity.outgoing:
            out = graph.edges[out_index]
            if out.predicate == P108_HAS_PRODUCED and out.target_is_uri:
                add("person_to_object_via_production", performer, out.target)
                add("object_to_person_via_production", out.target, performer)
            elif out.predicate == P94_HAS_CREATED and out.target_is_uri:
                content = graph.nodes.get(out.target)
                if content and E33_LINGUISTIC_OBJECT in content.rdf_types:
                    for incoming_index in content.incoming:
                        carrier = graph.edges[incoming_index]
                        if carrier.predicate == P128_CARRIES:
                            add("creation_linguistic_object_to_carried_object", performer, carrier.source)
                            add("carried_object_to_creator_via_linguistic_object", carrier.source, performer)

    for event_uri in graph.by_type.get(E67_BIRTH, set()):
        scan_life_event_raw_pattern(explorer, event_uri, P98_BROUGHT_INTO_LIFE, "birth")
        event = graph.nodes.get(event_uri)
        if not event:
            continue
        people = [graph.edges[index].target for index in event.outgoing if graph.edges[index].predicate == P98_BROUGHT_INTO_LIFE and graph.edges[index].target_is_uri]
        places = [graph.edges[index].source for index in event.incoming if graph.edges[index].predicate == P7I_WITNESSED]
        times = [graph.edges[index].source for index in event.incoming if graph.edges[index].predicate == P4I_IS_TIME_SPAN_OF]
        for person in people:
            for place in places:
                add("birth_place", person, place)
                add("birth_place_inverse", place, person)
            for timespan in times:
                add("birth_time", person, timespan)

    for event_uri in graph.by_type.get(E69_DEATH, set()):
        event = graph.nodes.get(event_uri)
        if not event:
            continue
        people = [graph.edges[index].target for index in event.outgoing if graph.edges[index].predicate == P100_WAS_DEATH_OF and graph.edges[index].target_is_uri]
        places = [graph.edges[index].source for index in event.incoming if graph.edges[index].predicate == P7I_WITNESSED]
        times = [graph.edges[index].source for index in event.incoming if graph.edges[index].predicate == P4I_IS_TIME_SPAN_OF]
        for person in people:
            for place in places:
                add("death_place", person, place)
                add("death_place_inverse", place, person)
            for timespan in times:
                add("death_time", person, timespan)

    requested = (
        "person_to_object_via_production",
        "object_to_person_via_production",
        "birth_place",
        "birth_place_inverse",
        "birth_time",
        "death_place",
        "death_place_inverse",
        "death_time",
        "creation_linguistic_object_to_carried_object",
        "carried_object_to_creator_via_linguistic_object",
    )
    return {
        pattern: {
            "source_rdf_occurrences": counts[pattern]["source_rdf_occurrences"],
            "visible_by_filters_before_ui_dedup": counts[pattern]["visible_by_filters_before_ui_dedup"],
        }
        for pattern in requested
    }


def scan_life_event_raw_pattern(explorer: Any, event_uri: str, person_predicate: str, prefix: str) -> None:
    # Kept for readability if later life-event scans need to share additional diagnostics.
    return None


def build_relation_summary(
    expected_rows: list[dict[str, Any]],
    issue_rows: list[dict[str, Any]],
    occurrences: Counter[str],
    raw_requested_counts: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    expected_counts = Counter(row["pattern"] for row in expected_rows)
    missing_counts = Counter(row["pattern"] for row in issue_rows)
    patterns = sorted(set(expected_counts) | set(occurrences) | set(raw_requested_counts))
    rows = []
    for pattern in patterns:
        expected = expected_counts[pattern]
        missing = missing_counts[pattern]
        correct = expected - missing
        raw_count = raw_requested_counts.get(pattern, {}).get("source_rdf_occurrences", occurrences[pattern])
        rows.append(
            {
                "pattern": pattern,
                "source_rdf_occurrences": raw_count,
                "semantic_path_occurrences_before_ui_dedup": occurrences[pattern],
                "visible_by_filters_before_ui_dedup": raw_requested_counts.get(pattern, {}).get("visible_by_filters_before_ui_dedup", occurrences[pattern]),
                "should_be_visible": expected,
                "correctly_mapped": correct,
                "missing_relations": missing,
                "wrong_relations": 0,
                "coverage_percent": round(correct / expected * 100.0, 4) if expected else 0.0,
            }
        )
    return rows


def path_len(row: ExpectedRelation) -> int:
    return 0 if not row.path_signature else row.path_signature.count(" || ") + 1


def path_signature(path: tuple[Any, ...]) -> str:
    return " || ".join(f"{edge.source} {edge.predicate} {edge.target}" for edge in path)


def expected_relation_to_row(item: ExpectedRelation) -> dict[str, Any]:
    return {
        "source_uri": item.source_uri,
        "source_label": item.source_label,
        "source_type": item.source_type,
        "target_uri": item.target_uri,
        "target_label": item.target_label,
        "target_type": item.target_type,
        "pattern": item.pattern,
        "relation": item.relation,
        "direction": item.direction,
        "category": item.category,
        "confidence": item.confidence,
        "path_signature": item.path_signature,
        "path_predicates": item.path_predicates,
        "path_readable": item.path_readable,
        "status": "",
        "expected_inverse_relation": "",
    }


def actual_relation_to_row(source_uri: str, item: dict[str, Any]) -> dict[str, Any]:
    return {"source_uri": source_uri, **item}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def case_fieldnames() -> tuple[str, ...]:
    return (
        "source_uri",
        "source_label",
        "source_type",
        "target_uri",
        "target_label",
        "target_type",
        "pattern",
        "relation",
        "direction",
        "category",
        "confidence",
        "path_predicates",
        "path_readable",
        "path_signature",
    )


def issue_fieldnames() -> tuple[str, ...]:
    return case_fieldnames() + ("status", "expected_inverse_relation")


def summary_fieldnames() -> tuple[str, ...]:
    return (
        "pattern",
        "source_rdf_occurrences",
        "semantic_path_occurrences_before_ui_dedup",
        "visible_by_filters_before_ui_dedup",
        "should_be_visible",
        "correctly_mapped",
        "missing_relations",
        "wrong_relations",
        "coverage_percent",
    )


def actual_fieldnames() -> tuple[str, ...]:
    return (
        "source_uri",
        "category",
        "target_uri",
        "target_label",
        "target_type",
        "relation",
        "direction",
        "symmetric",
        "path_len",
    )


def technical_fieldnames() -> tuple[str, ...]:
    return (
        "uri",
        "label",
        "rdf_types",
        "local_prefix",
        "profile_available",
        "appears_in_user_relation",
        "reachable_by_basic_search",
    )


def canonical_fieldnames() -> tuple[str, ...]:
    return (
        "placeholder_uri",
        "placeholder_label",
        "canonical_uri",
        "canonical_label",
        "candidate_count_same_label",
        "same_prefix_candidate_count",
        "expected_by_implementation",
        "status",
        "canonical_profile_available",
    )


def print_report(summary: dict[str, Any], per_case_csv: Path, summary_csv: Path, issues_csv: Path) -> None:
    print()
    print("=== Tested patterns ===")
    print(f"{'pattern':<52} {'cases':>10} {'ok':>10} {'bad/miss':>10} {'coverage':>10}")
    for row in summary["relation_summary"]:
        bad = row["missing_relations"] + row["wrong_relations"]
        print(
            f"{row['pattern']:<52} {row['should_be_visible']:>10} "
            f"{row['correctly_mapped']:>10} {bad:>10} {row['coverage_percent']:>9.4f}%"
        )

    inverse = summary["inverse_relations"]
    print()
    print("=== Inverse relations ===")
    print(f"Relations requiring inverse: {inverse['relations_requiring_inverse']}")
    print(f"Correct inverse pairs: {inverse['correct_pairs']}")
    print(f"One-sided cases: {inverse['one_sided']}")
    print(f"Inverse relation coverage: {inverse['inverse_relation_coverage_percent']:.4f}%")

    technical = summary["technical_filtering"]
    print()
    print("=== Technical filtering ===")
    print(f"Technical nodes: {technical['technical_nodes']}")
    print(f"Technical leaks detected: {technical['technical_leaks_detected']}")
    print(f"Technical search leaks detected: {technical['technical_search_leaks_detected']}")

    canonical = summary["canonicalization"]
    print()
    print("=== Canonicalization ===")
    print(f"Placeholder references: {canonical['placeholder_references']}")
    print(f"Canonical mappings: {canonical['canonical_mappings']}")
    print(f"Correct by implementation rule: {canonical['correctly_resolved_by_implementation_rule']}")
    print(f"Ambiguous without external ground truth: {canonical['ambiguous_without_external_ground_truth']}")
    print(f"Wrong against implementation rule: {canonical['wrong_against_implementation_rule']}")

    print()
    print("=== Correct mapping examples ===")
    for index, row in enumerate(summary["examples_correct"], start=1):
        print(f"{index:02d}. {row['source_label']} --{row['relation']}--> {row['target_label']}")
        print(f"    pattern: {row['pattern']}; path: {row['path_readable']}")

    print()
    print("=== Issue examples ===")
    if not summary["example_issues"]:
        print("No missing, wrong, inverse, or technical leak examples recorded.")
    for index, row in enumerate(summary["example_issues"], start=1):
        print(f"{index:02d}. {row.get('status', '')}: {row.get('source_label', '')} -> {row.get('target_label', '')}")
        print(f"    pattern: {row.get('pattern', '')}; relation: {row.get('relation', '')}; expected inverse: {row.get('expected_inverse_relation', '')}")

    print()
    print("=== Files ===")
    print(f"Cases CSV: {per_case_csv}")
    print(f"Summary CSV: {summary_csv}")
    print(f"Issues CSV: {issues_csv}")
    print(f"JSON summary: {summary['files']['summary_json']}")
    print(f"Runtime seconds: {summary['runtime_seconds']}")


if __name__ == "__main__":
    raise SystemExit(main())
