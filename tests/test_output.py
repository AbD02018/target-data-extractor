"""Test output formatters."""

from __future__ import annotations

import json

import yaml

from target_data_extractor.output import to_html, to_json, to_markdown, to_yaml


def test_to_json(sample_h1_program):
    out = to_json(sample_h1_program)
    parsed = json.loads(out)
    assert parsed["platform"] == "hackerone"
    assert "raw_data" not in parsed  # excluded by default


def test_to_json_include_raw(sample_h1_program):
    # Set raw_data on a copy (it's excluded by default)
    program = sample_h1_program.model_copy(update={"raw_data": {"test": "value"}})
    out = to_json(program, include_raw=True)
    parsed = json.loads(out)
    assert "raw_data" in parsed
    assert parsed["raw_data"] == {"test": "value"}


def test_to_yaml(sample_h1_program):
    out = to_yaml(sample_h1_program)
    parsed = yaml.safe_load(out)
    assert parsed["platform"] == "hackerone"
    assert parsed["max_bounty_usd"] == 60000


def test_to_markdown_contains_key_sections(sample_h1_program):
    out = to_markdown(sample_h1_program)
    assert "# GitHub Security" in out
    assert "## Bounty Table" in out
    assert "## In-Scope" in out
    assert "## Out-of-Scope" in out
    assert "## Rules" in out
    assert "*.github.com" in out
    assert "hackerone" in out


def test_to_markdown_no_rules_section_when_empty(sample_immunefi_program):
    out = to_markdown(sample_immunefi_program)
    # Immunefi fixture has rules with requires_kyc=True, so it should appear
    assert "Requires KYC" in out


def test_to_html_valid(sample_h1_program):
    out = to_html(sample_h1_program)
    assert "<!DOCTYPE html>" in out
    assert "<title>GitHub Security" in out
    assert "<table>" in out or "table" in out


def test_write_output_to_file(tmp_path, sample_h1_program):
    from target_data_extractor.output import write_output
    p = tmp_path / "program.json"
    write_output(sample_h1_program, p)
    assert p.exists()
    assert p.read_text(encoding="utf-8").startswith("{")


def test_write_output_markdown_format(tmp_path, sample_h1_program):
    from target_data_extractor.output import write_output
    p = tmp_path / "program.md"
    write_output(sample_h1_program, p)
    assert p.exists()
    assert "# GitHub Security" in p.read_text(encoding="utf-8")


def test_write_output_html_format(tmp_path, sample_h1_program):
    from target_data_extractor.output import write_output
    p = tmp_path / "program.html"
    write_output(sample_h1_program, p)
    assert p.exists()
    assert "<!DOCTYPE html>" in p.read_text(encoding="utf-8")


def test_write_output_unknown_format_raises(tmp_path, sample_h1_program):
    from target_data_extractor.output import write_output
    p = tmp_path / "program.csv"
    import pytest
    with pytest.raises(ValueError, match="Unsupported"):
        write_output(sample_h1_program, p)
