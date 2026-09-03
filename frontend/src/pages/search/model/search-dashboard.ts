import { Database, Link2, Tags, type LucideIcon } from "lucide-react";
import { GRAPH_STATS } from "@/entities/entity";
import type { TFunction } from "@/shared/i18n";

export type GraphStatItem = {
  accent: string;
  background: string;
  description: string;
  icon: LucideIcon;
  key: string;
  label: string;
  value: number;
};

export function graphStatItems(t: TFunction): GraphStatItem[] {
  return [
    {
      accent: "#9a7135",
      background: "linear-gradient(180deg, rgba(255, 247, 229, 0.95), rgba(246, 231, 205, 0.82))",
      description: t("graphStats.entitiesDescription"),
      icon: Database,
      key: "entities",
      label: t("entities"),
      value: GRAPH_STATS.entities,
    },
    {
      accent: "#8a3f4a",
      background: "linear-gradient(180deg, rgba(255, 239, 235, 0.95), rgba(243, 218, 211, 0.8))",
      description: t("graphStats.relationsDescription"),
      icon: Link2,
      key: "relations",
      label: t("relations"),
      value: GRAPH_STATS.relations,
    },
    {
      accent: "#2f6d50",
      background: "linear-gradient(180deg, rgba(237, 246, 240, 0.96), rgba(215, 234, 222, 0.82))",
      description: t("graphStats.typesDescription"),
      icon: Tags,
      key: "types",
      label: t("types"),
      value: GRAPH_STATS.types,
    },
  ];
}
