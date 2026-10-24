import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Math;

module Draw {
    // Offset of the digit/cap top below the text cell top, and the glyph height,
    // measured on fenix 7 Pro fonts.
    function glyphTop(font as Graphics.FontType) as Number {
        if (font == Graphics.FONT_NUMBER_HOT) { return 25; }
        if (font == Graphics.FONT_NUMBER_MEDIUM) { return 19; }
        if (font == Graphics.FONT_NUMBER_MILD) { return 15; }
        if (font == Graphics.FONT_MEDIUM) { return 9; }
        if (font == Graphics.FONT_SMALL) { return 7; }
        if (font == Graphics.FONT_TINY) { return 7; }
        return 5;
    }

    function glyphHeight(font as Graphics.FontType) as Number {
        if (font == Graphics.FONT_NUMBER_HOT) { return 48; }
        if (font == Graphics.FONT_NUMBER_MEDIUM) { return 35; }
        if (font == Graphics.FONT_NUMBER_MILD) { return 29; }
        if (font == Graphics.FONT_MEDIUM) { return 21; }
        if (font == Graphics.FONT_SMALL) { return 17; }
        if (font == Graphics.FONT_TINY) { return 16; }
        return 10;
    }

    function unitFontFor(font as Graphics.FontType) as Graphics.FontType {
        if (font == Graphics.FONT_NUMBER_HOT) { return Graphics.FONT_MEDIUM; }
        if (font == Graphics.FONT_NUMBER_MEDIUM) { return Graphics.FONT_SMALL; }
        return Graphics.FONT_TINY;
    }

    function isNumeric(text as String) as Boolean {
        return text.length() > 0 && text.toNumber() != null;
    }

    function valueWidth(dc as Graphics.Dc, font as Graphics.FontType, text as String, unit as String) as Number {
        if (!isNumeric(text)) {
            return dc.getTextWidthInPixels(text, Graphics.FONT_LARGE);
        }
        return dc.getTextWidthInPixels(text, font) + 2 + dc.getTextWidthInPixels("°" + unit, unitFontFor(font));
    }

    // Draws a number with a "°F" whose top edge lines up with the top of the digits.
    // yc is the vertical center of the digits; x is the left edge.
    function valueLeft(dc as Graphics.Dc, x as Number, yc as Number, font as Graphics.FontType, text as String, unit as String, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        if (!isNumeric(text)) {
            dc.drawText(x, yc, Graphics.FONT_LARGE, text, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
            return;
        }
        var top = yc - glyphHeight(font) / 2;
        dc.drawText(x, top - glyphTop(font), font, text, Graphics.TEXT_JUSTIFY_LEFT);
        var uf = unitFontFor(font);
        dc.drawText(x + dc.getTextWidthInPixels(text, font) + 2, top - glyphTop(uf), uf, "°" + unit, Graphics.TEXT_JUSTIFY_LEFT);
    }

    function value(dc as Graphics.Dc, x as Number, yc as Number, font as Graphics.FontType, text as String, unit as String, color as Number) as Void {
        valueLeft(dc, x - valueWidth(dc, font, text, unit) / 2, yc, font, text, unit, color);
    }

    function grill(dc as Graphics.Dc, x as Number, y as Number, r as Number, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(2);
        var pts = [] as Array<[Numeric, Numeric]>;
        for (var a = 0; a <= 180; a += 20) {
            var rad = Math.toRadians(a);
            pts.add([x + r * Math.cos(rad), y + r * 0.8 * Math.sin(rad)]);
        }
        dc.fillPolygon(pts);
        dc.drawLine(x - r - 2, y - 2, x + r + 3, y - 2);
        dc.drawLine(x - r / 2, y + r * 0.6, x - r, y + r * 1.6);
        dc.drawLine(x + r / 2, y + r * 0.6, x + r, y + r * 1.6);
        dc.drawLine(x, y + r * 0.8, x, y + r * 1.6);
        dc.drawLine(x - r * 0.7, y + r * 1.2, x + r * 0.7, y + r * 1.2);
        dc.fillPolygon([
            [x - r * 0.45, y - 5], [x - r * 0.55, y - r * 0.7], [x - r * 0.2, y - r * 0.45],
            [x, y - r * 1.25], [x + r * 0.25, y - r * 0.5], [x + r * 0.55, y - r * 0.8], [x + r * 0.45, y - 5]
        ]);
        dc.setPenWidth(1);
    }

    function probe(dc as Graphics.Dc, x as Number, y as Number, r as Number, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(3);
        dc.drawLine(x - r, y + r, x + r * 0.3, y - r * 0.3);
        dc.setPenWidth(1);
        dc.fillPolygon([
            [x + r * 0.1, y - r * 0.6], [x + r * 0.9, y - r * 1.2], [x + r * 1.2, y - r * 0.9], [x + r * 0.6, y - r * 0.1]
        ]);
    }

    function fan(dc as Graphics.Dc, x as Number, y as Number, r as Number, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        for (var i = 0; i < 3; i++) {
            var a = Math.toRadians(i * 120 + 30);
            dc.fillCircle(x + r * 0.5 * Math.cos(a), y + r * 0.5 * Math.sin(a), r * 0.45);
        }
        dc.setColor(Theme.bg(), Graphics.COLOR_TRANSPARENT);
        dc.fillCircle(x, y, r * 0.2);
    }

    function bell(dc as Graphics.Dc, x as Number, y as Number, r as Number, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.fillCircle(x, y - r * 0.2, r * 0.6);
        dc.fillPolygon([[x - r * 0.6, y - r * 0.2], [x + r * 0.6, y - r * 0.2], [x + r * 0.9, y + r * 0.6], [x - r * 0.9, y + r * 0.6]]);
        dc.fillCircle(x, y + r * 0.8, r * 0.2);
    }

    function arrowCircle(dc as Graphics.Dc, x as Number, y as Number, r as Number, up as Boolean, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(2);
        dc.drawCircle(x, y, r);
        var d = up ? -1 : 1;
        dc.drawLine(x, y - d * r * 0.55, x, y + d * r * 0.55);
        dc.fillPolygon([[x - r * 0.45, y + d * r * 0.1], [x + r * 0.45, y + d * r * 0.1], [x, y + d * r * 0.6]]);
        dc.setPenWidth(1);
    }

    function plusMinus(dc as Graphics.Dc, x as Number, y as Number, r as Number, plus as Boolean, active as Boolean) as Void {
        dc.setColor(Theme.accent(), Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(3);
        if (active) {
            dc.fillCircle(x, y, r);
            dc.setColor(Theme.onAccent(), Graphics.COLOR_TRANSPARENT);
        } else {
            dc.drawCircle(x, y, r);
        }
        dc.drawLine(x - r / 2, y, x + r / 2 + 1, y);
        if (plus) {
            dc.drawLine(x, y - r / 2, x, y + r / 2 + 1);
        }
        dc.setPenWidth(1);
    }

    function battery(dc as Graphics.Dc, x as Number, y as Number, pct as Float?, color as Number) as Number {
        var bw = 18;
        var bh = 10;
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(2);
        dc.drawRectangle(x, y - bh / 2, bw, bh);
        dc.setPenWidth(1);
        dc.fillRectangle(x + bw, y - 2, 2, 4);
        if (pct != null) {
            var p = pct < 0 ? 0 : (pct > 100 ? 100 : pct);
            dc.fillRectangle(x + 2, y - bh / 2 + 2, ((bw - 4) * p / 100).toNumber(), bh - 4);
        }
        var text = pct == null ? "--" : pct.toNumber() + "%";
        dc.drawText(x + bw + 5, y, Graphics.FONT_XTINY, text, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        return bw + 5 + dc.getTextWidthInPixels(text, Graphics.FONT_XTINY);
    }

    function bluetooth(dc as Graphics.Dc, x as Number, y as Number, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(2);
        dc.drawLine(x, y - 7, x, y + 7);
        dc.drawLine(x - 4, y - 4, x + 4, y + 3);
        dc.drawLine(x + 4, y + 3, x, y + 7);
        dc.drawLine(x - 4, y + 4, x + 4, y - 3);
        dc.drawLine(x + 4, y - 3, x, y - 7);
        dc.setPenWidth(1);
    }

    function wifi(dc as Graphics.Dc, x as Number, y as Number, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(2);
        for (var r = 4; r <= 12; r += 4) {
            dc.drawArc(x, y + 5, r, Graphics.ARC_COUNTER_CLOCKWISE, 45, 135);
        }
        dc.setPenWidth(1);
        dc.fillCircle(x, y + 5, 2);
    }

    // Cloud glyph, centred roughly on (x, y); about 18 px wide.
    function cloud(dc as Graphics.Dc, x as Number, y as Number, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.fillCircle(x - 5, y + 1, 4);
        dc.fillCircle(x + 5, y + 1, 5);
        dc.fillCircle(x, y - 3, 5);
        dc.fillRectangle(x - 8, y, 16, 5);
    }

    // Stopwatch glyph: dial of radius r centred on (x, y) with a stem, a top
    // button and a single hand.
    function timerIcon(dc as Graphics.Dc, x as Number, y as Number, r as Number, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(2);
        dc.drawCircle(x, y + 1, r);
        dc.drawLine(x, y - r - 2, x, y - r + 2);
        dc.drawLine(x - 3, y - r - 2, x + 3, y - r - 2);
        dc.drawLine(x, y + 1, x, (y + 1 - r * 0.6).toNumber());
        dc.drawLine(x, y + 1, (x + r * 0.45).toNumber(), (y + 1 - r * 0.2).toNumber());
        dc.setPenWidth(1);
    }

    function check(dc as Graphics.Dc, x as Number, y as Number, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(3);
        dc.drawLine(x - 7, y, x - 2, y + 5);
        dc.drawLine(x - 2, y + 5, x + 7, y - 5);
        dc.setPenWidth(1);
    }

    function roundBox(dc as Graphics.Dc, x as Number, y as Number, w as Number, h as Number, color as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(3);
        dc.drawRoundedRectangle(x, y, w, h, 10);
        dc.setPenWidth(1);
    }

    function pill(dc as Graphics.Dc, x as Number, y as Number, w as Number, h as Number, text as String, withCheck as Boolean) as Void {
        dc.setColor(Theme.accent(), Graphics.COLOR_TRANSPARENT);
        dc.fillRoundedRectangle(x - w / 2, y - h / 2, w, h, h / 2);
        var tw = dc.getTextWidthInPixels(text, Graphics.FONT_TINY);
        var tx = x;
        if (withCheck) {
            tx = x + 12;
            check(dc, tx - tw / 2 - 14, y, Theme.onAccent());
        }
        dc.setColor(Theme.onAccent(), Graphics.COLOR_TRANSPARENT);
        dc.drawText(tx, y, Graphics.FONT_TINY, text, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
    }

    function pageDots(dc as Graphics.Dc, page as Number, count as Number) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        var cx = w / 2;
        var cy = h / 2;
        var r = w / 2 - 7;
        for (var i = 0; i < count; i++) {
            var a = Math.toRadians(180 + (i - (count - 1) / 2.0) * 7);
            var px = cx + r * Math.cos(a);
            var py = cy - r * Math.sin(a);
            if (i == page) {
                dc.setColor(Theme.accent(), Graphics.COLOR_TRANSPARENT);
                dc.fillCircle(px, py, 4);
            } else {
                dc.setColor(Theme.faint(), Graphics.COLOR_TRANSPARENT);
                dc.fillCircle(px, py, 3);
            }
        }
    }
}
