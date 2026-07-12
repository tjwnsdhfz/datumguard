import { ImageResponse } from "next/og";

export const alt = "DatumGuard independent CAD assurance pipeline";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    <div
      style={{
        alignItems: "stretch",
        background: "#f7f8f6",
        color: "#0a0a0a",
        display: "flex",
        flexDirection: "column",
        fontFamily: "Arial, sans-serif",
        height: "100%",
        justifyContent: "space-between",
        padding: "56px 64px",
        width: "100%",
      }}
    >
      <div style={{ alignItems: "center", display: "flex", justifyContent: "space-between" }}>
        <div style={{ alignItems: "center", display: "flex", gap: 18 }}>
          <div
            style={{
              alignItems: "center",
              background: "#000",
              borderRadius: 999,
              color: "#fff",
              display: "flex",
              fontSize: 24,
              height: 64,
              justifyContent: "center",
              width: 64,
            }}
          >
            DG
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <strong style={{ fontSize: 34, letterSpacing: "-0.03em" }}>DatumGuard</strong>
            <span style={{ color: "#52635c", fontSize: 19 }}>Independent CAD Assurance</span>
          </div>
        </div>
        <div style={{ color: "#0b6046", display: "flex", fontSize: 18, fontWeight: 700 }}>
          VERIFIED-ONLY EXPORT
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        <div style={{ display: "flex", fontSize: 58, fontWeight: 800, letterSpacing: "-0.055em", lineHeight: 1.08 }}>
          CAD COMMAND SUCCESS
          <br />
          IS NOT ACCURACY EVIDENCE.
        </div>
        <div style={{ color: "#42554d", display: "flex", fontSize: 23 }}>
          Lock requirements. Reopen serialized CAD. Remeasure independently. Gate export.
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, width: "100%" }}>
        {["01 CONTRACT", "02 SERIALIZE", "03 REOPEN", "04 REMEASURE", "05 GATE"].map(
          (label, index) => (
            <div
              key={label}
              style={{
                background: index === 4 ? "#dceee6" : "#fff",
                border: `2px solid ${index === 4 ? "#0b7655" : "#d3ddd8"}`,
                color: index === 4 ? "#07553e" : "#1d3028",
                display: "flex",
                flex: 1,
                fontSize: 16,
                fontWeight: 700,
                justifyContent: "center",
                padding: "18px 10px",
              }}
            >
              {label}
            </div>
          ),
        )}
      </div>
    </div>,
    size,
  );
}
