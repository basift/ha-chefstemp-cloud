"""Offline tests for the grill setpoint controller's decision template.

Renders the `desired` Jinja (the control law) against synthetic (fan state,
temperature, rate) contexts and asserts the chosen action. No Home Assistant
services are called.
"""
from __future__ import annotations

from pathlib import Path

import jinja2
import yaml

PATH = (
    Path(__file__).resolve().parent.parent
    / "blueprints/automation/chefstemp/grill_setpoint_controller.yaml"
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


def _is_number(value):
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


DECISION = next(t for t in _templates(BLUEPRINT) if "lidrate = lid_drop_rate" in t)

DEFAULTS = dict(
    overshoot_lead=5, ramp_rate=6, hold_high=2, hold_low=3,
    lid_drop_rate=30, fast_drop_guard=10, rising_margin=1,
)


def decide(fan, T, R, target=200.0, factor=1.0, **over):
    th = {**DEFAULTS, **over}
    env = jinja2.Environment(autoescape=False)
    env.globals.update(is_state=lambda ent, val: fan == val)
    ctx = dict(R=float(R), T=float(T), target_d=float(target), factor=float(factor),
               fan_entity="fan.x", **th)
    return env.from_string(DECISION).render(**ctx).strip()


def test_lid_open_guard_forces_off_from_any_state():
    assert decide("on", T=190, R=-40) == "off"
    assert decide("off", T=190, R=-40) == "off"   # even already off, stays off-desired
    assert decide("on", T=120, R=-90) == "off"


def test_anti_overshoot_cuts_on_a_fast_climb_near_target():
    assert decide("on", T=196, R=8) == "off"      # T>=target-lead and R>ramp
    assert decide("on", T=196, R=3) == "none"     # near target but climbing gently -> hold
    assert decide("on", T=193, R=8) == "none"     # fast climb but still below target-lead


def test_drift_cap_cuts_above_the_band():
    assert decide("on", T=203, R=1) == "off"      # T>=target+hold_high
    assert decide("on", T=201, R=0) == "none"     # inside the band


def test_stall_escape_enables_when_settled_below_target():
    assert decide("off", T=195, R=0) == "on"      # flat below target-low
    assert decide("off", T=150, R=-3) == "on"     # slowly declining deep below target
    assert decide("off", T=199, R=0) == "none"    # inside band, do not enable


def test_natural_rise_is_left_alone():
    assert decide("off", T=180, R=5) == "none"    # recovering on its own -> wait


def test_do_not_enable_while_still_falling_fast():
    assert decide("off", T=180, R=-15) == "none"  # drop not settled yet (smoke grace)


def test_fahrenheit_scaling():
    # 200C target in F = 392; thresholds scale by 1.8
    assert decide("off", T=380, R=0, target=392, factor=1.8) == "on"      # below band
    assert decide("off", T=389, R=0, target=392, factor=1.8) == "none"    # within band (hold_low*1.8=5.4)
    assert decide("on", T=392, R=18, target=392, factor=1.8) == "off"     # fast climb at target-lead
    assert decide("on", T=350, R=-60, target=392, factor=1.8) == "off"    # lid drop (-30C/min = -54F/min)


def test_every_template_parses():
    env = jinja2.Environment()
    for t in _templates(BLUEPRINT):
        env.parse(t)
