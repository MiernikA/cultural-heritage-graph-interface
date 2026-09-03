import type { EntityRef, ExplanationEvidence } from "@/entities/entity";
import type { TFunction, TranslationKey } from "@/shared/i18n";

export function noEvidenceNarrative(t: TFunction) {
  return t("recommendation.evidence.none");
}

export function recommendationExplanationSentence(
  evidence: ExplanationEvidence,
  currentType: string,
  recommendedType: string,
  t: TFunction,
) {
  const genericSentence = evidenceNarrative(evidence.type, currentType, recommendedType, t);
  if (MAPPED_EVIDENCE_REASON_TYPES.has(evidence.type)) {
    return genericSentence;
  }

  return readableEvidenceDescription(evidence.description || genericSentence, t);
}

export function rdfStoryIntro(pathLength: number): TranslationKey {
  return pathLength === 1 ? "rdfPath.intro.direct" : "rdfPath.intro.chain";
}

export function pathSentence(
  step: { source: EntityRef | string; predicate_label: string; target: EntityRef | string },
  index: number,
  t: TFunction,
) {
  return t(index === 0 ? "rdfPath.step.first" : "rdfPath.step.next", {
    source: endpointLabel(step.source),
    relationship: relationshipPhrase(step.predicate_label, t),
    target: endpointLabel(step.target),
  });
}

export function semanticTone(type: string) {
  return type.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function evidenceNarrative(reasonType: string, currentType: string, recommendedType: string, t: TFunction) {
  const pair = `${normalizeType(currentType)}:${normalizeType(recommendedType)}`;
  return t(evidenceNarrativeKey(reasonType, pair));
}

function readableEvidenceDescription(description: string, t: TFunction) {
  const staticMatch = READABLE_EVIDENCE_STATIC_PATTERNS.find(([pattern]) => pattern.test(description));
  if (staticMatch) {
    return t(staticMatch[1]);
  }

  for (const [pattern, key] of READABLE_EVIDENCE_DYNAMIC_PATTERNS) {
    const match = description.match(pattern);
    if (match) {
      return t(key, { first: match[1], second: match[2] });
    }
  }

  return description;
}

function normalizeType(type: string) {
  return type.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function evidenceNarrativeKey(reasonType: string, pair: string): TranslationKey {
  switch (reasonType) {
    case "same_created_object":
      if (pair === "person:person" || pair === "actor:actor") {
        return "recommendation.evidence.sameCreatedObject.people";
      }
      if (pair.endsWith(":object")) {
        return "recommendation.evidence.sameCreatedObject.objectTarget";
      }
      if (pair === "object:object") {
        return "recommendation.evidence.sameCreatedObject.objects";
      }
      return "recommendation.evidence.sameCreatedObject.default";
    case "same_creator":
      return pair === "object:object" ? "recommendation.evidence.sameCreator.objects" : "recommendation.evidence.sameCreator.default";
    case "created_by":
    case "content_created_by":
      return "recommendation.evidence.createdBy";
    case "created_object":
    case "actor_publication":
    case "published_by_actor":
      return "recommendation.evidence.createdObject";
    case "same_content_creator":
      return "recommendation.evidence.sameContentCreator";
    case "same_production":
    case "common_production":
      return "recommendation.evidence.sameProduction";
    case "same_event":
    case "common_event":
      return "recommendation.evidence.sameEvent";
    case "same_subject":
      return "recommendation.evidence.sameSubject";
    case "same_collection":
      return "recommendation.evidence.sameCollection";
    case "same_location":
    case "common_place":
    case "related_place":
      return "recommendation.evidence.sameLocation";
    case "same_type":
    case "related_semantic_type":
    case "object_of_type":
    case "entity_of_type":
    case "person_associated_with_type":
    case "event_associated_with_type":
      return "recommendation.evidence.sameType";
    case "historical_proximity":
      return "recommendation.evidence.historicalProximity";
    case "target_connection":
    case "direct_semantic_relation":
      return "recommendation.evidence.targetConnection";
    case "same_objects_connection":
      return "recommendation.evidence.sameObjectsConnection";
    case "same_events":
      return "recommendation.evidence.sameEvents";
    case "same_identification":
      return "recommendation.evidence.sameIdentification";
    case "same_occurs_in":
      return "recommendation.evidence.sameOccursIn";
    case "same_place_of_birth":
      return "recommendation.evidence.samePlaceOfBirth";
    case "close_birth":
      return "recommendation.evidence.closeBirth";
    case "close_death":
      return "recommendation.evidence.closeDeath";
    case "same_collaborator":
    case "common_collaborator":
      return "recommendation.evidence.sameCollaborator";
    case "born_here":
      return "recommendation.evidence.bornHere";
    case "died_here":
      return "recommendation.evidence.diedHere";
    case "active_here":
      return "recommendation.evidence.activeHere";
    case "object_created_here":
      return "recommendation.evidence.objectCreatedHere";
    case "event_located_here":
      return "recommendation.evidence.eventLocatedHere";
    case "automatic_rdf_path":
      return "recommendation.evidence.automaticRdfPath";
    default:
      return "recommendation.evidence.default";
  }
}

function relationshipPhrase(predicate: string, t: TFunction) {
  const label = predicate.toLowerCase();
  if (label.includes("type") || label.includes("class") || label.includes("classified")) {
    return t("rdfPath.relationship.classified");
  }
  if (label.includes("creator") || label.includes("created") || label.includes("author")) {
    return t("rdfPath.relationship.creator");
  }
  if (label.includes("birth") || label.includes("born")) {
    return t("rdfPath.relationship.birthplace");
  }
  if (label.includes("location") || label.includes("place")) {
    return t("rdfPath.relationship.place");
  }
  if (label.includes("period") || label.includes("date")) {
    return t("rdfPath.relationship.period");
  }
  return t("rdfPath.relationship.fallback", { predicate: label });
}

function endpointLabel(value: EntityRef | string) {
  if (isExplanationEntity(value)) {
    return value.label;
  }
  return String(value);
}

function isExplanationEntity(value: unknown): value is EntityRef {
  return Boolean(value && typeof value === "object" && "label" in value && "semantic_type" in value);
}

const MAPPED_EVIDENCE_REASON_TYPES = new Set([
  "same_created_object",
  "same_creator",
  "created_by",
  "content_created_by",
  "created_object",
  "actor_publication",
  "published_by_actor",
  "same_content_creator",
  "same_production",
  "common_production",
  "same_event",
  "common_event",
  "same_subject",
  "same_collection",
  "same_location",
  "common_place",
  "related_place",
  "same_type",
  "related_semantic_type",
  "object_of_type",
  "entity_of_type",
  "person_associated_with_type",
  "event_associated_with_type",
  "historical_proximity",
  "target_connection",
  "same_objects_connection",
  "same_events",
  "same_identification",
  "same_occurs_in",
  "same_place_of_birth",
  "close_birth",
  "close_death",
  "same_collaborator",
  "common_collaborator",
  "born_here",
  "died_here",
  "active_here",
  "object_created_here",
  "event_located_here",
  "direct_semantic_relation",
  "automatic_rdf_path",
]);

const READABLE_EVIDENCE_STATIC_PATTERNS: Array<[RegExp, TranslationKey]> = [
  [/^The RDF evidence links these entities through a creator or producer relationship\.$/, "recommendation.readable.creatorProducer"],
  [/^The RDF evidence links these entities through the same production activity\.$/, "recommendation.readable.sameProduction"],
  [/^The RDF evidence links these entities through a common person or institution\.$/, "recommendation.readable.commonActor"],
  [/^The RDF evidence links these entities through a shared subject or collection context\.$/, "recommendation.readable.sharedSubject"],
  [/^The RDF evidence links these entities through a shared classification\.$/, "recommendation.readable.sharedClassification"],
];

const READABLE_EVIDENCE_DYNAMIC_PATTERNS: Array<[RegExp, TranslationKey]> = [
  [/^The RDF evidence links (.+) and (.+) through a recorded place relationship\.$/, "recommendation.readable.placeRelationship"],
  [/^The RDF evidence records a direct relationship between (.+) and (.+)\.$/, "recommendation.readable.directRelationship"],
  [/^The RDF path connects (.+) and (.+) through recorded historical relationships\.$/, "recommendation.readable.rdfPath"],
  [/^(.+) has recorded activity connected with (.+)\.$/, "recommendation.readable.activityPlace"],
];
