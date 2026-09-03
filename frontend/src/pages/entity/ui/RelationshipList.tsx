import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { isUserFacingEntity } from "@/entities/entity";
import type { EntityDetail, RelationshipGroup } from "@/entities/entity";
import { useI18n } from "@/shared/i18n";
import { SemanticIcon } from "@/shared/ui";
import { ConnectionEntityCard } from "./ConnectionEntityCard";
import { ConnectionMap } from "./ConnectionMap";
import {
  filterRelationships,
  groupIcon,
  groupTone,
  mapTypeLabel,
  semanticTone,
  translatedGroupLabel,
} from "./relationship-ui";

type Props = {
  entity: EntityDetail;
  groups: RelationshipGroup[];
  view?: "all" | "map" | "list";
  onOpen: (uri: string) => void;
};

const RELATIONSHIP_PAGE_SIZE = 4;

export function RelationshipList({ entity, groups, view = "all", onOpen }: Props) {
  const { language, t } = useI18n();
  const [listQuery, setListQuery] = useState("");
  const [selectedGroup, setSelectedGroup] = useState("all");
  const [groupPages, setGroupPages] = useState<Record<string, number>>({});
  const visibleGroups = groups
    .map((group) => ({
      ...group,
      relationships: group.relationships.filter((relationship) => isUserFacingEntity(relationship.target)),
    }))
    .filter((group) => group.relationships.length > 0);
  const filteredGroups = visibleGroups
    .filter((group) => selectedGroup === "all" || group.label === selectedGroup)
    .map((group) => ({
      ...group,
      relationships: filterRelationships(group.relationships, listQuery, language, t),
    }))
    .filter((group) => group.relationships.length > 0);

  if (visibleGroups.length === 0) {
    return (
      <section className="knowledge-section entity-content-card">
        <h2>{t("connections")}</h2>
        <p className="muted">{t("noConnections")}</p>
      </section>
    );
  }

  return (
    <section className="knowledge-section">
      {view === "all" && <h2>{t("connections")}</h2>}
      {(view === "all" || view === "map") && <ConnectionMap entity={entity} groups={visibleGroups} onOpen={onOpen} />}
      {(view === "all" || view === "list") && (
        <section className="connection-list-section entity-content-card">
          <div className="connection-section-header">
            <h2>{t("connectionList")}</h2>
          </div>
          <RelationshipListControls
            listQuery={listQuery}
            onListQueryChange={setListQuery}
            onResetPages={() => setGroupPages({})}
            onSelectedGroupChange={setSelectedGroup}
            selectedGroup={selectedGroup}
            visibleGroups={visibleGroups}
          />
          {filteredGroups.length === 0 && <p className="muted">{t("noConnectionsForFilters")}</p>}
          <div className="knowledge-groups">
            {filteredGroups.map((group) => (
              <RelationshipGroupSection
                group={group}
                currentPage={Math.min(groupPages[group.label] ?? 0, Math.max(1, Math.ceil(group.relationships.length / RELATIONSHIP_PAGE_SIZE)) - 1)}
                key={group.label}
                onOpen={onOpen}
                onPageChange={(page) => setGroupPages((value) => ({ ...value, [group.label]: page }))}
              />
            ))}
          </div>
        </section>
      )}
    </section>
  );
}

function RelationshipListControls({
  listQuery,
  onListQueryChange,
  onResetPages,
  onSelectedGroupChange,
  selectedGroup,
  visibleGroups,
}: {
  listQuery: string;
  onListQueryChange: (value: string) => void;
  onResetPages: () => void;
  onSelectedGroupChange: (value: string) => void;
  selectedGroup: string;
  visibleGroups: RelationshipGroup[];
}) {
  const { t } = useI18n();
  const selectGroup = (group: string) => {
    onSelectedGroupChange(group);
    onResetPages();
  };

  return (
    <div className="connection-list-controls">
      <input
        className="connection-list-search"
        value={listQuery}
        onChange={(event) => {
          onListQueryChange(event.target.value);
          onResetPages();
        }}
        placeholder={t("connectionSearchPlaceholder")}
      />
      <div className="connection-filter-panel" aria-label={t("typeFilter")}>
        <span className="connection-filter-label">{t("typeFilter")}</span>
        <button className={selectedGroup === "all" ? "connection-filter-badge active" : "connection-filter-badge"} onClick={() => selectGroup("all")}>
          {t("all")}
        </button>
        {visibleGroups.map((group) => (
          <button
            className={`connection-filter-badge entity-tone-${groupTone(group.label)} ${selectedGroup === group.label ? "active" : ""}`}
            onClick={() => selectGroup(group.label)}
            key={group.label}
          >
            <SemanticIcon name={groupIcon(group.label)} size={13} />
            <span>{mapTypeLabel(group.label, t)}</span>
            <em>{group.relationships.length}</em>
          </button>
        ))}
      </div>
    </div>
  );
}

function RelationshipGroupSection({
  currentPage,
  group,
  onOpen,
  onPageChange,
}: {
  currentPage: number;
  group: RelationshipGroup;
  onOpen: (uri: string) => void;
  onPageChange: (page: number) => void;
}) {
  const { t } = useI18n();
  const pageCount = Math.max(1, Math.ceil(group.relationships.length / RELATIONSHIP_PAGE_SIZE));
  const displayedRelationships = group.relationships.slice(
    currentPage * RELATIONSHIP_PAGE_SIZE,
    currentPage * RELATIONSHIP_PAGE_SIZE + RELATIONSHIP_PAGE_SIZE,
  );

  return (
    <section className={`knowledge-group knowledge-group-${semanticTone(group.label)}`}>
      <div className="knowledge-group-header">
        <h3>{translatedGroupLabel(group.label, t)}</h3>
        <span>{group.relationships.length}</span>
      </div>
      <div className="relationship-list">
        {displayedRelationships.map((relationship, index) => (
          <article className={`relationship-row entity-tone-${semanticTone(relationship.target.semantic_type)}`} key={`${group.label}-${relationship.relation}-${index}`}>
            <ConnectionEntityCard relationship={relationship} onOpen={onOpen} variant="list" />
          </article>
        ))}
      </div>
      {pageCount > 1 && (
        <div className="connection-pagination">
          <button onClick={() => onPageChange(Math.max(0, currentPage - 1))} disabled={currentPage === 0}>
            <ChevronRight className="connection-pagination-prev-icon" size={14} />
            <span>{t("previous")}</span>
          </button>
          <span>
            {currentPage + 1} / {pageCount}
          </span>
          <button onClick={() => onPageChange(Math.min(pageCount - 1, currentPage + 1))} disabled={currentPage >= pageCount - 1}>
            <span>{t("next")}</span>
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </section>
  );
}
