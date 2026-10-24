import Toybox.Attention;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;

module Alarm {
    const REPEAT_MS = 20000;
    const MAX_REPEATS = 15;

    var view as AlertView? = null;

    function check(d as Dictionary) as Void {
        var msg = Ct.checkAlarms(d, true);
        if (msg != null) {
            fire(msg);
        }
    }

    function fire(msg as String) as Void {
        buzz();
        if (view != null) {
            (view as AlertView).message = msg;
            WatchUi.requestUpdate();
            return;
        }
        var v = new AlertView(msg);
        view = v;
        WatchUi.pushView(v, new AlertDelegate(), WatchUi.SLIDE_IMMEDIATE);
    }

    // Vibration and tones follow the watch's own Sounds & Vibe settings.
    function buzz() as Void {
        var s = System.getDeviceSettings();
        if (Attention has :vibrate && s.vibrateOn) {
            Attention.vibrate([
                new Attention.VibeProfile(100, 700),
                new Attention.VibeProfile(0, 300),
                new Attention.VibeProfile(100, 700),
                new Attention.VibeProfile(0, 300),
                new Attention.VibeProfile(100, 700)
            ]);
        }
        if (Attention has :playTone && s.tonesOn) {
            Attention.playTone(Attention.TONE_ALARM);
        }
        if (Attention has :backlight) {
            try {
                Attention.backlight(true);
            } catch (e) {
            }
        }
    }

    function dismiss() as Void {
        if (view != null) {
            (view as AlertView).stop();
            view = null;
            WatchUi.popView(WatchUi.SLIDE_IMMEDIATE);
        }
    }
}

class AlertView extends WatchUi.View {
    var message as String;
    private var _timer as Timer.Timer?;
    private var _repeats as Number = 0;

    function initialize(msg as String) {
        View.initialize();
        message = msg;
    }

    function onShow() as Void {
        if (_timer == null) {
            _timer = new Timer.Timer();
            (_timer as Timer.Timer).start(method(:repeat), Alarm.REPEAT_MS, true);
        }
    }

    function repeat() as Void {
        _repeats++;
        if (_repeats >= Alarm.MAX_REPEATS) {
            stop();
            return;
        }
        Alarm.buzz();
    }

    function stop() as Void {
        if (_timer != null) {
            (_timer as Timer.Timer).stop();
            _timer = null;
        }
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        dc.setColor(Theme.fg(), Theme.bg());
        dc.clear();
        var w = dc.getWidth();
        var h = dc.getHeight();
        Draw.bell(dc, w / 2, (h * 0.2).toNumber(), 18, Theme.accent());
        dc.setColor(Theme.accent(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, h * 0.36, Graphics.FONT_MEDIUM, "ALERT", Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.setColor(Theme.fg(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(w / 2, h * 0.6, Graphics.FONT_SMALL, message, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
        Draw.pill(dc, w / 2, (h * 0.85).toNumber(), (w * 0.45).toNumber(), 30, "DISMISS", false);
    }
}

class AlertDelegate extends WatchUi.BehaviorDelegate {
    function initialize() {
        BehaviorDelegate.initialize();
    }

    function onSelect() as Boolean {
        Alarm.dismiss();
        return true;
    }

    function onBack() as Boolean {
        Alarm.dismiss();
        return true;
    }

    function onNextPage() as Boolean {
        return true;
    }

    function onPreviousPage() as Boolean {
        return true;
    }
}
