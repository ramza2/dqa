import { CatalogApiError } from "../types/catalog";
import type {
  ExecutionFormBlockerCode,
  ExecutionFormParameter,
} from "../types/queryAssistant";

export function blockerMessage(code: ExecutionFormBlockerCode | string): string {
  switch (code) {
    case "CONNECTION_PROFILE_INCOMPLETE":
      return "실행 환경 설정이 완료되지 않았습니다.";
    case "DEMIS_ADAPTER_UNAVAILABLE":
      return "DEMIS 실행 어댑터가 아직 구성되지 않았습니다.";
    default:
      return "실행할 수 없는 상태입니다.";
  }
}

export function formatAssistantError(error: unknown): { code: string | null; message: string } {
  if (error instanceof CatalogApiError) {
    if (error.status === 401) {
      return { code: error.code, message: "인증 정보가 없습니다." };
    }
    if (error.status === 403 && error.code === "AUTHORIZATION_DENIED") {
      return { code: error.code, message: "조회 실행 권한이 없습니다." };
    }
    if (error.code === "DEMIS_ADAPTER_UNAVAILABLE" || error.status === 503) {
      if (error.code === "DEMIS_ADAPTER_UNAVAILABLE") {
        return {
          code: error.code,
          message: blockerMessage("DEMIS_ADAPTER_UNAVAILABLE"),
        };
      }
    }
    return {
      code: error.code,
      message: error.message || `요청이 실패했습니다 (${error.status}).`,
    };
  }
  return { code: null, message: "요청 처리 중 오류가 발생했습니다." };
}

export function isEgressNotAllowed(error: unknown): boolean {
  if (!(error instanceof CatalogApiError)) {
    return false;
  }
  if (error.status !== 403) {
    return false;
  }
  const code = error.code ?? "";
  return code === "PARAMETER_EXTRACTION_EGRESS_NOT_ALLOWED" || code.includes("EGRESS_NOT_ALLOWED");
}

/** True when the operator has not supplied a value (and no invented default). */
export function isUnsetParameterValue(raw: unknown): boolean {
  return raw === undefined || raw === null || raw === "";
}

/**
 * Initialize form values from backend metadata defaults only.
 * Never invent false / [] when no default is present.
 */
export function defaultsFromFormParameters(
  parameters: ExecutionFormParameter[],
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const param of parameters) {
    if (param.default !== undefined && param.default !== null) {
      values[param.name] = param.default;
    }
  }
  return values;
}

function parseStringList(raw: unknown): string[] | null {
  if (Array.isArray(raw)) {
    return raw.map((item) => String(item));
  }
  if (typeof raw !== "string") {
    return null;
  }
  const trimmed = raw.trim();
  if (!trimmed) {
    return null;
  }
  return trimmed
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseIntegerList(raw: unknown): number[] | null {
  if (Array.isArray(raw)) {
    return raw.map((item) =>
      typeof item === "number" ? item : Number.parseInt(String(item), 10),
    );
  }
  if (typeof raw !== "string") {
    return null;
  }
  const trimmed = raw.trim();
  if (!trimmed) {
    return null;
  }
  return trimmed
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => Number.parseInt(item, 10));
}

/** Convert form state into API parameter payload (omit blank optional values). */
export function buildParameterPayload(
  parameters: ExecutionFormParameter[],
  values: Record<string, unknown>,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const param of parameters) {
    const raw = values[param.name];

    if (param.type === "boolean") {
      if (isUnsetParameterValue(raw)) {
        // Required blank stays missing; optional blank is omitted.
        continue;
      }
      payload[param.name] = raw === true;
      continue;
    }

    if (param.type === "integer") {
      if (isUnsetParameterValue(raw)) {
        continue;
      }
      payload[param.name] = typeof raw === "number" ? raw : Number.parseInt(String(raw), 10);
      continue;
    }

    if (param.type === "decimal") {
      if (isUnsetParameterValue(raw)) {
        continue;
      }
      payload[param.name] = typeof raw === "number" ? raw : Number(raw);
      continue;
    }

    if (param.type === "string_list") {
      const list = parseStringList(raw);
      if (list === null || list.length === 0) {
        continue;
      }
      payload[param.name] = list;
      continue;
    }

    if (param.type === "integer_list") {
      const list = parseIntegerList(raw);
      if (list === null || list.length === 0) {
        continue;
      }
      payload[param.name] = list;
      continue;
    }

    if (param.type === "enum") {
      if (isUnsetParameterValue(raw)) {
        continue;
      }
      // Preserve exact JSON type from allowed_values selection.
      payload[param.name] = raw;
      continue;
    }

    if (isUnsetParameterValue(raw)) {
      continue;
    }
    payload[param.name] = raw;
  }
  return payload;
}

export function listInputDisplayValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(", ");
  }
  if (isUnsetParameterValue(value)) {
    return "";
  }
  return String(value);
}

export function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return "[object]";
    }
  }
  return String(value);
}

export function stableParametersKey(parameters: Record<string, unknown>): string {
  const keys = Object.keys(parameters).sort();
  const normalized: Record<string, unknown> = {};
  for (const key of keys) {
    normalized[key] = parameters[key];
  }
  return JSON.stringify(normalized);
}

/** Selected enum option index for exact-type mapping (string "1" vs number 1). */
export function findEnumOptionIndex(allowedValues: unknown[], value: unknown): number {
  return allowedValues.findIndex((item) => Object.is(item, value));
}
