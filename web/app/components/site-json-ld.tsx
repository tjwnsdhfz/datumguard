import { PRODUCTION_ORIGIN } from "../../lib/site-config";

const GITHUB_PROFILE = "https://github.com/tjwnsdhfz";
const REPOSITORY_URL = `${GITHUB_PROFILE}/datumguard`;
const PERSON_ID = `${GITHUB_PROFILE}#person`;
const APPLICATION_ID = `${PRODUCTION_ORIGIN}/#application`;

const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebSite",
      "@id": `${PRODUCTION_ORIGIN}/#website`,
      url: PRODUCTION_ORIGIN,
      name: "DatumGuard",
      description:
        "Independent, fail-closed verification evidence for AI-assisted CAD workflows.",
      inLanguage: ["ko-KR", "en"],
      publisher: { "@id": PERSON_ID },
    },
    {
      "@type": "WebApplication",
      "@id": APPLICATION_ID,
      url: PRODUCTION_ORIGIN,
      name: "DatumGuard",
      applicationCategory: "DesignApplication",
      operatingSystem: "Web",
      softwareVersion: "0.3.0",
      datePublished: "2026-07-12",
      description:
        "DatumGuard locks structured design requirements, independently reopens and remeasures serialized CAD artifacts, and blocks official export when verification fails.",
      isAccessibleForFree: true,
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "USD",
      },
      license: "https://spdx.org/licenses/MIT.html",
      releaseNotes: `${REPOSITORY_URL}/releases/tag/v0.3.0`,
      author: { "@id": PERSON_ID },
      featureList: [
        "Structured design contracts",
        "Independent DXF and STEP artifact remeasurement",
        "Fail-closed verified-only export",
        "Limited 2D linear-elastic structural frame screening",
      ],
      disambiguatingDescription:
        "Engineering verification research software. It does not certify structural safety or replace review by a responsible engineer.",
    },
    {
      "@type": "SoftwareSourceCode",
      "@id": `${REPOSITORY_URL}#source`,
      name: "DatumGuard source code",
      codeRepository: REPOSITORY_URL,
      programmingLanguage: ["Python", "TypeScript"],
      license: "https://spdx.org/licenses/MIT.html",
      targetProduct: { "@id": APPLICATION_ID },
      author: { "@id": PERSON_ID },
    },
    {
      "@type": "Person",
      "@id": PERSON_ID,
      name: "tjwnsdhfz",
      url: GITHUB_PROFILE,
    },
  ],
};

const serializedStructuredData = JSON.stringify(structuredData).replace(/</g, "\\u003c");

export default function SiteJsonLd() {
  return (
    <script
      id="datumguard-structured-data"
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: serializedStructuredData }}
    />
  );
}
