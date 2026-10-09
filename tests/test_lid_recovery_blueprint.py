"""Offline template and structural checks; no Home Assistant services are called."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import jinja2
import pytest
import yaml

PATH = (
    Path(__file__).resolve().parent.parent
    / "blueprints/automation/chefstemp/lid_open_recovery_stall.yaml"
)


class BlueprintLoader(yaml.SafeLoader):
    """Preserve !input references for offline validation."""


BlueprintLoader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
BLUEPRINT = yaml.load(PATH.read_text(encoding="utf-8"), Loader=BlueprintLoader)


def _templates(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _templates(value)
    elif isinstance(node, list):
        for value in node:
            yield from _templates(value)
    elif isinstance(node, str) and ("{{" in node or "{%" in node):
        yield node


def _actions(node):
    if isinstance(node, dict):
        if "action" in node:
            yield node["action"]
        for value in node.values():
            yield from _actions(value)
    elif isinstance(node, list):
        for value in node:
            yield from _actions(value)


def _template(fragment):
    return next(text for text in _templates(BLUEPRINT) if fragment in text)


def _timestamp(value, default=0):
    if value is None:
        return default
    if isinstance(value, (float, int)):
        return value
    if isinstance(value, datetime):
        return value.timestamp()
    return datetime.fromisoformat(value).timestamp()


def _render(text, **context):
    env = jinja2.Environment(autoescape=False)
    env.globals.update(
        is_number=lambda value: _is_number(value),
        as_timestamp=_timestamp,
        now=lambda: datetime.fromtimestamp(1000, tz=UTC),
        states=lambda entity: context["entities"][entity].state,
        state_attr=lambda entity, key: context["entities"][entity].attributes.get(key),
        is_state=lambda entity, value: context["entities"][entity].state == value,
    )
    return env.from_string(text).render(**context).strip() == "True"


def _is_number(value):
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _initial(unit="°C", *, before=110, after=97, target=110, fan="on"):
    factor = 1.8 if unit == "°F" else 1
    def convert(value):
        return value * factor + (32 if unit == "°F" else 0)
    old = SimpleNamespace(state=str(convert(before)), attributes={
        "unit_of_measurement": unit, "ambient_sample_at": "1970-01-01T00:16:20+00:00",
    })
    new = SimpleNamespace(state=str(convert(after)), attributes={
        "unit_of_measurement": unit, "ambient_sample_at": "1970-01-01T00:16:30+00:00",
    })
    entities = {
        "target": SimpleNamespace(state=str(convert(target)), attributes={"unit_of_measurement": unit}),
        "fan": SimpleNamespace(state=fan, attributes={
            "thermostat_enabled_observed": fan == "on", "command_status": "observed",
        }),
    }
    return dict(trigger=SimpleNamespace(from_state=old, to_state=new),
                entities=entities, target_entity="target", fan_entity="fan",
                drop_threshold=10, near_target_margin=12, target_deadband=8,
                freshness_seconds=90)


@pytest.mark.parametrize("unit", ["°C", "°F"])
def test_initial_drop_requires_fresh_near_target_and_previously_on(unit):
    text = BLUEPRINT["conditions"][0]["value_template"]
    assert _render(text, **_initial(unit))
    assert not _render(text, **_initial(unit, fan="off"))
    assert not _render(text, **_initial(unit, before=108, after=105))
    assert not _render(text, **_initial(unit, before=90, after=77))
    assert not _render(text, **_initial(unit, before=110, after=103))
    context = _initial(unit)
    context["entities"]["target"].attributes["unit_of_measurement"] = "°F" if unit == "°C" else "°C"
    assert not _render(text, **context)
    context = _initial(unit)
    context["trigger"].to_state.attributes["ambient_sample_at"] = "1970-01-01T00:16:20+00:00"
    assert not _render(text, **context)
    context = _initial(unit)
    context["trigger"].to_state.state = "unavailable"
    assert not _render(text, **context)


def test_initial_stale_sample_fails_closed():
    context = _initial()
    context["trigger"].from_state.attributes["ambient_sample_at"] = "1970-01-01T00:13:00+00:00"
    assert not _render(BLUEPRINT["conditions"][0]["value_template"], **context)


@pytest.mark.parametrize("unit", ["°C", "°F"])
def test_recovery_requires_multiple_samples_and_rise_and_stall_is_windowed(unit):
    factor = 1.8 if unit == "°F" else 1
    recovery = _template("recovery_count | int >= minimum_samples")
    stall = _template("sample_ts | float - window_start | float >= stall_window")
    trend = _template("reading | float - window_temp | float <= allowed_rise")
    base = dict(reading=104 * factor, trough=97 * factor, recovery_rise=5,
                factor=factor, minimum_samples=3)
    assert not _render(recovery, **(base | {"recovery_count": 2}))
    assert _render(recovery, **(base | {"recovery_count": 3}))
    assert not _render(stall, sample_ts=1120, window_start=1000, stall_window=180,
                       window_count=3, minimum_samples=3)
    assert _render(stall, sample_ts=1180, window_start=1000, stall_window=180,
                   window_count=3, minimum_samples=3)
    options = dict(window_temp=104 * factor, factor=factor, allowed_rise=1,
                   reversal_threshold=2)
    assert not _render(trend, reading=108 * factor, **options)  # still rising rapidly
    assert _render(trend, reading=104.5 * factor, **options)  # plateau
    assert _render(trend, reading=101 * factor, **options)  # sustained reversal


def test_fail_safe_guards_and_no_restart_activation():
    assert BLUEPRINT["mode"] == "single"
    assert len(BLUEPRINT["triggers"]) == 1
    assert BLUEPRINT["triggers"][0]["trigger"] == "state"
    actions = BLUEPRINT["actions"]
    assert [step["action"] for step in actions if "action" in step][:2] == [
        "persistent_notification.create", "fan.turn_off",
    ]
    assert "observed" in actions[3]["wait_template"]
    assert actions[3]["continue_on_timeout"] is True
    abort = _template("wait.trigger.id in ['fan_override', 'target_change']")
    for safety in ("not wait.completed", "deadline", "freshness_seconds",
                   "fan_override", "target_change", "command_status",
                   "thermostat_enabled_observed", "initial_unit"):
        assert safety in abort
    enable = _template("ambient_sample_at') == wait.trigger.to_state")
    assert "target_deadband" in enable
    assert "is_state(fan_entity, 'off')" in enable
    assert list(_actions(BLUEPRINT)).count("fan.turn_on") == 1


def test_observation_aborts_on_timeout_staleness_override_and_target_change():
    template = _template("wait.trigger.id in ['fan_override', 'target_change']")
    context = _initial()
    context["entities"]["fan"].state = "off"
    context["entities"]["fan"].attributes["thermostat_enabled_observed"] = False
    context["entities"]["sensor"] = SimpleNamespace(
        state="97", attributes={"unit_of_measurement": "°C"},
    )
    context.update(temperature_sensor="sensor", initial_target=110.0,
                   initial_unit="°C", last_ts=990, deadline=1200,
                   wait=SimpleNamespace(completed=True, trigger=SimpleNamespace(id="sample")))
    assert not _render(template, **context)
    context["wait"].completed = False
    assert _render(template, **context)
    context["wait"].completed = True
    context["last_ts"] = 800
    assert _render(template, **context)
    context["last_ts"] = 990
    context["deadline"] = 1000
    assert _render(template, **context)
    context["deadline"] = 1200
    context["wait"].trigger.id = "fan_override"
    assert _render(template, **context)
    context["wait"].trigger.id = "target_change"
    assert _render(template, **context)
    context["wait"].trigger.id = "sample"
    context["entities"]["target"].state = "111.0"
    assert _render(template, **context)
    context["entities"]["target"].state = "110.0"
    context["entities"]["fan"].state = "on"
    assert _render(template, **context)
    context["entities"]["fan"].state = "off"
    context["entities"]["fan"].attributes["command_status"] = "unconfirmed"
    assert _render(template, **context)


@pytest.mark.parametrize("unit", ["°C", "°F"])
def test_final_enable_guard_requires_below_target_fresh_and_off(unit):
    template = _template("ambient_sample_at') == wait.trigger.to_state")
    factor = 1.8 if unit == "°F" else 1
    target = 110 * factor + (32 if unit == "°F" else 0)
    context = _initial(unit)
    fan = context["entities"]["fan"]
    fan.state = "off"
    fan.attributes["thermostat_enabled_observed"] = False
    sample_at = "sample-one"
    context["entities"]["sensor"] = SimpleNamespace(
        state=str(target - 12 * factor),
        attributes={"unit_of_measurement": unit, "ambient_sample_at": sample_at},
    )
    context.update(temperature_sensor="sensor", initial_target=target,
                   initial_unit=unit, factor=factor,
                   wait=SimpleNamespace(trigger=SimpleNamespace(
                       to_state=SimpleNamespace(attributes={"ambient_sample_at": sample_at}),
                   )))
    assert _render(template, **context)
    context["entities"]["sensor"].state = str(target - 2 * factor)
    assert not _render(template, **context)  # reached the target deadband first
    context["entities"]["sensor"].state = str(target - 12 * factor)
    fan.state = "on"
    assert not _render(template, **context)
    fan.state = "off"
    context["entities"]["sensor"].attributes["ambient_sample_at"] = "different"
    assert not _render(template, **context)


def test_every_jinja_template_parses():
    env = jinja2.Environment()
    for template in _templates(BLUEPRINT):
        env.parse(template)


@pytest.mark.parametrize("unit", ["°C", "°F"])
def test_observed_meat_in_steps_need_threshold_five(unit):
    """2026-10-09 live cook: the steepest single-sample drops were 8-9 °C.

    Both real meat-in drops (199->147 C and 200->156 C in about a minute)
    arrived in 4-9 C steps, so the previous default of 10 would never have
    fired. A 4 C step must still not fire (noise margin: steady wobble +/-1).
    """
    text = BLUEPRINT["conditions"][0]["value_template"]
    context = _initial(unit, before=199, after=195, target=200)
    context["drop_threshold"] = 5
    assert not _render(text, **context)
    for before, after in ((195, 187), (194, 185)):
        context = _initial(unit, before=before, after=after, target=200)
        context["drop_threshold"] = 5
        assert _render(text, **context)
        context["drop_threshold"] = 10
        assert not _render(text, **context)
