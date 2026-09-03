import { lazy, Suspense, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import Snackbar from "@mui/material/Snackbar";
import { getEntity } from "@/shared/api";
import { useI18n } from "@/shared/i18n";
import type { EntityDetail } from "@/entities/entity";
import { isUserFacingType } from "@/entities/entity";
import { readRoute, updateRoute, type RouteState } from "./model/route";
import { AppProviders } from "./providers/AppProviders";
import { AppFooter } from "./ui/AppFooter";
import { AppHeader } from "./ui/AppHeader";

const EntityPage = lazy(() => import("@/pages/entity").then((module) => ({ default: module.EntityPage })));
const SearchPage = lazy(() => import("@/pages/search").then((module) => ({ default: module.SearchPage })));

export function App() {
  return (
    <AppProviders>
      <AppShell />
    </AppProviders>
  );
}

function AppShell() {
  const [route, setRoute] = useState<RouteState>(() => readRoute());
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [loadingEntity, setLoadingEntity] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectionMapFocusRequest, setConnectionMapFocusRequest] = useState(0);
  const [expertMode, setExpertMode] = useState(() => localStorage.getItem("kg-expert-mode") === "true");
  const [detailsInfoOpen, setDetailsInfoOpen] = useState(false);
  const { t } = useI18n();

  useEffect(() => {
    const initialRoute = readRoute();
    if (initialRoute.entityUri && !window.history.state) {
      updateRoute({ ...initialRoute, entityUri: null }, "replace");
      updateRoute(initialRoute, "push");
    } else {
      updateRoute(initialRoute, "replace");
    }
    const handlePopState = () => setRoute(readRoute());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (!route.entityUri) {
      setEntity(null);
      setLoadingEntity(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoadingEntity(true);
    setError(null);
    getEntity(route.entityUri)
      .then((nextEntity) => {
        if (cancelled) {
          return;
        }
        if (!isUserFacingType(nextEntity.semantic_type)) {
          setEntity(null);
          setError(t("entityUnavailable"));
          const nextRoute = { ...route, entityUri: null };
          updateRoute(nextRoute, "replace");
          setRoute(nextRoute);
          return;
        }
        setEntity(nextEntity);
        if (nextEntity.uri !== route.entityUri) {
          const canonicalRoute = { ...route, entityUri: nextEntity.uri };
          updateRoute(canonicalRoute, "replace");
          setRoute(canonicalRoute);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingEntity(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [route, t]);

  const openEntity = (uri: string) => {
    if (route.entityUri === uri || entity?.uri === uri) {
      setConnectionMapFocusRequest((request) => request + 1);
      return;
    }
    const nextRoute = { ...route, entityUri: uri };
    updateRoute(nextRoute, "push");
    setRoute(nextRoute);
  };
  const updateSearchQuery = (query: string) => {
    const nextRoute = { query, entityUri: null };
    updateRoute(nextRoute, "replace");
    setRoute(nextRoute);
  };
  const goToSearch = () => {
    const nextRoute = { ...route, entityUri: null };
    updateRoute(nextRoute, "push");
    setRoute(nextRoute);
  };
  const toggleExpertMode = () => {
    if (expertMode) {
      localStorage.setItem("kg-expert-mode", "false");
      setExpertMode(false);
    } else {
      setDetailsInfoOpen(true);
    }
  };
  const cancelExpertMode = () => {
    setDetailsInfoOpen(false);
  };
  const confirmExpertMode = () => {
    localStorage.setItem("kg-expert-mode", "true");
    setExpertMode(true);
    setDetailsInfoOpen(false);
  };
  return (
    <>
      <AppHeader
        expertMode={expertMode}
        hasEntity={Boolean(entity)}
        onBack={() => window.history.back()}
        onExpertModeToggle={toggleExpertMode}
        onGoToSearch={goToSearch}
      />
      <Snackbar
        anchorOrigin={{ horizontal: "center", vertical: "bottom" }}
        autoHideDuration={6000}
        onClose={() => setError(null)}
        open={Boolean(error)}
      >
        <Alert severity="error" variant="filled" onClose={() => setError(null)} sx={{ maxWidth: "min(560px, calc(100vw - 24px))", width: "100%" }}>
          {error}
        </Alert>
      </Snackbar>
      <Dialog
        aria-labelledby="details-mode-dialog-title"
        open={detailsInfoOpen}
        onClose={() => setDetailsInfoOpen(false)}
      >
        <DialogTitle id="details-mode-dialog-title">{t("detailsModeDialogTitle")}</DialogTitle>
        <DialogContent>{t("detailsModeDialogBody")}</DialogContent>
        <DialogActions>
          <Button color="inherit" onClick={cancelExpertMode}>
            {t("cancel")}
          </Button>
          <Button onClick={confirmExpertMode} autoFocus>
            {t("understood")}
          </Button>
        </DialogActions>
      </Dialog>
      {loadingEntity && <LinearProgress />}
      <Suspense fallback={<LinearProgress />}>
        {entity ? (
          <EntityPage
            connectionMapFocusRequest={connectionMapFocusRequest}
            entity={entity}
            expertMode={expertMode}
            onOpen={openEntity}
          />
        ) : (
          <SearchPage query={route.query} onQueryChange={updateSearchQuery} onOpen={openEntity} />
        )}
      </Suspense>
      <AppFooter />
    </>
  );
}
