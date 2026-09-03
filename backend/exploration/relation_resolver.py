from __future__ import annotations

from dataclasses import dataclass

from backend.data.graph.constants import (
    P100_WAS_DEATH_OF,
    P102_HAS_TITLE,
    P102I_IS_TITLE_OF,
    P108_HAS_PRODUCED,
    P11_HAD_PARTICIPANT,
    P11I_PARTICIPATED_IN,
    P14_CARRIED_OUT_BY,
    P128_CARRIES,
    P129I_IS_SUBJECT_OF,
    P14I_PERFORMED,
    P4I_IS_TIME_SPAN_OF,
    P1I_IDENTIFIES,
    P2I_IS_TYPE_OF,
    P7I_WITNESSED,
    P94_HAS_CREATED,
    P98_BROUGHT_INTO_LIFE,
)
from backend.data.graph.models import Edge
from backend.data.label_resolver import LabelResolver
from backend.data.semantic_resolver import SemanticProfile
from backend.data.text import uri_tail


@dataclass(frozen=True, slots=True)
class PredicateLabels:
    forward: str
    reverse: str


@dataclass(frozen=True, slots=True)
class ResolvedRelation:
    display_label: str
    direction: str
    category: str
    confidence: int
    symmetric: bool
    explanation: str


RELATION_LABELS = {
    P11_HAD_PARTICIPANT: PredicateLabels("had participant", "participated in"),
    P11I_PARTICIPATED_IN: PredicateLabels("participated in", "had participant"),
    P14_CARRIED_OUT_BY: PredicateLabels("carried out by", "carried out"),
    P14I_PERFORMED: PredicateLabels("performed", "performed by"),
    P98_BROUGHT_INTO_LIFE: PredicateLabels("brought into life", "was born in"),
    P100_WAS_DEATH_OF: PredicateLabels("was death of", "died in"),
    P108_HAS_PRODUCED: PredicateLabels("produced", "was produced by"),
    P94_HAS_CREATED: PredicateLabels("created", "created by"),
    P102_HAS_TITLE: PredicateLabels("has title", "is title of"),
    P102I_IS_TITLE_OF: PredicateLabels("is title of", "has title"),
    P128_CARRIES: PredicateLabels("carries", "is carried by"),
    P129I_IS_SUBJECT_OF: PredicateLabels("is described in", "describes"),
    P1I_IDENTIFIES: PredicateLabels("identifies", "is identified by"),
    P2I_IS_TYPE_OF: PredicateLabels("classifies", "is classified as"),
    P7I_WITNESSED: PredicateLabels("witnessed", "was witnessed at"),
}


class RelationResolver:
    def __init__(self, labels: LabelResolver) -> None:
        self.labels = labels

    def resolve(
        self,
        source_uri: str,
        target_uri: str,
        path: tuple[Edge, ...],
        source_profile: SemanticProfile,
        target_profile: SemanticProfile,
        confidence: int,
    ) -> ResolvedRelation:
        if not path:
            return ResolvedRelation(
                display_label="is related to",
                direction="undirected",
                category=target_profile.category,
                confidence=confidence,
                symmetric=True,
                explanation="No RDF path was available for this connection.",
            )

        direct = self._direct_relation(source_uri, path)
        if direct:
            label = self._contextual_label(direct.display_label, source_profile, target_profile)
            return ResolvedRelation(
                display_label=label,
                direction=direct.direction,
                category=target_profile.category,
                confidence=confidence,
                symmetric=False,
                explanation=self._explain(path, label),
            )

        bridged = self._bridged_relation(path, source_profile, target_profile)
        if bridged:
            label, direction, symmetric = bridged
            return ResolvedRelation(
                display_label=label,
                direction=direction,
                category=target_profile.category,
                confidence=max(confidence - 5, 1),
                symmetric=symmetric,
                explanation=self._explain(path, label),
            )

        fallback = self._ontology_fallback(source_uri, path[0])
        return ResolvedRelation(
            display_label=fallback.display_label,
            direction=fallback.direction,
            category=target_profile.category,
            confidence=max(confidence - 20, 1),
            symmetric=False,
            explanation=self._explain(path, fallback.display_label),
        )

    def _direct_relation(self, source_uri: str, path: tuple[Edge, ...]) -> ResolvedRelation | None:
        if len(path) != 1:
            return None
        edge = path[0]
        labels = RELATION_LABELS.get(edge.predicate)
        if not labels:
            return None
        if edge.source == source_uri:
            return ResolvedRelation(labels.forward, "outgoing", "Other", 100, False, "")
        return ResolvedRelation(labels.reverse, "incoming", "Other", 100, False, "")

    def _bridged_relation(
        self,
        path: tuple[Edge, ...],
        source_profile: SemanticProfile,
        target_profile: SemanticProfile,
    ) -> tuple[str, str, bool] | None:
        predicates = [edge.predicate for edge in path]

        if (
            P94_HAS_CREATED in predicates
            and (P14I_PERFORMED in predicates or P14_CARRIED_OUT_BY in predicates)
            and P128_CARRIES in predicates
        ):
            if source_profile.semantic_type in {"Person", "Actor", "Institution"} and target_profile.semantic_type == "Object":
                return "created", "outgoing", False
            if source_profile.semantic_type == "Object" and target_profile.semantic_type in {"Person", "Actor", "Institution"}:
                return "created by", "incoming", False

        if P129I_IS_SUBJECT_OF in predicates or P128_CARRIES in predicates:
            if source_profile.semantic_type in {"Object", "Document"}:
                return "describes", "outgoing", False
            if target_profile.semantic_type in {"Object", "Document"}:
                return "is described in", "incoming", False
            return "appears in the same described context as", "undirected", True

        if P2I_IS_TYPE_OF in predicates:
            if source_profile.semantic_type == "Type":
                return "classifies", "outgoing", False
            if target_profile.semantic_type == "Type":
                return "is classified as", "incoming", False
            return "shares classification with", "undirected", True

        if (
            P108_HAS_PRODUCED in predicates
            or P94_HAS_CREATED in predicates
            or P14I_PERFORMED in predicates
            or P14_CARRIED_OUT_BY in predicates
        ):
            if P128_CARRIES in predicates and source_profile.semantic_type == "Object" and target_profile.semantic_type in {"Person", "Actor", "Institution"}:
                return "created by", "incoming", False
            if source_profile.semantic_type in {"Person", "Actor", "Institution"}:
                return "created", "outgoing", False
            if target_profile.semantic_type in {"Person", "Actor", "Institution"}:
                return "created by", "incoming", False
            return "created", "outgoing", False

        if P98_BROUGHT_INTO_LIFE in predicates:
            if P4I_IS_TIME_SPAN_OF in predicates:
                return "birth date", "outgoing", False
            if P7I_WITNESSED in predicates and source_profile.semantic_type == "Person" and target_profile.semantic_type == "Place":
                return "born in", "outgoing", False
            if P7I_WITNESSED in predicates and source_profile.semantic_type == "Place" and target_profile.semantic_type == "Person":
                return "birthplace of", "incoming", False
            if source_profile.semantic_type == "Person":
                return "was born in", "outgoing", False
            if target_profile.semantic_type == "Person":
                return "birth place of", "incoming", False
            return "is connected by birth event to", "undirected", True

        if P100_WAS_DEATH_OF in predicates:
            if P4I_IS_TIME_SPAN_OF in predicates:
                return "death date", "outgoing", False
            if P7I_WITNESSED in predicates and source_profile.semantic_type == "Person" and target_profile.semantic_type == "Place":
                return "died in", "outgoing", False
            if P7I_WITNESSED in predicates and source_profile.semantic_type == "Place" and target_profile.semantic_type == "Person":
                return "death place of", "incoming", False
            if source_profile.semantic_type == "Person":
                return "died in", "outgoing", False
            if target_profile.semantic_type == "Person":
                return "death place of", "incoming", False
            return "is connected by death event to", "undirected", True

        if P11_HAD_PARTICIPANT in predicates or P11I_PARTICIPATED_IN in predicates:
            return "participated with", "undirected", True

        if P102_HAS_TITLE in predicates or P102I_IS_TITLE_OF in predicates:
            if source_profile.semantic_type == "Object":
                return "has title", "outgoing", False
            if target_profile.semantic_type == "Object":
                return "is title of", "incoming", False
            return "shares title context with", "undirected", True

        if P1I_IDENTIFIES in predicates:
            return "is identified with", "undirected", True

        return None

    def _ontology_fallback(self, source_uri: str, edge: Edge) -> ResolvedRelation:
        label = self.labels.predicate_label(edge.predicate)
        if not label or label == uri_tail(edge.predicate):
            label = "is related to"
        if edge.source == source_uri:
            return ResolvedRelation(label, "outgoing", "Other", 30, False, "")
        return ResolvedRelation(f"is {label}", "incoming", "Other", 30, False, "")

    def _contextual_label(self, label: str, source_profile: SemanticProfile, target_profile: SemanticProfile) -> str:
        if label == "is described in" and source_profile.semantic_type == "Object":
            return "describes"
        if label == "describes" and target_profile.semantic_type == "Object":
            return "is described in"
        return label

    def _explain(self, path: tuple[Edge, ...], label: str) -> str:
        predicates = " -> ".join(self.labels.predicate_label(edge.predicate) for edge in path)
        return f"Resolved as '{label}' from RDF path: {predicates}."
