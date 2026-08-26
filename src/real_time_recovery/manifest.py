"""Typed loading and validation for the hardware manifest."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

ManifestStatus = Literal["draft", "verified"]
SUPPORTED_SCHEMA_VERSION = 1
SO101_BUS_BAUD_RATE = 1_000_000


class ManifestError(ValueError):
    """Raised when a hardware manifest is malformed or unsafe to verify."""


@dataclass(frozen=True)
class KitHardware:
    """Identity copied from the arm kit packaging."""

    manufacturer: str
    model: str
    variant: str
    sku: str | None


@dataclass(frozen=True)
class PowerSupplyHardware:
    """Power-supply ratings transcribed from its physical label."""

    label: str | None
    output_voltage_v: float | None
    output_current_a: float | None


@dataclass(frozen=True)
class ArmHardware:
    """Label information for one independent servo bus."""

    controller_label: str | None
    servo_model_label: str | None
    power_supply: PowerSupplyHardware


@dataclass(frozen=True)
class ArmPair:
    """Follower and leader hardware, each with its own IDs 1 through 6."""

    follower: ArmHardware
    leader: ArmHardware


@dataclass(frozen=True)
class HardwareManifest:
    """Hardware facts that are safe to keep in the public repository."""

    schema_version: int
    status: ManifestStatus
    kit: KitHardware
    bus_baud_rate: int
    arms: ArmPair

    @property
    def safety_omissions(self) -> tuple[str, ...]:
        """Return label and power fields that still need physical verification."""

        missing: list[str] = []
        if self.kit.sku is None:
            missing.append("kit.sku")

        for arm_name in ("follower", "leader"):
            arm = getattr(self.arms, arm_name)
            if arm.controller_label is None:
                missing.append(f"arms.{arm_name}.controller_label")
            if arm.servo_model_label is None:
                missing.append(f"arms.{arm_name}.servo_model_label")
            if arm.power_supply.label is None:
                missing.append(f"arms.{arm_name}.power_supply.label")
            if arm.power_supply.output_voltage_v is None:
                missing.append(f"arms.{arm_name}.power_supply.output_voltage_v")
            if arm.power_supply.output_current_a is None:
                missing.append(f"arms.{arm_name}.power_supply.output_current_a")
        return tuple(missing)

    @property
    def warnings(self) -> tuple[str, ...]:
        """Return bring-up warnings for a valid draft manifest."""

        if self.status == "verified":
            return ()

        messages = [
            "Manifest status is draft; verify physical labels before applying power."
        ]
        if self.safety_omissions:
            messages.append(
                "Missing safety-critical fields: " + ", ".join(self.safety_omissions)
            )
        return tuple(messages)


def load_hardware_manifest(path: str | Path) -> HardwareManifest:
    """Load a YAML manifest without accessing any connected hardware."""

    manifest_path = Path(path)
    try:
        with manifest_path.open(encoding="utf-8") as stream:
            document = yaml.safe_load(stream)
    except OSError as exc:
        raise ManifestError(f"Could not read manifest {manifest_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ManifestError(f"Invalid YAML in manifest {manifest_path}: {exc}") from exc

    return parse_hardware_manifest(document)


def parse_hardware_manifest(document: Any) -> HardwareManifest:
    """Parse a manifest mapping and reject unknown keys at every level."""

    root = _as_mapping(document, "manifest")
    _reject_unknown(root, {"schema_version", "status", "kit", "bus_baud_rate", "arms"}, "manifest")
    _require_keys(root, {"schema_version", "status", "kit", "bus_baud_rate", "arms"}, "manifest")

    schema_version = _as_integer(root["schema_version"], "schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ManifestError(
            f"schema_version must be {SUPPORTED_SCHEMA_VERSION}, got {schema_version}"
        )

    status = root["status"]
    if status not in ("draft", "verified"):
        raise ManifestError("status must be 'draft' or 'verified'")

    baud_rate = _as_integer(root["bus_baud_rate"], "bus_baud_rate")
    if baud_rate != SO101_BUS_BAUD_RATE:
        raise ManifestError(
            f"bus_baud_rate must be {SO101_BUS_BAUD_RATE} for the SO-ARM101"
        )

    manifest = HardwareManifest(
        schema_version=schema_version,
        status=status,
        kit=_parse_kit(root["kit"]),
        bus_baud_rate=baud_rate,
        arms=_parse_arms(root["arms"]),
    )
    if manifest.status == "verified" and manifest.safety_omissions:
        raise ManifestError(
            "verified manifest is missing safety-critical fields: "
            + ", ".join(manifest.safety_omissions)
        )
    return manifest


def _parse_kit(value: Any) -> KitHardware:
    item = _as_mapping(value, "kit")
    allowed = {"manufacturer", "model", "variant", "sku"}
    _reject_unknown(item, allowed, "kit")
    _require_keys(item, allowed, "kit")
    return KitHardware(
        manufacturer=_as_required_text(item["manufacturer"], "kit.manufacturer"),
        model=_as_required_text(item["model"], "kit.model"),
        variant=_as_required_text(item["variant"], "kit.variant"),
        sku=_as_optional_text(item["sku"], "kit.sku"),
    )


def _parse_arms(value: Any) -> ArmPair:
    item = _as_mapping(value, "arms")
    allowed = {"follower", "leader"}
    _reject_unknown(item, allowed, "arms")
    _require_keys(item, allowed, "arms")
    return ArmPair(
        follower=_parse_arm(item["follower"], "arms.follower"),
        leader=_parse_arm(item["leader"], "arms.leader"),
    )


def _parse_arm(value: Any, context: str) -> ArmHardware:
    item = _as_mapping(value, context)
    allowed = {"controller_label", "servo_model_label", "power_supply"}
    _reject_unknown(item, allowed, context)
    _require_keys(item, allowed, context)
    return ArmHardware(
        controller_label=_as_optional_text(
            item["controller_label"], f"{context}.controller_label"
        ),
        servo_model_label=_as_optional_text(
            item["servo_model_label"], f"{context}.servo_model_label"
        ),
        power_supply=_parse_power_supply(item["power_supply"], f"{context}.power_supply"),
    )


def _parse_power_supply(value: Any, context: str) -> PowerSupplyHardware:
    item = _as_mapping(value, context)
    allowed = {"label", "output_voltage_v", "output_current_a"}
    _reject_unknown(item, allowed, context)
    _require_keys(item, allowed, context)
    return PowerSupplyHardware(
        label=_as_optional_text(item["label"], f"{context}.label"),
        output_voltage_v=_as_optional_positive_number(
            item["output_voltage_v"], f"{context}.output_voltage_v"
        ),
        output_current_a=_as_optional_positive_number(
            item["output_current_a"], f"{context}.output_current_a"
        ),
    )


def _as_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ManifestError(f"{context} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise ManifestError(f"{context} keys must be strings")
    return value


def _reject_unknown(item: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise ManifestError(f"unknown {context} field(s): {', '.join(unknown)}")


def _require_keys(item: Mapping[str, Any], required: set[str], context: str) -> None:
    missing = sorted(required - set(item))
    if missing:
        raise ManifestError(f"missing {context} field(s): {', '.join(missing)}")


def _as_integer(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestError(f"{context} must be an integer")
    return value


def _as_required_text(value: Any, context: str) -> str:
    text = _as_optional_text(value, context)
    if text is None:
        raise ManifestError(f"{context} must be a non-empty string")
    return text


def _as_optional_text(value: Any, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{context} must be null or a non-empty string")
    return value.strip()


def _as_optional_positive_number(value: Any, context: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(f"{context} must be null or a positive number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ManifestError(f"{context} must be null or a positive number")
    return number
