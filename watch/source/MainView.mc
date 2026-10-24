import Toybox.Communications;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Math;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;

const PAGE_DASH = 0;
const PAGE_ALERTS = 1;
const PAGE_FAN = 2;
const PAGE_PROBE = 3;
const PAGE_TIMER = 4;
const PAGE_STATUS = 5;
const PAGE_COUNT = 6;

class MainView extends WatchUi.View {
    const POLL_MS = 5000;

    var page as Number = PAGE_DASH;
    // Selected box on the Alerts page (:high / :low), null when nothing is selected.
    var alertFocus as Symbol? = null;
    var lastError as Number? = null;
    private var _timer as Timer.Timer?;
    private var _tick as Number = 0;
    private var _busy as Boolean = false;

    function initialize() {
        View.initialize();
    }

    // One 1 Hz timer does everything: it polls every POLL_MS and, in between,
    // redraws the live countdown while a cook timer runs. Connect IQ caps the
    // number of concurrent Timer.Timer objects, so the view keeps just this one
    // (a second one plus the editor's timers overflowed the limit and crashed).
    // It is not stopped in onHide, so polling and alarms keep running while an
    // editor or alert is on top.
    function onShow() as Void {
        poll();
        if (_timer == null) {
            _timer = new Timer.Timer();
            (_timer as Timer.Timer).start(method(:onSecond), 1000, true);
        }
    }

    function onSecond() as Void {
        _tick++;
        if (_tick % (POLL_MS / 1000) == 0) {
            poll();
        }
        if (Ct.timerState(Ct.getData()).equals("active")) {
            WatchUi.requestUpdate();
        }
    }

    function poll() as Void {
        if (_busy) {
            return;
        }
        // Nothing to poll until the user has entered a URL and token.
        if (!Ha.configured()) {
            WatchUi.requestUpdate();
            return;
        }
        _busy = true;
        Ha.fetchState(method(:onResponse));
    }

    function onResponse(code as Number, data as Dictionary or String or Null) as Void {
        _busy = false;
        var parsed = null;
        if (code == 200 && data instanceof String) {
            parsed = Ct.parse(data);
        }
        if (parsed != null) {
            Ct.store(parsed);
            lastError = null;
            Alarm.check(parsed);
        } else {
            lastError = code;
        }
        WatchUi.requestUpdate();
    }

    function nextPage(delta as Number) as Void {
        page = (page + delta + PAGE_COUNT) % PAGE_COUNT;
        alertFocus = null;
        WatchUi.requestUpdate();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        dc.setColor(Theme.fg(), Theme.bg());
        dc.clear();
        var d = Ct.getData();
        // Until a URL and token are known, every page is meaningless (any stored
        // data is stale), so show the one-time setup instructions instead.
        if (!Ha.configured()) {
            drawSetup(dc);
            return;
        }
        if (page == PAGE_DASH) {
            drawDash(dc, d);
        } else if (page == PAGE_ALERTS) {
            drawAlerts(dc, d);
        } else if (page == PAGE_FAN) {
            TargetLayout.draw(dc, :fan, d, null, false, null);
        } else if (page == PAGE_PROBE) {
            TargetLayout.draw(dc, :probe, d, null, false, null);
        } else if (page == PAGE_TIMER) {
            drawTimer(dc, d);
        } else {
            drawStatus(dc, d);
        }
        drawFooter(dc, d);
        Draw.pageDots(dc, page, PAGE_COUNT);
    }

    function errorText() as String? {
        var e = lastError;
        if (e == null) {
            return null;
        }
        if (e == Communications.BLE_CONNECTION_UNAVAILABLE || e == Communications.BLE_HOST_TIMEOUT) {
            return "No phone connection";
        }
        if (e == 401) {
            return "HA token rejected";
        }
        if (e == 200) {
            return "Bad HA response";
        }
        return "HA error " + e;
    }

    function drawFooter(dc as Graphics.Dc, d as Dictionary?) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        var err = errorText();
        if (err != null) {
            dc.setColor(Theme.error(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w / 2, h * 0.94, Graphics.FONT_XTINY, err, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        } else if (page != PAGE_TIMER && Ct.timerRunning(d)) {
            drawTimerChip(dc, d);
        } else if (d != null && Ct.ageSeconds(d) > 60) {
            dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w / 2, h * 0.94, Graphics.FONT_XTINY, Ct.ageText(d), Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        }
    }

    // Compact stopwatch + remaining time, shown at the bottom whenever a cook
    // timer is running. Paused is dimmed; active is in the accent colour.
    function drawTimerChip(dc as Graphics.Dc, d as Dictionary?) as Void {
        var secs = Ct.timerRemaining(d);
        if (secs == null) {
            return;
        }
        var w = dc.getWidth();
        var h = dc.getHeight();
        var paused = Ct.timerState(d).equals("paused");
        var color = paused ? Theme.dim() : Theme.accent();
        var text = Ct.fmtClockSecs(secs);
        var tw = dc.getTextWidthInPixels(text, Graphics.FONT_XTINY);
        var cx = (w / 2 + 7).toNumber();
        Draw.timerIcon(dc, (cx - tw / 2 - 12).toNumber(), (h * 0.93).toNumber(), 6, color);
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.93, Graphics.FONT_XTINY, text, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
    }

    // Top row: stand battery, the 24-hour clock, and how the integration is
    // reaching the stand right now (BLE / cloud / disconnected) — not the
    // watch's own phone/WiFi link, which said nothing about the grill.
    function drawTopBar(dc as Graphics.Dc, d as Dictionary?) as Void {
        var w = dc.getWidth();
        var y = 22;
        var clock = Ct.clockText();
        var cw = dc.getTextWidthInPixels(clock, Graphics.FONT_XTINY);
        var sb = d != null ? d["sb"] as Float? : null;
        var battW = 23 + dc.getTextWidthInPixels(sb == null ? "--" : sb.toNumber() + "%", Graphics.FONT_XTINY);
        var total = 18 + 10 + cw + 10 + battW;
        var x = (w / 2 - total / 2).toNumber();

        var src = Ct.connSource(d);
        if (src == :ble) {
            Draw.bluetooth(dc, x + 8, y, Theme.accent());
        } else if (src == :cloud) {
            Draw.cloud(dc, x + 8, y, Theme.accent());
        } else {
            Draw.cloud(dc, x + 8, y, Theme.faint());
        }
        x += 18 + 10;
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(x, y, Graphics.FONT_XTINY, clock, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        x += cw + 10;
        Draw.battery(dc, x, y, sb, Theme.dim());
    }

    function drawSetup(dc as Graphics.Dc) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        var cx = w / 2;
        drawTopBar(dc, null);
        dc.setColor(Theme.accent(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.18, Graphics.FONT_SMALL, "ChefsTemp", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.33, Graphics.FONT_XTINY, "Set up", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        var lines = ["Garmin Connect app >", "ChefsTemp > Settings:", "enter your Home", "Assistant URL + token"];
        dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
        for (var i = 0; i < lines.size(); i++) {
            dc.drawText(cx, h * (0.45 + i * 0.09), Graphics.FONT_XTINY, lines[i], Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        }
    }

    function drawDash(dc as Graphics.Dc, d as Dictionary?) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        var u = Ct.unitLabel();
        var cx = w / 2;

        drawTopBar(dc, d);
        dc.setColor(Theme.accent(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(cx, h * 0.17, Graphics.FONT_SMALL, "ChefsTemp", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);

        if (d == null) {
            dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(cx, h * 0.5, Graphics.FONT_SMALL, "Connecting...", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
            return;
        }

        // grill
        Draw.grill(dc, (w * 0.16).toNumber(), (h * 0.37).toNumber(), 15, Theme.accent());
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w * 0.3, h * 0.255, Graphics.FONT_XTINY, "GRILL", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        Draw.valueLeft(dc, (w * 0.29).toNumber(), (h * 0.385).toNumber(), Graphics.FONT_NUMBER_HOT, Ct.fmt(d["g"], d["gF"]), u, Theme.fg());

        dc.setColor(Theme.accent(), Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(2);
        dc.drawLine(w * 0.07, h * 0.52, w * 0.93, h * 0.52);
        dc.setPenWidth(1);

        // probe
        var probeOk = d["p"] != null;
        var probeColor = probeOk ? Theme.accent() : Theme.faint();
        Draw.probe(dc, (w * 0.16).toNumber(), (h * 0.64).toNumber(), 12, probeColor);
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w * 0.26, h * 0.6, Graphics.FONT_XTINY, "PROBE", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        if (probeOk) {
            Draw.battery(dc, (w * 0.26).toNumber(), (h * 0.68).toNumber(), d["pb"] as Float?, Theme.dim());
            Draw.valueLeft(dc, (w * 0.52).toNumber(), (h * 0.64).toNumber(), Graphics.FONT_NUMBER_MEDIUM, Ct.fmt(d["p"], d["pF"]), u, Theme.fg());
        } else {
            dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w * 0.26, h * 0.68, Graphics.FONT_XTINY, "disconnected", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        }

        // fan
        // The fan is a thermostat: OFF, or enabled and either running or waiting.
        var fanOn = "on".equals(d["fan"]);
        var running = fanOn && d["run"] == true;
        Draw.fan(dc, (w * 0.3).toNumber(), (h * 0.8).toNumber(), 9, running ? Theme.accent() : Theme.fg());
        dc.setColor(running ? Theme.accent() : Theme.fg(), Graphics.COLOR_TRANSPARENT);
        var fanText = !fanOn ? "FAN OFF" : (running ? "FAN RUN" : "FAN STOP");
        dc.drawText(w * 0.37, h * 0.795, Graphics.FONT_XTINY, fanText, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        if (fanOn) {
            dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w * 0.37, h * 0.865, Graphics.FONT_XTINY, "TARGET " + Ct.fmtU(d["ft"], d["nF"] as Boolean), Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        }
    }

    function drawAlertBox(dc as Graphics.Dc, y as Number, boxH as Number, kind as Symbol, d as Dictionary?, focused as Boolean) as Void {
        var w = dc.getWidth();
        var x = (w * 0.1).toNumber();
        var bw = (w * 0.8).toNumber();
        var up = kind == :high;
        var title = up ? "MAX ALERT" : "MIN ALERT";
        var hint = up ? "Grill rises above" : "Grill drops below";
        Draw.roundBox(dc, x, y, bw, boxH, focused ? Theme.accent() : Theme.faint());
        if (focused) {
            Draw.roundBox(dc, x + 2, y + 2, bw - 4, boxH - 4, Theme.accent());
        }
        var iy = (y + boxH * 0.42).toNumber();
        Draw.arrowCircle(dc, x + 22, iy, 12, up, Theme.accent());
        Draw.bell(dc, x + bw - 22, iy, 10, Theme.accent());
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, y + boxH * 0.17, Graphics.FONT_XTINY, title, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        Draw.value(dc, w / 2, (y + boxH * 0.5).toNumber(), Graphics.FONT_NUMBER_MILD, TargetLayout.valueText(kind, d, null), Ct.unitLabel(), Theme.fg());
        dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, y + boxH * 0.84, Graphics.FONT_XTINY, hint, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
    }

    function drawAlerts(dc as Graphics.Dc, d as Dictionary?) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, h * 0.11, Graphics.FONT_SMALL, "Alerts", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        var boxH = (h * 0.33).toNumber();
        drawAlertBox(dc, (h * 0.19).toNumber(), boxH, :high, d, alertFocus == :high);
        drawAlertBox(dc, (h * 0.55).toNumber(), boxH, :low, d, alertFocus == :low);
    }

    function probeStatus(d as Dictionary?) as String {
        if (d == null) {
            return "--";
        }
        if (d["p"] == null) {
            return "Disconnected";
        }
        if (Ct.probeTargetSet(d)) {
            return "Target " + Ct.fmtU(d["pt"], d["ptF"] as Boolean);
        }
        return "Connected";
    }

    function drawStatus(dc as Graphics.Dc, d as Dictionary?) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, 18, Graphics.FONT_XTINY, Ct.clockText(), Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, h * 0.14, Graphics.FONT_SMALL, "Grill & Probe", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);

        var gF = d != null ? d["gF"] as Boolean : false;
        var pF = d != null ? d["pF"] as Boolean : false;
        Draw.grill(dc, (w * 0.17).toNumber(), (h * 0.24).toNumber(), 10, Theme.accent());
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w * 0.27, h * 0.2, Graphics.FONT_XTINY, "GRILL", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.drawText(w * 0.27, h * 0.29, Graphics.FONT_SMALL, d != null ? Ct.fmtU(d["g"], gF) : "--", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.setColor(Theme.accent(), Graphics.COLOR_TRANSPARENT);
        dc.drawLine(w / 2 + 6, h * 0.17, w / 2 + 6, h * 0.33);
        Draw.probe(dc, (w * 0.6).toNumber(), (h * 0.26).toNumber(), 8, Theme.accent());
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w * 0.67, h * 0.2, Graphics.FONT_XTINY, "PROBE", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.drawText(w * 0.67, h * 0.29, Graphics.FONT_SMALL, d != null ? Ct.fmtU(d["p"], pF) : "--", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);

        drawGraph(dc, (w * 0.18).toNumber(), (h * 0.37).toNumber(), (w * 0.7).toNumber(), (h * 0.22).toNumber(), gF);

        var rowY = [h * 0.66, h * 0.74, h * 0.82];
        var labels = ["Fan", "Probe", "Alerts"];
        var values = ["--", "--", "--"];
        if (d != null) {
            values[0] = TargetLayout.isOn(:fan, d) ? (d["run"] == true ? "Run " : "Stop ") + Ct.fmtU(d["ft"], d["nF"] as Boolean) : "Off";
            values[1] = probeStatus(d);
            var lo = TargetLayout.valueText(:low, d, null);
            var hi = TargetLayout.valueText(:high, d, null);
            values[2] = lo.equals("OFF") && hi.equals("OFF") ? "Off" : lo + "-" + hi + (hi.equals("OFF") ? "" : "°" + Ct.unitLabel());
        }
        for (var i = 0; i < 3; i++) {
            dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w * 0.17, rowY[i], Graphics.FONT_XTINY, labels[i], Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
            dc.setColor(Theme.accent(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w * 0.85, rowY[i], Graphics.FONT_XTINY, values[i], Graphics.TEXT_JUSTIFY_RIGHT | Graphics.TEXT_JUSTIFY_VCENTER);
        }
    }

    function drawTimer(dc as Graphics.Dc, d as Dictionary?) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, h * 0.13, Graphics.FONT_SMALL, "Timer", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);

        var cy = (h * 0.4).toNumber();
        var running = Ct.timerRunning(d);
        var paused = Ct.timerState(d).equals("paused");
        var secs = Ct.timerRemaining(d);
        var color = running ? (paused ? Theme.dim() : Theme.accent()) : Theme.faint();
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, cy, Graphics.FONT_NUMBER_MEDIUM, secs == null ? "--:--" : Ct.fmtClockSecs(secs), Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
        var sub = running ? (paused ? "paused" : "remaining") : "no timer running";
        dc.drawText(w / 2, h * 0.57, Graphics.FONT_XTINY, sub, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);

        var lines = running
            ? ["Pause, resume or", "cancel. HA announces", "when it finishes."]
            : ["Set a cook timer.", "HA announces by voice", "when it finishes."];
        var ix = (w * 0.2).toNumber();
        var iy = (h * 0.655).toNumber();
        Draw.timerIcon(dc, ix, iy, 9, Theme.fg());
        dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
        for (var i = 0; i < lines.size(); i++) {
            dc.drawText(w * 0.29, h * (0.62 + i * 0.065), Graphics.FONT_XTINY, lines[i], Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        }
        Draw.pill(dc, w / 2, (h * 0.8).toNumber(), (w * 0.7).toNumber(), 32, running ? "MANAGE" : "SET TIMER", false);
    }

    function drawGraph(dc as Graphics.Dc, x as Number, y as Number, gw as Number, gh as Number, srcF as Boolean) as Void {
        var hist = Ct.getHistory();
        var pts = [] as Array<Array>;
        var lo = null;
        var hi = null;
        for (var i = 0; i < hist.size(); i++) {
            var p = hist[i] as Array;
            var v = Ct.toDisplay(p[1] as Float?, srcF);
            if (v != null) {
                pts.add([p[0], v]);
                lo = (lo == null || v < lo) ? v : lo;
                hi = (hi == null || v > hi) ? v : hi;
            }
        }
        dc.setColor(Theme.faint(), Graphics.COLOR_TRANSPARENT);
        dc.drawRectangle(x, y, gw, gh);
        dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(x + gw - 3, y + gh - 8, Graphics.FONT_XTINY, "LAST HOUR", Graphics.TEXT_JUSTIFY_RIGHT | Graphics.TEXT_JUSTIFY_VCENTER);
        if (pts.size() < 2) {
            dc.drawText(x + gw / 2, y + gh / 2 - 4, Graphics.FONT_XTINY, "collecting...", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
            return;
        }
        lo = Math.floor(lo - 2);
        hi = Math.ceil(hi + 2);
        dc.drawText(x - 2, y + 6, Graphics.FONT_XTINY, hi.toNumber().toString(), Graphics.TEXT_JUSTIFY_RIGHT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.drawText(x - 2, y + gh - 6, Graphics.FONT_XTINY, lo.toNumber().toString(), Graphics.TEXT_JUSTIFY_RIGHT | Graphics.TEXT_JUSTIFY_VCENTER);
        var t1 = pts[pts.size() - 1][0] as Number;
        var t0 = t1 - Ct.HIST_WINDOW;
        dc.setColor(Theme.accent(), Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(2);
        var px = 0.0;
        var py = 0.0;
        for (var i = 0; i < pts.size(); i++) {
            var t = pts[i][0] as Number;
            var v = pts[i][1] as Float;
            var nx = x + gw * (t - t0) / Ct.HIST_WINDOW.toFloat();
            var ny = y + gh - gh * (v - lo) / (hi - lo);
            if (i > 0) {
                dc.drawLine(px, py, nx, ny);
            }
            px = nx;
            py = ny;
        }
        dc.setPenWidth(1);
    }
}

// Shared layout of the Fan Target / Probe Target pages and of every value editor.
module TargetLayout {
    function title(kind as Symbol) as String {
        if (kind == :fan) { return "Fan Target"; }
        if (kind == :probe) { return "Probe Target"; }
        if (kind == :high) { return "Max Alert"; }
        return "Min Alert";
    }

    function dataKey(kind as Symbol) as String {
        if (kind == :fan) { return "ft"; }
        if (kind == :probe) { return "pt"; }
        if (kind == :high) { return "hi"; }
        return "lo";
    }

    function unitKey(kind as Symbol) as String {
        return kind == :probe ? "ptF" : "nF";
    }

    function isOn(kind as Symbol, d as Dictionary?) as Boolean {
        if (d == null) { return false; }
        if (kind == :fan) { return "on".equals(d["fan"]); }
        if (kind == :probe) { return d["ptOn"] == true; }
        if (kind == :high) { return d["hiOn"] == true; }
        return d["loOn"] == true;
    }

    // Data key of the on/off flag; for the fan it is the fan state string.
    function onKey(kind as Symbol) as String {
        if (kind == :fan) { return "fan"; }
        if (kind == :probe) { return "ptOn"; }
        if (kind == :high) { return "hiOn"; }
        return "loOn";
    }

    function enableEntity(kind as Symbol) as String {
        if (kind == :fan) { return Ct.ENTITY_FAN; }
        if (kind == :probe) { return Ct.ENTITY_PROBE_ON; }
        if (kind == :high) { return Ct.ENTITY_MAX_ON; }
        return Ct.ENTITY_MIN_ON;
    }

    // Value text for a page (value == null, read from d) or an editor (value < 0 means OFF).
    function valueText(kind as Symbol, d as Dictionary?, value as Float?) as String {
        var srcF = d != null ? d[unitKey(kind)] as Boolean : false;
        if (value != null) {
            return value < 0 ? "OFF" : Ct.fmt(value, srcF);
        }
        if (d == null) { return "--"; }
        return isOn(kind, d) ? Ct.fmt(d[dataKey(kind)] as Float?, srcF) : "OFF";
    }

    function entity(kind as Symbol) as String {
        if (kind == :fan) { return Ct.ENTITY_FAN_TARGET; }
        if (kind == :probe) { return Ct.ENTITY_PROBE_TARGET; }
        if (kind == :high) { return Ct.ENTITY_HIGH; }
        return Ct.ENTITY_LOW;
    }

    function description(kind as Symbol) as Array<String> {
        if (kind == :fan) { return ["Fan will run automatically", "to reach and maintain", "the target temperature."]; }
        if (kind == :probe) { return ["Watch alarms when the", "probe reaches this", "temperature."]; }
        if (kind == :high) { return ["Alert if grill rises", "above this", "temperature."]; }
        return ["Alert if grill drops", "below this", "temperature."];
    }

    // value overrides the stored value (editor, -1 = OFF); null means read it from d.
    function draw(dc as Graphics.Dc, kind as Symbol, d as Dictionary?, value as Float?, editing as Boolean, status as String?) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, h * 0.13, Graphics.FONT_SMALL, title(kind), Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);

        var cy = (h * 0.37).toNumber();
        Draw.plusMinus(dc, (w * 0.105).toNumber(), cy, 15, false, editing);
        Draw.plusMinus(dc, (w * 0.895).toNumber(), cy, 15, true, editing);
        Draw.value(dc, w / 2, cy, Graphics.FONT_NUMBER_HOT, valueText(kind, d, value), Ct.unitLabel(), Theme.fg());

        var ix = (w * 0.17).toNumber();
        var iy = (h * 0.62).toNumber();
        if (kind == :fan) {
            Draw.fan(dc, ix, iy, 10, Theme.fg());
        } else if (kind == :probe) {
            Draw.probe(dc, ix, iy, 9, Theme.fg());
        } else {
            Draw.bell(dc, ix, iy, 9, Theme.accent());
        }
        var lines = description(kind);
        dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
        for (var i = 0; i < lines.size(); i++) {
            dc.drawText(w * 0.26, h * (0.555 + i * 0.065), Graphics.FONT_XTINY, lines[i], Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        }

        var action = kind == :high || kind == :low ? "SET ALERT" : "SET TARGET";
        Draw.pill(dc, w / 2, (h * 0.8).toNumber(), (w * 0.7).toNumber(), 32, status != null ? status : action, status == null);
    }
}
