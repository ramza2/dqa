import { describe, expect, it } from "vitest";
import { finalizeRequestHeaders } from "../api/client";
import type { ExecutionFormParameter } from "../types/queryAssistant";
import { CatalogApiError } from "../types/catalog";
import {
  buildParameterPayload,
  defaultsFromFormParameters,
  findEnumOptionIndex,
  formatAssistantError,
  isAuditReadDenied,
  readinessGuidanceMessage,
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
