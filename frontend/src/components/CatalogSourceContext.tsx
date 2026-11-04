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
 * Table Explorer and ERD Explorer. Schema Search / Index / Snapshot keep
 * their own source flows so they do not collide with this workspace selection.
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
