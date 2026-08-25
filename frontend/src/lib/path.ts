/** next.config trailingSlash:true → pathname çoğu zaman `/gizlilik/` gelir. */
export function normalizeAppPath(path: string | null | undefined): string {
  if (!path) return "/";
  if (path.length > 1 && path.endsWith("/")) return path.slice(0, -1);
  return path;
}
