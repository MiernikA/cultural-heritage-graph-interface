import { Info } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Recommendation } from "@/entities/entity";
import { useI18n } from "@/shared/i18n";
import { RecommendationCard } from "./RecommendationCard";
import { RecommendationDataTable } from "./RecommendationDataTable";
import { sortRecommendations } from "./recommendation-logic";
import type { RecommendationSortKey, RecommendationSortState } from "./recommendation-types";

const RECOMMENDATION_TABLE_ROWS_PER_PAGE = 10;

type StagedRecommendationPanelProps = {
  currentType: string;
  expertMode: boolean;
  recommendations: Recommendation[];
  featuredRecommendations: Recommendation[];
  loading: boolean;
  error: string | null;
  onOpen: (uri: string) => void;
};

export function StagedRecommendationPanel({
  currentType,
  expertMode,
  recommendations,
  featuredRecommendations,
  loading,
  error,
  onOpen,
}: StagedRecommendationPanelProps) {
  const [page, setPage] = useState(0);
  const [sortState, setSortState] = useState<RecommendationSortState>({ direction: "asc", key: "distance" });
  const { language, t } = useI18n();
  const featuredRecommendationUris = useMemo(() => new Set(featuredRecommendations.map((recommendation) => recommendation.uri)), [featuredRecommendations]);
  const sortedRecommendationTableRows = useMemo(
    () => sortRecommendations(recommendations, sortState.key, sortState.direction, currentType, language, t, t("recommendationFallbackReason")),
    [currentType, language, recommendations, sortState.direction, sortState.key, t],
  );
  const visibleRecommendationTableRows = sortedRecommendationTableRows.slice(
    page * RECOMMENDATION_TABLE_ROWS_PER_PAGE,
    page * RECOMMENDATION_TABLE_ROWS_PER_PAGE + RECOMMENDATION_TABLE_ROWS_PER_PAGE,
  );

  useEffect(() => {
    setPage(0);
  }, [recommendations]);

  useEffect(() => {
    const pageCount = Math.max(1, Math.ceil(sortedRecommendationTableRows.length / RECOMMENDATION_TABLE_ROWS_PER_PAGE));
    setPage((value) => Math.min(value, pageCount - 1));
  }, [sortedRecommendationTableRows.length]);

  const handleSort = (key: RecommendationSortKey) => {
    setSortState((previous) => ({
      direction: previous?.key === key && previous.direction === "asc" ? "desc" : "asc",
      key,
    }));
    setPage(0);
  };

  return (
    <aside className="recommendation-panel entity-content-card" aria-label={t("mainRecommendations")}>
      <RecommendationPanelHeader />
      {loading && <RecommendationLoader />}
      {!loading && error && (
        <p className="muted" title={error}>
          {t("recommendationsUnavailable")}
        </p>
      )}
      {!loading && !error && (
        <div className="recommendation-stage-list">
          <section className="recommendation-stage">
            {recommendations.length === 0 ? (
              <p className="muted">{t("noRecommendations")}</p>
            ) : (
              <>
                <div className="recommendation-showcase">
                  {featuredRecommendations.map((recommendation) => (
                    <RecommendationCard
                      currentType={currentType}
                      expertMode={expertMode}
                      key={recommendation.uri}
                      recommendation={recommendation}
                      onOpen={onOpen}
                    />
                  ))}
                </div>
                {expertMode && (
                  <div className="recommendation-table-section">
                    <div className="recommendation-table-header">
                      <h3>{t("allRecommendations")}</h3>
                    </div>
                    <RecommendationDataTable
                      currentType={currentType}
                      expertMode={expertMode}
                      onOpen={onOpen}
                      onSort={handleSort}
                      page={page}
                      recommendations={visibleRecommendationTableRows}
                      rowCount={sortedRecommendationTableRows.length}
                      rowsPerPage={RECOMMENDATION_TABLE_ROWS_PER_PAGE}
                      featuredRecommendationUris={featuredRecommendationUris}
                      sortDirection={sortState.direction}
                      sortKey={sortState.key}
                      setPage={setPage}
                    />
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </aside>
  );
}

function RecommendationPanelHeader() {
  const { t } = useI18n();
  return (
    <div className="recommendation-panel-header">
      <div>
        <h2>
          {t("mainRecommendations")}
          <span
            className="recommendation-info tooltip-target"
            data-tooltip={t("recommendationsGeneratedTooltip")}
            aria-label={t("recommendationsGeneratedAria")}
          >
            <Info size={14} />
          </span>
        </h2>
      </div>
    </div>
  );
}

function RecommendationLoader() {
  const { t } = useI18n();
  return (
    <div className="recommendation-loader" role="status" aria-live="polite">
      <span className="loader-dot" aria-hidden="true" />
      <span>{t("loadingRecommendations")}</span>
      <div className="recommendation-loader-list" aria-hidden="true">
        {Array.from({ length: 3 }, (_, index) => (
          <span className="recommendation-loader-row" key={index} />
        ))}
      </div>
    </div>
  );
}
