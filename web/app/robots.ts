import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: "https://datumguard-tjwnsdhfz.vercel.app/sitemap.xml",
  };
}
