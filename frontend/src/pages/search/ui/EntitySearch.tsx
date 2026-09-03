import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import InputAdornment from "@mui/material/InputAdornment";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { searchEntities } from "@/shared/api";
import type { SearchResult } from "@/entities/entity";
import { isUserFacingEntity } from "@/entities/entity";
import { useI18n } from "@/shared/i18n";
import { SemanticIcon } from "@/shared/ui";

type Props = {
  query: string;
  onQueryChange: (query: string) => void;
  onOpen: (uri: string) => void;
};

export function EntitySearch({ query, onQueryChange, onOpen }: Props) {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const { t } = useI18n();
  const trimmed = useMemo(() => query.trim(), [query]);

  useEffect(() => {
    if (trimmed.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    const abort = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      searchEntities(trimmed, 25, abort.signal)
        .then((items) => {
          if (!abort.signal.aborted) {
            setResults(items.filter(isUserFacingEntity));
          }
        })
        .catch((err: Error) => {
          if (!abort.signal.aborted && err.name !== "AbortError") {
            setError(err.message);
          }
        })
        .finally(() => {
          if (!abort.signal.aborted) {
            setLoading(false);
          }
        });
    }, 350);
    return () => {
      abort.abort();
      window.clearTimeout(timer);
    };
  }, [trimmed]);

  return (
    <Autocomplete
      autoHighlight
      filterOptions={(options) => options}
      getOptionLabel={(option) => option.label}
      inputValue={query}
      loading={loading}
      noOptionsText={error ?? t("noConnectionsForFilters")}
      onChange={(_, item) => {
        if (item) {
          setOpen(false);
          onOpen(item.uri);
        }
      }}
      onClose={() => setOpen(false)}
      onInputChange={(_, value, reason) => {
        if (reason === "input" || reason === "clear") {
          onQueryChange(value);
          setOpen(true);
        }
      }}
      onOpen={() => setOpen(true)}
      open={open && (results.length > 0 || loading || Boolean(error))}
      options={results}
      renderInput={(params) => (
        <TextField
          {...params}
          autoFocus
          error={Boolean(error)}
          helperText={error}
          placeholder={t("searchPlaceholder")}
          sx={{
            "& .MuiOutlinedInput-root": {
              bgcolor: "#ffffff",
              borderRadius: 1,
            },
            "& .MuiOutlinedInput-root.Mui-focused": {
              bgcolor: "#ffffff",
            },
          }}
          slotProps={{
            input: {
              ...params.slotProps.input,
              startAdornment: (
                <InputAdornment position="start">
                  <Search size={18} />
                </InputAdornment>
              ),
              endAdornment: (
                <>
                  {loading && <CircularProgress color="inherit" size={18} />}
                  {params.slotProps.input.endAdornment}
                </>
              ),
            },
            htmlInput: params.slotProps.htmlInput,
          }}
        />
      )}
      renderOption={(props, item) => (
        <Box component="li" {...props} key={item.uri} sx={{ alignItems: "flex-start", display: "grid", gap: 0.5, py: 1 }}>
          <Box sx={{ alignItems: "center", display: "flex", gap: 1.25, minWidth: 0 }}>
            <SemanticIcon name={item.icon} />
            <Typography noWrap sx={{ fontWeight: 700 }}>
              {item.label}
            </Typography>
          </Box>
        </Box>
      )}
      sx={{ width: "100%" }}
    />
  );
}
