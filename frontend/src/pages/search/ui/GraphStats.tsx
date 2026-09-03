import { useMemo, useState, type MouseEvent } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useI18n } from "@/shared/i18n";
import { graphStatItems } from "../model/search-dashboard";

export function GraphStats() {
  const { language, t } = useI18n();
  const [activeStat, setActiveStat] = useState<string | null>(null);
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const numberFormatter = useMemo(() => new Intl.NumberFormat(language === "pl" ? "pl-PL" : "en-US"), [language]);
  const stats = useMemo(() => graphStatItems(t), [t]);
  const activeStatDetails = stats.find((stat) => stat.key === activeStat);

  const openStatPopup = (event: MouseEvent<HTMLElement>, key: string) => {
    setAnchorEl(event.currentTarget);
    setActiveStat(key);
  };

  const closeStatPopup = () => {
    setAnchorEl(null);
    setActiveStat(null);
  };

  return (
    <Box component="section" aria-label={t("graphStats")} sx={{ display: "flex", justifyContent: "center", py: 1.35, width: "100%" }}>
      <Stack
        component="dl"
        direction="row"
        spacing={0.9}
        sx={{
          alignItems: "center",
          flexWrap: "wrap",
          justifyContent: "center",
          m: 0,
          width: "fit-content",
        }}
      >
        {stats.map(({ accent, background, icon: Icon, key, label, value }) => (
          <Paper
            component="button"
            elevation={0}
            key={label}
            onClick={(event) => openStatPopup(event, key)}
            sx={{
              alignItems: "center",
              background,
              border: 1,
              borderColor: "rgba(72, 66, 55, 0.1)",
              borderRadius: 999,
              boxShadow: "0 8px 18px rgba(57, 48, 36, 0.04)",
              color: accent,
              display: "inline-flex",
              gap: 1,
              maxWidth: "100%",
              minHeight: 38,
              px: 1.25,
              py: 0.75,
              textAlign: "left",
              transition: "transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease, background 160ms ease",
              "&:hover, &:focus-visible": {
                borderColor: accent,
                boxShadow: "0 12px 24px rgba(57, 48, 36, 0.09)",
                outline: 0,
                transform: "translateY(-1px)",
              },
            }}
          >
            <Box
              aria-hidden="true"
              sx={{
                alignItems: "center",
                bgcolor: "rgba(255, 252, 244, 0.68)",
                borderRadius: 999,
                display: "inline-flex",
                flex: "0 0 auto",
                height: 24,
                justifyContent: "center",
                width: 24,
              }}
            >
              <Icon size={14} />
            </Box>
            <Typography component="dt" sx={{ color: "rgba(37, 33, 29, 0.64)", fontSize: 11, fontWeight: 700, lineHeight: 1, textTransform: "uppercase" }}>
              {label}
            </Typography>
            <Typography component="dd" sx={{ color: "#25211d", fontSize: 15, fontWeight: 800, lineHeight: 1, m: 0 }}>
              {numberFormatter.format(value)}
            </Typography>
          </Paper>
        ))}
      </Stack>
      <Popover
        anchorEl={anchorEl}
        onClose={closeStatPopup}
        open={Boolean(anchorEl && activeStatDetails)}
        anchorOrigin={{ horizontal: "left", vertical: "bottom" }}
        transformOrigin={{ horizontal: "left", vertical: "top" }}
        slotProps={{
          paper: {
            sx: {
              bgcolor: "#fffaf0",
              border: "1px solid rgba(72, 66, 55, 0.12)",
              borderRadius: 1,
              boxShadow: "0 14px 28px rgba(57, 48, 36, 0.14)",
              maxWidth: 260,
              mt: 0.75,
              p: 1.25,
            },
          },
        }}
      >
        {activeStatDetails && (
          <Box>
            <Typography sx={{ color: "#25211d", fontSize: 13, fontWeight: 800, mb: 0.35 }}>{activeStatDetails.label}</Typography>
            <Typography sx={{ color: "#625d52", fontSize: 12.5, lineHeight: 1.35 }}>{activeStatDetails.description}</Typography>
          </Box>
        )}
      </Popover>
    </Box>
  );
}
