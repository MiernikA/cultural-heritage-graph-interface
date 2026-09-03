import Box from "@mui/material/Box";
import { useI18n } from "@/shared/i18n";

export function AppFooter() {
  const { t } = useI18n();
  return (
    <Box component="footer" className="app-footer">
      {t("footerText")}
    </Box>
  );
}
