import { useEffect, useState, type SetStateAction } from "react";
import { isEntityRef, isUserFacingEntity, semanticTypeLabel, shortUri } from "@/entities/entity";
import type { EntityDetail, EntityRef, RawTriple, RelationshipGroup } from "@/entities/entity";
import { useI18n } from "@/shared/i18n";
import {
  groupSemanticReasoning,
  type SemanticRelationGroup,
} from "./relationship-ui";

const RAW_TRIPLE_PAGE_SIZE = 50;

type TechnicalGraphDetailsPanelProps = {
  entity: EntityDetail;
  groups: RelationshipGroup[];
  onOpen: (uri: string) => void;
};

export function TechnicalGraphDetailsPanel({ entity, groups, onOpen }: TechnicalGraphDetailsPanelProps) {
  const { language, t } = useI18n();
  const [visibleRawTripleCount, setVisibleRawTripleCount] = useState(RAW_TRIPLE_PAGE_SIZE);
  const [expandedMatches, setExpandedMatches] = useState<Record<string, boolean>>({});
  const reasoningGroups = groupSemanticReasoning(
    groups
      .flatMap((group) => group.relationships)
      .filter((relationship) => isUserFacingEntity(relationship.target) && relationship.rdf_path.length > 0),
    language,
    t,
  );
  const visibleRawTriples = entity.advanced.raw_triples.slice(0, visibleRawTripleCount);
  const hasMoreRawTriples = visibleRawTripleCount < entity.advanced.raw_triples.length;

  useEffect(() => {
    setVisibleRawTripleCount(RAW_TRIPLE_PAGE_SIZE);
    setExpandedMatches({});
  }, [entity.uri]);

  return (
    <section className="technical-graph-details">
      <details className="technical-console-panel">
        <summary className="technical-section-heading">
          <span>{t("advanced.section2")}</span>
          <h3>{t("advanced.rdfReasoning")}</h3>
          <p>{t("advanced.rdfReasoningDescription")}</p>
        </summary>
        <RdfReasoningLog
          expandedMatches={expandedMatches}
          onExpandedMatchesChange={setExpandedMatches}
          reasoningGroups={reasoningGroups}
        />
      </details>
      <details className="technical-console-panel">
        <summary className="technical-section-heading">
          <span>{t("advanced.section3")}</span>
          <h3>{t("advanced.rdfTriples")}</h3>
          <p>{t("advanced.rdfTriplesDescription")}</p>
        </summary>
        <RawTriplesLog
          entity={entity}
          hasMoreRawTriples={hasMoreRawTriples}
          onOpen={onOpen}
          onVisibleRawTripleCountChange={setVisibleRawTripleCount}
          visibleRawTriples={visibleRawTriples}
        />
      </details>
    </section>
  );
}

function RdfReasoningLog({
  expandedMatches,
  onExpandedMatchesChange,
  reasoningGroups,
}: {
  expandedMatches: Record<string, boolean>;
  onExpandedMatchesChange: (value: SetStateAction<Record<string, boolean>>) => void;
  reasoningGroups: SemanticRelationGroup[];
}) {
  const { t } = useI18n();
  return (
    <div className="semantic-reasoning">
      {reasoningGroups.length === 0 && <p className="muted">{t("advanced.noPublicRdfPaths")}</p>}
      {reasoningGroups.map((relationGroup) => (
        <section className="semantic-relation-block" key={relationGroup.key}>
          <div className="semantic-relation-header">
            <span>{t("advanced.semanticRelation")}</span>
            <strong>{relationGroup.label}</strong>
          </div>
          <div className="semantic-pattern-list">
            {relationGroup.patterns.map((pattern) => {
              const matchKey = `${relationGroup.key}-${pattern.key}`;
              const showAll = Boolean(expandedMatches[matchKey]);
              const visibleMatches = showAll ? pattern.matches : pattern.matches.slice(0, 8);
              return (
                <article className="semantic-pattern-block" key={pattern.key}>
                  <div className="semantic-pattern-header">
                    <span>{t("advanced.derivedFromRdfPattern")}</span>
                    <em>
                      {pattern.matches.length} {t("matchedEntitiesCount")}
                    </em>
                  </div>
                  <div className="semantic-pattern-chain" aria-label={t("advanced.rdfPattern")}>
                    {pattern.pattern.map((part, index) => (
                      <span className={part.kind === "context" ? "semantic-pattern-context" : "semantic-pattern-predicate"} title={part.uri} key={`${part.label}-${index}`}>
                        {part.label}
                      </span>
                    ))}
                  </div>
                  <div className="semantic-match-section">
                    <span className="semantic-match-heading">{t("advanced.matchedEntities")}</span>
                    <ol className="semantic-match-list">
                      {visibleMatches.map((match) => (
                        <li className="semantic-bibliography-item" key={match.uri}>
                          <span>{match.label}</span>
                          <small>{semanticTypeLabel(match.semantic_type, t)}</small>
                        </li>
                      ))}
                    </ol>
                    {pattern.matches.length > 8 && (
                      <button className="semantic-show-all" onClick={() => onExpandedMatchesChange((value) => ({ ...value, [matchKey]: !showAll }))}>
                        {showAll ? t("advanced.showFewer") : t("advanced.showAll")}
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

function RawTriplesLog({
  entity,
  hasMoreRawTriples,
  onOpen,
  onVisibleRawTripleCountChange,
  visibleRawTriples,
}: {
  entity: EntityDetail;
  hasMoreRawTriples: boolean;
  onOpen: (uri: string) => void;
  onVisibleRawTripleCountChange: (value: SetStateAction<number>) => void;
  visibleRawTriples: RawTriple[];
}) {
  const { t } = useI18n();
  return (
    <div className="raw-triples">
      <p className="muted raw-triples-count">
        {t("rawTriplesCountBefore")} {visibleRawTriples.length} {t("rawTriplesCountMiddle")} {entity.advanced.raw_triples.length} {t("rawTriplesCountAfter")}
      </p>
      <div className="raw-triples-table">
        <div className="raw-triple raw-triple-header">
          <span>{t("tableSubject")}</span>
          <span>{t("tablePredicate")}</span>
          <span>{t("tableObject")}</span>
        </div>
        {visibleRawTriples.map((triple, index) => (
          <RawTripleRow triple={triple} onOpen={onOpen} key={`${rdfValueKey(triple.subject)}-${triple.predicate_uri}-${index}`} />
        ))}
      </div>
      {hasMoreRawTriples && (
        <button className="raw-triples-load-more" onClick={() => onVisibleRawTripleCountChange((count) => Math.min(count + RAW_TRIPLE_PAGE_SIZE, entity.advanced.raw_triples.length))}>
          {t("advanced.loadMore")}
        </button>
      )}
    </div>
  );
}

function RawTripleRow({ triple, onOpen }: { triple: RawTriple; onOpen: (uri: string) => void }) {
  return (
    <div className="raw-triple">
      <RawRdfValue value={triple.subject} onOpen={onOpen} />
      <span title={triple.predicate_uri}>{triple.predicate_label || shortUri(triple.predicate_uri)}</span>
      <RawRdfValue value={triple.object} onOpen={onOpen} />
    </div>
  );
}

function RawRdfValue({ value, onOpen }: { value: EntityRef | string; onOpen: (uri: string) => void }) {
  if (!isEntityRef(value)) {
    return (
      <span className="raw-rdf-value literal" title={value}>
        {value}
      </span>
    );
  }
  return (
    <button className="raw-rdf-value raw-rdf-entity" onClick={() => onOpen(value.uri)}>
      <strong>{value.label || value.uri}</strong>
      {value.label && value.label !== value.uri && <small>{value.uri}</small>}
    </button>
  );
}

function rdfValueKey(value: EntityRef | string) {
  return isEntityRef(value) ? value.uri : value;
}
