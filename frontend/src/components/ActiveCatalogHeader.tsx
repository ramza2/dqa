import type { CatalogActiveSummary } from "../types/catalog";
import { shortenFingerprint } from "../utils/fingerprint";

interface Props {
  sources: CatalogActiveSummary[];
  selectedSource: string;
  onSelect: (sourceName: string) => void;
  disabled?: boolean;
}

export function SourceSelector({ sources, selectedSource, onSelect, disabled }: Props) {
  if (sources.length === 0) {
    return null;
  }
  if (sources.length === 1) {
    return (
      <div className="status-item">
        <span className="label">Source</span>
        <span className="value">{sources[0].source_name}</span>
      </div>
    );
  }
  return (
    <label className="status-item">
      <span className="label">Source</span>
      <select
        className="source-select"
        value={selectedSource}
        disabled={disabled}
        onChange={(event) => onSelect(event.target.value)}
        aria-label="Active Catalog source"
      >
        {sources.map((source) => (
          <option key={source.source_name} value={source.source_name}>
            {source.source_name}
          </option>
        ))}
      </select>
    </label>
  );
}

interface HeaderProps {
  active: CatalogActiveSummary | null;
  staleWarning: string | null;
}

export function ActiveCatalogHeader({ active, staleWarning }: HeaderProps) {
  if (!active) {
    return null;
  }

  const readinessClass =
    active.package_readiness === "READY"
      ? "badge badge-ready"
      : "badge badge-warn";

  return (
    <>
      <div className="status-grid" data-testid="active-catalog-status">
        <div className="status-item">
          <span className="label">Source</span>
          <span className="value">{active.source_name}</span>
        </div>
        <div className="status-item">
          <span className="label">Revision</span>
          <span className="value">{active.revision_id}</span>
        </div>
        <div className="status-item">
          <span className="label">Package version</span>
          <span className="value">{active.package_version}</span>
        </div>
        <div className="status-item">
          <span className="label">Readiness</span>
          <span className={readinessClass}>{active.package_readiness}</span>
        </div>
        <div className="status-item">
          <span className="label">Schema fingerprint</span>
          <button
            type="button"
            className="fingerprint-btn"
            title={active.schema_fingerprint}
            onClick={() => {
              void navigator.clipboard?.writeText(active.schema_fingerprint);
            }}
          >
            {shortenFingerprint(active.schema_fingerprint)}
          </button>
        </div>
      </div>
      {staleWarning ? <div className="banner banner-warn">{staleWarning}</div> : null}
    </>
  );
}
