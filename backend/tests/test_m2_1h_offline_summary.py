"""M2-1H CLI summary contract; synthetic files only."""
from __future__ import annotations
import json

from app.cli.offline_metadata_preview import main
from tests.test_m2_1d_offline_metadata_export import encode, envelope
from tests.test_m2_1e_offline_provenance import fixture_claim, raw_claim
from tests.test_m2_1f_offline_review_draft import review_fixture

def test_offline_summary_without_claim_is_bounded_and_never_ready(tmp_path, capsys):
    metadata = tmp_path / "mock.json"
    metadata.write_bytes(encode(envelope()))
    assert main(["--input", str(metadata), "--summary-json"]) == 0
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert len(output.out) < 2048
    assert output.err == ""
    assert data["format"] == "dqa-offline-metadata-summary-v1"
    assert data["source_name"] == "oracle_demis_mock"
    assert data["table_count"] == 2 and data["column_count"] == 5
    assert data["claim_binding"] == "ABSENT"
    assert data["review_draft_status"] == "ABSENT"
    for name in ("issuer_authenticated", "review_actor_authenticated",
                 "independent_preflight_verified", "site_approval_verified",
                 "catalog_ready", "activation_eligible"):
        assert data[name] is False
    assert data["catalog_package_readiness"] == "WARNING"
    assert "snapshot" not in data
    assert "candidate_zip" not in data

def test_summary_includes_untrusted_claim_draft_but_never_approves(tmp_path, capsys):
    raw = encode(envelope())
    claim = raw_claim(fixture_claim(raw))
    draft = encode(review_fixture(raw, claim))
    metadata = tmp_path / "meta.json"
    sidecar = tmp_path / "claim.json"
    review = tmp_path / "draft.json"
    metadata.write_bytes(raw)
    sidecar.write_bytes(claim)
    review.write_bytes(draft)
    before = set(tmp_path.iterdir())
    assert main(["--input", str(metadata), "--claim", str(sidecar),
                 "--review-draft", str(review), "--summary-json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["claim_binding"] == "MATCHED_UNTRUSTED"
    assert data["review_draft_status"] == "ACKNOWLEDGED_UNVERIFIED"
    assert data["site_approval_verified"] is False
    assert data["catalog_ready"] is False
    assert "SYNTHETIC-REVIEWER" not in str(data)
    assert set(tmp_path.iterdir()) == before

def test_invalid_export_never_emits_success_summary(tmp_path, capsys):
    f = tmp_path / "bad.json"
    f.write_bytes(b'{"patient_rows":[{"name":"PRIVATE_RECORD"}]}')
    assert main(["--input", str(f), "--summary-json"]) != 0
    output = capsys.readouterr()
    assert output.out == ""
    assert "M2_1D_BLOCKED=" in output.err
    assert "PRIVATE_RECORD" not in output.err

def test_plain_cli_mode_stays_backward_compatible(tmp_path, capsys):
    f = tmp_path / "good.json"
    f.write_bytes(encode(envelope()))
    assert main(["--input", str(f)]) == 0
    out = capsys.readouterr().out
    assert "M2_1D_OFFLINE_SHAPE_PASS" in out
    assert "CATALOG_ACTIVATED=false" in out
    assert not out.lstrip().startswith("{")
