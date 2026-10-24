import Toybox.Application;
import Toybox.Graphics;
import Toybox.Lang;

// fenix 7 Pro has a reflective MIP display: only full-intensity palette colors stay
// readable without the backlight, so grays are avoided for anything that carries information.
module Theme {
    const KEY_THEME = "theme";
    const DARK = 0;
    const LIGHT = 1;

    var _light as Boolean? = null;

    function get() as Number {
        var t = Application.Storage.getValue(KEY_THEME);
        return (t instanceof Number) ? t : LIGHT;
    }

    function set(t as Number) as Void {
        Application.Storage.setValue(KEY_THEME, t);
        _light = t == LIGHT;
    }

    function light() as Boolean {
        if (_light == null) {
            _light = get() == LIGHT;
        }
        return _light as Boolean;
    }

    function bg() as Number {
        return light() ? Graphics.COLOR_WHITE : Graphics.COLOR_BLACK;
    }

    function fg() as Number {
        return light() ? Graphics.COLOR_BLACK : Graphics.COLOR_WHITE;
    }

    // Secondary text: still full contrast on the dark theme.
    function dim() as Number {
        return light() ? Graphics.COLOR_DK_GRAY : Graphics.COLOR_WHITE;
    }

    // Inactive outlines, empty bars, unselected dots.
    function faint() as Number {
        return light() ? Graphics.COLOR_DK_GRAY : Graphics.COLOR_LT_GRAY;
    }

    function accent() as Number {
        return light() ? 0xFF5500 : Ct.COLOR_ACCENT;
    }

    // Text drawn on top of an accent fill.
    function onAccent() as Number {
        return Graphics.COLOR_BLACK;
    }

    function error() as Number {
        return light() ? 0xAA0000 : Graphics.COLOR_RED;
    }
}
