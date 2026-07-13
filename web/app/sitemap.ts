import type { MetadataRoute } from "next";

import { PRODUCTION_ORIGIN } from "../lib/site-config";

const SITE_LAST_MODIFIED = new Date("2026-07-13T00:00:00.000Z");

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: `${PRODUCTION_ORIGIN}/case-study`,
      lastModified: SITE_LAST_MODIFIED,
      priority: 1,
      changeFrequency: "weekly",
    },
    {
      url: `${PRODUCTION_ORIGIN}/`,
      lastModified: SITE_LAST_MODIFIED,
      priority: 0.9,
      changeFrequency: "weekly",
    },
    {
      url: `${PRODUCTION_ORIGIN}/piping`,
      lastModified: SITE_LAST_MODIFIED,
      priority: 0.9,
      changeFrequency: "weekly",
    },
    {
      url: `${PRODUCTION_ORIGIN}/frame`,
      lastModified: SITE_LAST_MODIFIED,
      priority: 0.9,
      changeFrequency: "weekly",
    },
    {
      url: `${PRODUCTION_ORIGIN}/plate`,
      lastModified: SITE_LAST_MODIFIED,
      priority: 0.8,
      changeFrequency: "weekly",
    },
    {
      url: `${PRODUCTION_ORIGIN}/openbim`,
      lastModified: SITE_LAST_MODIFIED,
      priority: 0.8,
      changeFrequency: "weekly",
    },
    {
      url: `${PRODUCTION_ORIGIN}/intake`,
      lastModified: SITE_LAST_MODIFIED,
      priority: 0.7,
      changeFrequency: "weekly",
    },
    {
      url: `${PRODUCTION_ORIGIN}/solid`,
      lastModified: SITE_LAST_MODIFIED,
      priority: 0.5,
      changeFrequency: "monthly",
    },
    {
      url: `${PRODUCTION_ORIGIN}/privacy`,
      lastModified: SITE_LAST_MODIFIED,
      priority: 0.4,
      changeFrequency: "monthly",
    },
  ];
}
