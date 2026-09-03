from __future__ import annotations

import re
from dataclasses import dataclass

from backend.data.graph.constants import (
    CIDOC,
    E12_PRODUCTION,
    E33_LINGUISTIC_OBJECT,
    E65_CREATION,
    E67_BIRTH,
    E69_DEATH,
    P108_HAS_PRODUCED,
    P128_CARRIES,
    P14_CARRIED_OUT_BY,
    P14I_PERFORMED,
    P7I_WITNESSED,
    P94_HAS_CREATED,
)
from backend.data.graph.knowledge_graph import KnowledgeGraph
from backend.data.schemas import (
    ExplanationEvidence,
    EntityRef,
    RdfPathStep,
    Recommendation,
    RecommendationDebugExplanation,
    RecommendationExplanation,
    RecommendationReason,
)
from backend.data.label_resolver import LabelResolver
from backend.data.semantic_resolver import SemanticResolver


GENERIC_MEANINGFUL_RELATIONSHIP = "The knowledge graph records a meaningful historical relationship between these entities."
FILTER_ONLY_REASON_TYPES = frozenset({"person_or_actor"})

REASON_TITLES = {
    "same_creator": "Shared creator",
    "created_by": "Creator or producer of this object",
    "created_object": "Object created by this person",
    "same_created_object": "Connected through produced works",
    "same_content_creator": "Shared content responsibility",
    "content_created_by": "Creator of the carried content",
    "same_production": "Shared production context",
    "same_event": "Common historical event",
    "same_subject": "Shared subject",
    "same_collection": "Shared collection",
    "same_location": "Shared place",
    "same_type": "Similar historical category",
    "historical_proximity": "Shared historical period",
    "same_collaborator": "Shared collaborator",
    "born_here": "Shared birthplace",
    "died_here": "Shared death place",
    "active_here": "Activity in this place",
    "object_created_here": "Object produced here",
    "event_located_here": "Event in this place",
    "related_place": "Related place",
    "object_of_type": "Objects in the same historical category",
    "entity_of_type": "Entity in this historical category",
    "person_associated_with_type": "Person associated with this category",
    "event_associated_with_type": "Event associated with this category",
    "related_semantic_type": "Similar historical category",
    "common_place": "Common place",
    "common_event": "Common historical event",
    "common_production": "Common production activity",
    "common_collaborator": "Common collaborator",
    "published_by_actor": "Published by this actor",
    "actor_publication": "Object produced by this actor",
    "direct_semantic_relation": "Direct graph relationship",
    "automatic_rdf_path": "Meaningful graph connection",
    "target_connection": "Direct target connection",
    "same_objects_connection": "Shared object connection",
    "same_events": "Shared event connection",
    "same_identification": "Shared identifier",
    "same_occurs_in": "Shared referenced context",
    "same_place_of_birth": "Shared birthplace",
    "close_birth": "Nearby birth date",
    "close_death": "Nearby death date",
}


TYPE_AWARE_REASON_LABELS = {
    ("same_created_object", "Person", "Person"): (
        "Connected through produced works",
        "Both people are connected through the same produced works recorded in the knowledge graph.",
    ),
    ("same_created_object", "Person", "Object"): (
        "Connected through production",
        "This person is connected to the recommended object through its production.",
    ),
    ("same_created_object", "Object", "Object"): (
        "Shared production context",
        "Both objects were created through the same production context.",
    ),
    ("same_created_object", "Institution", "Object"): (
        "Institution connected to production",
        "This institution is connected to the production of the recommended object.",
    ),
    ("same_creator", "Object", "Object"): (
        "Shared creator",
        "Both objects share the same creator.",
    ),
    ("same_creator", "Person", "Object"): (
        "Creator of the recommended object",
        "This person is the creator of the recommended object.",
    ),
    ("same_location", "Person", "Person"): (
        "Shared historical place",
        "Both people are connected to the same historical place.",
    ),
    ("same_location", "Object", "Object"): (
        "Shared place",
        "Both objects are associated with the same place.",
    ),
    ("same_location", "Place", "Person"): (
        "Person connected to this place",
        "This person is historically connected to this place.",
    ),
}

PREDICATE_LABELS = {
    CIDOC + "P108_has_produced": "Produced",
    CIDOC + "P14_carried_out_by": "Carried out by",
    CIDOC + "P14i_performed": "Performed",
    CIDOC + "P128_carries": "Carries content",
    CIDOC + "P94_has_created": "Created content",
    CIDOC + "P2i_is_type_of": "Classifies",
    CIDOC + "P2_has_type": "Has type",
    CIDOC + "P7i_witnessed": "Took place in",
    CIDOC + "P7_took_place_at": "Took place at",
    CIDOC + "P98_brought_into_life": "Brought person into life",
    CIDOC + "P100_was_death_of": "Was death of",
    CIDOC + "P11i_participated_in": "Participated in",
    CIDOC + "P11_had_participant": "Had participant",
    CIDOC + "P129i_is_subject_of": "Is subject of",
    CIDOC + "P129_is_about": "Is about",
    CIDOC + "P45i_is_incorporated_in": "Is incorporated in",
}


@dataclass(frozen=True, slots=True)
class Triple:
    source: str
    predicate: str
    target: str


class RecommendationExplainer:
    def __init__(self, graph: KnowledgeGraph, labels: LabelResolver, semantics: SemanticResolver) -> None:
        self.graph = graph
        self.labels = labels
        self.semantics = semantics

    def explain(self, current_uri: str, recommendation: Recommendation) -> RecommendationExplanation:
        semantic_reasons = [reason for reason in recommendation.reasons if reason.type not in FILTER_ONLY_REASON_TYPES and reason.type != "embedding_similarity"]
        ordered_reasons = semantic_reasons
        evidence = _dedupe_supporting_evidence(
            [self._evidence_for(current_uri, recommendation, reason) for reason in ordered_reasons]
        )
        embedding = next((reason for reason in recommendation.reasons if reason.type == "embedding_similarity"), None)
        semantic_contribution = round(sum(reason.contribution for reason in semantic_reasons), 4)
        return RecommendationExplanation(
            summary=self._summary(current_uri, recommendation, evidence),
            evidence=evidence,
            debug=RecommendationDebugExplanation(
                embedding_contribution=embedding.contribution if embedding else 0.0,
                semantic_contribution=semantic_contribution,
                rule_weights={reason.type: reason.weight for reason in recommendation.reasons},
                raw_rdf_paths={reason.type: reason.rdf_path for reason in recommendation.reasons if reason.rdf_path},
            ),
        )

    def _evidence_for(self, current_uri: str, recommendation: Recommendation, reason: RecommendationReason) -> ExplanationEvidence:
        current_type = self._entity_type_label(current_uri)
        recommended_type = recommendation.semantic_type
        title, description = _reason_label(reason.type, current_type, recommended_type)
        if reason.type == "automatic_rdf_path":
            automatic = self._automatic_path_explanation(current_uri, recommendation, reason)
            if automatic:
                title, description = automatic
        path_steps: list[RdfPathStep] = []
        for raw_path in reason.rdf_path:
            for triple in _parse_path(raw_path):
                step = RdfPathStep(
                    source=self._explain_entity(triple.source),
                    predicate_uri=triple.predicate,
                    predicate_label=self._predicate_label(triple),
                    target=self._explain_entity(triple.target),
                )
                path_steps.append(step)
        current_label = _readable_label(self.labels.label_for(current_uri), "the currently viewed entity")
        recommended_label = _readable_label(recommendation.label, "the recommended entity")
        fact_description = _fallback_fact_description(reason.type, current_label, recommended_label, current_type, recommended_type)
        if fact_description:
            description = fact_description
        return ExplanationEvidence(
            type=reason.type,
            title=title,
            description=description,
            weight=reason.weight,
            contribution=reason.contribution,
            rdf_path=path_steps,
        )

    def _automatic_path_explanation(
        self,
        current_uri: str,
        recommendation: Recommendation,
        reason: RecommendationReason,
    ) -> tuple[str, str] | None:
        triples = [triple for raw_path in reason.rdf_path for triple in _parse_path(raw_path)]
        if not triples:
            return None
        predicates = {triple.predicate for triple in triples}
        current_type = self._entity_type_label(current_uri)
        recommended_type = recommendation.semantic_type
        technical_types = {
            uri: self._technical_type(uri)
            for triple in triples
            for uri in (triple.source, triple.target)
            if uri.startswith("http")
        }
        has_creation = P94_HAS_CREATED in predicates
        has_production = P108_HAS_PRODUCED in predicates
        has_actor = bool({P14I_PERFORMED, P14_CARRIED_OUT_BY}.intersection(predicates))
        has_carried_content = P128_CARRIES in predicates
        has_place = P7I_WITNESSED in predicates
        has_creation_event = "Creation Event" in technical_types.values()
        has_production_event = "Production Event" in technical_types.values()

        if current_type in {"Person", "Actor", "Institution"} and recommended_type == "Object":
            if has_creation and has_carried_content:
                return ("Created object", "This entity is connected to the recommended object through a recorded creation activity.")
            if has_production:
                return ("Produced object", "This entity is connected to the recommended object through a recorded production activity.")
        if current_type == "Institution" and recommended_type == "Object" and (has_production or has_creation):
            return ("Produced by the institution", "This institution is connected to an activity that produced or published the recommended object.")
        if current_type == "Place" and recommended_type == "Object" and has_place and has_production:
            return ("Produced at this place", "This place is connected to the production of the recommended object.")
        if current_type == "Object" and recommended_type in {"Person", "Actor", "Institution"}:
            if has_creation and has_carried_content:
                return ("Creator of carried content", "The object carries content attributed to the recommended person or institution.")
            if has_production:
                return ("Produced by this actor", "The object is connected to a production activity involving the recommended person or institution.")
        if current_type == "Object" and recommended_type == "Object":
            if has_creation and has_carried_content:
                return ("Shared created content", "Both objects are connected through recorded content creation.")
            if has_production:
                return ("Shared production context", "Both objects are connected through production activity recorded in the knowledge graph.")
        if has_actor and has_creation_event and has_carried_content:
            return ("Published work", "The entities are connected through a recorded creation or publication context.")
        if has_production_event and has_place:
            return ("Shared production place", "The entities are connected through production activity associated with a recorded place.")
        return None

    def _entity_type_label(self, uri: str) -> str:
        profile = self.semantics.profile_for(uri)
        if profile:
            return profile.semantic_type
        return self._technical_type(uri)

    def _explain_entity(self, value: str) -> EntityRef | str:
        if not value.startswith("http"):
            return value
        profile = self.semantics.profile_for(value)
        if profile:
            return EntityRef(
                uri=value,
                label=_readable_label(profile.display_name, profile.semantic_type),
                semantic_type=profile.semantic_type,
                icon=profile.icon,
            )
        return EntityRef(
            uri=value,
            label=self._technical_label(value),
            semantic_type=self._technical_type(value),
            icon="circle-dot",
        )

    def _technical_label(self, uri: str) -> str:
        technical_id = _compact_uri_label(uri)
        node = self.graph.nodes.get(uri)
        if node:
            if E12_PRODUCTION in node.rdf_types:
                return f"Production Event ({technical_id})"
            if E65_CREATION in node.rdf_types:
                return f"Creation Event ({technical_id})"
            if E67_BIRTH in node.rdf_types:
                return f"Birth Event ({technical_id})"
            if E69_DEATH in node.rdf_types:
                return f"Death Event ({technical_id})"
            if E33_LINGUISTIC_OBJECT in node.rdf_types:
                return f"Linguistic Content ({technical_id})"
        label = self.labels.label_for(uri)
        return label if not re.match(r"^[A-Z]{1,3}\d*[_ ]", label) else f"RDF Node ({technical_id})"

    def _technical_type(self, uri: str) -> str:
        node = self.graph.nodes.get(uri)
        if not node:
            return "RDF Node"
        if E12_PRODUCTION in node.rdf_types:
            return "Production Event"
        if E65_CREATION in node.rdf_types:
            return "Creation Event"
        if E67_BIRTH in node.rdf_types:
            return "Birth Event"
        if E69_DEATH in node.rdf_types:
            return "Death Event"
        if E33_LINGUISTIC_OBJECT in node.rdf_types:
            return "Linguistic Content"
        return "RDF Node"

    def _predicate_label(self, triple: Triple) -> str:
        source_type = self._technical_type(triple.source)
        target_type = self._technical_type(triple.target)
        if triple.predicate == CIDOC + "P7i_witnessed" and target_type == "Birth Event":
            return "Birth took place in"
        if triple.predicate == CIDOC + "P7i_witnessed" and target_type == "Death Event":
            return "Death took place in"
        if triple.predicate == CIDOC + "P7i_witnessed" and target_type == "Production Event":
            return "Production took place in"
        if triple.predicate == CIDOC + "P108_has_produced" and source_type == "Production Event":
            return "Produced object"
        return PREDICATE_LABELS.get(triple.predicate, self.labels.predicate_label(triple.predicate).replace("_", " "))

    def _summary(self, current_uri: str, recommendation: Recommendation, evidence: list[ExplanationEvidence]) -> str:
        current_label = _readable_label(self.labels.label_for(current_uri), "the currently viewed entity")
        recommended_label = _readable_label(recommendation.label, "the recommended entity")
        if not evidence:
            return f"{recommended_label} does not have a recorded explanation for {current_label}."

        main = evidence[0]
        current_type = self._entity_type_label(current_uri)
        explanation = _recommendation_sentence(main.type, current_label, recommended_label, current_type, recommendation.semantic_type, main.title)
        supporting = [_supporting_sentence(item) for item in evidence[1:3]]
        supporting = [item for item in supporting if item]
        if supporting:
            explanation += f" Additional support comes from {_join_readable(supporting)}."
        return explanation


def _parse_path(raw_path: str) -> list[Triple]:
    triples: list[Triple] = []
    for segment in raw_path.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        if segment.startswith("fact:"):
            continue
        match = re.match(r"^(.*?)\s+(https?://\S+)\s+(.*)$", segment)
        if match:
            triples.append(Triple(match.group(1), match.group(2), match.group(3)))
    return triples


def _compact_uri_label(uri: str) -> str:
    compact = uri.rstrip("/#").rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    return compact or uri


def _reason_label(reason_type: str, source_type: str, target_type: str) -> tuple[str, str]:
    type_aware_label = TYPE_AWARE_REASON_LABELS.get((reason_type, source_type, target_type))
    if type_aware_label:
        return type_aware_label
    title = REASON_TITLES.get(reason_type, reason_type.replace("_", " ").capitalize())
    return title, GENERIC_MEANINGFUL_RELATIONSHIP


def _readable_label(label: str, fallback: str) -> str:
    if re.match(r"^(E|NE)\d+[_ -]", label):
        return fallback
    return label


def _dedupe_supporting_evidence(evidence: list[ExplanationEvidence]) -> list[ExplanationEvidence]:
    if not evidence:
        return evidence
    main = evidence[0]
    main_signature = _evidence_signature(main)
    deduped = [main]
    seen = {main_signature}
    for item in evidence[1:]:
        signature = _evidence_signature(item)
        if item.type == main.type or signature in seen:
            continue
        seen.add(signature)
        deduped.append(item)
    return deduped


def _evidence_signature(evidence: ExplanationEvidence) -> tuple[str, str]:
    paths = tuple((str(_endpoint_label(step.source)), step.predicate_uri, str(_endpoint_label(step.target))) for step in evidence.rdf_path)
    return (evidence.type, repr(paths))


def _endpoint_label(endpoint: EntityRef | str) -> str:
    return endpoint.label if isinstance(endpoint, EntityRef) else str(endpoint)


def _recommendation_sentence(
    reason_type: str,
    current_label: str,
    recommended_label: str,
    current_type: str,
    recommended_type: str,
    evidence_title: str = "",
) -> str:
    fallback_description = _fallback_fact_description(reason_type, current_label, recommended_label, current_type, recommended_type)
    if fallback_description:
        return f"{recommended_label} was recommended because {fallback_description[0].lower()}{fallback_description[1:]}"
    type_aware_description = TYPE_AWARE_REASON_LABELS.get((reason_type, current_type, recommended_type))
    if type_aware_description:
        return f"{recommended_label} was recommended because {type_aware_description[1][0].lower()}{type_aware_description[1][1:]}"
    if reason_type == "automatic_rdf_path":
        automatic_title = evidence_title.casefold() if evidence_title else ""
        if "created object" in automatic_title:
            return f"{recommended_label} was recommended because {current_label} is connected to it through a recorded creation path."
        if "produced object" in automatic_title or "produced by the institution" in automatic_title:
            return f"{recommended_label} was recommended because {current_label} is connected to it through a recorded production path."
        if "published work" in automatic_title:
            return f"{recommended_label} was recommended because the graph records a publication-style path from {current_label} to this work."
        if "produced at this place" in automatic_title or "shared production place" in automatic_title:
            return f"{recommended_label} was recommended because the graph records production activity connected with {current_label}."
        return f"{recommended_label} was recommended because the knowledge graph records a meaningful historical relationship between these entities."
    return f"{recommended_label} was recommended because the knowledge graph records a meaningful historical relationship between these entities."


def _supporting_sentence(evidence: ExplanationEvidence) -> str:
    return evidence.title.lower()


def _fallback_fact_description(
    reason_type: str,
    current_label: str,
    recommended_label: str,
    current_type: str,
    recommended_type: str,
) -> str | None:
    if reason_type in {"same_creator", "same_content_creator"}:
        return "The RDF evidence links these entities through a creator or producer relationship."
    if reason_type in {"created_by", "content_created_by"}:
        return f"{recommended_label} is recorded as a creator or producer connected with {current_label}."
    if reason_type in {"created_object", "actor_publication"}:
        return f"{recommended_label} is recorded as an object produced or published through activity connected with {current_label}."
    if reason_type in {"same_created_object", "same_production", "common_production"}:
        return "The RDF evidence links these entities through the same production activity."
    if reason_type in {"same_location", "common_place", "related_place"}:
        return f"The RDF evidence links {current_label} and {recommended_label} through a recorded place relationship."
    if reason_type == "born_here":
        return f"{recommended_label} is recorded with a birth event connected to {current_label}."
    if reason_type == "died_here":
        return f"{recommended_label} is recorded with a death event connected to {current_label}."
    if reason_type == "active_here":
        return f"{recommended_label} has recorded activity connected with {current_label}."
    if reason_type in {"object_created_here", "event_located_here"}:
        return f"{recommended_label} is connected with production or event activity at {current_label}."
    if reason_type in {"same_event", "common_event"}:
        return "The RDF evidence links these entities through the same recorded historical activity."
    if reason_type in {"same_collaborator", "common_collaborator"}:
        return "The RDF evidence links these entities through a common person or institution."
    if reason_type in {"same_subject", "same_collection"}:
        return "The RDF evidence links these entities through a shared subject or collection context."
    if reason_type in {"same_type", "object_of_type", "entity_of_type", "person_associated_with_type", "event_associated_with_type", "related_semantic_type"}:
        if current_type in {"Type", "Professional role", "Role", "Academic degree", "Field of study", "Language"}:
            return f"{recommended_label} is connected with the category '{current_label}'."
        if recommended_type in {"Type", "Professional role", "Role", "Academic degree", "Field of study", "Language"}:
            return f"{current_label} is connected with the category '{recommended_label}'."
        return "The RDF evidence links these entities through a shared classification."
    if reason_type == "direct_semantic_relation":
        return f"The RDF evidence records a direct relationship between {current_label} and {recommended_label}."
    if reason_type == "automatic_rdf_path":
        return f"The RDF path connects {current_label} and {recommended_label} through recorded historical relationships."
    if reason_type == "historical_proximity":
        return "The entities are supported by nearby recorded dates."
    if reason_type == "target_connection":
        return f"The RDF evidence records a direct relationship between {current_label} and {recommended_label}."
    if reason_type == "same_objects_connection":
        return "The RDF evidence links these entities through connected objects or production context."
    if reason_type == "same_events":
        return "The RDF evidence links these entities through shared recorded events."
    if reason_type == "same_identification":
        return "The RDF evidence links these entities through shared identifiers."
    if reason_type == "same_occurs_in":
        return "Both entities occur in similar recorded places or contexts."
    if reason_type == "same_place_of_birth":
        return "The RDF evidence links these people through the same recorded birthplace."
    if reason_type == "close_birth":
        return "The entities have nearby recorded birth dates."
    if reason_type == "close_death":
        return "The entities have nearby recorded death dates."
    return None


def _join_readable(values: list[str]) -> str:
    if len(values) == 1:
        return values[0]
    return f"{', '.join(values[:-1])} and {values[-1]}"
