/** Existing backend Connection Profile API contract. No live probe in S-05-C1. */
export interface ConnectionProfile {
  id: number;
  name: string;
  source_name: string;
  environment: string;
  enabled: boolean;
  dbms_type: string | null;
  host: string | null;
  port: number | null;
  database_name: string | null;
  username: string | null;
  /** Never display or prefill this reference in the UI. Not a credential value. */
  credential_secret_ref: string | null;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectionProfileList {
  total: number;
  limit: number;
  offset: number;
  items: ConnectionProfile[];
}

export interface ConnectionProfileDiagnostics {
  profile_id: number;
  source_name: string;
  environment: string;
  enabled: boolean;
  credential_reference_configured: boolean;
  target_metadata_configured: boolean;
  status: "INCOMPLETE" | "CONFIGURED_DISABLED" | "CONFIGURED_ENABLED";
  issues: { code: string; message: string }[];
  live_connection_tested: false;
}

/** No credential_secret_ref field or live connection operation in this UI. */
export interface ConnectionProfileCreate {
  name: string;
  source_name: string;
  environment: string;
  dbms_type?: string | null;
  host?: string | null;
  port?: number | null;
  database_name?: string | null;
  username?: string | null;
}

export type ConnectionProfileUpdate = Partial<
  Omit<ConnectionProfileCreate, "source_name" | "environment">
>;
