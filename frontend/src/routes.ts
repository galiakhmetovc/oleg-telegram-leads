export function currentRoute(): string {
  if (window.location.hash.startsWith("#/")) {
    return normalizeRoute(window.location.hash);
  }
  return `${window.location.pathname}${window.location.search}`;
}

export function normalizeRoute(route: string): string {
  if (!route) {
    return "/";
  }
  if (route.startsWith("#/")) {
    return `/${route.slice(2)}`;
  }
  if (route.startsWith("#")) {
    return "/";
  }
  return route.startsWith("/") ? route : `/${route}`;
}

export function routeWithoutQuery(route: string): string {
  const normalized = normalizeRoute(route);
  const queryIndex = normalized.indexOf("?");
  return queryIndex === -1 ? normalized : normalized.slice(0, queryIndex);
}

export function routeQuery(route: string): URLSearchParams {
  const normalized = normalizeRoute(route);
  const queryIndex = normalized.indexOf("?");
  return queryIndex === -1 ? new URLSearchParams() : new URLSearchParams(normalized.slice(queryIndex + 1));
}

export function routeParts(route: string): string[] {
  return routeWithoutQuery(route).split("/").filter(Boolean).map(decodeURIComponent);
}

export function navigateRoute(route: string, options: { replace?: boolean } = {}) {
  const normalized = normalizeRoute(route);
  const current = `${window.location.pathname}${window.location.search}`;
  if (current === normalized && !window.location.hash) {
    window.dispatchEvent(new Event("popstate"));
    return;
  }
  if (options.replace) {
    window.history.replaceState(null, "", normalized);
  } else {
    window.history.pushState(null, "", normalized);
  }
  window.dispatchEvent(new Event("popstate"));
}

export function replaceRoute(route: string) {
  navigateRoute(route, { replace: true });
}

export function isCurrentPathRoute(prefix: string): boolean {
  return routeWithoutQuery(currentRoute()).startsWith(prefix);
}
