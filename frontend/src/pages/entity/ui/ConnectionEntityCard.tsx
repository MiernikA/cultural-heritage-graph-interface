import type { RelationshipGroup } from "@/entities/entity";
import { useI18n } from "@/shared/i18n";
import { OverflowTitle, SemanticIcon } from "@/shared/ui";
import { semanticTone, translatedRelationLabel } from "./relationship-ui";

type ConnectionEntityCardProps = {
  relationship: RelationshipGroup["relationships"][number];
  onOpen: (uri: string) => void;
  variant: "map" | "list";
};

export function ConnectionEntityCard({ relationship, onOpen, variant }: ConnectionEntityCardProps) {
  const { t } = useI18n();
  const buttonClass =
    variant === "map"
      ? `connection-map-representative entity-tone-${semanticTone(relationship.target.semantic_type)}`
      : `connection-card connection-card-unified entity-tone-${semanticTone(relationship.target.semantic_type)}`;
  const iconClass = variant === "map" ? "connection-map-node-icon" : "connection-card-icon";
  const copyClass = variant === "map" ? "connection-map-node-copy" : "connection-card-copy";
  const iconSize = variant === "map" ? 15 : 18;

  return (
    <button className={buttonClass} onClick={() => onOpen(relationship.target.uri)}>
      <span className={iconClass}>
        <SemanticIcon name={relationship.target.icon} size={iconSize} />
      </span>
      <span className={copyClass}>
        <small className="connection-map-reason-badge">{translatedRelationLabel(relationship.display_label, t)}</small>
        <OverflowTitle as="strong" title={relationship.target.label}>
          {relationship.target.label}
        </OverflowTitle>
      </span>
    </button>
  );
}
