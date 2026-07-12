import type { MetadataRoute } from "next";

const ORIGIN = "https://datumguard-tjwnsdhfz.vercel.app";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${ORIGIN}/case-study`, priority: 1, changeFrequency: "weekly" },
    { url: `${ORIGIN}/`, priority: 0.9, changeFrequency: "weekly" },
    { url: `${ORIGIN}/piping`, priority: 0.9, changeFrequency: "weekly" },
    { url: `${ORIGIN}/plate`, priority: 0.8, changeFrequency: "weekly" },
    { url: `${ORIGIN}/intake`, priority: 0.7, changeFrequency: "weekly" },
    { url: `${ORIGIN}/solid`, priority: 0.5, changeFrequency: "monthly" },
    { url: `${ORIGIN}/privacy`, priority: 0.4, changeFrequency: "monthly" },
  ];
}
