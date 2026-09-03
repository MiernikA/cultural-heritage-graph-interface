import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { FEATURED_ENTITIES } from "@/entities/entity";
import { useI18n } from "@/shared/i18n";
import { FeaturedEntityCard } from "./FeaturedEntityCard";

export function FeaturedEntities({ onOpen }: { onOpen: (uri: string) => void }) {
  const { language, t } = useI18n();
  const sliderViewportRef = useRef<HTMLDivElement | null>(null);
  const sliderTrackRef = useRef<HTMLDivElement | null>(null);
  const idleTimerRef = useRef<number | null>(null);
  const offsetRef = useRef(0);
  const boostVelocityRef = useRef(0);
  const dragStateRef = useRef<{ didDrag: boolean; offset: number; pointerId: number; startX: number } | null>(null);
  const suppressNextClickRef = useRef(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isInteracting, setIsInteracting] = useState(false);
  const sliderItems = useMemo(() => [...FEATURED_ENTITIES, ...FEATURED_ENTITIES], []);

  const applySliderOffset = useCallback((nextOffset: number) => {
    const track = sliderTrackRef.current;

    if (!track) {
      return;
    }

    const loopWidth = track.scrollWidth / 2;

    if (loopWidth <= 0) {
      return;
    }

    offsetRef.current = ((nextOffset % loopWidth) + loopWidth) % loopWidth;
    track.style.transform = `translate3d(${-offsetRef.current}px, 0, 0)`;
  }, []);

  const scrollSliderBy = useCallback(
    (distance: number) => {
      applySliderOffset(offsetRef.current + distance);
    },
    [applySliderOffset],
  );

  const markInteracted = useCallback(() => {
    setIsInteracting(true);

    if (idleTimerRef.current !== null) {
      window.clearTimeout(idleTimerRef.current);
    }

    idleTimerRef.current = window.setTimeout(() => {
      setIsInteracting(false);
      idleTimerRef.current = null;
    }, 650);
  }, []);

  const boostSlider = useCallback((direction: -1 | 1) => {
    const nextVelocity = boostVelocityRef.current + direction * 520;
    boostVelocityRef.current = Math.max(-1200, Math.min(1200, nextVelocity));
  }, []);

  const handleWheel = useCallback(
    (event: WheelEvent<HTMLDivElement>) => {
      event.preventDefault();
      markInteracted();
      scrollSliderBy(Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY);
    },
    [markInteracted, scrollSliderBy],
  );

  const handlePointerDown = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      const viewport = sliderViewportRef.current;

      if (!viewport) {
        return;
      }

      markInteracted();
      dragStateRef.current = {
        didDrag: false,
        pointerId: event.pointerId,
        offset: offsetRef.current,
        startX: event.clientX,
      };
    },
    [markInteracted],
  );

  const handlePointerMove = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      const dragState = dragStateRef.current;

      if (!dragState || dragState.pointerId !== event.pointerId) {
        return;
      }

      const movement = event.clientX - dragState.startX;

      if (Math.abs(movement) > 4) {
        const viewport = sliderViewportRef.current;
        dragState.didDrag = true;

        if (viewport && !viewport.hasPointerCapture(event.pointerId)) {
          viewport.setPointerCapture(event.pointerId);
        }
      }

      markInteracted();
      applySliderOffset(dragState.offset - movement);
    },
    [applySliderOffset, markInteracted],
  );

  const handlePointerUp = useCallback((event: PointerEvent<HTMLDivElement>) => {
    const viewport = sliderViewportRef.current;

    if (viewport && viewport.hasPointerCapture(event.pointerId)) {
      viewport.releasePointerCapture(event.pointerId);
    }

    if (dragStateRef.current?.didDrag) {
      suppressNextClickRef.current = true;
      window.setTimeout(() => {
        suppressNextClickRef.current = false;
      }, 180);
    }

    dragStateRef.current = null;
  }, []);

  useEffect(() => {
    let animationFrame = 0;
    let previousTime = performance.now();

    const animate = (time: number) => {
      const elapsedSeconds = (time - previousTime) / 1000;
      previousTime = time;

      const boostVelocity = boostVelocityRef.current;
      const baseVelocity = !isPaused && !isInteracting ? 16 : 0;
      const velocity = baseVelocity + boostVelocity;

      if (velocity !== 0) {
        applySliderOffset(offsetRef.current + elapsedSeconds * velocity);
      }

      if (boostVelocity !== 0) {
        const decay = Math.sign(boostVelocity) * elapsedSeconds * 620;
        const nextBoostVelocity = boostVelocity - decay;
        boostVelocityRef.current = Math.sign(boostVelocity) === Math.sign(nextBoostVelocity) ? nextBoostVelocity : 0;
      }

      animationFrame = window.requestAnimationFrame(animate);
    };

    animationFrame = window.requestAnimationFrame(animate);

    return () => {
      window.cancelAnimationFrame(animationFrame);
    };
  }, [applySliderOffset, isInteracting, isPaused]);

  useEffect(() => {
    return () => {
      if (idleTimerRef.current !== null) {
        window.clearTimeout(idleTimerRef.current);
      }
    };
  }, []);

  return (
    <Box component="section" sx={{ pt: 2, width: "100%" }}>
      <Paper
        component="section"
        elevation={0}
        sx={{
          background: "linear-gradient(90deg, #536d60, #455f53)",
          border: 1,
          borderColor: "rgba(255, 255, 255, 0.18)",
          borderRadius: 2,
          color: "#fffaf0",
          display: "grid",
          gap: { xs: 2.5, md: 3.25 },
          overflow: "hidden",
          pb: { xs: 1.25, md: 1.5 },
          pt: { xs: 2, md: 3 },
          px: { xs: 2, md: 3 },
          position: "relative",
        }}
      >
        <Box sx={{ alignItems: "center", display: "flex", gap: 1.5, justifyContent: "space-between", minWidth: 0, textAlign: "left" }}>
          <Typography variant="h2" sx={{ color: "inherit", fontSize: { xs: 28, md: 36 }, mb: 0.5 }}>
            {t("startExploring")}:
          </Typography>
          <Stack direction="row" spacing={0.75} sx={{ flex: "0 0 auto" }}>
            <Box
              aria-label={t("sliderPreviousAria")}
              component="button"
              onClick={() => boostSlider(-1)}
              sx={sliderControlSx}
              title={t("sliderPrevious")}
              type="button"
            >
              <ChevronLeft size={18} />
            </Box>
            <Box
              aria-label={isPaused ? t("sliderResumeAria") : t("sliderPauseAria")}
              component="button"
              onClick={() => {
                markInteracted();
                setIsPaused((current) => !current);
              }}
              sx={sliderControlSx}
              title={isPaused ? t("sliderResume") : t("sliderPause")}
              type="button"
            >
              {isPaused ? <Play size={16} /> : <Pause size={16} />}
            </Box>
            <Box
              aria-label={t("sliderNextAria")}
              component="button"
              onClick={() => boostSlider(1)}
              sx={sliderControlSx}
              title={t("sliderNext")}
              type="button"
            >
              <ChevronRight size={18} />
            </Box>
          </Stack>
        </Box>
        <Box
          onPointerCancel={handlePointerUp}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onWheel={handleWheel}
          ref={sliderViewportRef}
          sx={{
            cursor: "grab",
            mx: 0,
            overflow: "hidden",
            pb: 0.75,
            position: "relative",
            touchAction: "pan-y",
            userSelect: "none",
            width: "100%",
            WebkitMaskImage: "linear-gradient(90deg, transparent 0, #000 9%, #000 91%, transparent 100%)",
            maskImage: "linear-gradient(90deg, transparent 0, #000 9%, #000 91%, transparent 100%)",
            "&:active": {
              cursor: "grabbing",
            },
            "&::before, &::after": {
              bottom: 0,
              content: '""',
              pointerEvents: "none",
              position: "absolute",
              top: 0,
              width: { xs: 34, md: 58 },
              zIndex: 2,
            },
            "&::before": {
              backdropFilter: "blur(1.8px)",
              left: 0,
            },
            "&::after": {
              backdropFilter: "blur(1.8px)",
              right: 0,
            },
          }}
        >
          <Box
            ref={sliderTrackRef}
            sx={{
              display: "flex",
              gap: 1.5,
              minWidth: "max-content",
              willChange: "transform",
              width: "max-content",
            }}
          >
            {sliderItems.map((item, index) => (
              <FeaturedEntityCard
                item={item}
                key={`${item.uri}-${index}`}
                language={language}
                onOpen={onOpen}
                suppressNextClickRef={suppressNextClickRef}
                t={t}
              />
            ))}
          </Box>
        </Box>
        <Typography
          sx={{
            color: "rgba(255, 250, 240, 0.66)",
            fontSize: { xs: 12, md: 13 },
            fontWeight: 500,
            lineHeight: 1.35,
            mt: -1.5,
            textAlign: "left",
          }}
        >
          {t("featuredSliderNote")}
        </Typography>
      </Paper>
    </Box>
  );
}

const sliderControlSx = {
  alignItems: "center",
  bgcolor: "rgba(255, 250, 240, 0.14)",
  border: "1px solid rgba(255, 250, 240, 0.32)",
  borderRadius: 1,
  color: "#fffaf0",
  cursor: "pointer",
  display: "inline-flex",
  height: 34,
  justifyContent: "center",
  p: 0,
  transition: "background 140ms ease, border-color 140ms ease",
  width: 34,
  "&:hover, &:focus-visible": {
    bgcolor: "rgba(255, 250, 240, 0.24)",
    borderColor: "rgba(255, 250, 240, 0.58)",
    outline: 0,
  },
};
