import type { LoadState } from "../hooks/useCatalogExplorer";

interface Props {
  state: LoadState;
  emptyLabel?: string;
}

export function StatusBanner({ state, emptyLabel = "No data" }: Props) {
  if (state.status === "loading") {
    return <div className="banner banner-empty">Loading…</div>;
  }
  if (state.status === "error") {
    return (
      <div className="banner banner-error" role="alert">
        <div>Catalog data could not be loaded.</div>
        <div>
          HTTP {state.httpStatus ?? "—"}
          {state.code ? (
            <>
              {" "}
              <code>{state.code}</code>
            </>
          ) : null}
        </div>
        <div>{state.message}</div>
      </div>
    );
  }
  if (state.status === "empty") {
    return <div className="banner banner-empty">{state.message ?? emptyLabel}</div>;
  }
  return null;
}
