const DEFAULT_PRODUCTION_ORIGIN = "https://datumguard-tjwnsdhfz.vercel.app";

function normalizeOrigin(value: string | undefined): string | null {
  if (!value) {
    return null;
  }

  try {
    const url = new URL(value);
    if (url.protocol !== "https:" && url.protocol !== "http:") {
      return null;
    }

    return url.origin;
  } catch {
    return null;
  }
}

/**
 * The canonical public origin. Vercel preview deployments intentionally keep
 * pointing at the production site instead of indexing a per-commit hostname.
 */
export const PRODUCTION_ORIGIN =
  process.env.VERCEL_ENV === "preview"
    ? DEFAULT_PRODUCTION_ORIGIN
    : (normalizeOrigin(process.env.NEXT_PUBLIC_DATUMGUARD_SITE_URL) ??
      DEFAULT_PRODUCTION_ORIGIN);
