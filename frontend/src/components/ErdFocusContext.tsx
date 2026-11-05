import { useCallback, useMemo, useState, type ReactNode } from "react";
import {
  ErdFocusContext,
  type ErdFocusRequest,
} from "../hooks/erdFocusContext";

interface Props {
  children: ReactNode;
  onAfterRequest?: () => void;
}

/**
 * Carries a one-shot focus request from Table Explorer into ERD Explorer.
 * Does not replace Catalog Source selection or bypass /catalog/active gates.
 */
export function ErdFocusProvider({ children, onAfterRequest }: Props) {
  const [focusRequest, setFocusRequest] = useState<ErdFocusRequest | null>(null);

  const requestErdFocus = useCallback((request: ErdFocusRequest) => {
    setFocusRequest(request);
    onAfterRequest?.();
  }, [onAfterRequest]);

  const clearErdFocus = useCallback(() => {
    setFocusRequest(null);
  }, []);

  const value = useMemo(() => ({
    focusRequest,
    requestErdFocus,
    clearErdFocus,
  }), [focusRequest, requestErdFocus, clearErdFocus]);

  return (
    <ErdFocusContext.Provider value={value}>
      {children}
    </ErdFocusContext.Provider>
  );
}
