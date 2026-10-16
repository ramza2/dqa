/** Advisory comparison only. This shape does not carry authority or target values. */
export interface InspectorTargetReview {
  profile_id: number;
  inspector_configuration_state:
    | "DISABLED" | "ENV_BLOCKED" | "INVALID" | "CONFIGURED_UNVERIFIED";
  comparison_state:
    | "NOT_COMPARABLE" | "TARGET_METADATA_MISMATCH" | "STRUCTURAL_MATCH_UNVERIFIED";
  mismatch_fields: Array<
    | "environment" | "source_name" | "dbms_type" | "host" | "port"
    | "database_name_vs_service_name" | "username"
  >;
  profile_enabled: boolean;
  inspector_bound_to_profile: false;
  connection_authorized: false;
  live_connection_tested: false;
  inspector_credentials_shared: false;
}
