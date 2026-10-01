"""The stand-level probe diagnostics remain available before a probe appears."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.chefstemp import sensor


def test_probe_diagnostics_entity_exists_without_probe_sensor() -> None:
    counts = {"probe_1": {"received": 0, "accepted": 0, "rejected": 0}}
    coordinator = SimpleNamespace(
        device_mac="synthetic",
        device_name="stand",
        last_update_success=True,
        data={"available": True, "probes": {}, "probe_frame_counts": counts},
        async_add_listener=lambda callback: lambda: None,
    )
    batches = []
    entry = SimpleNamespace(runtime_data=coordinator, async_on_unload=lambda remove: None)
    asyncio.run(sensor.async_setup_entry(None, entry, batches.append))
    entities = list(batches[0])
    assert {entity.entity_description.key for entity in entities} == {
        "ambient", "stand_battery", "probe_frames"
    }
    diagnostic = next(entity for entity in entities if entity.entity_description.key == "probe_frames")
    assert diagnostic.native_value == 0
    assert diagnostic.extra_state_attributes == {
        "period": "since integration load (volatile)", **counts
    }
    coordinator.data["probe_frame_counts"] = {
        "probe_1": {"received": 3, "accepted": 1, "rejected": 2},
        "unindexed": {"received": 1, "accepted": 0, "rejected": 1},
    }
    assert diagnostic.native_value == 4
    assert "synthetic" not in str(diagnostic.extra_state_attributes)
