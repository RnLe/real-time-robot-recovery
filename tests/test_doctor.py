from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from real_time_recovery.doctor import (
    CheckResult,
    CudaProbe,
    DoctorReport,
    SerialAlias,
    SerialPortInfo,
    check_cuda,
    check_required_commands,
    check_serial_devices,
    check_usb_attachment,
    is_wsl_environment,
)


def test_report_prioritizes_errors_and_is_frozen() -> None:
    report = DoctorReport(
        (
            CheckResult("gpu", "info", "optional"),
            CheckResult("usb", "warning", "not attached"),
            CheckResult("python", "error", "wrong version"),
        )
    )

    assert report.overall_status == "error"
    assert report.exit_code == 1
    assert report.to_dict()["checks"][0]["status"] == "info"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        report.checks = ()  # type: ignore[misc]


def test_no_serial_device_is_a_warning() -> None:
    result = check_serial_devices((), ())

    assert result.status == "warning"
    assert result.summary == "No serial ports are visible"
    assert "Attach" in result.details[0]


def test_serial_devices_include_stable_aliases() -> None:
    port = SerialPortInfo(
        "/dev/ttyACM0",
        description="USB-Enhanced-SERIAL CH343",
        vendor_id=0x1A86,
        product_id=0x55D3,
        serial_number="ABC",
    )
    alias = SerialAlias("/dev/serial/by-id/usb-WCH_ABC", "/dev/ttyACM0")

    result = check_serial_devices((port,), (alias,))

    assert result.status == "ok"
    assert "1 serial port(s)" in result.summary
    assert any("1a86:55d3" in detail for detail in result.details)
    assert any("by-id" in detail for detail in result.details)


def test_wsl_without_forwarded_adapter_mentions_usbipd() -> None:
    result = check_usb_attachment(is_wsl=True, ports=(), lsusb_output="")

    assert result.status == "warning"
    assert "WSL detected" in result.summary
    assert "usbipd list" in result.details[0]


def test_wsl_with_ch343_adapter_is_ready() -> None:
    listing = "Bus 001 Device 002: ID 1a86:55d3 QinHeng Electronics USB Single Serial"

    result = check_usb_attachment(is_wsl=True, ports=(), lsusb_output=listing)

    assert result.status == "ok"
    assert "CH343" in result.summary


def test_unrelated_wch_serial_adapter_is_not_reported_as_ch343() -> None:
    listing = "Bus 001 Device 002: ID 1a86:7523 QinHeng Electronics CH340 serial converter"

    result = check_usb_attachment(is_wsl=True, ports=(), lsusb_output=listing)

    assert result.status == "warning"
    assert "no WCH/CH343" in result.summary


def test_native_linux_does_not_require_usbipd() -> None:
    result = check_usb_attachment(is_wsl=False, ports=(), lsusb_output="")

    assert result.status == "warning"
    assert "Native Linux" in result.summary
    assert "not required" in result.details[0]


@pytest.mark.parametrize(
    ("release", "environment", "expected"),
    [
        ("6.6.87.2-microsoft-standard-WSL2", {}, True),
        ("6.8.0-generic", {"WSL_INTEROP": "/run/WSL/1_interop"}, True),
        ("6.8.0-generic", {}, False),
    ],
)
def test_wsl_detection(
    release: str, environment: dict[str, str], expected: bool
) -> None:
    assert is_wsl_environment(release, environment) is expected


def test_missing_official_commands_are_errors() -> None:
    result = check_required_commands({"lerobot-find-port": "/bin/lerobot-find-port"})

    assert result.status == "error"
    assert "lerobot-setup-motors" in result.summary


def test_cuda_is_always_informational_for_bringup() -> None:
    result = check_cuda(CudaProbe("2.8.0", "12.8", False))

    assert result.status == "info"
    assert "acceptable" in result.details[0]
