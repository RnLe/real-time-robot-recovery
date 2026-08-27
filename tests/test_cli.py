from __future__ import annotations

import json
from pathlib import Path

from real_time_recovery import cli
from real_time_recovery.doctor import CheckResult, DoctorReport


def test_doctor_json_output(monkeypatch, capsys, tmp_path: Path) -> None:
    manifest_path = tmp_path / "hardware.yaml"
    observed: list[Path] = []

    def fake_run_doctor(path: str | Path) -> DoctorReport:
        observed.append(Path(path))
        return DoctorReport(
            (
                CheckResult("python", "ok", "CPython 3.12.14"),
                CheckResult("cuda", "info", "deferred"),
            )
        )

    monkeypatch.setattr(cli, "run_doctor", fake_run_doctor)

    exit_code = cli.main(["doctor", "--json", "--manifest", str(manifest_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert observed == [manifest_path]
    assert output["schema_version"] == 1
    assert output["overall_status"] == "ok"
    assert output["checks"][1]["status"] == "info"


def test_doctor_human_output_and_error_exit(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "run_doctor",
        lambda _path: DoctorReport((CheckResult("manifest", "error", "invalid"),)),
    )

    exit_code = cli.main(["doctor"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[ERROR" in output
    assert "Overall: error" in output
