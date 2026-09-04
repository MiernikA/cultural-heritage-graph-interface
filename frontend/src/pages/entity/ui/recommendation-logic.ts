import type { Recommendation } from "@/entities/entity";
import { semanticTypeLabel } from "@/entities/entity";
import type { TFunction, TranslationKey } from "@/shared/i18n";
import { recommendationExplanationSentence } from "../model/evidence";
import { translatedRelationLabel } from "./relationship-ui";
import type { RecommendationSortKey, SortDirection } from "./recommendation-types";

export function explanationSentences(
  evidence: NonNullable<Recommendation["explanation"]>["evidence"],
  currentType: string,
  recommendedType: string,
  t: TFunction,
) {
  return Array.from(
    new Set(
      evidence
        .map((item) => recommendationExplanationSentence(item, currentType, recommendedType, t))
        .filter((description) => Boolean(description.trim())),
    ),
  );
}

export function semanticReasonBadges(recommendation: Recommendation, currentType: string, t: TFunction, fallbackLabel: string) {
  const tags = recommendation.reason_tags
    .map((tag) => recommendationReasonLabel(tag, t))
    .filter((tag) => tag.trim())
    .slice(0, 3);
  if (tags.length > 0) {
    return tags;
  }
  return [recommendationReasonBadge(recommendation, currentType, t, fallbackLabel)];
}

export function sortRecommendations(
  recommendations: Recommendation[],
  sortKey: RecommendationSortKey,
  direction: SortDirection,
  currentType: string,
  language: string,
  t: TFunction,
  fallbackReasonLabel: string,
) {
  const multiplier = direction === "asc" ? 1 : -1;
  return [...recommendations].sort((a, b) => {
    if (sortKey === "distance") {
      return (a.semantic_similarity - b.semantic_similarity) * multiplier;
    }
    const aValue =
      sortKey === "semantic_type"
        ? semanticTypeLabel(a.semantic_type, t)
        : sortKey === "reason"
          ? recommendationReasonBadge(a, currentType, t, fallbackReasonLabel)
          : a.label;
    const bValue =
      sortKey === "semantic_type"
        ? semanticTypeLabel(b.semantic_type, t)
        : sortKey === "reason"
          ? recommendationReasonBadge(b, currentType, t, fallbackReasonLabel)
          : b.label;
    return aValue.localeCompare(bValue, language) * multiplier;
  });
}

export function formatRawDistance(distance: number) {
  return Number.isFinite(distance) ? distance.toString() : "-";
}

function recommendationReasonBadge(recommendation: Recommendation, currentType: string, t: TFunction, fallbackLabel: string) {
  const evidence = recommendation.explanation?.evidence ?? [];
  const firstEvidence = evidence.find((item) => item.title.trim() || item.description.trim());
  const title = firstEvidence ? recommendationReasonLabel(firstEvidence.type, t) : "";

  if (title) {
    return title;
  }

  const firstExplanation = explanationSentences(evidence, currentType, recommendation.semantic_type, t)[0];
  if (firstExplanation) {
    return firstExplanation.length > 82 ? `${firstExplanation.slice(0, 79).trim()}...` : firstExplanation;
  }

  return fallbackLabel;
}

export function recommendationReasonLabel(reason: string, t: TFunction) {
  const normalizedReason = reason.trim();
  const key = RECOMMENDATION_REASON_KEYS[normalizedReason];
  if (key) {
    return t(key);
  }

  const translatedRelation = translatedRelationLabel(normalizedReason, t);
  if (translatedRelation !== normalizedReason) {
    return translatedRelation;
  }

  return normalizedReason;
}

const RECOMMENDATION_REASON_KEYS: Record<string, TranslationKey> = {
  active_here: "recommendation.reason.activeHere",
  actor_publication: "recommendation.reason.actorPublication",
  automatic_rdf_path: "recommendation.reason.automaticRdfPath",
  born_here: "recommendation.reason.bornHere",
  close_birth: "recommendation.reason.closeBirth",
  close_death: "recommendation.reason.closeDeath",
  common_collaborator: "recommendation.reason.commonCollaborator",
  common_event: "recommendation.reason.commonEvent",
  common_place: "recommendation.reason.commonPlace",
  common_production: "recommendation.reason.commonProduction",
  content_created_by: "recommendation.reason.contentCreatedBy",
  created_by: "recommendation.reason.createdBy",
  created_object: "recommendation.reason.createdObject",
  died_here: "recommendation.reason.diedHere",
  direct_semantic_relation: "recommendation.reason.directSemanticRelation",
  entity_of_type: "recommendation.reason.entityOfType",
  event_associated_with_type: "recommendation.reason.eventAssociatedWithType",
  event_located_here: "recommendation.reason.eventLocatedHere",
  historical_proximity: "recommendation.reason.historicalProximity",
  object_created_here: "recommendation.reason.objectCreatedHere",
  object_of_type: "recommendation.reason.objectOfType",
  person_associated_with_type: "recommendation.reason.personAssociatedWithType",
  published_by_actor: "recommendation.reason.publishedByActor",
  related_place: "recommendation.reason.relatedPlace",
  related_semantic_type: "recommendation.reason.relatedSemanticType",
  same_birth_event: "recommendation.reason.sameBirthEvent",
  same_birth_year: "recommendation.reason.sameBirthYear",
  same_collection: "recommendation.reason.sameCollection",
  same_collaborator: "recommendation.reason.sameCollaborator",
  same_content_creator: "recommendation.reason.sameContentCreator",
  same_created_object: "recommendation.reason.sameCreatedObject",
  same_creation_event: "recommendation.reason.sameCreationEvent",
  same_creation_place: "recommendation.reason.sameCreationPlace",
  same_creator: "recommendation.reason.sameCreator",
  same_death_event: "recommendation.reason.sameDeathEvent",
  same_death_place: "recommendation.reason.sameDeathPlace",
  same_death_year: "recommendation.reason.sameDeathYear",
  same_described_context: "recommendation.reason.sameDescribedContext",
  same_educational_activity: "recommendation.reason.sameEducationalActivity",
  same_event: "recommendation.reason.sameEvent",
  same_events: "recommendation.reason.sameEvents",
  same_identification: "recommendation.reason.sameIdentification",
  same_location: "recommendation.reason.sameLocation",
  same_objects_connection: "recommendation.reason.sameObjectsConnection",
  same_occupational_activity: "recommendation.reason.sameOccupationalActivity",
  same_occurs_in: "recommendation.reason.sameOccursIn",
  same_place_of_birth: "recommendation.reason.samePlaceOfBirth",
  same_production: "recommendation.reason.sameProduction",
  same_subject: "recommendation.reason.sameSubject",
  same_time_span: "recommendation.reason.sameTimeSpan",
  same_type: "recommendation.reason.sameType",
  target_connection: "recommendation.reason.targetConnection",
};
