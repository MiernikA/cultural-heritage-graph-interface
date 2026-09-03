import { Route, X } from "lucide-react";
import { Fragment, useState } from "react";
import type { ExplanationEvidence, Recommendation } from "@/entities/entity";
import { semanticTypeLabel } from "@/entities/entity";
import { useI18n } from "@/shared/i18n";
import { OverflowTitle, SemanticIcon } from "@/shared/ui";
import { noEvidenceNarrative, pathSentence, rdfStoryIntro, semanticTone } from "../model/evidence";
import { explanationSentences } from "./recommendation-logic";

type RecommendationCardProps = {
  currentType: string;
  expertMode: boolean;
  recommendation: Recommendation;
  onOpen: (uri: string) => void;
};

export function RecommendationCard({ currentType, expertMode, recommendation, onOpen }: RecommendationCardProps) {
  const [pathOpen, setPathOpen] = useState(false);
  const pathEvidence = (recommendation.explanation?.evidence ?? []).filter((item) => item.rdf_path.length > 0);

  if (pathOpen) {
    return (
      <article
        className={`recommendation-row recommendation-row-path-open recommendation-entity-card entity-tone-${semanticTone(recommendation.semantic_type)}`}
        onClick={(event) => event.stopPropagation()}
      >
        <RecommendationPathDetails evidence={pathEvidence} onClose={() => setPathOpen(false)} />
      </article>
    );
  }

  return (
    <article
      className={`recommendation-row recommendation-entity-card entity-tone-${semanticTone(recommendation.semantic_type)}`}
      onClick={() => onOpen(recommendation.uri)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(recommendation.uri);
        }
      }}
      role="button"
      tabIndex={0}
    >
      <RecommendationEntityHeader recommendation={recommendation} />
      <span className="recommendation-main">
        <RecommendationNarrative
          currentType={currentType}
          expertMode={expertMode}
          recommendation={recommendation}
          onOpenPath={() => setPathOpen(true)}
        />
      </span>
    </article>
  );
}

function RecommendationEntityHeader({ recommendation }: { recommendation: Recommendation }) {
  const { t } = useI18n();
  return (
    <div className="recommendation-card-button">
      <span className="connection-map-node-icon">
        <SemanticIcon name={recommendation.icon} size={20} />
      </span>
      <span className="connection-map-node-copy">
        <OverflowTitle as="strong" title={recommendation.label}>
          {recommendation.label}
        </OverflowTitle>
        <small>{semanticTypeLabel(recommendation.semantic_type, t)}</small>
      </span>
    </div>
  );
}

function RecommendationNarrative({
  currentType,
  expertMode,
  onOpenPath,
  recommendation,
}: {
  currentType: string;
  expertMode: boolean;
  onOpenPath: () => void;
  recommendation: Recommendation;
}) {
  const { t } = useI18n();
  const evidence = recommendation.explanation?.evidence ?? [];
  const explanations = explanationSentences(evidence, currentType, recommendation.semantic_type, t);
  const pathEvidence = evidence.filter((item) => item.rdf_path.length > 0);

  return (
    <div className="recommendation-narrative">
      <section className="narrative-section narrative-section-primary">
        <div className="narrative-section-title narrative-section-title-why">
          <h3>{t("why")}</h3>
        </div>
        {explanations.length === 0 ? (
          <p className="historical-relationship-copy">{noEvidenceNarrative(t)}</p>
        ) : (
            <ul className="recommendation-why-list">
              {explanations.map((description) => (
                <li key={description}>{description}</li>
              ))}
            </ul>
        )}
        {expertMode && pathEvidence.length > 0 && (
          <button
            className="connection-path-button"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenPath();
            }}
          >
            <Route size={13} />
            <span>{t("connectionPath")}</span>
          </button>
        )}
      </section>
    </div>
  );
}

export function RecommendationPathDetails({ evidence, onClose }: { evidence: ExplanationEvidence[]; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <div
      className="recommendation-path-inline"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.stopPropagation();
        }
      }}
    >
      <div className="recommendation-path-panel" aria-label={t("rdfPathStory")}>
        <div className="recommendation-path-panel-header">
          <strong>{t("connectionPath")}</strong>
          <button className="recommendation-path-close" type="button" onClick={onClose} aria-label={t("close")}>
            <X size={14} />
          </button>
        </div>
        <div className="recommendation-path-list">
          {evidence.map((item, itemIndex) => (
            <Fragment key={item.type}>
              {itemIndex > 0 && <hr className="explanation-path-separator" />}
              <section className="explanation-path">
                <p className="story-intro">{t(rdfStoryIntro(item.rdf_path.length))}</p>
                {item.rdf_path.map((step, index) => (
                  <div className="explanation-step story-step" key={`${item.type}-${index}`}>
                    <span className="story-index">{index + 1}</span>
                    <span className="story-sentence">{pathSentence(step, index, t)}</span>
                  </div>
                ))}
              </section>
            </Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
