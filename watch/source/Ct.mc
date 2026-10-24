import Toybox.Application;
import Toybox.Lang;
import Toybox.Math;
import Toybox.System;
import Toybox.Time;

(:background :glance)
module Ct {
    const ENTITY_GRILL = "sensor.mllngo_grill_temperature";
    const ENTITY_PROBE = "sensor.backyard_mllngo_probe_1_temperature";
    const ENTITY_FAN = "fan.mllngo_fan";
    const ENTITY_FAN_TARGET = "number.mllngo_fan_target";
    const ENTITY_HIGH = "number.mllngo_grill_high_alarm";
    const ENTITY_LOW = "number.mllngo_grill_low_alarm";
    const ENTITY_PROBE_BATT = "sensor.backyard_mllngo_probe_1_battery";
    const ENTITY_STAND_BATT = "sensor.mllngo_stand_battery";
    const ENTITY_PROBE_TARGET = "input_number.chefstemp_probe_target";
    const ENTITY_MAX_ON = "input_boolean.chefstemp_max_alert";
    const ENTITY_MIN_ON = "input_boolean.chefstemp_min_alert";
    const ENTITY_PROBE_ON = "input_boolean.chefstemp_probe_alert";
    // How the integration currently reaches the stand: ble / cloud / disconnected.
    const ENTITY_CONN = "sensor.backyard_mllngo_connection_source";
    // HA timer helper driven from the watch; HA announces when it finishes.
    const ENTITY_TIMER = "timer.chefstemp_cook";

    const NUMBER_MIN = 0;
    const NUMBER_MAX = 300;

    // Readings outside this range (752 °F / -40 °F) are sensor errors, not temperatures.
    const TEMP_MAX_C = 400.0;
    const TEMP_MIN_C = -40.0;

    const KEY_DATA = "data";
    const KEY_HIST = "hist";
    const KEY_UNIT = "unit";
    const KEY_ALARM = "alarm";

    const UNIT_WATCH = 0;
    const UNIT_C = 1;
    const UNIT_F = 2;

    const HIST_WINDOW = 3600;
    const HIST_MIN_STEP = 20;
    const HIST_MAX_POINTS = 180;

    // Hysteresis (in the HA unit) before an alarm can fire again.
    const ALARM_RESET = 2;
    // Seconds the grill must hold above MIN to arm it, and below MIN to fire it.
    const LOW_HOLD = 120;

    const COLOR_ACCENT = 0xFFAA00;

    var _data as Dictionary? = null;

    function template() as String {
        return "{{ states('" + ENTITY_GRILL + "') }}|"
            + "{{ state_attr('" + ENTITY_GRILL + "','unit_of_measurement') }}|"
            + "{{ states('" + ENTITY_PROBE + "') }}|"
            + "{{ state_attr('" + ENTITY_PROBE + "','unit_of_measurement') }}|"
            + "{{ states('" + ENTITY_FAN_TARGET + "') }}|"
            + "{{ states('" + ENTITY_HIGH + "') }}|"
            + "{{ states('" + ENTITY_LOW + "') }}|"
            + "{{ state_attr('" + ENTITY_FAN_TARGET + "','unit_of_measurement') }}|"
            + "{{ states('" + ENTITY_FAN + "') }}|"
            + "{{ state_attr('" + ENTITY_FAN + "','motor_running') }}|"
            + "{{ states('" + ENTITY_PROBE_BATT + "') }}|"
            + "{{ states('" + ENTITY_STAND_BATT + "') }}|"
            + "{{ states('" + ENTITY_PROBE_TARGET + "') }}|"
            + "{{ state_attr('" + ENTITY_PROBE_TARGET + "','unit_of_measurement') }}|"
            + "{{ states('" + ENTITY_MAX_ON + "') }}|"
            + "{{ states('" + ENTITY_MIN_ON + "') }}|"
            + "{{ states('" + ENTITY_PROBE_ON + "') }}|"
            + "{{ states('" + ENTITY_CONN + "') }}|"
            + "{{ states('" + ENTITY_TIMER + "') }}|"
            // Remaining seconds: computed live for an active timer, the frozen
            // remainder while paused, -1 when idle/unknown/absent.
            + "{% set t='" + ENTITY_TIMER + "' %}"
            + "{% if is_state(t,'active') and state_attr(t,'finishes_at') %}"
            + "{{ (as_datetime(state_attr(t,'finishes_at'))-now()).total_seconds()|int }}"
            + "{% elif is_state(t,'paused') and state_attr(t,'remaining') %}"
            + "{{ as_timedelta(state_attr(t,'remaining')).total_seconds()|int }}"
            + "{% else %}-1{% endif %}";
    }

    function split(s as String, sep as String) as Array<String> {
        var out = [] as Array<String>;
        var i = s.find(sep);
        while (i != null) {
            out.add(s.substring(0, i) as String);
            s = s.substring(i + sep.length(), s.length()) as String;
            i = s.find(sep);
        }
        out.add(s);
        return out;
    }

    function num(s as String) as Float? {
        if (s.length() == 0) {
            return null;
        }
        var c = s.substring(0, 1) as String;
        if (!(c.equals("-") || (c.toNumber() != null))) {
            return null;
        }
        return s.toFloat();
    }

    function isF(unit as String?) as Boolean {
        return unit != null && unit.find("F") != null;
    }

    // A thermometer lifted off its stand reports error codes such as 65282 as the temperature.
    function temp(s as String, unit as String) as Float? {
        var v = num(s);
        if (v == null) {
            return null;
        }
        var c = isF(unit) ? (v - 32.0) * 5.0 / 9.0 : v;
        return (c > TEMP_MAX_C || c < TEMP_MIN_C) ? null : v;
    }

    function parse(s as String) as Dictionary? {
        var p = split(s, "|");
        if (p.size() < 20) {
            return null;
        }
        return {
            "g" => temp(p[0], p[1]),
            "gF" => isF(p[1]),
            "p" => temp(p[2], p[3]),
            "pF" => isF(p[3]),
            "ft" => num(p[4]),
            "hi" => num(p[5]),
            "lo" => num(p[6]),
            "nF" => isF(p[7]),
            "fan" => p[8],
            "run" => "True".equals(p[9]),
            "pb" => num(p[10]),
            "sb" => num(p[11]),
            "pt" => num(p[12]),
            "ptF" => isF(p[13]),
            "hiOn" => "on".equals(p[14]),
            "loOn" => "on".equals(p[15]),
            "ptOn" => "on".equals(p[16]),
            "conn" => p[17],
            "tState" => p[18],
            "tRem" => num(p[19]),
            "ts" => Time.now().value()
        };
    }

    function getData() as Dictionary? {
        if (_data == null) {
            var d = Application.Storage.getValue(KEY_DATA);
            if (d instanceof Dictionary) {
                _data = d;
            }
        }
        return _data;
    }

    function store(d as Dictionary) as Void {
        _data = d;
        try {
            Application.Storage.setValue(KEY_DATA, d);
            addHistory(d);
        } catch (e) {
        }
    }

    // Each history point: [timestamp, grill, probe], temperatures in the HA unit of the grill sensor.
    function getHistory() as Array {
        var h = Application.Storage.getValue(KEY_HIST);
        return (h instanceof Array) ? h : [];
    }

    function addHistory(d as Dictionary) as Void {
        var ts = d["ts"] as Number;
        var h = getHistory();
        if (h.size() > 0) {
            var last = h[h.size() - 1] as Array;
            if (ts - (last[0] as Number) < HIST_MIN_STEP) {
                return;
            }
        }
        h.add([ts, d["g"], d["p"]]);
        var cut = 0;
        while (cut < h.size() && (ts - ((h[cut] as Array)[0] as Number) > HIST_WINDOW || h.size() - cut > HIST_MAX_POINTS)) {
            cut++;
        }
        if (cut > 0) {
            h = h.slice(cut, null);
        }
        Application.Storage.setValue(KEY_HIST, h);
    }

    function getUnitPref() as Number {
        var u = Application.Storage.getValue(KEY_UNIT);
        return (u instanceof Number) ? u : UNIT_WATCH;
    }

    function setUnitPref(u as Number) as Void {
        Application.Storage.setValue(KEY_UNIT, u);
    }

    // Last timer duration the user set, in minutes (default 30).
    function getTimerMinutes() as Number {
        var m = Application.Storage.getValue("tmin");
        return (m instanceof Number && m >= 1) ? m : 30;
    }

    function setTimerMinutes(m as Number) as Void {
        Application.Storage.setValue("tmin", m);
    }

    function displayF() as Boolean {
        var u = getUnitPref();
        if (u == UNIT_F) {
            return true;
        }
        if (u == UNIT_C) {
            return false;
        }
        return System.getDeviceSettings().temperatureUnits == System.UNIT_STATUTE;
    }

    function unitLabel() as String {
        return displayF() ? "F" : "C";
    }

    function convert(v as Float, fromF as Boolean, toF as Boolean) as Float {
        if (fromF == toF) {
            return v;
        }
        return toF ? v * 9.0 / 5.0 + 32.0 : (v - 32.0) * 5.0 / 9.0;
    }

    function toDisplay(v as Float?, srcF as Boolean) as Float? {
        return v == null ? null : convert(v, srcF, displayF());
    }

    function fmt(v as Float?, srcF as Boolean) as String {
        var d = toDisplay(v, srcF);
        if (d == null) {
            return "--";
        }
        return Math.round(d).toNumber().toString();
    }

    function fmtU(v as Float?, srcF as Boolean) as String {
        var s = fmt(v, srcF);
        return s.equals("--") ? s : s + "°" + unitLabel();
    }

    function probeTargetSet(d as Dictionary) as Boolean {
        return d["ptOn"] == true && d["pt"] != null;
    }

    // Returns alert text for alarms that just crossed their threshold, or null.
    // With commit=false the stored alarm state is only read, so a later check
    // with the same data still fires.
    //
    // MIN only arms once the grill has held above that exact MIN for LOW_HOLD
    // seconds (a grill still heating up, or a MIN raised above the current
    // temperature, never alarms), and fires only after the grill stays below
    // it for LOW_HOLD seconds, so a lid opening does not alarm either.
    function checkAlarms(d as Dictionary, commit as Boolean) as String? {
        var st = Application.Storage.getValue(KEY_ALARM);
        if (!(st instanceof Dictionary)) {
            st = {};
        }
        var ts = d["ts"] as Number;
        var msgs = [] as Array<String>;
        var nF = d["nF"] as Boolean;
        var g = d["g"] as Float?;
        var lo = d["loOn"] == true ? d["lo"] as Float? : null;
        var hi = d["hiOn"] == true ? d["hi"] as Float? : null;
        if (lo == null || st["loFor"] != lo) {
            st["loFor"] = lo;
            st["loArmed"] = false;
            st["loAbove"] = null;
            st["loBelow"] = null;
        }
        if (hi == null || st["hiFor"] != hi) {
            st["hiFor"] = hi;
            st["hiFired"] = false;
        }
        if (g != null) {
            var gn = convert(g, d["gF"] as Boolean, nF);
            if (lo != null) {
                if (gn >= lo + ALARM_RESET) {
                    st["loBelow"] = null;
                    if (st["loAbove"] == null) {
                        st["loAbove"] = ts;
                    }
                    if (ts - (st["loAbove"] as Number) >= LOW_HOLD) {
                        st["loArmed"] = true;
                    }
                } else if (gn < lo) {
                    st["loAbove"] = null;
                    if (st["loArmed"] == true) {
                        if (st["loBelow"] == null) {
                            st["loBelow"] = ts;
                        }
                        if (ts - (st["loBelow"] as Number) >= LOW_HOLD) {
                            st["loArmed"] = false;
                            st["loBelow"] = null;
                            msgs.add("Grill below MIN\n" + fmtU(g, d["gF"] as Boolean) + " < " + fmtU(lo, nF));
                        }
                    }
                } else {
                    st["loAbove"] = null;
                    st["loBelow"] = null;
                }
            }
            if (hi != null) {
                if (gn > hi) {
                    if (st["hiFired"] != true) {
                        st["hiFired"] = true;
                        msgs.add("Grill above MAX\n" + fmtU(g, d["gF"] as Boolean) + " > " + fmtU(hi, nF));
                    }
                } else if (gn <= hi - ALARM_RESET) {
                    st["hiFired"] = false;
                }
            }
        }
        var p = d["p"] as Float?;
        var pt = d["pt"] as Float?;
        if (p != null && pt != null && d["ptOn"] == true) {
            var ptF = d["ptF"] as Boolean;
            var pn = convert(p, d["pF"] as Boolean, ptF);
            if (pn >= pt) {
                if (st["ptFired"] == null || (st["ptFired"] as Float) != pt) {
                    st["ptFired"] = pt;
                    msgs.add("Probe reached target\n" + fmtU(p, d["pF"] as Boolean));
                }
            } else if (pn <= pt - ALARM_RESET) {
                st["ptFired"] = null;
            }
        }
        if (d["ptOn"] != true) {
            st["ptFired"] = null;
        }
        if (commit) {
            try {
                Application.Storage.setValue(KEY_ALARM, st);
            } catch (e) {
            }
        }
        if (msgs.size() == 0) {
            return null;
        }
        var text = msgs[0];
        for (var i = 1; i < msgs.size(); i++) {
            text += "\n" + msgs[i];
        }
        return text;
    }

    function ageSeconds(d as Dictionary?) as Number? {
        if (d == null || d["ts"] == null) {
            return null;
        }
        return Time.now().value() - (d["ts"] as Number);
    }

    function ageText(d as Dictionary?) as String {
        var a = ageSeconds(d);
        if (a == null) {
            return "no data";
        }
        if (a < 60) {
            return "now";
        }
        if (a < 3600) {
            return (a / 60) + "m ago";
        }
        return (a / 3600) + "h ago";
    }

    // Local 24-hour wall clock, "HH:MM".
    function clockText() as String {
        var c = System.getClockTime();
        var hh = c.hour < 10 ? "0" + c.hour : c.hour.toString();
        var mm = c.min < 10 ? "0" + c.min : c.min.toString();
        return hh + ":" + mm;
    }

    // Connection source of the integration: :ble / :cloud / :off (disconnected/unknown).
    function connSource(d as Dictionary?) as Symbol {
        if (d == null) {
            return :off;
        }
        var c = d["conn"];
        if ("ble".equals(c)) {
            return :ble;
        }
        if ("cloud".equals(c)) {
            return :cloud;
        }
        return :off;
    }

    function timerState(d as Dictionary?) as String {
        if (d == null) {
            return "idle";
        }
        var s = d["tState"];
        return (s instanceof String) ? s : "idle";
    }

    function timerRunning(d as Dictionary?) as Boolean {
        var s = timerState(d);
        return s.equals("active") || s.equals("paused");
    }

    // Seconds left right now: the polled remainder, extrapolated locally while
    // active so the display ticks smoothly between 5-second polls. null = no timer.
    function timerRemaining(d as Dictionary?) as Number? {
        if (d == null) {
            return null;
        }
        var r = d["tRem"] as Float?;
        if (r == null || r < 0) {
            return null;
        }
        var secs = r.toNumber();
        if (timerState(d).equals("active")) {
            var age = Time.now().value() - (d["ts"] as Number);
            secs -= age;
        }
        return secs < 0 ? 0 : secs;
    }

    // "MM:SS", or "H:MM:SS" once an hour or more remains.
    function fmtClockSecs(secs as Number) as String {
        var h = secs / 3600;
        var m = (secs % 3600) / 60;
        var s = secs % 60;
        var mm = m < 10 ? "0" + m : m.toString();
        var ss = s < 10 ? "0" + s : s.toString();
        if (h > 0) {
            return h + ":" + mm + ":" + ss;
        }
        return mm + ":" + ss;
    }
}
