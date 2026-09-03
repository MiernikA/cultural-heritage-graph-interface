import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { useI18n } from "@/shared/i18n";
import { EntitySearch } from "./EntitySearch";
import { FeaturedEntities } from "./FeaturedEntities";
import { GraphStats } from "./GraphStats";

type Props = {
  query: string;
  onQueryChange: (query: string) => void;
  onOpen: (uri: string) => void;
};

export function SearchPage({ query, onQueryChange, onOpen }: Props) {
  const { t } = useI18n();
  return (
    <Container
      component="main"
      maxWidth="xl"
      sx={{
        alignItems: "center",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        minHeight: "calc(100dvh - 112px)",
        py: { xs: 2, md: 3 },
      }}
    >
      <Paper
        component="header"
        elevation={0}
        sx={{
          bgcolor: "transparent",
          borderBottom: 1,
          borderColor: "divider",
          maxWidth: 980,
          pb: 2,
          textAlign: "center",
          width: "100%",
        }}
      >
        <Box sx={{ maxWidth: "100%" }}>
          <Typography variant="h1" sx={{ fontSize: { xs: 34, md: 58 }, lineHeight: 1.02, maxWidth: "100%", overflowWrap: "anywhere" }}>
            {t("landingTitle")}
          </Typography>
          <Typography color="text.secondary" sx={{ fontSize: { xs: 16, md: 19 }, lineHeight: 1.45, maxWidth: 760, mx: "auto", mt: 1 }} variant="body1">
            {t("landingIntro")}
          </Typography>
        </Box>
        <Box sx={{ mt: 2.25 }}>
          <EntitySearch query={query} onQueryChange={onQueryChange} onOpen={onOpen} />
        </Box>
      </Paper>
      <GraphStats />
      <FeaturedEntities onOpen={onOpen} />
    </Container>
  );
}
