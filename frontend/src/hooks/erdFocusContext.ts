import { createContext, useContext } from "react";
import type { ErdHops } from "../utils/catalogErd";

/** One-shot Table Explorer → ERD Explorer focus handoff. */
export interface ErdFocusRequest {
  sourceName: string;
  schemaName: string;
  tableName: string;
  hops: ErdHops;
}

export interface ErdFocusApi {
  focusRequest: ErdFocusRequest | null;
  requestErdFocus: (request: ErdFocusRequest) => void;
  clearErdFocus: () => void;
}

export const ErdFocusContext = createContext<ErdFocusApi | null>(null);

export function useErdFocus(): ErdFocusApi {
  const value = useContext(ErdFocusContext);
  if (!value) {
    throw new Error("useErdFocus requires ErdFocusProvider");
  }
  return value;
}

export function useOptionalErdFocus(): ErdFocusApi | null {
  return useContext(ErdFocusContext);
}
