import { searchEntities } from "@/shared/api";
import { isUserFacingEntity } from "@/entities/entity";

export async function resolveAliasTarget(alias: string, currentUri: string) {
  for (const query of aliasSearchQueries(alias)) {
    const items = (await searchEntities(query, 10)).filter(isUserFacingEntity).filter((item) => item.uri !== currentUri);
    const exact = items.find((item) => normalizeAliasLabel(item.label) === normalizeAliasLabel(query));
    if (exact) {
      return exact;
    }

    const partial = items.find((item) => labelsMatchAlias(item.label, query));
    if (partial) {
      return partial;
    }

    if (items[0]) {
      return items[0];
    }
  }

  return null;
}

export function isDisplayableAlias(alias: string) {
  const value = alias.trim();
  if (value.length < 2) {
    return false;
  }
  if (/^(?:https?:\/\/|urn:|cidoc:)/i.test(value)) {
    return false;
  }
  if (/^[A-Z]{1,4}\d+_[A-Za-z0-9_-]+$/.test(value)) {
    return false;
  }
  if (/^E\d+[_-]/.test(value)) {
    return false;
  }
  return /[^\d_\-#:/]/.test(value);
}

function aliasSearchQueries(alias: string) {
  const withoutParentheses = alias.replace(/\([^)]*\)/g, " ");
  const withoutDates = withoutParentheses.replace(/\b\d{3,4}\s*[-–—]\s*\d{0,4}\b/g, " ");
  const compact = withoutDates.replace(/[;:]+/g, " ").replace(/\s+/g, " ").trim();
  const reversed = reverseCommaName(compact);
  return Array.from(new Set([alias, compact, reversed].filter((value) => value.length >= 2)));
}

function reverseCommaName(value: string) {
  const [lastName, rest] = value.split(",").map((part) => part.trim());
  if (!lastName || !rest) {
    return value;
  }
  return `${rest} ${lastName}`.replace(/\s+/g, " ").trim();
}

function labelsMatchAlias(label: string, alias: string) {
  const normalizedLabel = normalizeAliasLabel(label);
  const normalizedAlias = normalizeAliasLabel(alias);
  return normalizedLabel === normalizedAlias || normalizedLabel.includes(normalizedAlias) || normalizedAlias.includes(normalizedLabel);
}

function normalizeAliasLabel(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}
