from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest
import yaml

from real_time_recovery.manifest import (
    ManifestError,
    load_hardware_manifest,
    parse_hardware_manifest,
)


def complete_document(status: str = "verified") -> dict[str, object]:
    power = {
        "label": "AC/DC adapter 12 V 5 A",
        "output_voltage_v": 12,
        "output_current_a": 5,
    }
    return {
        "schema_version": 1,
        "status": status,
        "kit": {
            "manufacturer": "Waveshare",
            "model": "SO-ARM101",
            "variant": "SE",
            "sku": "label-transcription",
        },
        "bus_baud_rate": 1_000_000,
        "arms": {
            "follower": {
                "controller_label": "Bus Servo Adapter (A)",
                "servo_model_label": "STS3215",
                "power_supply": deepcopy(power),
            },
            "leader": {
                "controller_label": "Bus Servo Adapter (A)",
                "servo_model_label": "STS3215",
                "power_supply": deepcopy(power),
            },
        },
    }


def test_verified_manifest_is_typed_complete_and_frozen() -> None:
    manifest = parse_hardware_manifest(complete_document())

    assert manifest.status == "verified"
    assert manifest.safety_omissions == ()
    assert manifest.arms.follower.power_supply.output_voltage_v == 12.0
    with pytest.raises(FrozenInstanceError):
        manifest.status = "draft"  # type: ignore[misc]


def test_draft_manifest_warns_about_each_unverified_field() -> None:
    document = complete_document(status="draft")
    document["kit"]["sku"] = None  # type: ignore[index]
    document["arms"]["follower"]["controller_label"] = None  # type: ignore[index]
    document["arms"]["leader"]["power_supply"]["output_voltage_v"] = None  # type: ignore[index]

    manifest = parse_hardware_manifest(document)

    assert manifest.safety_omissions == (
        "kit.sku",
        "arms.follower.controller_label",
        "arms.leader.power_supply.output_voltage_v",
    )
    assert manifest.warnings[0].startswith("Manifest status is draft")
    assert "arms.follower.controller_label" in manifest.warnings[1]


@pytest.mark.parametrize(
    ("path", "unexpected"),
    [
        ((), "notes"),
        (("kit",), "color"),
        (("arms",), "spare"),
        (("arms", "leader"), "port"),
        (("arms", "follower", "power_supply"), "input_voltage_v"),
    ],
)
def test_unknown_keys_are_rejected_at_every_level(
    path: tuple[str, ...], unexpected: str
) -> None:
    document = complete_document()
    target = document
    for component in path:
        target = target[component]  # type: ignore[assignment,index]
    target[unexpected] = "not in schema"

    with pytest.raises(ManifestError, match="unknown"):
        parse_hardware_manifest(document)


def test_verified_manifest_requires_all_safety_fields() -> None:
    document = complete_document()
    document["arms"]["leader"]["servo_model_label"] = None  # type: ignore[index]

    with pytest.raises(
        ManifestError,
        match=r"verified manifest.*arms\.leader\.servo_model_label",
    ):
        parse_hardware_manifest(document)


def test_wrong_bus_baud_rate_is_rejected() -> None:
    document = complete_document(status="draft")
    document["bus_baud_rate"] = 115_200

    with pytest.raises(ManifestError, match="1000000"):
        parse_hardware_manifest(document)


def test_yaml_file_is_loaded(tmp_path) -> None:
    path = tmp_path / "hardware.yaml"
    path.write_text(yaml.safe_dump(complete_document()), encoding="utf-8")

    manifest = load_hardware_manifest(path)

    assert manifest.kit.model == "SO-ARM101"


@pytest.mark.parametrize("unsafe_rating", [0, -12, float("nan"), float("inf")])
def test_power_ratings_must_be_finite_and_positive(unsafe_rating: float) -> None:
    document = complete_document()
    document["arms"]["follower"]["power_supply"][  # type: ignore[index]
        "output_voltage_v"
    ] = unsafe_rating

    with pytest.raises(ManifestError, match="positive number"):
        parse_hardware_manifest(document)
