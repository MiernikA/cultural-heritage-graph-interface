import { ArrowLeft, Network } from "lucide-react";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Toolbar from "@mui/material/Toolbar";
import { useI18n } from "@/shared/i18n";
import enFlag from "./flags/en.png";
import plFlag from "./flags/pl.png";

type AppHeaderProps = {
  expertMode: boolean;
  hasEntity: boolean;
  onBack: () => void;
  onExpertModeToggle: () => void;
  onGoToSearch: () => void;
};

export function AppHeader({ expertMode, hasEntity, onBack, onExpertModeToggle, onGoToSearch }: AppHeaderProps) {
  const { language, setLanguage, t } = useI18n();

  return (
    <AppBar
      position="sticky"
      color="primary"
      elevation={0}
      sx={{
        borderBottom: 1,
        borderColor: "rgba(72, 66, 55, 0.16)",
        background: "linear-gradient(90deg, #536d60, #455f53)",
      }}
    >
      <Toolbar variant="dense" sx={{ gap: 1, justifyContent: "space-between" }}>
        <Box sx={{ alignItems: "center", display: "inline-flex", gap: 0.75, minHeight: 34, minWidth: 0 }}>
          {hasEntity && (
            <IconButton className="app-back-button" color="inherit" onClick={onBack} aria-label={t("back")} title={t("back")}>
              <ArrowLeft size={24} strokeWidth={2.6} />
            </IconButton>
          )}
          <Button className="app-brand-button" color="inherit" onClick={onGoToSearch} startIcon={<Network size={20} />}>
            {t("culturalGraph")}
          </Button>
        </Box>
        <Box sx={{ alignItems: "center", display: "inline-flex", gap: 0.75 }}>
          <Button
            color="inherit"
            onClick={onExpertModeToggle}
            size="small"
            variant={expertMode ? "outlined" : "text"}
            aria-pressed={expertMode}
            sx={{
              borderColor: "rgba(255, 255, 255, 0.62)",
              color: "#fff",
              fontSize: 12,
              fontWeight: 800,
              minHeight: 30,
              px: 1,
              textTransform: "none",
              whiteSpace: "nowrap",
              "&:hover": {
                borderColor: "rgba(255, 255, 255, 0.86)",
              },
            }}
          >
            {t("expertMode")}
          </Button>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={language}
            onChange={(_, value: "pl" | "en" | null) => value && setLanguage(value)}
            aria-label={t("language")}
            sx={{
              bgcolor: "transparent",
              "& .MuiToggleButton-root": {
                bgcolor: "transparent",
                border: 0,
                minWidth: 42,
                px: 0.5,
                py: 0.35,
                "&:hover": {
                  bgcolor: "transparent",
                },
              },
              "& .Mui-selected": {
                bgcolor: "transparent",
                "&:hover": {
                  bgcolor: "transparent",
                },
              },
            }}
          >
            <ToggleButton value="pl" aria-label={t("languagePolish")} title={t("languagePolish")}>
              <FlagImage active={language === "pl"} src={plFlag} />
            </ToggleButton>
            <ToggleButton value="en" aria-label={t("languageEnglish")} title={t("languageEnglish")}>
              <FlagImage active={language === "en"} src={enFlag} />
            </ToggleButton>
          </ToggleButtonGroup>
        </Box>
      </Toolbar>
    </AppBar>
  );
}

function FlagImage({ active, src }: { active: boolean; src: string }) {
  return (
    <Box
      component="img"
      src={src}
      alt=""
      sx={{
        borderRadius: 0.5,
        display: "block",
        filter: active ? "saturate(1.15) contrast(1.08)" : "saturate(0.45) contrast(0.82) opacity(0.62)",
        height: active ? 22 : 16,
        objectFit: "cover",
        transition: "height 140ms ease, width 140ms ease, filter 140ms ease",
        width: active ? 36 : 27,
      }}
    />
  );
}
