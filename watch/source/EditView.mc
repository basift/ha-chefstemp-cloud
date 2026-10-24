import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Math;
import Toybox.System;
import Toybox.Time;
import Toybox.Timer;
import Toybox.WatchUi;

// Edits one target. value is in the HA unit (whole degrees); OFF is -1, one step below 0.
// Setting a number also turns its on/off entity on; OFF only turns it off and keeps the number.
class EditView extends WatchUi.View {
    const OFF = -1;

    var kind as Symbol;
    var value as Number;
    var status as String? = null;
    var sending as Boolean = false;
    private var _resume as Number;
    private var _timer as Timer.Timer?;

    function initialize(k as Symbol, d as Dictionary) {
        View.initialize();
        kind = k;
        var v = d[TargetLayout.dataKey(kind)] as Float?;
        if (v != null && v > 0) {
            _resume = Math.round(v).toNumber();
        } else {
            var f = d[TargetLayout.unitKey(kind)] as Boolean;
            _resume = kind == :probe ? (f ? 145 : 63) : (f ? 225 : 110);
        }
        value = TargetLayout.isOn(kind, d) ? _resume : OFF;
    }

    function adjust(delta as Number) as Void {
        if (sending) {
            return;
        }
        if (value == OFF) {
            if (delta < 0) {
                return;
            }
            value = _resume;
        } else {
            var next = value + delta;
            if (next < Ct.NUMBER_MIN) {
                next = value > Ct.NUMBER_MIN ? Ct.NUMBER_MIN : OFF;
            }
            if (next > Ct.NUMBER_MAX) {
                next = Ct.NUMBER_MAX;
            }
            value = next;
        }
        status = null;
        WatchUi.requestUpdate();
    }

    function send() as Void {
        if (sending) {
            return;
        }
        sending = true;
        status = "Sending...";
        WatchUi.requestUpdate();
        if (value == OFF) {
            Ha.callService(TargetLayout.enableEntity(kind), "turn_off", method(:onDone));
        } else {
            Ha.setNumber(TargetLayout.entity(kind), value, method(:onNumberSet));
        }
    }

    function onNumberSet(code as Number, data as Dictionary or String or Null) as Void {
        if (code != 200) {
            fail(code);
            return;
        }
        var d = Ct.getData();
        if (kind == :fan) {
            if (d != null && "on".equals(d["fan"])) {
                onDone(200, null);
            } else if (d != null && d["g"] != null && d["p"] != null) {
                Ha.callService(Ct.ENTITY_FAN, "turn_on", method(:onDone));
            } else {
                // The dashboard warns against enabling the fan without valid grill and probe readings.
                updateLocal(false);
                finish("Saved, fan off");
            }
            return;
        }
        Ha.callService(TargetLayout.enableEntity(kind), "turn_on", method(:onDone));
    }

    function onDone(code as Number, data as Dictionary or String or Null) as Void {
        if (code != 200) {
            fail(code);
            return;
        }
        updateLocal(value != OFF);
        finish("Saved");
    }

    function updateLocal(on as Boolean) as Void {
        var d = Ct.getData();
        if (d == null) {
            return;
        }
        if (value != OFF) {
            d[TargetLayout.dataKey(kind)] = value.toFloat();
        }
        var key = TargetLayout.onKey(kind);
        d[key] = kind == :fan ? (on ? "on" : "off") : on;
        Ct.store(d);
    }

    function fail(code as Number) as Void {
        sending = false;
        status = "Failed (" + code + ")";
        WatchUi.requestUpdate();
    }

    function finish(text as String) as Void {
        sending = false;
        status = text;
        _timer = new Timer.Timer();
        (_timer as Timer.Timer).start(method(:close), 900, false);
        WatchUi.requestUpdate();
    }

    function close() as Void {
        WatchUi.popView(WatchUi.SLIDE_DOWN);
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        dc.setColor(Theme.fg(), Theme.bg());
        dc.clear();
        TargetLayout.draw(dc, kind, Ct.getData(), value.toFloat(), true, status);
    }
}

class EditDelegate extends WatchUi.BehaviorDelegate {
    const HOLD_START_TICKS = 5;
    const FAST_TICKS = 25;

    private var _view as EditView;
    private var _repeat as Timer.Timer?;
    private var _dir as Number = 0;
    private var _ticks as Number = 0;

    function initialize(view as EditView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function isUpDown(evt as WatchUi.KeyEvent) as Boolean {
        var k = evt.getKey();
        return k == WatchUi.KEY_UP || k == WatchUi.KEY_DOWN;
    }

    // A single UP/DOWN press steps once via onPreviousPage/onNextPage; holding the key
    // starts a repeat that gets faster after a few seconds.
    function onKeyPressed(evt as WatchUi.KeyEvent) as Boolean {
        if (!isUpDown(evt)) {
            return false;
        }
        stopRepeat();
        _dir = evt.getKey() == WatchUi.KEY_UP ? 1 : -1;
        _ticks = 0;
        _repeat = new Timer.Timer();
        (_repeat as Timer.Timer).start(method(:tick), 100, true);
        return false;
    }

    function onKeyReleased(evt as WatchUi.KeyEvent) as Boolean {
        if (isUpDown(evt)) {
            stopRepeat();
        }
        return false;
    }

    function tick() as Void {
        _ticks++;
        if (_ticks >= HOLD_START_TICKS) {
            _view.adjust(_ticks >= FAST_TICKS ? _dir * 5 : _dir);
        }
    }

    function stopRepeat() as Void {
        if (_repeat != null) {
            (_repeat as Timer.Timer).stop();
            _repeat = null;
        }
    }

    function onPreviousPage() as Boolean {
        _view.adjust(1);
        return true;
    }

    function onNextPage() as Boolean {
        _view.adjust(-1);
        return true;
    }

    function onSelect() as Boolean {
        stopRepeat();
        _view.send();
        return true;
    }

    function onBack() as Boolean {
        stopRepeat();
        return false;
    }

    function onTap(evt as WatchUi.ClickEvent) as Boolean {
        var xy = evt.getCoordinates();
        var s = System.getDeviceSettings();
        if (xy[1] > s.screenHeight * 0.7) {
            _view.send();
        } else if (xy[0] < s.screenWidth * 0.35) {
            _view.adjust(-1);
        } else if (xy[0] > s.screenWidth * 0.65) {
            _view.adjust(1);
        }
        return true;
    }

    function onSwipe(evt as WatchUi.SwipeEvent) as Boolean {
        return true;
    }
}

// Sets and runs the HA cook timer. Idle: pick minutes and START. Running:
// PAUSE / RESUME (primary) and CANCEL (a separate control). HA owns the timer
// and announces by voice when it finishes; the watch only drives it.
class TimerEditView extends WatchUi.View {
    const MIN_MIN = 1;
    const MAX_MIN = 1440;

    var minutes as Number;
    var status as String? = null;
    var sending as Boolean = false;
    // Which running-state button the buttons act on: :primary (pause/resume) or
    // :cancel. In the simulator a screen click arrives as SELECT, not a touch,
    // so button focus — not tap position — is what reaches Cancel there.
    var focus as Symbol = :primary;
    private var _tick as Timer.Timer?;
    private var _close as Timer.Timer?;

    function initialize() {
        View.initialize();
        minutes = Ct.getTimerMinutes();
    }

    function toggleFocus() as Void {
        focus = focus == :primary ? :cancel : :primary;
        WatchUi.requestUpdate();
    }

    // SELECT: activate whichever running-state button is focused, or START/pause
    // /resume otherwise.
    function activate() as Void {
        if (running() && focus == :cancel) {
            cancelTimer();
        } else {
            primary();
        }
    }

    // The 1 Hz redraw is only needed for a live (active) countdown. In the idle
    // minute-setting state it is not started, which keeps a spare Timer slot free
    // for the button-hold repeat (Connect IQ caps concurrent timers).
    function onShow() as Void {
        if (_tick == null && state().equals("active")) {
            _tick = new Timer.Timer();
            (_tick as Timer.Timer).start(method(:onTick), 1000, true);
        }
    }

    function onHide() as Void {
        stopTick();
        if (_close != null) {
            (_close as Timer.Timer).stop();
            _close = null;
        }
    }

    function stopTick() as Void {
        if (_tick != null) {
            (_tick as Timer.Timer).stop();
            _tick = null;
        }
    }

    function onTick() as Void {
        if (state().equals("active")) {
            WatchUi.requestUpdate();
        }
    }

    function state() as String {
        return Ct.timerState(Ct.getData());
    }

    function running() as Boolean {
        return Ct.timerRunning(Ct.getData());
    }

    function adjust(delta as Number) as Void {
        if (sending || running()) {
            return;
        }
        var n = minutes + delta;
        if (n < MIN_MIN) {
            n = MIN_MIN;
        }
        if (n > MAX_MIN) {
            n = MAX_MIN;
        }
        minutes = n;
        status = null;
        WatchUi.requestUpdate();
    }

    // HA timer.start accepts "H:MM:SS".
    function durationText(mins as Number) as String {
        var hh = mins / 60;
        var mm = mins % 60;
        return hh + ":" + (mm < 10 ? "0" + mm : mm.toString()) + ":00";
    }

    // SELECT / primary pill: start when idle, else pause/resume.
    function primary() as Void {
        if (sending) {
            return;
        }
        var st = state();
        sending = true;
        status = "Sending...";
        WatchUi.requestUpdate();
        if (st.equals("active")) {
            Ha.callService(Ct.ENTITY_TIMER, "pause", method(:onPaused));
        } else if (st.equals("paused")) {
            // timer.start with no duration resumes from the remaining time.
            Ha.callService(Ct.ENTITY_TIMER, "start", method(:onResumed));
        } else {
            Ct.setTimerMinutes(minutes);
            Ha.callServiceData(Ct.ENTITY_TIMER, "start", { "duration" => durationText(minutes) }, method(:onStarted));
        }
    }

    function cancelTimer() as Void {
        if (sending || !running()) {
            return;
        }
        sending = true;
        status = "Sending...";
        WatchUi.requestUpdate();
        Ha.callService(Ct.ENTITY_TIMER, "cancel", method(:onCancelled));
    }

    // Optimistic local update so the watch reflects the change before the next poll.
    function setLocal(st as String, rem as Number) as Void {
        var d = Ct.getData();
        if (d == null) {
            return;
        }
        d["tState"] = st;
        d["tRem"] = rem.toFloat();
        d["ts"] = Time.now().value();
        Ct.store(d);
    }

    function onStarted(code as Number, data as Dictionary or String or Null) as Void {
        if (code != 200) { fail(code); return; }
        setLocal("active", minutes * 60);
        finish("Started");
    }

    function onPaused(code as Number, data as Dictionary or String or Null) as Void {
        if (code != 200) { fail(code); return; }
        var r = Ct.timerRemaining(Ct.getData());
        setLocal("paused", r == null ? 0 : r);
        finish("Paused");
    }

    function onResumed(code as Number, data as Dictionary or String or Null) as Void {
        if (code != 200) { fail(code); return; }
        var r = Ct.timerRemaining(Ct.getData());
        setLocal("active", r == null ? 0 : r);
        finish("Resumed");
    }

    function onCancelled(code as Number, data as Dictionary or String or Null) as Void {
        if (code != 200) { fail(code); return; }
        setLocal("idle", -1);
        finish("Cancelled");
    }

    function fail(code as Number) as Void {
        sending = false;
        status = "Failed (" + code + ")";
        WatchUi.requestUpdate();
    }

    function finish(text as String) as Void {
        sending = false;
        status = text;
        // Free the 1 Hz tick before arming the close timer so only one
        // Timer.Timer from this view is ever live at once.
        stopTick();
        _close = new Timer.Timer();
        (_close as Timer.Timer).start(method(:close), 900, false);
        WatchUi.requestUpdate();
    }

    function close() as Void {
        WatchUi.popView(WatchUi.SLIDE_DOWN);
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        dc.setColor(Theme.fg(), Theme.bg());
        dc.clear();
        var w = dc.getWidth();
        var h = dc.getHeight();
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, h * 0.13, Graphics.FONT_SMALL, "Timer", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);

        var cy = (h * 0.4).toNumber();
        var run = running();
        var paused = state().equals("paused");
        if (run) {
            var secs = Ct.timerRemaining(Ct.getData());
            dc.setColor(paused ? Theme.dim() : Theme.accent(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w / 2, cy, Graphics.FONT_NUMBER_MEDIUM, Ct.fmtClockSecs(secs == null ? 0 : secs), Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
            dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w / 2, h * 0.57, Graphics.FONT_XTINY, paused ? "paused" : "remaining", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        } else {
            Draw.plusMinus(dc, (w * 0.105).toNumber(), cy, 15, false, true);
            Draw.plusMinus(dc, (w * 0.895).toNumber(), cy, 15, true, true);
            var nf = Graphics.FONT_NUMBER_HOT;
            var ns = minutes.toString();
            var nw = dc.getTextWidthInPixels(ns, nf);
            var uw = dc.getTextWidthInPixels("min", Graphics.FONT_TINY);
            var sx = (w / 2 - (nw + 4 + uw) / 2).toNumber();
            dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(sx, cy, nf, ns, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
            dc.drawText(sx + nw + 4, cy, Graphics.FONT_TINY, "min", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
            dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w / 2, h * 0.57, Graphics.FONT_XTINY, "HA announces when done", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        }

        if (run) {
            if (status != null) {
                Draw.pill(dc, w / 2, (h * 0.68).toNumber(), (w * 0.6).toNumber(), 34, status, false);
            } else {
                // Two stacked buttons; the focused one is a filled pill, the other
                // a dim outline. Up/Down move the focus, SELECT activates it.
                drawAction(dc, (h * 0.64).toNumber(), (w * 0.6).toNumber(), 34, paused ? "RESUME" : "PAUSE", focus == :primary);
                drawAction(dc, (h * 0.85).toNumber(), (w * 0.52).toNumber(), 32, "Cancel", focus == :cancel);
            }
        } else {
            Draw.pill(dc, w / 2, (h * 0.78).toNumber(), (w * 0.66).toNumber(), 32, status != null ? status : "START", status == null);
        }
    }

    function drawAction(dc as Graphics.Dc, yc as Number, bw as Number, bh as Number, text as String, focused as Boolean) as Void {
        var w = dc.getWidth();
        if (focused) {
            Draw.pill(dc, w / 2, yc, bw, bh, text, false);
        } else {
            dc.setColor(Theme.faint(), Graphics.COLOR_TRANSPARENT);
            dc.setPenWidth(2);
            dc.drawRoundedRectangle((w / 2 - bw / 2).toNumber(), yc - bh / 2, bw, bh, bh / 2);
            dc.setPenWidth(1);
            dc.setColor(Theme.dim(), Graphics.COLOR_TRANSPARENT);
            dc.drawText(w / 2, yc, Graphics.FONT_TINY, text, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        }
    }
}

class TimerEditDelegate extends WatchUi.BehaviorDelegate {
    const HOLD_START_TICKS = 5;
    const FAST_TICKS = 25;

    private var _view as TimerEditView;
    private var _repeat as Timer.Timer?;
    private var _dir as Number = 0;
    private var _ticks as Number = 0;

    function initialize(view as TimerEditView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function isUpDown(evt as WatchUi.KeyEvent) as Boolean {
        var k = evt.getKey();
        return k == WatchUi.KEY_UP || k == WatchUi.KEY_DOWN;
    }

    function onKeyPressed(evt as WatchUi.KeyEvent) as Boolean {
        // While running, Up/Down only move the button focus (once per press, in
        // onPreviousPage/onNextPage), so no hold-repeat is armed.
        if (!isUpDown(evt) || _view.running()) {
            return false;
        }
        stopRepeat();
        _dir = evt.getKey() == WatchUi.KEY_UP ? 1 : -1;
        _ticks = 0;
        _repeat = new Timer.Timer();
        (_repeat as Timer.Timer).start(method(:tick), 100, true);
        return false;
    }

    function onKeyReleased(evt as WatchUi.KeyEvent) as Boolean {
        if (isUpDown(evt)) {
            stopRepeat();
        }
        return false;
    }

    function tick() as Void {
        _ticks++;
        if (_ticks >= HOLD_START_TICKS) {
            _view.adjust(_ticks >= FAST_TICKS ? _dir * 5 : _dir);
        }
    }

    function stopRepeat() as Void {
        if (_repeat != null) {
            (_repeat as Timer.Timer).stop();
            _repeat = null;
        }
    }

    function onPreviousPage() as Boolean {
        if (_view.running()) {
            _view.toggleFocus();
        } else {
            _view.adjust(1);
        }
        return true;
    }

    function onNextPage() as Boolean {
        if (_view.running()) {
            _view.toggleFocus();
        } else {
            _view.adjust(-1);
        }
        return true;
    }

    function onSelect() as Boolean {
        stopRepeat();
        _view.activate();
        return true;
    }

    function onBack() as Boolean {
        stopRepeat();
        return false;
    }

    function onTap(evt as WatchUi.ClickEvent) as Boolean {
        var xy = evt.getCoordinates();
        var s = System.getDeviceSettings();
        if (_view.running()) {
            // Real-watch touch: lower band is Cancel (button at 0.85h), the band
            // around the pill above it is pause/resume. Focus follows the tap.
            if (xy[1] > s.screenHeight * 0.76) {
                _view.focus = :cancel;
                _view.cancelTimer();
            } else if (xy[1] > s.screenHeight * 0.54) {
                _view.focus = :primary;
                _view.primary();
            }
        } else if (xy[1] > s.screenHeight * 0.68) {
            _view.primary();
        } else if (xy[0] < s.screenWidth * 0.35) {
            _view.adjust(-1);
        } else if (xy[0] > s.screenWidth * 0.65) {
            _view.adjust(1);
        }
        return true;
    }

    function onSwipe(evt as WatchUi.SwipeEvent) as Boolean {
        return true;
    }
}
