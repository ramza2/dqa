import { describe, expect, it } from "vitest";
import { assertSameSnapshot, matchesActive, sameRevision } from "./revision";

describe("revision helpers", () => {
  it("sameRevision compares id and fingerprint", () => {
    expect(
      sameRevision(
        { revision_id: 2, schema_fingerprint: "aaa" },
        { revision_id: 2, schema_fingerprint: "aaa" },
      ),
    ).toBe(true);
    expect(
      sameRevision(
        { revision_id: 2, schema_fingerprint: "aaa" },
        { revision_id: 1, schema_fingerprint: "aaa" },
      ),
    ).toBe(false);
  });

  it("assertSameSnapshot rejects mixed batches", () => {
    expect(
      assertSameSnapshot([
        { revision_id: 2, schema_fingerprint: "fp2" },
        { revision_id: 2, schema_fingerprint: "fp2" },
      ]),
    ).toEqual({ revision_id: 2, schema_fingerprint: "fp2" });
    expect(
      assertSameSnapshot([
        { revision_id: 2, schema_fingerprint: "fp2" },
        { revision_id: 1, schema_fingerprint: "fp2" },
      ]),
    ).toBeNull();
  });

  it("matchesActive requires source and revision meta", () => {
    expect(
      matchesActive(
        { revision_id: 2, schema_fingerprint: "fp2" },
        {
          source_name: "oracle_demis_mock",
          revision_id: 2,
          schema_fingerprint: "fp2",
        },
        "oracle_demis_mock",
      ),
    ).toBe(true);
    expect(
      matchesActive(
        { revision_id: 1, schema_fingerprint: "fp1" },
        {
          source_name: "oracle_demis_mock",
          revision_id: 2,
          schema_fingerprint: "fp2",
        },
        "oracle_demis_mock",
      ),
    ).toBe(false);
  });
});
