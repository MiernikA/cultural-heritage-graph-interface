export type RouteState = {
  entityUri: string | null;
  query: string;
};

export function readRoute(): RouteState {
  const params = new URLSearchParams(window.location.search);
  return {
    entityUri: params.get("entity"),
    query: params.get("q") ?? "",
  };
}

export function routeUrl(route: RouteState): string {
  const params = new URLSearchParams();
  if (route.query) {
    params.set("q", route.query);
  }
  if (route.entityUri) {
    params.set("entity", route.entityUri);
  }
  const query = params.toString();
  return `${window.location.pathname}${query ? `?${query}` : ""}`;
}

export function updateRoute(route: RouteState, mode: "push" | "replace") {
  const url = routeUrl(route);
  if (mode === "push") {
    window.history.pushState(route, "", url);
  } else {
    window.history.replaceState(route, "", url);
  }
}
