type Mesh = {
  vertices: [number, number, number][];
  triangles: [number, number, number][];
  truncated: boolean;
  source_triangle_count: number;
};

type ProjectedVertex = {
  x: number;
  y: number;
  depth: number;
};

function project([x, y, z]: [number, number, number]): ProjectedVertex {
  return {
    x: (x - y) * 0.8660254,
    y: (x + y) * 0.42 - z * 0.92,
    depth: x + y + z * 0.35,
  };
}

function faceShade(
  a: [number, number, number],
  b: [number, number, number],
  c: [number, number, number],
): number {
  const ux = b[0] - a[0];
  const uy = b[1] - a[1];
  const uz = b[2] - a[2];
  const vx = c[0] - a[0];
  const vy = c[1] - a[1];
  const vz = c[2] - a[2];
  const nx = uy * vz - uz * vy;
  const ny = uz * vx - ux * vz;
  const nz = ux * vy - uy * vx;
  const length = Math.hypot(nx, ny, nz) || 1;
  const light = Math.max(0, (nx * -0.35 + ny * -0.45 + nz * 0.82) / length);
  return Math.round(205 + light * 42);
}

export default function MeshPreview({ mesh, label }: { mesh: Mesh; label: string }) {
  if (!mesh.vertices.length || !mesh.triangles.length) {
    return <div className="mesh-empty">표시할 tessellation이 없습니다.</div>;
  }

  const projected = mesh.vertices.map(project);
  const minX = Math.min(...projected.map((point) => point.x));
  const maxX = Math.max(...projected.map((point) => point.x));
  const minY = Math.min(...projected.map((point) => point.y));
  const maxY = Math.max(...projected.map((point) => point.y));
  const width = Math.max(maxX - minX, 1);
  const height = Math.max(maxY - minY, 1);
  const padding = Math.max(width, height) * 0.1;
  const sampleStep = Math.max(1, Math.ceil(mesh.triangles.length / 1800));
  const faces = mesh.triangles
    .filter((_, index) => index % sampleStep === 0)
    .map((triangle, index) => {
      const points = triangle.map((vertexIndex) => projected[vertexIndex]);
      const vertices = triangle.map((vertexIndex) => mesh.vertices[vertexIndex]);
      return {
        key: `${triangle.join("-")}-${index}`,
        depth: points.reduce((sum, point) => sum + point.depth, 0) / 3,
        points: points.map((point) => `${point.x},${point.y}`).join(" "),
        shade: faceShade(vertices[0], vertices[1], vertices[2]),
      };
    })
    .sort((a, b) => a.depth - b.depth);

  return (
    <figure className="mesh-figure" data-testid="cad-mesh-preview">
      <svg
        viewBox={`${minX - padding} ${minY - padding} ${width + padding * 2} ${height + padding * 2}`}
        role="img"
        aria-label={`${label} OpenCascade tessellation preview`}
      >
        {faces.map((face) => (
          <polygon
            key={face.key}
            points={face.points}
            fill={`rgb(${face.shade} ${face.shade} ${Math.min(255, face.shade + 5)})`}
            stroke="#15151a"
            strokeWidth={Math.max(width, height) / 1100}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
      <figcaption>
        <span>OpenCascade mesh</span>
        <code>{mesh.source_triangle_count.toLocaleString()} triangles</code>
        {mesh.truncated && <b>preview capped</b>}
      </figcaption>
    </figure>
  );
}
