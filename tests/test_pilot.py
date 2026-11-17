"""Yapay birim fikstürleri; bu kayıtlar gerçek insan pilotu sonucu değildir."""

import copy
import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from sekilden_denkleme.pilot import (
    CHECKS,
    PilotStudy,
    PilotTrial,
    Stopwatch,
    evidence_file,
    export_study,
    load_study,
    save_study,
    summarize,
)
from sekilden_denkleme.project import load_project
from sekilden_denkleme.research_report import comparison_data, export_comparison

ROOT = Path(__file__).parents[1]


def trial(**updates):
    """Sadece test için kalite koşullarını sağlayan ölçüm fikstürü kurar."""
    values = dict(
        participant="UNIT-TEST",
        product="FreeCAD",
        product_version="test-version",
        operating_system="test-os",
        experience="test-fixture",
        baseline_method="test-only",
        case_id="unit-case",
        task="import",
        method="generated",
        kind="human",
        consent=True,
        seconds=10.0,
        checks=dict.fromkeys(CHECKS, True),
        status="completed",
    )
    return PilotTrial(**(values | updates))


def test_monotonic_stopwatch_excludes_pauses_and_prevents_double_start():
    clock = [100.0]
    watch = Stopwatch(clock=lambda: clock[0])
    watch.start()
    clock[0] = 102
    watch.start()
    assert watch.pause() == 2
    clock[0] = 1000
    assert watch.elapsed() == 2
    watch.start()
    clock[0] = 1003
    assert watch.pause() == 5 and watch.pause() == 5


@pytest.mark.parametrize(
    "updates",
    [
        {"consent": False},
        {"seconds": float("nan")},
        {"seconds": float("inf")},
        {"seconds": 0},
        {"seconds": -1},
        {"seconds": 601},
        {"repairs": True},
        {"checks": dict.fromkeys(CHECKS)},
        {"target_tolerance_mm": -1},
        {"evidence": {"sha256": "bad"}},
        {"recorded_at": "2026-10-15"},
    ],
)
def test_invalid_or_unverified_success_is_rejected(updates):
    with pytest.raises(ValueError):
        trial(**updates).validate()


def test_pairs_require_same_product_version_target_and_success_and_exclude_training():
    records = [
        trial(),
        trial(method="baseline", order=2, seconds=30, repairs=3),
        trial(product="AutoCAD"),
        trial(product="SolidWorks", kind="training_demo", consent=False),
        trial(repeat="2", status="timeout", seconds=600),
        trial(repeat="2", method="baseline", order=2),
        trial(repeat="3"),
        trial(repeat="3", method="baseline", order=2, target_tolerance_mm=0.2),
        trial(repeat="4"),
        trial(repeat="4", method="baseline", product_version="other", order=2),
    ]
    summary = summarize(PilotStudy(trials=records))
    assert summary["human_participants"] == 1 and summary["training_trials"] == 1
    assert len(summary["paired_results"]) == 1 and len(summary["excluded_pairs"]) == 6
    assert summary["by_product"][0]["median_seconds_delta"] == -20
    assert summary["by_product"][0]["median_repairs_delta"] == -3
    assert summary["by_product"][0]["product"] == "FreeCAD"


def test_ambiguous_order_and_different_tasks_are_not_pooled():
    records = [
        trial(),
        trial(method="baseline"),
        trial(task="edit", seconds=100),
        trial(task="edit", method="baseline", order=2, seconds=80),
    ]
    summary = summarize(PilotStudy(trials=records))
    assert summary["excluded_pairs"][0]["reason"] == "ambiguous_order"
    assert summary["by_product"][0]["task"] == "edit"
    assert summary["by_product"][0]["median_seconds_delta"] == 20
    with pytest.raises(ValueError, match="çift kayıt"):
        PilotStudy(trials=[trial(), trial()]).validate()


def test_study_save_reopen_schema_and_atomic_failure_preserve_previous(tmp_path, monkeypatch):
    study = PilotStudy(trials=[trial(kind="training_demo")])
    path = save_study(study, tmp_path / "pilot.json")
    assert load_study(path).to_dict() == study.to_dict()
    schema = json.loads((ROOT / "docs/pilot.schema.json").read_text(encoding="utf8"))
    Draft202012Validator(schema).validate(study.to_dict())
    previous = path.read_bytes()

    def fail(*args):
        raise OSError("Test yazma hatası")

    monkeypatch.setattr("sekilden_denkleme.pilot.os.replace", fail)
    with pytest.raises(OSError):
        save_study(PilotStudy(), path)
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob(".pilot-*"))


@pytest.mark.parametrize(
    "content", ['{"schema_version":"999"}', "[]", '{"schema_version":"1.0"}', "not json"]
)
def test_corrupt_or_future_pilot_file_has_explanatory_error(tmp_path, content):
    path = tmp_path / "broken.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        load_study(path)


def test_empty_export_and_formula_html_escaping_and_evidence_hash(tmp_path):
    assert summarize(PilotStudy())["human_participants"] == 0
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("actual test bytes")
    assert len(evidence_file(evidence)["sha256"]) == 64
    t = trial(participant="=2+3", notes="<script>alert(1)</script>", kind="training_demo")
    paths = export_study(PilotStudy(trials=[t]), tmp_path / "reports")
    assert len(paths) == 3
    with paths[1].open(encoding="utf-8-sig", newline="") as stream:
        row = list(csv.DictReader(stream))[0]
    assert row["participant"] == "'=2+3"
    text = paths[2].read_text(encoding="utf8")
    assert "<script>" not in text and "&lt;script&gt;" in text
    assert "İnsan katılımcı: 0" in text


def test_research_report_distinguishes_references_and_certificates(tmp_path):
    circle = load_project(ROOT / "examples/cad_validation/circle/model.json")
    ring = load_project(ROOT / "examples/cad_validation/ring/model.json")
    assert comparison_data([circle, copy.deepcopy(circle)])["same_reference"] is True
    assert comparison_data([circle, ring])["same_reference"] is False
    paths = export_comparison([circle, ring], tmp_path)
    text = paths[1].read_text(encoding="utf8")
    assert "Referans sınırları farklı" in text and "Sertifika U" in text and "Sayısal U" in text
    assert len(json.loads(paths[0].read_text())["projects"][0]["candidates"]) == len(
        circle.candidates
    )
    assert (
        comparison_data([replace(circle, config=replace(circle.config, tolerance=5))])[
            "same_reference"
        ]
        is True
    )
