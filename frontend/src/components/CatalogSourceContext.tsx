import type { ReactNode } from "react";
import { CatalogSourceContext } from "../hooks/catalogSourceContext";
import {
  useCatalogSourceSelection,
  type CatalogSourceSelection,
} from "../hooks/useCatalogSourceSelection";

interface ProviderProps {
  children: ReactNode;
  /** Test override — skips the live /catalog/active loader. */
  value?: CatalogSourceSelection;
}

function LiveCatalogSourceProvider({ children }: { children: ReactNode }) {
  const live = useCatalogSourceSelection();
  return (
    <CatalogSourceContext.Provider value={live}>
      {children}
    </CatalogSourceContext.Provider>
  );
}

/**
 * Shares one permission-filtered active Catalog Source selection across
 * Schema Search, Table Explorer, ERD Explorer, Index Status and the default
 * Snapshot History view. Snapshot-only Sources retain a separate manual path.
 */
export function CatalogSourceProvider({ children, value }: ProviderProps) {
  if (value) {
    return (
      <CatalogSourceContext.Provider value={value}>
        {children}
      </CatalogSourceContext.Provider>
    );
  }
  return <LiveCatalogSourceProvider>{children}</LiveCatalogSourceProvider>;
}
