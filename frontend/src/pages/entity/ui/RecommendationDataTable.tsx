import { Eye, Route } from "lucide-react";
import { Fragment, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import TableSortLabel from "@mui/material/TableSortLabel";
import type { Recommendation } from "@/entities/entity";
import { semanticTypeLabel } from "@/entities/entity";
import { useI18n } from "@/shared/i18n";
import { OverflowTitle, SemanticIcon } from "@/shared/ui";
import { semanticTone } from "../model/evidence";
import { RecommendationPathDetails } from "./RecommendationCard";
import { formatRawDistance, semanticReasonBadges } from "./recommendation-logic";
import type { RecommendationSortKey, SortDirection } from "./recommendation-types";

type RecommendationDataTableProps = {
  currentType: string;
  expertMode: boolean;
  onOpen: (uri: string) => void;
  onSort: (key: RecommendationSortKey) => void;
  page: number;
  recommendations: Recommendation[];
  rowCount: number;
  rowsPerPage: number;
  featuredRecommendationUris: Set<string>;
  setPage: (value: number) => void;
  sortDirection: SortDirection;
  sortKey: RecommendationSortKey;
};

export function RecommendationDataTable({
  currentType,
  expertMode,
  onOpen,
  onSort,
  page,
  recommendations,
  rowCount,
  rowsPerPage,
  featuredRecommendationUris,
  setPage,
  sortDirection,
  sortKey,
}: RecommendationDataTableProps) {
  const { t } = useI18n();
  const [expandedPathUri, setExpandedPathUri] = useState<string | null>(null);
  return (
    <Box className="recommendation-data-grid">
      <TableContainer className="recommendation-mui-table-container">
        <Table size="small" stickyHeader aria-label={t("allRecommendations")}>
          <TableHead>
            <TableRow>
              <TableCell className="recommendation-icon-cell">{t("recommendationIcon")}</TableCell>
              <SortableHeader activeKey={sortKey} direction={sortDirection} label={t("recommendationEntityType")} sortKey="semantic_type" onSort={onSort} />
              <SortableHeader activeKey={sortKey} direction={sortDirection} label={t("recommendationEntityName")} sortKey="label" onSort={onSort} />
              <SortableHeader activeKey={sortKey} direction={sortDirection} label={t("recommendationSemanticReason")} sortKey="reason" onSort={onSort} />
              <SortableHeader activeKey={sortKey} direction={sortDirection} label={t("recommendationHnswDistance")} sortKey="distance" onSort={onSort} align="right" />
              <TableCell align="right">{t("recommendationAction")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {recommendations.map((recommendation) => {
              const pathEvidence = (recommendation.explanation?.evidence ?? []).filter((item) => item.rdf_path.length > 0);
              const pathExpanded = expandedPathUri === recommendation.uri;
              return (
                <Fragment key={recommendation.uri}>
                  <TableRow className={featuredRecommendationUris.has(recommendation.uri) ? "recommendation-table-row-featured" : undefined} hover>
                    <TableCell className="recommendation-icon-cell">
                      <span className={`connection-map-node-icon entity-tone-${semanticTone(recommendation.semantic_type)}`}>
                        <SemanticIcon name={recommendation.icon} size={18} />
                      </span>
                    </TableCell>
                    <TableCell>{semanticTypeLabel(recommendation.semantic_type, t)}</TableCell>
                    <TableCell className="recommendation-name-cell">
                      <OverflowTitle as="strong" title={recommendation.label}>
                        {recommendation.label}
                      </OverflowTitle>
                    </TableCell>
                    <TableCell>
                      <div className="recommendation-reason-chip-list">
                        {semanticReasonBadges(recommendation, currentType, t, t("recommendationFallbackReason")).map((reason) => (
                          <Chip key={reason} label={reason} size="small" />
                        ))}
                      </div>
                    </TableCell>
                    <TableCell align="right" className="recommendation-distance-cell">
                      {formatRawDistance(recommendation.semantic_similarity)}
                    </TableCell>
                    <TableCell align="right">
                      {expertMode && (
                        <IconButton
                          size="small"
                          aria-label={t("connectionPath")}
                          disabled={pathEvidence.length === 0}
                          onClick={() => setExpandedPathUri(pathExpanded ? null : recommendation.uri)}
                        >
                          <Route size={16} />
                        </IconButton>
                      )}
                      <IconButton size="small" aria-label={t("openRecommendation")} onClick={() => onOpen(recommendation.uri)}>
                        <Eye size={16} />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                  {expertMode && pathExpanded && (
                    <TableRow>
                      <TableCell colSpan={6}>
                        <RecommendationPathDetails evidence={pathEvidence} onClose={() => setExpandedPathUri(null)} />
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        className="recommendation-table-pagination"
        component="div"
        count={rowCount}
        onPageChange={(_, nextPage) => setPage(nextPage)}
        page={page}
        rowsPerPage={rowsPerPage}
        rowsPerPageOptions={[]}
        labelDisplayedRows={({ from, to, count }) => t("recommendationPaginationRange", { count, from, to })}
      />
    </Box>
  );
}

function SortableHeader({
  activeKey,
  align,
  direction,
  label,
  onSort,
  sortKey,
}: {
  activeKey: RecommendationSortKey;
  align?: "left" | "right";
  direction: SortDirection;
  label: string;
  onSort: (key: RecommendationSortKey) => void;
  sortKey: RecommendationSortKey;
}) {
  return (
    <TableCell align={align}>
      <TableSortLabel active={activeKey === sortKey} direction={activeKey === sortKey ? direction : "asc"} onClick={() => onSort(sortKey)}>
        {label}
      </TableSortLabel>
    </TableCell>
  );
}
