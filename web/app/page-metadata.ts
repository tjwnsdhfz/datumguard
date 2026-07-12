import type { Metadata } from "next";

import { PRODUCTION_ORIGIN } from "../lib/site-config";

const SOCIAL_IMAGE = {
  url: `${PRODUCTION_ORIGIN}/opengraph-image`,
  width: 1200,
  height: 630,
  alt: "DatumGuard independent CAD assurance pipeline",
};

export function pageMetadata({
  title,
  description,
  path,
}: {
  title: string;
  description: string;
  path: `/${string}` | "/";
}): Metadata {
  const canonicalUrl = `${PRODUCTION_ORIGIN}${path}`;

  return {
    title,
    description,
    alternates: { canonical: canonicalUrl },
    openGraph: {
      type: "website",
      locale: "ko_KR",
      siteName: "DatumGuard",
      url: canonicalUrl,
      title,
      description,
      images: [SOCIAL_IMAGE],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [SOCIAL_IMAGE.url],
    },
  };
}
