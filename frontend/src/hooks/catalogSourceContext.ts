import { createContext, useContext } from "react";
import type { CatalogSourceSelection } from "./useCatalogSourceSelection";

export const CatalogSourceContext = createContext<CatalogSourceSelection | null>(null);

export function useCatalogSource(): CatalogSourceSelection {
  const value = useContext(CatalogSourceContext);
  if (!value) {
    throw new Error("useCatalogSource requires CatalogSourceProvider");
  }
  return value;
}

/** Prefer the shared workspace selection when mounted under the provider. */
export function useOptionalCatalogSource(): CatalogSourceSelection | null {
  return useContext(CatalogSourceContext);
}
