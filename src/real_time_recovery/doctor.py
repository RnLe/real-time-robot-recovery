"""Read-only environment diagnostics for SO-ARM101 bring-up."""

from __future__ import annotations

import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from serial.tools import list_ports

from .manifest import ManifestError, load_hardware_manifest

CheckStatus = Literal["ok", "warning", "error", "info"]
EXPECTED_PYTHON = (3, 12)
EXPECTED_LEROBOT_VERSION = "0.6.1"
REQUIRED_LEROBOT_COMMANDS = (
    "lerobot-find-port",
    "lerobot-setup-motors",
    "lerobot-calibrate",
    "lerobot-teleoperate",
)


@dataclass(frozen=True)
class CheckResult:
    """One diagnostic observation and its user-facing explanation."""

    name: str
    status: CheckStatus
    summary: str
    details: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "details": list(self.details),
        }


@dataclass(frozen=True)
class DoctorReport:
    """Complete, immutable result of a diagnostics run."""

    checks: tuple[CheckResult, ...]

    @property
    def overall_status(self) -> Literal["ok", "warning", "error"]:
        statuses = {check.status for check in self.checks}
        if "error" in statuses:
            return "error"
        if "warning" in statuses:
            return "warning"
        return "ok"

    @property
    def exit_code(self) -> int:
        return 1 if self.overall_status == "error" else 0

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "overall_status": self.overall_status,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class SerialPortInfo:
    """Metadata obtained by enumerating a port, without opening it."""

    device: str
    description: str | None = None
    hardware_id: str | None = None
    vendor_id: int | None = None
    product_id: int | None = None
    serial_number: str | None = None

    @property
    def search_text(self) -> str:
        fields = (
            self.device,
            self.description or "",
            self.hardware_id or "",
            self.serial_number or "",
            _format_usb_id(self.vendor_id, self.product_id),
        )
        return " ".join(fields).lower()


@dataclass(frozen=True)
class SerialAlias:
    """Stable Linux alias and its current device target."""

    alias: str
    target: str


@dataclass(frozen=True)
class CudaProbe:
    """CUDA information collected from PyTorch, when it is installed."""

    torch_version: str | None
    compiled_cuda_version: str | None
    available: bool | None
    device_names: tuple[str, ...] = ()
    error: str | None = None


def run_doctor(
    manifest_path: str | Path = "configs/hardware_manifest.yaml",
    *,
    serial_ports: Sequence[SerialPortInfo] | None = None,
    serial_aliases: Sequence[SerialAlias] | None = None,
    is_wsl: bool | None = None,
    lsusb_output: str | None = None,
) -> DoctorReport:
    """Run diagnostics that never open a serial device or modify hardware."""

    ports = tuple(serial_ports) if serial_ports is not None else discover_serial_ports()
    aliases = tuple(serial_aliases) if serial_aliases is not None else discover_serial_aliases()
    wsl = is_wsl_environment() if is_wsl is None else is_wsl
    usb_listing = read_lsusb() if lsusb_output is None else lsusb_output

    checks = (
        check_python(),
        check_lerobot(probe_package_version("lerobot")),
        check_required_commands(
            {command: shutil.which(command) for command in REQUIRED_LEROBOT_COMMANDS}
        ),
        check_usb_attachment(is_wsl=wsl, ports=ports, lsusb_output=usb_listing),
        check_serial_devices(ports, aliases),
        check_manifest(manifest_path),
        check_cuda(probe_cuda()),
    )
    return DoctorReport(checks=checks)


def check_python(
    version: tuple[int, int, int] | None = None,
    implementation: str | None = None,
) -> CheckResult:
    """Check the project interpreter constraint."""

    detected = version or tuple(sys.version_info[:3])
    runtime = implementation or platform.python_implementation()
    rendered = ".".join(str(part) for part in detected)
    expected = ".".join(str(part) for part in EXPECTED_PYTHON)
    if detected[:2] == EXPECTED_PYTHON:
        return CheckResult("python", "ok", f"{runtime} {rendered} (expected {expected}.x)")
    return CheckResult(
        "python",
        "error",
        f"{runtime} {rendered}; this project requires Python {expected}.x",
    )


def probe_package_version(distribution: str) -> str | None:
    """Read installed distribution metadata without importing the package."""

    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def check_lerobot(version: str | None) -> CheckResult:
    """Check that the trusted LeRobot release is installed exactly."""

    if version is None:
        return CheckResult(
            "lerobot",
            "error",
            f"LeRobot {EXPECTED_LEROBOT_VERSION} is not installed",
            ("Install the locked hardware environment before assigning servo IDs.",),
        )
    if version != EXPECTED_LEROBOT_VERSION:
        return CheckResult(
            "lerobot",
            "error",
            f"LeRobot {version} is installed; expected {EXPECTED_LEROBOT_VERSION}",
        )
    return CheckResult("lerobot", "ok", f"LeRobot {version} is installed")


def check_required_commands(command_paths: Mapping[str, str | None]) -> CheckResult:
    """Report official CLI entry points without invoking them."""

    missing = tuple(
        command for command in REQUIRED_LEROBOT_COMMANDS if not command_paths.get(command)
    )
    details = tuple(
        f"{command}: {command_paths[command]}"
        for command in REQUIRED_LEROBOT_COMMANDS
        if command_paths.get(command)
    )
    if missing:
        return CheckResult(
            "lerobot_commands",
            "error",
            "Missing required LeRobot commands: " + ", ".join(missing),
            details,
        )
    return CheckResult(
        "lerobot_commands",
        "ok",
        "All required LeRobot commands are available",
        details,
    )


def discover_serial_ports() -> tuple[SerialPortInfo, ...]:
    """Enumerate OS serial metadata; no serial port is opened."""

    discovered: list[SerialPortInfo] = []
    try:
        ports = list_ports.comports()
    except Exception:  # pyserial delegates enumeration to platform-specific system APIs.
        return ()

    for port in ports:
        discovered.append(
            SerialPortInfo(
                device=str(port.device),
                description=_optional_string(port.description),
                hardware_id=_optional_string(port.hwid),
                vendor_id=port.vid,
                product_id=port.pid,
                serial_number=_optional_string(port.serial_number),
            )
        )
    return tuple(sorted(discovered, key=lambda item: item.device))


def discover_serial_aliases(
    directories: Sequence[Path] = (Path("/dev/serial/by-id"), Path("/dev/serial/by-path")),
) -> tuple[SerialAlias, ...]:
    """Read stable Linux symlinks, when udev exposes them."""

    aliases: list[SerialAlias] = []
    for directory in directories:
        try:
            entries = tuple(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                target = str(entry.resolve())
            except OSError:
                target = "unresolved"
            aliases.append(SerialAlias(alias=str(entry), target=target))
    return tuple(sorted(aliases, key=lambda item: item.alias))


def check_serial_devices(
    ports: Sequence[SerialPortInfo], aliases: Sequence[SerialAlias]
) -> CheckResult:
    """Summarize visible ports and stable aliases."""

    port_details = tuple(_format_port(port) for port in ports)
    alias_details = tuple(f"alias {alias.alias} -> {alias.target}" for alias in aliases)
    details = port_details + alias_details
    if not ports:
        return CheckResult(
            "serial_ports",
            "warning",
            "No serial ports are visible",
            ("Attach the USB adapter before motor setup.",) + alias_details,
        )
    if not aliases:
        return CheckResult(
            "serial_ports",
            "warning",
            f"{len(ports)} serial port(s) visible, but no stable Linux aliases found",
            details,
        )
    return CheckResult(
        "serial_ports",
        "ok",
        f"{len(ports)} serial port(s) and {len(aliases)} stable alias(es) visible",
        details,
    )


def is_wsl_environment(
    kernel_release: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> bool:
    """Detect WSL from the kernel release or WSL environment variables."""

    release = (kernel_release if kernel_release is not None else platform.release()).lower()
    environ = os.environ if environment is None else environment
    return "microsoft" in release or "WSL_INTEROP" in environ or "WSL_DISTRO_NAME" in environ


def read_lsusb() -> str:
    """Return the read-only USB device listing when lsusb is available."""

    if shutil.which("lsusb") is None:
        return ""
    try:
        result = subprocess.run(
            ["lsusb"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def check_usb_attachment(
    *, is_wsl: bool, ports: Sequence[SerialPortInfo], lsusb_output: str
) -> CheckResult:
    """Infer whether the WCH/CH343 adapter is attached to this Linux instance."""

    visible = _adapter_is_visible(ports, lsusb_output)
    if is_wsl and visible:
        return CheckResult(
            "usb_attachment",
            "ok",
            "WSL detected; a WCH/CH343 USB adapter is visible",
            ("The usbipd attachment is active for this WSL session.",),
        )
    if is_wsl:
        return CheckResult(
            "usb_attachment",
            "warning",
            "WSL detected, but no WCH/CH343 USB adapter is visible",
            (
                "From elevated Windows PowerShell, inspect `usbipd list`, then attach the "
                "adapter with `usbipd attach --wsl --busid <BUSID>`.",
            ),
        )
    if visible:
        return CheckResult(
            "usb_attachment",
            "ok",
            "Native Linux detected; a WCH/CH343 USB adapter is visible",
            ("usbipd is only required when using WSL.",),
        )
    return CheckResult(
        "usb_attachment",
        "warning",
        "Native Linux detected; no WCH/CH343 USB adapter is visible",
        ("usbipd is not required on native Linux.",),
    )


def check_manifest(path: str | Path) -> CheckResult:
    """Validate manifest completeness without using its values to control hardware."""

    try:
        manifest = load_hardware_manifest(path)
    except ManifestError as exc:
        return CheckResult("hardware_manifest", "error", str(exc))

    if manifest.status == "draft":
        return CheckResult(
            "hardware_manifest",
            "warning",
            f"Draft hardware manifest has {len(manifest.safety_omissions)} unverified field(s)",
            manifest.warnings,
        )
    return CheckResult(
        "hardware_manifest",
        "ok",
        "Hardware manifest is verified and complete",
    )


def probe_cuda() -> CudaProbe:
    """Ask the installed PyTorch build for CUDA state."""

    torch_version = probe_package_version("torch")
    if torch_version is None:
        return CudaProbe(None, None, None)

    try:
        import torch

        available = bool(torch.cuda.is_available())
        names = (
            tuple(torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count()))
            if available
            else ()
        )
        return CudaProbe(
            torch_version=torch_version,
            compiled_cuda_version=torch.version.cuda,
            available=available,
            device_names=names,
        )
    except Exception as exc:  # CUDA discovery can fail because of a host driver mismatch.
        return CudaProbe(torch_version, None, None, error=f"{type(exc).__name__}: {exc}")


def check_cuda(probe: CudaProbe) -> CheckResult:
    """Report CUDA without making it a laptop bring-up requirement."""

    if probe.torch_version is None:
        return CheckResult(
            "cuda",
            "info",
            "PyTorch is not installed; CUDA is deferred until ML setup",
        )
    if probe.error is not None:
        return CheckResult(
            "cuda",
            "info",
            f"PyTorch {probe.torch_version} is installed, but CUDA probing failed",
            (probe.error,),
        )
    if not probe.available:
        compiled = probe.compiled_cuda_version or "none"
        return CheckResult(
            "cuda",
            "info",
            f"CUDA is unavailable (PyTorch {probe.torch_version}, compiled CUDA {compiled})",
            ("This is acceptable for laptop hardware bring-up.",),
        )
    return CheckResult(
        "cuda",
        "info",
        f"CUDA is available (PyTorch {probe.torch_version}, CUDA {probe.compiled_cuda_version})",
        probe.device_names,
    )


def _adapter_is_visible(ports: Sequence[SerialPortInfo], lsusb_output: str) -> bool:
    text = " ".join([*(port.search_text for port in ports), lsusb_output.lower()])
    # The Waveshare Bus Servo Adapter (A) uses WCH's single-port CH343
    # (USB VID:PID 1a86:55d3). Avoid treating every WCH serial device as this adapter.
    markers = ("ch343", "1a86:55d3")
    return any(marker in text for marker in markers)


def _format_port(port: SerialPortInfo) -> str:
    fields = [port.device]
    if port.description:
        fields.append(port.description)
    usb_id = _format_usb_id(port.vendor_id, port.product_id)
    if usb_id:
        fields.append(f"USB {usb_id}")
    if port.serial_number:
        fields.append(f"serial {port.serial_number}")
    return " | ".join(fields)


def _format_usb_id(vendor_id: int | None, product_id: int | None) -> str:
    if vendor_id is None or product_id is None:
        return ""
    return f"{vendor_id:04x}:{product_id:04x}"


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None
