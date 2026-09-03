import { Network, Sparkles } from "lucide-react";
import Box from "@mui/material/Box";
import CardActionArea from "@mui/material/CardActionArea";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { RefObject } from "react";
import { semanticTypeLabel, type FeaturedEntity } from "@/entities/entity";
import { SemanticIcon } from "@/shared/ui";
import type { Language, TranslationKey } from "@/shared/i18n";

type FeaturedEntityCardProps = {
  item: FeaturedEntity;
  language: Language;
  onOpen: (uri: string) => void;
  suppressNextClickRef: RefObject<boolean>;
  t: (key: TranslationKey) => string;
};

export function FeaturedEntityCard({ item, language, onOpen, suppressNextClickRef, t }: FeaturedEntityCardProps) {
  return (
    <Paper
      variant="outlined"
      sx={{
        bgcolor: "rgba(255, 250, 240, 0.94)",
        borderColor: "rgba(255, 255, 255, 0.38)",
        flex: { xs: "0 0 230px", md: "0 0 220px" },
        maxWidth: { xs: 230, md: 220 },
        minHeight: 250,
        overflow: "hidden",
        pointerEvents: "auto",
      }}
    >
      <CardActionArea
        onClick={(event) => {
          if (suppressNextClickRef.current) {
            event.preventDefault();
            event.stopPropagation();
            suppressNextClickRef.current = false;
            return;
          }

          onOpen(item.uri);
        }}
        sx={{
          cursor: "pointer",
          display: "grid",
          gap: 1.25,
          height: "100%",
          p: 2,
          position: "relative",
        }}
      >
        <Box
          sx={{
            alignItems: "center",
            aspectRatio: "1",
            background:
              "radial-gradient(circle at 28% 18%, rgba(255, 252, 244, 0.95), rgba(255, 252, 244, 0) 36%), linear-gradient(145deg, rgba(224, 235, 218, 0.96), rgba(248, 244, 234, 0.9) 48%, rgba(228, 219, 195, 0.88))",
            border: "1px solid rgba(72, 66, 55, 0.14)",
            borderRadius: 1,
            color: "#7d765f",
            display: "grid",
            gap: "6px",
            height: 128,
            justifyItems: "center",
            maxHeight: 128,
            mx: "auto",
            p: "7px",
            placeItems: "center",
            textAlign: "center",
            width: 128,
            "& svg": {
              color: "#486456",
              strokeWidth: 2.8,
            },
          }}
        >
          <SemanticIcon name={item.icon} size={68} />
          <Box
            component="span"
            sx={{
              alignItems: "center",
              background: "rgba(237, 246, 240, 0.78)",
              border: "1px solid rgba(72, 100, 86, 0.26)",
              borderRadius: 999,
              boxShadow: "0 2px 6px rgba(72, 100, 86, 0.07)",
              color: "#486456",
              display: "inline-flex",
              fontSize: 12,
              fontWeight: 800,
              justifyContent: "center",
              lineHeight: 1.15,
              maxWidth: 112,
              px: "11px",
              py: "5px",
              textAlign: "center",
              textTransform: "uppercase",
            }}
          >
            {semanticTypeLabel(item.type, t)}
          </Box>
        </Box>
        <Box>
          <Typography
            sx={{
              color: "text.primary",
              display: "-webkit-box",
              fontSize: { xs: 16, md: 17 },
              fontWeight: 700,
              lineHeight: 1.12,
              minHeight: 60,
              overflow: "hidden",
              overflowWrap: "anywhere",
              textAlign: "center",
              WebkitBoxOrient: "vertical",
              WebkitLineClamp: 3,
            }}
            variant="h3"
          >
            {item.title}
          </Typography>
          <Stack sx={{ color: "text.secondary", gap: 0.75, mt: 1.5 }}>
            <Chip icon={<Network size={13} />} label={`${item.connections} ${t("connections").toLowerCase()}`} size="small" variant="outlined" />
            <Chip icon={<Sparkles size={13} />} label={`${item.recommendationCount} ${t("recommendations").toLowerCase()}`} size="small" variant="outlined" />
          </Stack>
        </Box>
      </CardActionArea>
    </Paper>
  );
}
