import { useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { EntityDetail, RelationshipGroup } from "@/entities/entity";
import { useI18n } from "@/shared/i18n";
import { SemanticIcon } from "@/shared/ui";
import { ConnectionEntityCard } from "./ConnectionEntityCard";
import { groupIcon, groupTone, mapTypeLabel, semanticTone } from "./relationship-ui";

type ConnectionMapProps = {
  entity: EntityDetail;
  groups: RelationshipGroup[];
  onOpen: (uri: string) => void;
};

export function ConnectionMap({ entity, groups, onOpen }: ConnectionMapProps) {
  const { t } = useI18n();
  const visibleGroups = useMemo(() => groups.slice(0, 8), [groups]);
  const branchesRef = useRef<HTMLDivElement | null>(null);
  const branchRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [timelineStyle, setTimelineStyle] = useState<CSSProperties>({});

  useLayoutEffect(() => {
    const updateTimeline = () => {
      const branches = branchesRef.current;
      const firstBranch = branchRefs.current[0];
      const lastBranch = branchRefs.current[visibleGroups.length - 1];
      if (!branches || !firstBranch || !lastBranch) {
        setTimelineStyle({});
        return;
      }
      const containerRect = branches.getBoundingClientRect();
      const firstRect = firstBranch.getBoundingClientRect();
      const lastRect = lastBranch.getBoundingClientRect();
      const top = firstRect.top - containerRect.top + firstRect.height / 2;
      const bottom = lastRect.top - containerRect.top + lastRect.height / 2;
      setTimelineStyle({ top, height: Math.max(0, bottom - top) });
    };

    updateTimeline();
    const observer = new ResizeObserver(updateTimeline);
    if (branchesRef.current) {
      observer.observe(branchesRef.current);
    }
    branchRefs.current.forEach((branch) => branch && observer.observe(branch));
    window.addEventListener("resize", updateTimeline);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", updateTimeline);
    };
  }, [visibleGroups]);

  if (visibleGroups.length === 0) {
    return null;
  }

  return (
    <section className="connection-map" aria-label={t("connectionMap")}>
      <div className="connection-map-body">
        <div className={`connection-map-origin entity-tone-${semanticTone(entity.semantic_type)}`}>
          <span className="connection-map-origin-dot" aria-hidden="true" />
        </div>
        <div className="connection-map-branches" ref={branchesRef}>
          <span className="connection-map-timeline" style={timelineStyle} aria-hidden="true" />
          {visibleGroups.map((group, groupIndex) => (
            <div
              className={`connection-map-branch entity-tone-${groupTone(group.label)}`}
              key={group.label}
              ref={(node) => {
                branchRefs.current[groupIndex] = node;
              }}
            >
              <span className="connection-map-line" aria-hidden="true" />
              <span className="connection-map-type-badge">
                <SemanticIcon name={groupIcon(group.label)} size={13} />
                <strong>{mapTypeLabel(group.label, t)}</strong>
                <em>{group.relationships.length}</em>
              </span>
              <div
                className="connection-map-representatives"
                onWheelCapture={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
                onWheel={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
              >
                {group.relationships.map((relationship, index) => (
                  <div className="connection-map-representative-row" key={`${group.label}-${relationship.target.uri}-${index}`}>
                    <span className="connection-map-representative-line" aria-hidden="true" />
                    <ConnectionEntityCard relationship={relationship} onOpen={onOpen} variant="map" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
