from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property, lru_cache

from backend.data.graph.constants import CIDOC, RDF_TYPE, UJ
from backend.data.graph.knowledge_graph import KnowledgeGraph
from backend.data.graph.models import Edge
from backend.recommendations.loader import RecommendationArtifacts
from backend.recommendations.similarity import query_similar


PERSON_OR_ACTOR_TYPES = frozenset({CIDOC + "E21_Person", CIDOC + "E39_Actor"})
OBJECT_TYPES = frozenset({CIDOC + "E22_Human-Made_Object"})
PLACE_TYPES = frozenset({CIDOC + "E53_Place"})
EVENT_TYPES = frozenset({
    CIDOC + "E5_Event",
    CIDOC + "E7_Activity",
    CIDOC + "E11_Modification",
    UJ + "NE1_Educational_Activity",
    UJ + "NE2_Occupational_Activity",
})
PERSON_PROPERTIES = {
    "same_location": (CIDOC + "P53_has_former_or_current_location",),
    "same_events": (
        CIDOC + "P11i_participated_in",
        CIDOC + "P12i_was_present_at",
        CIDOC + "P14i_performed",
    ),
    "same_identification": (
        CIDOC + "P1_is_identified_by",
        CIDOC + "P48_has_preferred_identifier",
    ),
    "same_production": (CIDOC + "P15i_influenced",),
    "same_occurs_in": (
        CIDOC + "P67i_is_referred_to_by",
        CIDOC + "P129i_is_subject_of",
    ),
    "same_type": (CIDOC + "P2_has_type",),
}

BIRTH_EVENT_TO_PERSON = (
    CIDOC + "P98_brought_into_life",
    CIDOC + "P92_brought_into_existence",
)
BIRTH_PERSON_TO_EVENT = (
    CIDOC + "P98i_was_born",
    CIDOC + "P92i_was_brought_into_existence_by",
)
DEATH_EVENT_TO_PERSON = (
    CIDOC + "P100_was_death_of",
    CIDOC + "P93_took_out_of_existence",
)
DEATH_PERSON_TO_EVENT = (
    CIDOC + "P100i_died_in",
    CIDOC + "P93i_was_taken_out_of_existence_by",
)
TIME_SPAN_PREDICATES = (
    CIDOC + "P82_at_some_time_within",
    CIDOC + "P82a_begin_of_the_begin",
    CIDOC + "P82b_end_of_the_end",
)
EVENT_TO_TIME_SPAN = CIDOC + "P4_has_time-span"
TIME_SPAN_TO_EVENT = CIDOC + "P4i_is_time-span_of"
EVENT_TO_PLACE = CIDOC + "P7_took_place_at"
PLACE_TO_EVENT = CIDOC + "P7i_witnessed"
PRODUCTION_TO_CREATOR = CIDOC + "P14_carried_out_by"
CREATOR_TO_PRODUCTION = CIDOC + "P14i_performed"
PRODUCTION_TO_OBJECT = CIDOC + "P108_has_produced"
CREATION_TO_OBJECT = CIDOC + "P94_has_created"
EDUCATIONAL_ACTIVITY = UJ + "NE1_Educational_Activity"
OCCUPATIONAL_ACTIVITY = UJ + "NE2_Occupational_Activity"
TECHNICAL_EXPLANATION_TYPES = frozenset({
    CIDOC + "E12_Production",
    CIDOC + "E33_Linguistic_Object",
    CIDOC + "E35_Title",
    CIDOC + "E41_Appellation",
    CIDOC + "E42_Identifier",
    CIDOC + "E52_Time-Span",
    CIDOC + "E65_Creation",
    CIDOC + "E67_Birth",
    CIDOC + "E69_Death",
    CIDOC + "PC14_carried_out_by",
})
CATALOG_RECORD_LABELS = frozenset({"cac rekord", "cac record"})


@dataclass(frozen=True, slots=True)
class OriginalCandidate:
    embedding_id: int
    uri: str
    label: str
    distance: float
    hnsw_rank: int
    recommendation_reason: list[str]
    rdf_paths_by_reason: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class RetrievedCandidate:
    embedding_id: int
    uri: str
    label: str
    distance: float
    hnsw_rank: int
    source_embedding_id: int


class OriginalPipelineEngine:
    def __init__(self, graph: KnowledgeGraph, artifacts: RecommendationArtifacts) -> None:
        self.graph = graph
        self.artifacts = artifacts

    def recommend(self, uri: str, candidate_limit: int = 500) -> list[OriginalCandidate]:
        main_uri = self.graph.canonical_uri(uri)
        embedding_ids = self.embedding_ids_for_uri(main_uri)
        if not embedding_ids:
            return []

        target_embedding_ids = set(embedding_ids)
        best_by_uri: dict[str, RetrievedCandidate] = {}

        for source_embedding_id in embedding_ids:
            neighbors = query_similar(
                self.artifacts.index,
                self.artifacts.embeddings,
                source_embedding_id,
                self._candidate_count(candidate_limit + len(target_embedding_ids)),
            )
            raw_neighbors = [
                neighbor
                for neighbor in neighbors
                if neighbor.embedding_id not in target_embedding_ids and neighbor.embedding_id in self.artifacts.embedding_metadata
            ][:candidate_limit]
            sorted_neighbors = sorted(raw_neighbors, key=lambda item: item.score)

            for rank, neighbor in enumerate(sorted_neighbors, start=1):
                label, candidate_uri = self.artifacts.embedding_metadata[neighbor.embedding_id]
                candidate_uri = self.graph.canonical_uri(candidate_uri)
                if not candidate_uri.startswith("http") or candidate_uri == main_uri:
                    continue
                candidate = RetrievedCandidate(
                    embedding_id=neighbor.embedding_id,
                    uri=candidate_uri,
                    label=self.label_by_uri.get(candidate_uri, label),
                    distance=float(neighbor.score),
                    hnsw_rank=rank,
                    source_embedding_id=source_embedding_id,
                )
                best_by_uri[candidate_uri] = _merge_retrieved(best_by_uri.get(candidate_uri), candidate)

        reasons_by_uri, paths_by_uri = self.recommend_with_semantic_filters(main_uri, list(best_by_uri))
        recommendations = [
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
        return _rank_recommendations(recommendations)

    def recommend_with_semantic_filters(self, main_uri: str, uris: list[str]) -> tuple[dict[str, list[str]], dict[str, dict[str, list[str]]]]:
        valid_uris = [uri for uri in uris if uri.startswith("http")]
        recommended: dict[str, list[str]] = defaultdict(list)
        paths: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        person_uris: list[str] = []

        for batch in _batches(valid_uris, 50):
            for candidate_uri in self._recommend_uris_by_type(batch, PERSON_OR_ACTOR_TYPES):
                person_uris.append(candidate_uri)
                recommended[candidate_uri].append("person_or_actor")

            for candidate_uri, evidence in self._query_connection(main_uri, batch).items():
                recommended[candidate_uri].append("target_connection")
                paths[candidate_uri]["target_connection"].extend(evidence)

            for candidate_uri, evidence in self._query_connection_to_same_objects(main_uri, batch).items():
                recommended[candidate_uri].append("same_objects_connection")
                paths[candidate_uri]["same_objects_connection"].extend(evidence)

            for reason, matches in self._additional_semantic_rules(main_uri, batch).items():
                for candidate_uri, evidence in matches.items():
                    recommended[candidate_uri].append(reason)
                    paths[candidate_uri][reason].extend(evidence)

        for batch in _batches(person_uris, 50):
            for reason, predicates in PERSON_PROPERTIES.items():
                for candidate_uri, evidence in self._query_same_property_value(main_uri, batch, predicates).items():
                    recommended[candidate_uri].append(reason)
                    paths[candidate_uri][reason].extend(evidence)

            for candidate_uri, evidence in self._close_life_event_year(main_uri, batch, "birth").items():
                recommended[candidate_uri].append("close_birth")
                paths[candidate_uri]["close_birth"].extend(evidence)

            for candidate_uri, evidence in self._close_life_event_year(main_uri, batch, "death").items():
                recommended[candidate_uri].append("close_death")
                paths[candidate_uri]["close_death"].extend(evidence)

            for candidate_uri, evidence in self._same_place_of_birth(main_uri, batch).items():
                recommended[candidate_uri].append("same_place_of_birth")
                paths[candidate_uri]["same_place_of_birth"].extend(evidence)

        return dict(recommended), {uri: dict(reason_paths) for uri, reason_paths in paths.items()}

    @cached_property
    def label_by_uri(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for _embedding_id, (label, uri) in sorted(self.artifacts.embedding_metadata.items()):
            labels.setdefault(self.graph.canonical_uri(uri), label)
        return labels

    def embedding_ids_for_uri(self, uri: str) -> list[int]:
        embedding_ids = self.canonical_embedding_ids_by_uri.get(self.graph.canonical_uri(uri), [])
        return [embedding_ids[-1]] if embedding_ids else []

    @cached_property
    def canonical_embedding_ids_by_uri(self) -> dict[str, list[int]]:
        ids_by_uri: dict[str, list[int]] = defaultdict(list)
        for embedding_id, (_label, uri_or_ref) in self.artifacts.embedding_metadata.items():
            ids_by_uri[self.graph.canonical_uri(uri_or_ref)].append(embedding_id)
        if not ids_by_uri:
            for uri, embedding_ids in self.artifacts.embedding_ids_by_uri.items():
                ids_by_uri[self.graph.canonical_uri(uri)].extend(embedding_ids)
        return {uri: _dedupe_ints(embedding_ids) for uri, embedding_ids in ids_by_uri.items()}

    def _recommend_uris_by_type(self, uris: list[str], type_filters: frozenset[str]) -> list[str]:
        return [uri for uri in uris if self._rdf_types(uri).intersection(type_filters)]

    def _query_connection(self, main_uri: str, uris: list[str]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        uri_set = set(uris)
        main_node = self.graph.nodes.get(main_uri)
        if main_node:
            for rdf_type in main_node.rdf_types.intersection(uri_set):
                result.setdefault(rdf_type, []).append(f"{main_uri} {RDF_TYPE} {rdf_type}")
        for edge in self._outgoing(main_uri):
            if edge.target in uri_set:
                result.setdefault(edge.target, []).append(_format_edge(edge))
        for edge in self._incoming(main_uri):
            if edge.source in uri_set:
                result.setdefault(edge.source, []).append(_format_edge(edge))
        return result

    def _query_connection_to_same_objects(self, main_uri: str, uris: list[str]) -> dict[str, list[str]]:
        main_connections = self._connected_values(main_uri)
        result: dict[str, list[str]] = {}
        for uri in uris:
            candidate_connections = self._touching_edges_by_value(uri)
            evidence: list[str] = []
            for common, main_edges in main_connections.items():
                other_edges = candidate_connections.get(common)
                if not other_edges:
                    continue
                for main_edge in main_edges[:2]:
                    for other_edge in other_edges[:2]:
                        fact_prefix = self._explanation_facts_for_shared_value(common, main_uri, uri)
                        evidence.append("; ".join([*fact_prefix, _format_edge(main_edge), _format_edge(other_edge)]))
            if evidence:
                result[uri] = _dedupe(evidence)
        return result

    def _query_same_property_value(self, main_uri: str, uris: list[str], predicates: tuple[str, ...]) -> dict[str, list[str]]:
        predicate_set = set(predicates)
        main_values = self._values_by_predicate(main_uri, frozenset(predicate_set))
        result: dict[str, list[str]] = {}
        for uri in uris:
            candidate_values = self._values_by_predicate(uri, frozenset(predicate_set))
            evidence: list[str] = []
            for predicate, values in main_values.items():
                for value in sorted(values.intersection(candidate_values.get(predicate, set()))):
                    evidence.append(f"{main_uri} {predicate} {value}; {uri} {predicate} {value}")
            if evidence:
                result[uri] = evidence
        return result

    def _additional_semantic_rules(self, main_uri: str, uris: list[str]) -> dict[str, dict[str, list[str]]]:
        rules: dict[str, dict[str, list[str]]] = {}
        object_uris = self._recommend_uris_by_type(uris, OBJECT_TYPES)
        person_uris = self._recommend_uris_by_type(uris, PERSON_OR_ACTOR_TYPES)
        event_uris = self._recommend_uris_by_type(uris, EVENT_TYPES)

        if self._rdf_types(main_uri).intersection(OBJECT_TYPES):
            _put_rule(rules, "same_creator", self._shared_fact_matches(main_uri, object_uris, self._object_creators))
            _put_rule(rules, "same_creation_event", self._shared_fact_matches(main_uri, object_uris, self._object_creation_events))
            _put_rule(rules, "same_creation_place", self._shared_fact_matches(main_uri, object_uris, self._object_creation_places))

        if self._rdf_types(main_uri).intersection(PERSON_OR_ACTOR_TYPES):
            _put_rule(rules, "same_created_object", self._shared_fact_matches(main_uri, person_uris, self._person_created_objects))
            _put_rule(rules, "same_death_place", self._shared_fact_matches(main_uri, person_uris, lambda uri: self._life_event_places(uri, "death")))
            _put_rule(rules, "same_birth_event", self._shared_fact_matches(main_uri, person_uris, lambda uri: self._life_event_facts(uri, "birth")))
            _put_rule(rules, "same_death_event", self._shared_fact_matches(main_uri, person_uris, lambda uri: self._life_event_facts(uri, "death")))
            _put_rule(rules, "same_educational_activity", self._shared_fact_matches(main_uri, person_uris, lambda uri: self._typed_participation_events(uri, EDUCATIONAL_ACTIVITY)))
            _put_rule(rules, "same_occupational_activity", self._shared_fact_matches(main_uri, person_uris, lambda uri: self._typed_participation_events(uri, OCCUPATIONAL_ACTIVITY)))
            _put_rule(rules, "same_birth_year", self._same_life_event_year(main_uri, person_uris, "birth"))
            _put_rule(rules, "same_death_year", self._same_life_event_year(main_uri, person_uris, "death"))

        if self._rdf_types(main_uri).intersection(EVENT_TYPES):
            _put_rule(rules, "same_time_span", self._shared_fact_matches(main_uri, event_uris, self._event_time_span_facts))

        return rules

    def _shared_fact_matches(
        self,
        main_uri: str,
        uris: list[str],
        fact_func,
    ) -> dict[str, list[str]]:
        main_facts = fact_func(main_uri)
        if not main_facts:
            return {}
        result: dict[str, list[str]] = {}
        for uri in uris:
            candidate_facts = fact_func(uri)
            evidence: list[str] = []
            for value in sorted(set(main_facts).intersection(candidate_facts)):
                evidence.append(self._fact_for_value(value))
                evidence.extend(main_facts[value][:2])
                evidence.extend(candidate_facts[value][:2])
            if evidence:
                result[uri] = _dedupe(evidence)
        return result

    def _same_life_event_year(self, main_uri: str, uris: list[str], event_type: str) -> dict[str, list[str]]:
        main_year = self._life_event_year(main_uri, event_type)
        if main_year is None:
            return {}
        result: dict[str, list[str]] = {}
        for uri in uris:
            year = self._life_event_year(uri, event_type)
            if year == main_year:
                result[uri] = [_format_fact("Time", f"{event_type} year {main_year}")]
        return result

    def _close_life_event_year(self, main_uri: str, uris: list[str], event_type: str, threshold: int = 50) -> dict[str, list[str]]:
        main_year = self._life_event_year(main_uri, event_type)
        if main_year is None:
            return {}
        result: dict[str, list[str]] = {}
        for uri in uris:
            year = self._life_event_year(uri, event_type)
            if year is not None and abs(main_year - year) <= threshold:
                result[uri] = [_format_fact("Time", f"{event_type} years {main_year} and {year}")]
        return result

    def _same_place_of_birth(self, main_uri: str, uris: list[str]) -> dict[str, list[str]]:
        main_places = self._birth_place_facts_by_label(main_uri)
        if not main_places:
            return {}
        result: dict[str, list[str]] = {}
        for uri in uris:
            candidate_places = self._birth_place_facts_by_label(uri)
            shared_places = sorted(set(main_places).intersection(candidate_places))
            if shared_places:
                place = shared_places[0]
                result[uri] = _dedupe([
                    _format_fact("Place", place),
                    *main_places[place],
                    *candidate_places[place],
                ])
        return result

    @lru_cache(maxsize=500_000)
    def _object_creators(self, uri: str) -> dict[str, tuple[str, ...]]:
        facts: dict[str, list[str]] = defaultdict(list)
        for event_uri, object_predicate in self._events_for_created_object(uri):
            for creator_uri, creator_predicate in self._creators_for_event(event_uri):
                facts[creator_uri].append(f"{uri} <- {object_predicate} {event_uri} -> {creator_predicate} {creator_uri}")
        return {value: tuple(evidence) for value, evidence in facts.items()}

    @lru_cache(maxsize=500_000)
    def _person_created_objects(self, uri: str) -> dict[str, tuple[str, ...]]:
        facts: dict[str, list[str]] = defaultdict(list)
        for event_uri, creator_predicate in self._events_for_creator(uri):
            for object_uri, object_predicate in self._created_objects_for_event(event_uri):
                facts[object_uri].append(f"{uri} <- {creator_predicate} {event_uri} -> {object_predicate} {object_uri}")
        return {value: tuple(evidence) for value, evidence in facts.items()}

    @lru_cache(maxsize=500_000)
    def _object_creation_events(self, uri: str) -> dict[str, tuple[str, ...]]:
        facts: dict[str, list[str]] = defaultdict(list)
        for event_uri, predicate in self._events_for_created_object(uri):
            facts[event_uri].append(f"{uri} <- {predicate} {event_uri}")
        return {value: tuple(evidence) for value, evidence in facts.items()}

    @lru_cache(maxsize=500_000)
    def _object_creation_places(self, uri: str) -> dict[str, tuple[str, ...]]:
        facts: dict[str, list[str]] = defaultdict(list)
        for event_uri, object_predicate in self._events_for_created_object(uri):
            for place_uri, place_predicate in self._places_for_event_with_predicates(event_uri):
                facts[place_uri].append(f"{uri} <- {object_predicate} {event_uri} -> {place_predicate} {place_uri}")
        return {value: tuple(evidence) for value, evidence in facts.items()}

    @lru_cache(maxsize=500_000)
    def _life_event_facts(self, uri: str, event_type: str) -> dict[str, tuple[str, ...]]:
        facts: dict[str, list[str]] = defaultdict(list)
        for event_uri, predicate in self._life_events_with_predicates(uri, event_type):
            facts[event_uri].append(f"{uri} <- {predicate} {event_uri}")
        return {value: tuple(evidence) for value, evidence in facts.items()}

    @lru_cache(maxsize=500_000)
    def _life_event_places(self, uri: str, event_type: str) -> dict[str, tuple[str, ...]]:
        facts: dict[str, list[str]] = defaultdict(list)
        for event_uri, event_predicate in self._life_events_with_predicates(uri, event_type):
            for place_uri, place_predicate in self._places_for_event_with_predicates(event_uri):
                facts[place_uri].append(f"{uri} <- {event_predicate} {event_uri} -> {place_predicate} {place_uri}")
        return {value: tuple(evidence) for value, evidence in facts.items()}

    @lru_cache(maxsize=500_000)
    def _typed_participation_events(self, uri: str, rdf_type: str) -> dict[str, tuple[str, ...]]:
        facts: dict[str, list[str]] = defaultdict(list)
        for event_uri, predicate in self._events_for_creator(uri):
            if rdf_type in self._rdf_types(event_uri):
                facts[event_uri].append(f"{uri} <- {predicate} {event_uri}; {event_uri} {RDF_TYPE} {rdf_type}")
        return {value: tuple(evidence) for value, evidence in facts.items()}

    @lru_cache(maxsize=500_000)
    def _event_time_span_facts(self, uri: str) -> dict[str, tuple[str, ...]]:
        facts: dict[str, list[str]] = defaultdict(list)
        for time_span_uri, predicate in self._time_spans_for_event_with_predicates(uri):
            facts[time_span_uri].append(f"{uri} -> {predicate} {time_span_uri}")
        return {value: tuple(evidence) for value, evidence in facts.items()}

    @lru_cache(maxsize=500_000)
    def _life_event_year(self, uri: str, event_type: str) -> int | None:
        events = self._life_events(uri, event_type)
        for event_uri in events:
            for time_span_uri in self._time_spans_for_event(event_uri):
                for edge in self._outgoing(time_span_uri):
                    if edge.predicate in TIME_SPAN_PREDICATES:
                        year = _year_from_value(edge.target)
                        if year is not None:
                            return year
        return None

    @lru_cache(maxsize=500_000)
    def _birth_place_facts_by_label(self, uri: str) -> dict[str, tuple[str, ...]]:
        facts: dict[str, list[str]] = defaultdict(list)
        for event_uri in self._life_events(uri, "birth"):
            for place_uri, place_predicate in self._places_for_event_with_predicates(event_uri):
                label = self._label_for_graph_uri(place_uri)
                if label:
                    facts[label].append(f"{place_uri} {place_predicate} {event_uri}")
        return {label: tuple(evidence) for label, evidence in facts.items()}

    def _life_events(self, uri: str, event_type: str) -> list[str]:
        return [event_uri for event_uri, _predicate in self._life_events_with_predicates(uri, event_type)]

    def _life_events_with_predicates(self, uri: str, event_type: str) -> list[tuple[str, str]]:
        if event_type == "birth":
            incoming_predicates = set(BIRTH_EVENT_TO_PERSON)
            outgoing_predicates = set(BIRTH_PERSON_TO_EVENT)
        else:
            incoming_predicates = set(DEATH_EVENT_TO_PERSON)
            outgoing_predicates = set(DEATH_PERSON_TO_EVENT)
        events = [
            (edge.source, edge.predicate)
            for edge in self._incoming(uri)
            if edge.predicate in incoming_predicates and edge.source.startswith("http")
        ]
        events.extend(
            (edge.target, edge.predicate)
            for edge in self._outgoing(uri)
            if edge.predicate in outgoing_predicates and edge.target.startswith("http")
        )
        return _dedupe_tuples(events)

    def _time_spans_for_event(self, event_uri: str) -> list[str]:
        return [time_span_uri for time_span_uri, _predicate in self._time_spans_for_event_with_predicates(event_uri)]

    def _time_spans_for_event_with_predicates(self, event_uri: str) -> list[tuple[str, str]]:
        result = [
            (edge.target, edge.predicate)
            for edge in self._outgoing(event_uri)
            if edge.predicate == EVENT_TO_TIME_SPAN and edge.target.startswith("http")
        ]
        result.extend(
            (edge.source, edge.predicate)
            for edge in self._incoming(event_uri)
            if edge.predicate == TIME_SPAN_TO_EVENT and edge.source.startswith("http")
        )
        return _dedupe_tuples(result)

    def _places_for_event_with_predicates(self, event_uri: str) -> list[tuple[str, str]]:
        result = [
            (edge.target, edge.predicate)
            for edge in self._outgoing(event_uri)
            if edge.predicate == EVENT_TO_PLACE and edge.target.startswith("http")
        ]
        result.extend(
            (edge.source, edge.predicate)
            for edge in self._incoming(event_uri)
            if edge.predicate == PLACE_TO_EVENT and edge.source.startswith("http")
        )
        return _dedupe_tuples(result)

    def _events_for_created_object(self, uri: str) -> list[tuple[str, str]]:
        events = [
            (edge.source, edge.predicate)
            for edge in self._incoming(uri)
            if edge.predicate in {PRODUCTION_TO_OBJECT, CREATION_TO_OBJECT} and edge.source.startswith("http")
        ]
        return _dedupe_tuples(events)

    def _created_objects_for_event(self, event_uri: str) -> list[tuple[str, str]]:
        objects = [
            (edge.target, edge.predicate)
            for edge in self._outgoing(event_uri)
            if edge.predicate in {PRODUCTION_TO_OBJECT, CREATION_TO_OBJECT} and edge.target.startswith("http")
        ]
        return _dedupe_tuples(objects)

    def _events_for_creator(self, uri: str) -> list[tuple[str, str]]:
        events = [
            (edge.source, edge.predicate)
            for edge in self._incoming(uri)
            if edge.predicate == PRODUCTION_TO_CREATOR and edge.source.startswith("http")
        ]
        events.extend(
            (edge.target, edge.predicate)
            for edge in self._outgoing(uri)
            if edge.predicate == CREATOR_TO_PRODUCTION and edge.target.startswith("http")
        )
        return _dedupe_tuples(events)

    def _creators_for_event(self, event_uri: str) -> list[tuple[str, str]]:
        creators = [
            (edge.target, edge.predicate)
            for edge in self._outgoing(event_uri)
            if edge.predicate == PRODUCTION_TO_CREATOR and edge.target.startswith("http")
        ]
        creators.extend(
            (edge.source, edge.predicate)
            for edge in self._incoming(event_uri)
            if edge.predicate == CREATOR_TO_PRODUCTION and edge.source.startswith("http")
        )
        return _dedupe_tuples(creators)

    def _label_for_graph_uri(self, uri: str) -> str:
        node = self.graph.nodes.get(uri)
        if node and node.labels:
            return node.labels[0]
        return self.label_by_uri.get(uri, "")

    def _fact_for_value(self, value: str) -> str:
        if value.startswith("http"):
            label = self._label_for_graph_uri(value) or value
            return _format_fact(_semantic_fact_type_for_uri(value), label)
        return _format_fact("Entity", value)

    def _explanation_facts_for_shared_value(self, value: str, main_uri: str, candidate_uri: str) -> list[str]:
        if not value.startswith("http") or self._is_meaningful_explanation_uri(value):
            return [self._fact_for_value(value)]
        facts = [
            fact
            for fact in self._meaningful_neighbor_facts(value)
            if main_uri not in fact and candidate_uri not in fact
        ]
        return facts[:4]

    @lru_cache(maxsize=500_000)
    def _meaningful_neighbor_facts(self, uri: str) -> tuple[str, ...]:
        node = self.graph.nodes.get(uri)
        if not node:
            return ()
        edge_indexes = [*node.outgoing, *node.incoming]
        if len(edge_indexes) > 200:
            return ()
        facts: list[str] = []
        for edge_index in edge_indexes:
            edge = self.graph.edges[edge_index]
            if edge.predicate == RDF_TYPE:
                continue
            for value in (edge.source, edge.target):
                if value == uri or not value.startswith("http"):
                    continue
                if self._is_meaningful_explanation_uri(value):
                    facts.append(self._fact_for_value(value))
        return tuple(_dedupe(facts))

    def _is_meaningful_explanation_uri(self, uri: str) -> bool:
        types = self._rdf_types(uri)
        if types.intersection(TECHNICAL_EXPLANATION_TYPES):
            return False
        label = (self._label_for_graph_uri(uri) or "").casefold()
        if label in CATALOG_RECORD_LABELS:
            return False
        return bool(types.intersection(PERSON_OR_ACTOR_TYPES | OBJECT_TYPES | PLACE_TYPES | EVENT_TYPES | {CIDOC + "E74_Group"}))

    def _rdf_types(self, uri: str) -> set[str]:
        node = self.graph.nodes.get(uri)
        return set(node.rdf_types) if node else set()

    @lru_cache(maxsize=500_000)
    def _values_by_predicate(self, uri: str, predicates: frozenset[str]) -> dict[str, set[str]]:
        predicate_set = set(predicates)
        values: dict[str, set[str]] = defaultdict(set)
        for edge in self._outgoing(uri):
            if edge.predicate in predicate_set:
                values[edge.predicate].add(edge.target)
        return values

    @lru_cache(maxsize=500_000)
    def _connected_values(self, uri: str) -> dict[str, tuple[Edge, ...]]:
        grouped: dict[str, list[Edge]] = defaultdict(list)
        for edge in self._outgoing(uri):
            if edge.predicate != RDF_TYPE:
                grouped[edge.target].append(edge)
        for edge in self._incoming(uri):
            if edge.predicate != RDF_TYPE:
                grouped[edge.source].append(edge)
        return {value: tuple(edges) for value, edges in grouped.items()}

    @lru_cache(maxsize=500_000)
    def _touching_edges_by_value(self, uri: str) -> dict[str, tuple[Edge, ...]]:
        grouped: dict[str, list[Edge]] = defaultdict(list)
        for edge in [*self._outgoing(uri), *self._incoming(uri)]:
            if edge.predicate == RDF_TYPE:
                continue
            grouped[edge.target].append(edge)
            if edge.source != edge.target:
                grouped[edge.source].append(edge)
        return {value: tuple(edges) for value, edges in grouped.items()}

    def _outgoing(self, uri: str) -> list[Edge]:
        node = self.graph.nodes.get(uri)
        if not node:
            return []
        return [self.graph.edges[index] for index in node.outgoing]

    def _incoming(self, uri: str) -> list[Edge]:
        node = self.graph.nodes.get(uri)
        if not node:
            return []
        return [self.graph.edges[index] for index in node.incoming]

    def _candidate_count(self, requested: int) -> int:
        if hasattr(self.artifacts.index, "get_current_count"):
            return max(1, min(requested, int(self.artifacts.index.get_current_count())))
        return requested


def _batches(values: list[str], batch_size: int) -> list[list[str]]:
    return [values[index : index + batch_size] for index in range(0, len(values), batch_size)]


def _put_rule(rules: dict[str, dict[str, list[str]]], reason: str, matches: dict[str, list[str]]) -> None:
    if matches:
        rules[reason] = matches


def _format_edge(edge: Edge) -> str:
    return f"{edge.source} {edge.predicate} {edge.target}"


def _format_fact(semantic_type: str, label: str) -> str:
    return f"fact:{semantic_type}:{label}"


def _semantic_fact_type_for_uri(uri: str) -> str:
    tail = uri.rsplit("#", 1)[-1].split("_", 1)[0]
    if tail in {"NE1", "NE2"}:
        return "Event"
    return {
        "E5": "Event",
        "E7": "Event",
        "E11": "Event",
        "E21": "Person",
        "E22": "Object",
        "E39": "Actor",
        "E52": "Time",
        "E53": "Place",
        "E55": "Type",
        "E74": "Institution",
    }.get(tail, "Entity")


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _dedupe_tuples(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return list(dict.fromkeys(values))


def _merge_retrieved(existing: RetrievedCandidate | None, incoming: RetrievedCandidate) -> RetrievedCandidate:
    if existing is None:
        return incoming
    return incoming if incoming.distance < existing.distance else existing


def _rank_recommendations(recommendations: list[OriginalCandidate]) -> list[OriginalCandidate]:
    nearest = sorted(recommendations, key=_distance_rank_key)
    nearest_uris = {candidate.uri for candidate in nearest[:2]}
    richer = sorted(
        [candidate for candidate in recommendations if candidate.uri not in nearest_uris],
        key=_semantic_rank_key,
    )
    top_four = [*nearest[:2], *richer[:2]]
    top_four_uris = {candidate.uri for candidate in top_four}
    remainder = [candidate for candidate in nearest if candidate.uri not in top_four_uris]
    return [*top_four, *remainder]


def _distance_rank_key(candidate: OriginalCandidate) -> tuple[float, int, str]:
    return (candidate.distance, candidate.hnsw_rank, candidate.label.casefold())


def _semantic_rank_key(candidate: OriginalCandidate) -> tuple[int, int, float, int, str]:
    explanation_reasons = [reason for reason in candidate.recommendation_reason if reason != "person_or_actor"]
    evidence_count = sum(len(paths) for reason, paths in candidate.rdf_paths_by_reason.items() if reason != "person_or_actor")
    return (-len(explanation_reasons), -evidence_count, candidate.distance, candidate.hnsw_rank, candidate.label.casefold())


def _dedupe_ints(values: list[int]) -> list[int]:
    return list(dict.fromkeys(values))


def _year_from_value(value: str) -> int | None:
    try:
        return int(str(value).split("-", 1)[0])
    except (TypeError, ValueError):
        return None
