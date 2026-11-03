import { describe, expect, it } from "vitest";
import { finalizeRequestHeaders } from "../api/client";
import type { ExecutionFormParameter, RecommendedTemplate } from "../types/queryAssistant";
import { CatalogApiError } from "../types/catalog";
import {
  buildParameterPayload,
  defaultsFromFormParameters,
  filterManualTemplates,
  findEnumOptionIndex,
  formatAssistantError,
  isAuditReadDenied,
  readinessGuidanceMessage,
  validateParameterValues,
} from "../utils/queryAssistant";

function param(
  overrides: Partial<ExecutionFormParameter> & Pick<ExecutionFormParameter, "name" | "type">,
): ExecutionFormParameter {
  return {
    label: overrides.name,
    description: null,
    required: true,
    default: null,
    allowed_values: null,
    pattern: null,
    min: null,
    max: null,
    min_items: null,
    max_items: null,
    sensitive: false,
    ...overrides,
  };
}

describe("defaultsFromFormParameters", () => {
  it("preserves backend defaults and does not invent boolean/list blanks", () => {
    const values = defaultsFromFormParameters([
      param({ name: "flag", type: "boolean", default: true }),
      param({ name: "needed", type: "boolean", required: true, default: null }),
      param({ name: "tags", type: "string_list", required: false, default: null }),
      param({ name: "ward", type: "string", default: "A01" }),
    ]);
    expect(values).toEqual({ flag: true, ward: "A01" });
    expect(values).not.toHaveProperty("needed");
    expect(values).not.toHaveProperty("tags");
  });
});

describe("buildParameterPayload", () => {
  it("omits optional blank boolean and list; preserves selected false", () => {
    const parameters = [
      param({ name: "opt_flag", type: "boolean", required: false }),
      param({ name: "req_flag", type: "boolean", required: true }),
      param({ name: "tags", type: "string_list", required: false }),
      param({ name: "codes", type: "integer_list", required: false }),
    ];
    expect(
      buildParameterPayload(parameters, {
        opt_flag: undefined,
        req_flag: undefined,
        tags: "",
        codes: "  ",
      }),
    ).toEqual({});

    expect(
      buildParameterPayload(parameters, {
        req_flag: false,
        tags: "a, b",
        codes: "1, 2",
      }),
    ).toEqual({
      req_flag: false,
      tags: ["a", "b"],
      codes: [1, 2],
    });
  });

  it("preserves exact enum JSON types including 1 vs \"1\"", () => {
    const parameters = [
      param({
        name: "kind",
        type: "enum",
        allowed_values: [1, "1", true, false],
      }),
    ];
    expect(buildParameterPayload(parameters, { kind: 1 })).toEqual({ kind: 1 });
    expect(buildParameterPayload(parameters, { kind: "1" })).toEqual({ kind: "1" });
    expect(buildParameterPayload(parameters, { kind: true })).toEqual({ kind: true });
    expect(buildParameterPayload(parameters, { kind: false })).toEqual({ kind: false });
    expect(typeof buildParameterPayload(parameters, { kind: 1 }).kind).toBe("number");
    expect(typeof buildParameterPayload(parameters, { kind: "1" }).kind).toBe("string");
  });
});

describe("findEnumOptionIndex", () => {
  it("distinguishes number 1 from string \"1\"", () => {
    const allowed = [1, "1", true];
    expect(findEnumOptionIndex(allowed, 1)).toBe(0);
    expect(findEnumOptionIndex(allowed, "1")).toBe(1);
    expect(findEnumOptionIndex(allowed, true)).toBe(2);
  });
});

describe("readinessGuidanceMessage / formatAssistantError", () => {
  it("maps Catalog Template Profile readiness codes to operator guidance", () => {
    expect(readinessGuidanceMessage("ACTIVE_CATALOG_NOT_FOUND")).toMatch(/활성 Catalog/);
    expect(readinessGuidanceMessage("TEMPLATE_NOT_ELIGIBLE")).toMatch(/승인·활성화/);
    expect(readinessGuidanceMessage("CONNECTION_PROFILE_NOT_FOUND")).toMatch(/연결 Profile/);
    expect(
      formatAssistantError(
        new CatalogApiError(404, "raw", "ACTIVE_CATALOG_NOT_FOUND"),
      ),
    ).toEqual({
      code: "ACTIVE_CATALOG_NOT_FOUND",
      message: readinessGuidanceMessage("ACTIVE_CATALOG_NOT_FOUND"),
    });
  });

  it("detects AUDIT_READ denial without treating other 403s as audit denial only", () => {
    expect(isAuditReadDenied(new CatalogApiError(403, "denied", "AUTHORIZATION_DENIED"))).toBe(
      true,
    );
    expect(
      isAuditReadDenied(
        new CatalogApiError(403, "egress", "PARAMETER_EXTRACTION_EGRESS_NOT_ALLOWED"),
      ),
    ).toBe(false);
    expect(isAuditReadDenied(new CatalogApiError(404, "missing", "NOT_FOUND"))).toBe(false);
  });
});

describe("finalizeRequestHeaders", () => {
  it("strips manually supplied X-DQA-Dev-* headers in production", () => {
    const headers = finalizeRequestHeaders(
      {
        headers: {
          Authorization: "Bearer keep-me",
          "X-DQA-Dev-Actor": "should-strip",
          "X-DQA-Dev-Roles": "query_operator",
        },
      },
      {
        DEV: false,
        VITE_DQA_DEV_ACTOR: "query-operator",
        VITE_DQA_DEV_ROLES: "query_operator",
      },
    );
    expect(headers.get("Authorization")).toBe("Bearer keep-me");
    expect(headers.has("X-DQA-Dev-Actor")).toBe(false);
    expect(headers.has("X-DQA-Dev-Roles")).toBe(false);
  });

  it("adds configured DEV identity headers when missing", () => {
    const headers = finalizeRequestHeaders(
      { headers: { Authorization: "Bearer keep-me" } },
      {
        DEV: true,
        VITE_DQA_DEV_ACTOR: "query-operator",
        VITE_DQA_DEV_ROLES: "query_operator",
      },
    );
    expect(headers.get("Authorization")).toBe("Bearer keep-me");
    expect(headers.get("X-DQA-Dev-Actor")).toBe("query-operator");
    expect(headers.get("X-DQA-Dev-Roles")).toBe("query_operator");
  });
});

describe("CPU-first parameter guidance", () => {
  it("reports required and pattern failures without echoing sensitive values", () => {
    const schema = [
      param({ name: "ward", type: "string", pattern: "^[A-Z][0-9]{2}$", sensitive: true }),
      param({ name: "optional", type: "string", required: false }),
    ];
    expect(validateParameterValues(schema, {})).toEqual({
      ward: "필수 조건을 입력하거나 선택하세요.",
    });
    const errors = validateParameterValues(schema, { ward: "secret-123", optional: "" });
    expect(errors.ward).toMatch(/입력 형식/);
    expect(JSON.stringify(errors)).not.toContain("secret-123");
    expect(errors).not.toHaveProperty("optional");
  });

  it("rejects fractional/partial integers and enforces numeric limits", () => {
    const schema = [
      param({ name: "count", type: "integer", min: 2, max: 5 }),
      param({ name: "ratio", type: "decimal", required: false, min: 0, max: 1 }),
    ];
    expect(validateParameterValues(schema, { count: "2.5" }).count).toMatch(/정수/);
    expect(validateParameterValues(schema, { count: "2abc" }).count).toMatch(/정수/);
    expect(validateParameterValues(schema, { count: "1" }).count).toMatch(/최솟값/);
    expect(validateParameterValues(schema, { count: "6" }).count).toMatch(/최댓값/);
    expect(validateParameterValues(schema, { count: "3", ratio: "0.5" })).toEqual({});
    expect(buildParameterPayload(schema, { count: "3" }).count).toBe(3);
  });

  it("checks list item types/bounds and preserves typed enum equality", () => {
    const schema = [
      param({ name: "codes", type: "integer_list", min_items: 2, max_items: 3 }),
      param({ name: "choice", type: "enum", allowed_values: [1, "1"] }),
    ];
    expect(validateParameterValues(schema, { codes: "1, bad", choice: 1 }).codes).toMatch(/정수/);
    expect(validateParameterValues(schema, { codes: "1,", choice: 1 }).codes).toMatch(/비워두지/);
    expect(validateParameterValues(schema, { codes: "1", choice: 1 }).codes).toMatch(/이상/);
    expect(validateParameterValues(schema, { codes: "1,2,3,4", choice: 1 }).codes).toMatch(/최대/);
    expect(validateParameterValues(schema, { codes: "1, 2", choice: "1" })).toEqual({});
    expect(validateParameterValues(schema, { codes: "1,2", choice: true }).choice).toMatch(/허용/);
  });

  it("validates ISO dates and maps backend parameter errors to safe guidance", () => {
    const schema = [param({ name: "on", type: "date" })];
    expect(validateParameterValues(schema, { on: "2026-02-30" }).on).toMatch(/YYYY-MM-DD/);
    expect(validateParameterValues(schema, { on: "2024-02-29" })).toEqual({});
    expect(readinessGuidanceMessage("PARAMETER_INVALID")).toMatch(/조건/);
    expect(readinessGuidanceMessage("SQL_UNSAFE")).toMatch(/안전성/);
  });
});

describe("M5-S3 loaded-only approved template search", () => {
  const templates: RecommendedTemplate[] = [
    {
      template_id: 1, version_id: 11, version: 1, stable_key: "wards.lookup",
      name: "병동 조회", description: "진료 병동 코드", target_schemas: ["DEMIS_OWNER"],
      parameter_names: ["ward_cd", "active_yn"], parameter_count: 2,
    },
    {
      template_id: 2, version_id: 22, version: 1, stable_key: "doctors.lookup",
      name: "의료진 조회", description: "진료과별 목록", target_schemas: ["DEMIS_OWNER"],
      parameter_names: ["doctor_id"], parameter_count: 1,
    },
  ];

  it("matches space-separated terms across metadata fields and parameter names", () => {
    expect(filterManualTemplates(templates, "  병동   진료  ")).toEqual([templates[0]]);
    expect(filterManualTemplates(templates, "WARD_CD  DEMIS_OWNER")).toEqual([templates[0]]);
    expect(filterManualTemplates(templates, "ｗａｒｄｓ．ｌｏｏｋｕｐ")).toEqual([templates[0]]);
    expect(filterManualTemplates(templates, "조회")).toEqual(templates);
  });

  it("does not synthesize unloaded results or change an empty search", () => {
    expect(filterManualTemplates(templates, "없는 임의 조회")).toEqual([]);
    expect(filterManualTemplates(templates, "   ")).toBe(templates);
    expect(filterManualTemplates([], "의료진")).toEqual([]);
  });
});
