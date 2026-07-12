import Link from "next/link";

type WorkspaceId = "architecture" | "piping" | "plate" | "solid" | "intake" | "openbim";

const WORKSPACES: ReadonlyArray<{ id: WorkspaceId | "case-study"; href: string; label: string }> = [
  { id: "architecture", href: "/", label: "Architecture" },
  { id: "piping", href: "/piping", label: "Piping" },
  { id: "plate", href: "/plate", label: "Plate" },
  { id: "solid", href: "/solid", label: "3D Solid" },
  { id: "intake", href: "/intake", label: "Artifact Lab" },
  { id: "openbim", href: "/openbim", label: "OpenBIM" },
  { id: "case-study", href: "/case-study", label: "Case Study" },
];

export function WorkspaceNavigation({
  active,
  ariaLabel = "Engineering workspaces",
  evidenceHref,
}: {
  active: WorkspaceId;
  ariaLabel?: string;
  evidenceHref?: string;
}) {
  return (
    <nav aria-label={ariaLabel}>
      {WORKSPACES.map((workspace) => (
        <Link
          href={workspace.href}
          aria-current={workspace.id === active ? "page" : undefined}
          key={workspace.id}
        >
          {workspace.label}
        </Link>
      ))}
      {evidenceHref ? <a href={evidenceHref}>Evidence</a> : null}
    </nav>
  );
}

export function WorkspaceSkipLink({ targetId }: { targetId: string }) {
  return (
    <a className="workspace-skip-link" href={`#${targetId}`}>
      Skip to engineering workspace
    </a>
  );
}
