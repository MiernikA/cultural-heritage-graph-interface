import type { Recommendation } from "@/entities/entity";
import { semanticTypeLabel } from "@/entities/entity";
import type { TFunction } from "@/shared/i18n";
import { recommendationExplanationSentence } from "../model/evidence";
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
  const tags = recommendation.reason_tags.filter((tag) => tag.trim()).slice(0, 3);
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
  const title = firstEvidence?.title.trim();

  if (title) {
    return title;
  }

  const firstExplanation = explanationSentences(evidence, currentType, recommendation.semantic_type, t)[0];
  if (firstExplanation) {
    return firstExplanation.length > 82 ? `${firstExplanation.slice(0, 79).trim()}...` : firstExplanation;
  }

  return fallbackLabel;
}
