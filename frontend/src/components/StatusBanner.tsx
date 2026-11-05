import type { LoadState } from "../hooks/useCatalogExplorer";

interface Props {
  state: LoadState;
  emptyLabel?: string;
}

export function StatusBanner({ state, emptyLabel = "표시할 데이터가 없습니다." }: Props) {
  if (state.status === "loading") {
    return <div className="banner banner-empty">불러오는 중…</div>;
  }
  if (state.status === "error") {
    return (
      <div className="banner banner-error" role="alert">
        <div>Catalog 데이터를 불러오지 못했습니다.</div>
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
