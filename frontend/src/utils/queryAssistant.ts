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

/** Operator-facing copy for known Catalog / Template / Profile readiness codes. */
export function readinessGuidanceMessage(code: string): string | null {
  switch (code) {
    case "ACTIVE_CATALOG_NOT_FOUND":
      return "활성 Catalog가 없습니다. Catalog Package를 먼저 활성화하세요.";
    case "CATALOG_MISMATCH":
      return "Catalog가 변경되었습니다. 소스를 다시 선택하고 목록을 갱신하세요.";
    case "TEMPLATE_NOT_FOUND":
      return "선택한 Query Template을 찾을 수 없습니다. 목록을 다시 불러오세요.";
    case "TEMPLATE_NOT_ELIGIBLE":
      return "선택한 Template이 승인·활성화 상태가 아니거나 현재 Catalog와 맞지 않습니다.";
    case "STALE_TEMPLATE_VERSION":
      return "선택한 Template 버전이 최신이 아닙니다. 목록을 다시 불러오세요.";
    case "PARAMETER_INVALID":
      return "입력한 조건이 템플릿 규칙에 맞지 않습니다. 각 항목을 확인한 뒤 다시 미리보기를 진행하세요.";
    case "PARAMETER_UNDECLARED":
      return "템플릿에 정의되지 않은 조건이 포함됐습니다. 템플릿을 다시 선택하세요.";
    case "PARAMETER_SCHEMA_INVALID":
      return "템플릿 조건 정의를 확인할 수 없습니다. 관리자에게 검토를 요청하세요.";
    case "SQL_UNSAFE":
      return "승인 템플릿의 안전성 검사를 통과하지 못했습니다. 실행할 수 없습니다.";
    case "CONNECTION_PROFILE_NOT_FOUND":
      return "해당 소스·환경의 연결 Profile이 없습니다. DB 연결 관리에서 등록하세요.";
    case "CONNECTION_PROFILE_DISABLED":
      return "연결 Profile이 비활성 상태입니다. 활성 Profile을 확인하세요.";
    case "CONNECTION_PROFILE_INCOMPLETE":
      return blockerMessage("CONNECTION_PROFILE_INCOMPLETE");
    case "DEMIS_ADAPTER_UNAVAILABLE":
      return blockerMessage("DEMIS_ADAPTER_UNAVAILABLE");
    default:
      return null;
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
    if (error.code) {
      const guided = readinessGuidanceMessage(error.code);
      if (guided) {
        return { code: error.code, message: guided };
      }
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

/** AUDIT_READ denied — history UI only; preserve query result rows. */
export function isAuditReadDenied(error: unknown): boolean {
  if (!(error instanceof CatalogApiError)) {
    return false;
  }
  if (error.status !== 403) {
    return false;
  }
  return error.code === "AUTHORIZATION_DENIED" || error.code === null || error.code === "";
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
      typeof item === "number" ? item : Number(String(item)),
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
    .map((item) => Number(item));
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
      payload[param.name] = typeof raw === "number" ? raw : Number(String(raw));
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

/**
 * Browser-side guidance only. The backend remains authoritative for template
 * eligibility, parameter validation and SQL safety on every preview/execute.
 * Messages never embed actual parameter values (including sensitive fields).
 */
export function validateParameterValues(
  parameters: ExecutionFormParameter[],
  values: Record<string, unknown>,
): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const param of parameters) {
    const raw = values[param.name];
    const missing = isUnsetParameterValue(raw) ||
      (typeof raw === "string" && raw.trim() === "");
    if (missing) {
      if (param.required) errors[param.name] = "필수 조건을 입력하거나 선택하세요.";
      continue;
    }

    if (param.type === "boolean") {
      if (typeof raw !== "boolean") errors[param.name] = "참/거짓 중 하나를 선택하세요.";
    } else if (param.type === "enum") {
      if (!((param.allowed_values ?? []).some((item) => Object.is(item, raw)))) {
        errors[param.name] = "허용된 선택지 중 하나를 선택하세요.";
      }
    } else if (param.type === "integer" || param.type === "decimal") {
      const value = typeof raw === "number" ? raw : Number(raw);
      const valid = typeof raw === "number" ||
        (typeof raw === "string" && (param.type === "integer"
          ? /^[+-]?\d+$/.test(raw.trim())
          : /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(raw.trim())));
      if (!valid || !Number.isFinite(value) ||
          (param.type === "integer" && !Number.isSafeInteger(value))) {
        errors[param.name] = param.type === "integer"
          ? "정수만 입력할 수 있습니다."
          : "유효한 숫자를 입력하세요.";
      } else if (param.min !== null && value < param.min) {
        errors[param.name] = `최솟값은 ${param.min}입니다.`;
      } else if (param.max !== null && value > param.max) {
        errors[param.name] = `최댓값은 ${param.max}입니다.`;
      }
    } else if (param.type === "integer_list" || param.type === "string_list") {
      const items = Array.isArray(raw) ? raw : typeof raw === "string"
        ? raw.split(",").map((item) => item.trim())
        : null;
      const valuesWithoutBlanks = items?.filter((item) => item !== "") ?? [];
      if (!items || valuesWithoutBlanks.length !== items.length) {
        errors[param.name] = "쉼표로 구분한 각 항목을 비워두지 마세요.";
      } else if (param.type === "integer_list" &&
          !items.every((item) => (typeof item === "number"
            ? Number.isSafeInteger(item)
            : /^[+-]?\d+$/.test(String(item)) && Number.isSafeInteger(Number(item))))) {
        errors[param.name] = "목록에는 정수만 입력할 수 있습니다.";
      } else if (param.min_items !== null && items.length < param.min_items) {
        errors[param.name] = `항목을 ${param.min_items}개 이상 입력하세요.`;
      } else if (param.max_items !== null && items.length > param.max_items) {
        errors[param.name] = `항목은 최대 ${param.max_items}개까지 입력할 수 있습니다.`;
      }
    } else if (param.type === "string") {
      if (typeof raw !== "string") {
        errors[param.name] = "문자열을 입력하세요.";
      } else if (param.pattern) {
        try {
          if (!new RegExp(`^(?:${param.pattern})$`).test(raw)) {
            errors[param.name] = "입력 형식이 템플릿 규칙에 맞지 않습니다.";
          }
        } catch {
          // Python-only regex: defer to the backend instead of blocking safely
          // entered values based on an unsupported browser expression.
        }
      }
    } else if (param.type === "date") {
      if (typeof raw !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(raw) ||
          !Number.isFinite(Date.parse(`${raw}T00:00:00Z`)) ||
          new Date(`${raw}T00:00:00Z`).toISOString().slice(0, 10) !== raw) {
        errors[param.name] = "날짜를 YYYY-MM-DD 형식으로 입력하세요.";
      }
    } else if (param.type === "datetime") {
      if (typeof raw !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(raw) ||
          !Number.isFinite(Date.parse(raw))) {
        errors[param.name] = "날짜와 시간을 올바르게 입력하세요.";
      }
    }
  }
  return errors;
}
