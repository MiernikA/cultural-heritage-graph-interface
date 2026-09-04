import { Info } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getFeaturedRecommendations, getRecommendations } from "@/shared/api";
import type { EntityDetail, Recommendation, SearchResult } from "@/entities/entity";
import { isUserFacingEntity, semanticDescription, semanticTypeLabel } from "@/entities/entity";
import { useI18n } from "@/shared/i18n";
import { SemanticIcon } from "@/shared/ui";
import { isDisplayableAlias, resolveAliasTarget } from "../model/alias";
import { StagedRecommendationPanel } from "./RecommendationPanel";
import { RelationshipList } from "./RelationshipList";
import { TechnicalGraphDetailsPanel } from "./TechnicalGraphDetailsPanel";
import { recommendationReasonLabel } from "./recommendation-logic";
import type { TFunction } from "@/shared/i18n";

type EntityTab = "map" | "list" | "recommendations" | "technical";

type Props = {
  connectionMapFocusRequest?: number;
  entity: EntityDetail;
  expertMode: boolean;
  onOpen: (uri: string) => void;
};

export function EntityPage({ connectionMapFocusRequest = 0, entity, expertMode, onOpen }: Props) {
  const { language, t } = useI18n();
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [featuredRecommendations, setFeaturedRecommendations] = useState<Recommendation[]>([]);
  const [recommendationsLoading, setRecommendationsLoading] = useState(false);
  const [recommendationsError, setRecommendationsError] = useState<string | null>(null);
  const [aliasTargets, setAliasTargets] = useState<Record<string, SearchResult | null>>({});
  const [activeTab, setActiveTab] = useState<EntityTab>("map");
  const titleRef = useRef<HTMLHeadingElement | null>(null);
  const [titleTruncated, setTitleTruncated] = useState(false);
  const entityDescription = semanticDescription(entity.semantic_type, entity.description, t);
  const visibleAliases = useMemo(() => entity.aliases.filter(isDisplayableAlias).slice(0, 5), [entity.aliases]);

  useEffect(() => {
    setActiveTab("map");
  }, [entity.uri, connectionMapFocusRequest]);

  useEffect(() => {
    if (!expertMode && activeTab === "technical") {
      setActiveTab("map");
    }
  }, [activeTab, expertMode]);

  useEffect(() => {
    let cancelled = false;
    setRecommendationsLoading(true);
    setRecommendationsError(null);
    setRecommendations([]);
    setFeaturedRecommendations([]);

    Promise.all([getRecommendations(entity.uri), getFeaturedRecommendations(entity.uri)])
      .then(([allRecommendations, topRecommendations]) => {
        if (!cancelled) {
          setRecommendations(allRecommendations.filter((item) => isUserFacingEntity(item)));
          setFeaturedRecommendations(topRecommendations.filter((item) => isUserFacingEntity(item)));
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setRecommendationsError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setRecommendationsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [entity.uri]);

  useEffect(() => {
    let cancelled = false;
    setAliasTargets({});

    if (visibleAliases.length === 0) {
      return;
    }

    Promise.all(
      visibleAliases.map((alias) =>
        resolveAliasTarget(alias, entity.uri)
          .then((items) => {
            return [alias, items] as const;
          })
          .catch(() => [alias, null] as const),
      ),
    ).then((entries) => {
      if (!cancelled) {
        setAliasTargets(Object.fromEntries(entries));
      }
    });

    return () => {
      cancelled = true;
    };
  }, [entity.uri, visibleAliases]);

  useEffect(() => {
    const title = titleRef.current;
    if (!title) {
      setTitleTruncated(false);
      return;
    }

    const updateTitleOverflow = () => {
      setTitleTruncated(title.scrollHeight > title.clientHeight + 4);
    };

    updateTitleOverflow();
    const observer = new ResizeObserver(updateTitleOverflow);
    observer.observe(title);
    return () => observer.disconnect();
  }, [entity.display_name]);

  return (
    <main className="page entity-page">
      <section className="entity-header">
        <div className="entity-header-grid">
          <div className="entity-portrait" aria-label={entity.semantic_type}>
            <SemanticIcon name={entity.icon} size={68} />
            <span className="entity-portrait-badge tooltip-target" data-tooltip={entityDescription}>{semanticTypeLabel(entity.semantic_type, t)}</span>
          </div>
          <div className="entity-header-copy">
            <div className="entity-title">
              <div className={titleTruncated ? "entity-title-tooltip tooltip-target" : "entity-title-tooltip"} data-tooltip={titleTruncated ? entity.display_name : undefined}>
                <h1 ref={titleRef}>{entity.display_name}</h1>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="entity-tabbed-explorer">
        {visibleAliases.length > 0 && (
          <p className="entity-aliases connections-aliases">
            <span className="entity-alias-label">{t("alsoKnownAs")}</span>
            {visibleAliases.map((alias, index) => (
              <AliasValue alias={alias} key={`${alias}-${index}`} target={aliasTargets[alias]} onOpen={onOpen} />
            ))}
            <span className="alias-info stat-info tooltip-target" data-tooltip={t("aliasesTooltip")}>
              <Info size={12} />
            </span>
          </p>
        )}
        <div className="entity-tabs" role="tablist" aria-label={t("connections")}>
          {[
            { key: "map" as const, label: t("connectionMap") },
            { key: "list" as const, label: t("connectionList") },
            { key: "recommendations" as const, label: t("mainRecommendations") },
            ...(expertMode ? [{ key: "technical" as const, label: t("technicalDetails") }] : []),
          ].map((tab) => (
            <button
              className={activeTab === tab.key ? "entity-tab active" : "entity-tab"}
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              role="tab"
              type="button"
              aria-selected={activeTab === tab.key}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="entity-tab-panel" role="tabpanel">
          {activeTab === "map" && <RelationshipList entity={entity} groups={entity.connections} view="map" onOpen={onOpen} />}
          {activeTab === "list" && <RelationshipList entity={entity} groups={entity.connections} view="list" onOpen={onOpen} />}
          {activeTab === "recommendations" && (
            <StagedRecommendationPanel
              currentType={entity.semantic_type}
              expertMode={expertMode}
              recommendations={recommendations}
              featuredRecommendations={featuredRecommendations}
              loading={recommendationsLoading}
              error={recommendationsError}
              onOpen={onOpen}
            />
          )}
          {expertMode && activeTab === "technical" && (
            <TechnicalDetailsTab
              entity={entity}
              recommendations={recommendations}
              onOpen={onOpen}
            />
          )}
        </div>
      </section>
    </main>
  );
}

function AliasValue({ alias, target, onOpen }: { alias: string; target: SearchResult | null | undefined; onOpen: (uri: string) => void }) {
  if (target) {
    return (
      <button className="entity-alias-value entity-alias-link" onClick={() => onOpen(target.uri)}>
        {alias}
      </button>
    );
  }

  return <strong className="entity-alias-value">{alias}</strong>;
}

function TechnicalDetailsTab({
  entity,
  recommendations,
  onOpen,
}: {
  entity: EntityDetail;
  recommendations: Recommendation[];
  onOpen: (uri: string) => void;
}) {
  const { t } = useI18n();
  const publicConnectionCount = useMemo(
    () =>
      entity.connections.reduce(
        (total, group) => total + group.relationships.filter((relationship) => isUserFacingEntity(relationship.target)).length,
        0,
      ),
    [entity.connections],
  );
  const statementCount = entity.advanced.raw_triples.length;
  const recommendationCount = recommendations.length;
  const recommendationReasonTags = Array.from(new Set(recommendations.flatMap((recommendation) => recommendation.reason_tags))).sort();
  const retrievalOrigins = Array.from(new Set(recommendations.map((recommendation) => recommendation.retrieval_origin))).sort();

  return (
    <section className="technical-details-tab">
      <section className="technical-console-panel technical-info-panel">
        <p>
          {t("technicalDebugNote")}
        </p>
        <p className="technical-inline-summary" aria-label={t("entityStats")}>
          <span>
            <strong>{t("connections")}:</strong> <b>{publicConnectionCount}</b>
          </span>
          <span>
            <strong>{t("recommendations")}:</strong> <b>{recommendationCount}</b>
          </span>
          <span>
            <strong>{t("statements")}:</strong> <b>{statementCount}</b>
          </span>
        </p>
      </section>
      <TechnicalGraphDetailsPanel entity={entity} groups={entity.connections} onOpen={onOpen} />
      <details className="technical-console-panel technical-extra-section">
        <summary className="technical-section-heading">
          <span>{t("advanced.section4")}</span>
          <h3>{t("technicalAdditionalInfo")}</h3>
          <p>{t("technicalRemainingMetadata")}</p>
        </summary>
        <div className="technical-metadata-grid">
          <section>
            <strong>{t("technicalEntityUri")}</strong>
            <code>{entity.advanced.uri}</code>
          </section>
          <section>
            <strong>{t("technicalRdfTypes")}</strong>
            {entity.rdf_types.length > 0 ? (
              <ul>
                {entity.rdf_types.map((type) => (
                  <li key={type.uri}>
                    <span>{type.label}</span>
                    <code>{type.uri}</code>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">{t("technicalNoRdfTypeMetadata")}</p>
            )}
          </section>
          <section>
            <strong>{t("technicalRecommendationMetadata")}</strong>
            <div className="technical-badge-list">
              {retrievalOrigins.map((origin) => (
                <span key={origin}>{translatedRetrievalOrigin(origin, t)}</span>
              ))}
              {recommendationReasonTags.map((tag) => (
                <span key={tag}>{recommendationReasonLabel(tag, t)}</span>
              ))}
              {retrievalOrigins.length === 0 && recommendationReasonTags.length === 0 && (
                <em>{t("technicalNoRecommendationMetadata")}</em>
              )}
            </div>
          </section>
        </div>
      </details>
    </section>
  );
}

function translatedRetrievalOrigin(origin: Recommendation["retrieval_origin"], t: TFunction) {
  if (origin === "Direct embedding retrieval") {
    return t("recommendation.origin.directEmbedding");
  }
  if (origin === "Technical embedding expansion") {
    return t("recommendation.origin.technicalExpansion");
  }
  return origin;
}
