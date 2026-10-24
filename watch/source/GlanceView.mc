import Toybox.Graphics;
import Toybox.Lang;
import Toybox.WatchUi;

(:glance)
class CtGlanceView extends WatchUi.GlanceView {
    function initialize() {
        GlanceView.initialize();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        dc.setColor(Graphics.COLOR_TRANSPARENT, Graphics.COLOR_BLACK);
        dc.clear();
        var h = dc.getHeight();
        var d = Ct.getData();

        dc.setColor(Ct.COLOR_ACCENT, Graphics.COLOR_TRANSPARENT);
        dc.drawText(0, h * 0.22, Graphics.FONT_GLANCE, "CHEFSTEMP", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);

        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        var line;
        if (d == null) {
            line = "Open app to connect";
        } else {
            line = "Grill " + Ct.fmtU(d["g"], d["gF"]);
            if (d["p"] != null) {
                line += "  Probe " + Ct.fmtU(d["p"], d["pF"]);
            }
        }
        dc.drawText(0, h * 0.55, Graphics.FONT_GLANCE, line, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);

        if (d != null) {
            dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
            var fan = "on".equals(d["fan"]) ? "Fan " + (d["run"] == true ? "run " : "stop ") + Ct.fmt(d["ft"], d["nF"]) + "°  " : "";
            dc.drawText(0, h * 0.86, Graphics.FONT_XTINY, fan + Ct.ageText(d), Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        }
    }
}
