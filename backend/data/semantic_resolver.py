from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from backend.data.graph.constants import (
    CIDOC,
    E33_LINGUISTIC_OBJECT,
    E67_BIRTH,
    E69_DEATH,
    E35_TITLE,
    E41_APPELLATION,
    P01_HAS_DOMAIN,
    P02_HAS_RANGE,
    P100_WAS_DEATH_OF,
    P102_HAS_TITLE,
    P102I_IS_TITLE_OF,
    P108_HAS_PRODUCED,
    P11_HAD_PARTICIPANT,
    P11I_PARTICIPATED_IN,
    P14_CARRIED_OUT_BY,
    P128_CARRIES,
    P129I_IS_SUBJECT_OF,
    P14_1_IN_ROLE,
    P14I_PERFORMED,
    P1I_IDENTIFIES,
    P2I_IS_TYPE_OF,
    P4I_IS_TIME_SPAN_OF,
    P7I_WITNESSED,
    P82A_BEGIN,
    P82B_END,
    P94_HAS_CREATED,
    P98_BROUGHT_INTO_LIFE,
    TECHNICAL_TYPES,
)
from backend.data.graph.knowledge_graph import KnowledgeGraph
from backend.data.graph.models import Edge, Node
from backend.data.label_resolver import LabelResolver
from backend.data.semantic_catalog import (
    SemanticType,
    is_technical_type,
    is_user_facing_semantic_type,
    semantic_type_for,
)
from backend.data.text import is_uri, local_class_prefix, uri_tail


@dataclass(frozen=True, slots=True)
class SemanticPath:
    hint: str
    target_uri: str
    path: tuple[Edge, ...]
    confidence: int = 50


@dataclass(frozen=True, slots=True)
class SemanticProfile:
    uri: str
    display_name: str
    semantic_type: str
    description: str
    icon: str
    aliases: tuple[str, ...]
    category: str


class SemanticResolver:
    def __init__(self, graph: KnowledgeGraph, labels: LabelResolver) -> None:
        self.graph = graph
        self.labels = labels

    @lru_cache(maxsize=500_000)
    def profile_for(self, uri: str) -> SemanticProfile | None:
        uri = self.graph.canonical_uri(uri)
        node = self.graph.nodes.get(uri)
        if not node or not self.is_displayable_entity(uri):
            return None

        semantic_type = semantic_type_for(node.rdf_types, uri)
        display_name = self.labels.label_for(uri)
        aliases = tuple(label for label in node.labels if label != display_name)
        return SemanticProfile(
            uri=uri,
            display_name=display_name,
            semantic_type=semantic_type.label,
            description=self._description_for(uri, node, semantic_type),
            icon=semantic_type.icon,
            aliases=aliases[:8],
            category=semantic_type.category,
        )

    def is_technical_node(self, uri: str) -> bool:
        node = self.graph.nodes.get(uri)
        if not node:
            return False
        if is_technical_type(node.rdf_types, uri):
            return True
        if node.rdf_types.intersection(TECHNICAL_TYPES):
            return True
        return any(uri_tail(type_uri).startswith("PC") for type_uri in node.rdf_types)

    def is_displayable_entity(self, uri: str) -> bool:
        if not is_uri(uri) or not self.graph.is_described_entity(uri) or self.is_technical_node(uri):
            return False
        node = self.graph.nodes.get(self.graph.canonical_uri(uri))
        if not node:
            return False
        return is_user_facing_semantic_type(semantic_type_for(node.rdf_types, uri).label)

    def semantic_paths_for(self, uri: str, limit: int = 250) -> list[SemanticPath]:
        return list(self._semantic_paths_for(uri))[:limit]

    @lru_cache(maxsize=200_000)
    def _semantic_paths_for(self, uri: str) -> tuple[SemanticPath, ...]:
        uri = self.graph.canonical_uri(uri)
        node = self.graph.nodes.get(uri)
        if not node:
            return ()

        paths: list[SemanticPath] = []
        paths.extend(self._rule_based_paths(uri, node))
        paths.extend(self._bridged_paths(uri, node))
        paths.extend(self._direct_meaningful_paths(uri, node))
        return tuple(self._dedupe(paths))

    def _rule_based_paths(self, uri: str, node: Node) -> list[SemanticPath]:
        paths: list[SemanticPath] = []
        for edge in self._outgoing(node):
            if edge.predicate == P11I_PARTICIPATED_IN and edge.target_is_uri:
                event = self.graph.nodes.get(edge.target)
                if event:
                    paths.extend(self._event_counterparts(uri, event, "event path", edge))
            elif edge.predicate == P14I_PERFORMED and edge.target_is_uri:
                activity = self.graph.nodes.get(edge.target)
                if activity:
                    paths.extend(self._produced_objects(activity, "created", edge))
                    paths.extend(self._created_carried_objects(activity, "created", edge))
            elif edge.predicate == P102_HAS_TITLE and edge.target_is_uri:
                title = self._best_owner_from_title(edge.target, uri)
                if title:
                    paths.append(SemanticPath("has title", title, (edge,), 95))
            elif edge.predicate == P128_CARRIES and edge.target_is_uri:
                content = self.graph.nodes.get(edge.target)
                if content:
                    paths.extend(self._creators_of_carried_content(content, edge))

        for edge in self._incoming(node):
            source = self.graph.nodes.get(edge.source)
            if edge.predicate == P98_BROUGHT_INTO_LIFE:
                event = self.graph.nodes.get(edge.source)
                if event:
                    paths.extend(self._life_event_values(event, edge))
            elif edge.predicate == P100_WAS_DEATH_OF:
                event = self.graph.nodes.get(edge.source)
                if event:
                    paths.extend(self._life_event_values(event, edge))
            elif edge.predicate == P108_HAS_PRODUCED:
                production = self.graph.nodes.get(edge.source)
                if production:
                    paths.extend(self._production_performers(production, edge))
            elif edge.predicate == P102I_IS_TITLE_OF:
                paths.append(SemanticPath("title of", edge.source, (edge,), 95))
            elif edge.predicate == P1I_IDENTIFIES:
                paths.append(SemanticPath("identifies", edge.source, (edge,), 80))
            elif edge.predicate == P128_CARRIES and source:
                paths.append(SemanticPath("carries", edge.source, (edge,), 75))
            elif edge.predicate == P129I_IS_SUBJECT_OF and source:
                paths.append(SemanticPath("described by", edge.source, (edge,), 75))
        return paths

    def _event_counterparts(self, origin_uri: str, event: Node, relation: str, first_edge: Edge) -> list[SemanticPath]:
        paths: list[SemanticPath] = []
        for edge in self._outgoing(event):
            if edge.predicate in {P11_HAD_PARTICIPANT, P98_BROUGHT_INTO_LIFE, P100_WAS_DEATH_OF}:
                target_uri = self.graph.canonical_uri(edge.target) if edge.target_is_uri else edge.target
                if edge.target_is_uri and target_uri != origin_uri and self.is_displayable_entity(target_uri):
                    paths.append(SemanticPath(relation, target_uri, (first_edge, edge), 90))
            elif edge.predicate == P4I_IS_TIME_SPAN_OF:
                continue
        paths.extend(self._produced_objects(event, "created", first_edge))
        paths.extend(self._created_carried_objects(event, "created", first_edge))
        paths.extend(self._typed_values(event, first_edge))
        paths.extend(self._life_event_values(event, first_edge))
        return paths

    def _produced_objects(self, activity: Node, relation: str, first_edge: Edge) -> list[SemanticPath]:
        paths: list[SemanticPath] = []
        for edge in self._outgoing(activity):
            if edge.predicate == P108_HAS_PRODUCED and edge.target_is_uri:
                paths.append(SemanticPath(relation, self.graph.canonical_uri(edge.target), (first_edge, edge), 95))
            elif edge.predicate == P94_HAS_CREATED and edge.target_is_uri:
                target_uri = self.graph.canonical_uri(edge.target)
                if self.is_displayable_entity(target_uri):
                    paths.append(SemanticPath(relation, target_uri, (first_edge, edge), 90))
        return paths

    def _created_carried_objects(self, activity: Node, relation: str, first_edge: Edge) -> list[SemanticPath]:
        paths: list[SemanticPath] = []
        for edge in self._outgoing(activity):
            if edge.predicate != P94_HAS_CREATED or not edge.target_is_uri:
                continue
            content = self.graph.nodes.get(edge.target)
            if not content or E33_LINGUISTIC_OBJECT not in content.rdf_types:
                continue
            for carrier_edge in self._incoming(content):
                if carrier_edge.predicate != P128_CARRIES:
                    continue
                carrier_uri = self.graph.canonical_uri(carrier_edge.source)
                if self.is_displayable_entity(carrier_uri):
                    paths.append(SemanticPath(relation, carrier_uri, (first_edge, edge, carrier_edge), 90))
        return paths

    def _production_performers(self, activity: Node, first_edge: Edge) -> list[SemanticPath]:
        paths: list[SemanticPath] = []
        for edge in self._incoming(activity):
            source_uri = self.graph.canonical_uri(edge.source)
            if edge.predicate == P14I_PERFORMED and self.is_displayable_entity(source_uri):
                paths.append(SemanticPath("created by", source_uri, (first_edge, edge), 95))
        for edge in self._outgoing(activity):
            if edge.predicate == P14_CARRIED_OUT_BY and edge.target_is_uri:
                target_uri = self.graph.canonical_uri(edge.target)
                if self.is_displayable_entity(target_uri):
                    paths.append(SemanticPath("created by", target_uri, (first_edge, edge), 95))
        return paths

    def _creators_of_carried_content(self, content: Node, first_edge: Edge) -> list[SemanticPath]:
        paths: list[SemanticPath] = []
        if E33_LINGUISTIC_OBJECT not in content.rdf_types:
            return paths
        for creation_edge in self._incoming(content):
            if creation_edge.predicate != P94_HAS_CREATED:
                continue
            creation = self.graph.nodes.get(creation_edge.source)
            if not creation:
                continue
            for performer_edge in self._incoming(creation):
                source_uri = self.graph.canonical_uri(performer_edge.source)
                if performer_edge.predicate == P14I_PERFORMED and self.is_displayable_entity(source_uri):
                    paths.append(SemanticPath("created by", source_uri, (first_edge, creation_edge, performer_edge), 90))
            for performer_edge in self._outgoing(creation):
                if performer_edge.predicate != P14_CARRIED_OUT_BY or not performer_edge.target_is_uri:
                    continue
                target_uri = self.graph.canonical_uri(performer_edge.target)
                if self.is_displayable_entity(target_uri):
                    paths.append(SemanticPath("created by", target_uri, (first_edge, creation_edge, performer_edge), 90))
        return paths

    def _typed_values(self, activity: Node, first_edge: Edge) -> list[SemanticPath]:
        relations = {
            "NP2i_is_educational_activity_type_of": "studied",
            "NP1i_is_occupational_activity_type_of": "worked as",
            "NP3i_is_academic_degree_of": "earned degree",
            "NP4i_is_field_of_study_of": "field of study",
            "NP5i_is_professional_role_of": "professional role",
        }
        paths: list[SemanticPath] = []
        for edge in self._incoming(activity):
            tail = uri_tail(edge.predicate).replace(" ", "_")
            relation = relations.get(tail)
            if relation and self.is_displayable_entity(edge.source):
                paths.append(SemanticPath(relation, edge.source, (first_edge, edge), 85))
        return paths

    def _life_event_values(self, event: Node, first_edge: Edge) -> list[SemanticPath]:
        if E67_BIRTH in event.rdf_types:
            time_relation = "birth date"
            place_relation = "born in"
        elif E69_DEATH in event.rdf_types:
            time_relation = "death date"
            place_relation = "died in"
        else:
            return []

        paths: list[SemanticPath] = []
        for edge in self._incoming(event):
            if edge.predicate == P4I_IS_TIME_SPAN_OF and self.is_displayable_entity(edge.source):
                paths.append(SemanticPath(time_relation, edge.source, (first_edge, edge), 95))
            elif edge.predicate == P7I_WITNESSED and self.is_displayable_entity(edge.source):
                paths.append(SemanticPath(place_relation, edge.source, (first_edge, edge), 95))
        return paths

    def _bridged_paths(self, origin_uri: str, node: Node) -> list[SemanticPath]:
        paths: list[SemanticPath] = []
        paths.extend(self._same_described_context_paths(origin_uri, node))
        return paths

    def _same_described_context_paths(self, origin_uri: str, node: Node) -> list[SemanticPath]:
        paths: list[SemanticPath] = []
        context_predicates = {P128_CARRIES, P129I_IS_SUBJECT_OF}

        for first_edge in self._outgoing(node):
            if first_edge.predicate == P7I_WITNESSED and first_edge.target_is_uri:
                event = self.graph.nodes.get(first_edge.target)
                if event:
                    paths.extend(self._place_life_event_people(event, first_edge))
            if first_edge.predicate not in context_predicates or not first_edge.target_is_uri:
                continue
            context = self.graph.nodes.get(first_edge.target)
            if not context or not self.is_technical_node(context.uri):
                continue

            for peer_edge in self._incoming(context)[:180]:
                if peer_edge.predicate not in context_predicates:
                    continue
                target_uri = self.graph.canonical_uri(peer_edge.source)
                if target_uri != origin_uri and self.is_displayable_entity(target_uri):
                    paths.append(SemanticPath("shared described context", target_uri, (first_edge, peer_edge), 80))
        return paths

    def _place_life_event_people(self, event: Node, first_edge: Edge) -> list[SemanticPath]:
        if E67_BIRTH in event.rdf_types:
            predicate = P98_BROUGHT_INTO_LIFE
            relation = "birthplace of"
        elif E69_DEATH in event.rdf_types:
            predicate = P100_WAS_DEATH_OF
            relation = "death place of"
        else:
            return []

        paths: list[SemanticPath] = []
        for edge in self._outgoing(event):
            target_uri = self.graph.canonical_uri(edge.target) if edge.target_is_uri else edge.target
            if edge.predicate == predicate and edge.target_is_uri and self.is_displayable_entity(target_uri):
                paths.append(SemanticPath(relation, target_uri, (first_edge, edge), 95))
        return paths

    def _direct_meaningful_paths(self, uri: str, node: Node) -> list[SemanticPath]:
        paths: list[SemanticPath] = []
        skip = {
            P01_HAS_DOMAIN,
            P02_HAS_RANGE,
            P14_1_IN_ROLE,
            P82A_BEGIN,
            P82B_END,
        }
        for edge in self._outgoing(node):
            if edge.predicate in skip or not edge.target_is_uri:
                continue
            target_uri = self.graph.canonical_uri(edge.target)
            if self.is_displayable_entity(target_uri):
                paths.append(SemanticPath("direct edge", target_uri, (edge,), 65))
        for edge in self._incoming(node):
            if edge.predicate in skip:
                continue
            source_uri = self.graph.canonical_uri(edge.source)
            if self.is_displayable_entity(source_uri):
                paths.append(SemanticPath("direct edge", source_uri, (edge,), 65))
        return paths

    def _best_owner_from_title(self, title_uri: str, origin_uri: str) -> str | None:
        title = self.graph.nodes.get(title_uri)
        if not title:
            return None
        for edge in [*self._outgoing(title), *self._incoming(title)]:
            candidate = edge.target if edge.source == title_uri else edge.source
            if candidate != origin_uri and self.is_displayable_entity(candidate):
                return candidate
        return None

    def _description_for(self, uri: str, node: Node, semantic_type: SemanticType) -> str:
        if semantic_type.label != "Entity":
            return semantic_type.description
        type_labels = [self.labels.predicate_label(type_uri) for type_uri in sorted(node.rdf_types)]
        readable_types = [label for label in type_labels if label and not label.startswith("E")]
        if readable_types:
            return f"{', '.join(readable_types[:2])} in the knowledge graph."
        return f"Described {local_class_prefix(uri)} entity in the knowledge graph."

    def _outgoing(self, node: Node) -> list[Edge]:
        return [self.graph.edges[index] for index in node.outgoing]

    def _incoming(self, node: Node) -> list[Edge]:
        return [self.graph.edges[index] for index in node.incoming]

    def _dedupe(self, paths: list[SemanticPath]) -> list[SemanticPath]:
        seen: set[tuple[str, tuple[tuple[str, str, str], ...]]] = set()
        result: list[SemanticPath] = []
        for path in sorted(paths, key=lambda item: (-item.confidence, item.target_uri, item.hint)):
            key = (path.target_uri, tuple((edge.source, edge.predicate, edge.target) for edge in path.path))
            if key in seen:
                continue
            seen.add(key)
            result.append(path)
        return result
