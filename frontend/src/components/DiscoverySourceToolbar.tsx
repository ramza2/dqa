import { useCatalogSource } from "../hooks/catalogSourceContext";
import { shortenFingerprint } from "../utils/fingerprint";
import { StatusBanner } from "./StatusBanner";

interface Props {
  actionBusy: boolean;
}

/** One permission-filtered active Catalog workspace, independent of connection profiles. */
export function DiscoverySourceToolbar({ actionBusy }: Props) {
  const { sources, selectedSource, selectSource, sourcesState } = useCatalogSource();
  const active = sources.find((item) => item.source_name === selectedSource) ?? null;

  return (
    <div className="dd-source-toolbar" data-testid="discovery-source-toolbar">
      <div className="dd-source-toolbar-main">
        <label className="dd-source-toolbar-picker">
          <span>활성 Catalog 데이터 소스</span>
          <select
            aria-label="Active Catalog source"
            data-testid="catalog-source-toolbar-select"
            value={active ? selectedSource : ""}
            disabled={actionBusy || sourcesState.status !== "ready"}
            onChange={(event) => selectSource(event.target.value)}
          >
            {!active ? <option value="">선택 가능한 활성 Catalog 없음</option> : null}
            {sources.map((item) => (
              <option key={item.source_name} value={item.source_name}>
                {item.source_name}
              </option>
            ))}
          </select>
        </label>
        {active ? (
          <div className="dd-source-toolbar-details" data-testid="toolbar-catalog-metadata">
            <span>개정번호 <strong>{active.revision_id}</strong></span>
            <span>패키지 버전 <strong>{active.package_version}</strong></span>
            <span>준비 상태 <strong className={active.package_readiness === "READY" ? "badge badge-ready" : "badge badge-warn"}>{active.package_readiness}</strong></span>
            <span>스키마 지문 <code title={active.schema_fingerprint}>{shortenFingerprint(active.schema_fingerprint)}</code></span>
          </div>
        ) : null}
      </div>
      {sourcesState.status !== "ready" ? (
        <StatusBanner state={sourcesState} emptyLabel="활성 Catalog가 없습니다." />
      ) : null}
    </div>
  );
}
