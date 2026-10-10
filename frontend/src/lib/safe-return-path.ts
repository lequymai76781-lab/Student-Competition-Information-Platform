export function safeReturnPath(value: string | null, origin: string): string | null {
  if (!value) return null;
  let decoded = value;
  // Reject ambiguous encodings at every level. Bound decoding work and reject
  // values still changing at the bound, rather than accepting a partial check.
  for (let level = 0; level < 12; level += 1) {
    if (!decoded.startsWith("/") || decoded.startsWith("//") || /[\u0000-\u001f\u007f-\u009f\\]/u.test(decoded)) return null;
    try {
      const parsed = new URL(decoded, origin);
      if (parsed.origin !== origin || parsed.pathname.startsWith("//")) return null;
      // Decode only the path for authority ambiguity; encoded query values may
      // legitimately contain spaces or full URLs and never become an authority.
      const pathEnd = decoded.search(/[?#]/);
      const pathname = pathEnd < 0 ? decoded : decoded.slice(0, pathEnd);
      const nextPath = decodeURIComponent(pathname);
      if (nextPath === pathname) {
        const original = new URL(value, origin);
        return original.origin === origin ? original.pathname + original.search + original.hash : null;
      }
      decoded = nextPath + (pathEnd < 0 ? "" : decoded.slice(pathEnd));
    } catch { return null; }
  }
  return null;
}
