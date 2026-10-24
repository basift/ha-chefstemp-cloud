import Toybox.Application;
import Toybox.Background;
import Toybox.Lang;
import Toybox.System;
import Toybox.Time;
import Toybox.WatchUi;

(:background)
class ChefsTempApp extends Application.AppBase {
    const BG_PERIOD = 300;

    var inApp as Boolean = false;

    function initialize() {
        AppBase.initialize();
    }

    function getServiceDelegate() as [System.ServiceDelegate] {
        return [new CtService()];
    }

    (:glance)
    function getGlanceView() as [WatchUi.GlanceView] or [WatchUi.GlanceView, WatchUi.GlanceViewDelegate] or Null {
        registerBackground();
        return [new CtGlanceView()];
    }

    function getInitialView() as [WatchUi.Views] or [WatchUi.Views, WatchUi.InputDelegates] {
        registerBackground();
        inApp = true;
        var view = new MainView();
        return [view, new MainDelegate(view)];
    }

    function onBackgroundData(data as Application.PersistableType) as Void {
        if (data instanceof Dictionary && data["ts"] != null) {
            var msg = data["alarm"] as String?;
            data.remove("alarm");
            Ct.store(data);
            if (inApp) {
                if (msg != null) {
                    Alarm.fire(msg);
                }
                Alarm.check(data);
            }
        }
        WatchUi.requestUpdate();
    }

    (:glance)
    function registerBackground() as Void {
        if (Background.getTemporalEventRegisteredTime() == null) {
            Background.registerForTemporalEvent(new Time.Duration(BG_PERIOD));
        }
    }
}

(:background)
class CtService extends System.ServiceDelegate {
    function initialize() {
        ServiceDelegate.initialize();
    }

    function onTemporalEvent() as Void {
        if (!Ha.configured()) {
            Background.exit(null);
            return;
        }
        Ha.fetchState(method(:onResponse));
    }

    function onResponse(code as Number, data as Dictionary or String or Null) as Void {
        var parsed = null;
        if (code == 200 && data instanceof String) {
            parsed = Ct.parse(data);
        }
        if (parsed != null) {
            var msg = Ct.checkAlarms(parsed, true);
            if (msg != null) {
                parsed["alarm"] = msg;
                Background.requestApplicationWake("ChefsTemp: " + msg);
            }
        }
        Background.exit(parsed);
    }
}
