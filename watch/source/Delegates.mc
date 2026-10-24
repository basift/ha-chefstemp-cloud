import Toybox.Graphics;
import Toybox.Lang;
import Toybox.System;
import Toybox.WatchUi;

class MainDelegate extends WatchUi.BehaviorDelegate {
    private var _view as MainView;

    function initialize(view as MainView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    // On the Alerts page with a box selected, UP/DOWN move the selection instead of the page.
    function onNextPage() as Boolean {
        if (_view.alertFocus != null) {
            toggleFocus();
        } else {
            _view.nextPage(1);
        }
        return true;
    }

    function onPreviousPage() as Boolean {
        if (_view.alertFocus != null) {
            toggleFocus();
        } else {
            _view.nextPage(-1);
        }
        return true;
    }

    function toggleFocus() as Void {
        _view.alertFocus = _view.alertFocus == :high ? :low : :high;
        WatchUi.requestUpdate();
    }

    function onSelect() as Boolean {
        var page = _view.page;
        if (page == PAGE_ALERTS) {
            if (_view.alertFocus == null) {
                _view.alertFocus = :high;
                WatchUi.requestUpdate();
            } else {
                openEditor(_view.alertFocus as Symbol);
            }
        } else if (page == PAGE_FAN) {
            openEditor(:fan);
        } else if (page == PAGE_PROBE) {
            openEditor(:probe);
        } else if (page == PAGE_TIMER) {
            openTimer();
        }
        return true;
    }

    function onBack() as Boolean {
        if (_view.alertFocus != null) {
            _view.alertFocus = null;
            WatchUi.requestUpdate();
            return true;
        }
        return false;
    }

    function onTap(evt as WatchUi.ClickEvent) as Boolean {
        var page = _view.page;
        if (page == PAGE_ALERTS) {
            var y = evt.getCoordinates()[1];
            var kind = y < System.getDeviceSettings().screenHeight / 2 ? :high : :low;
            _view.alertFocus = kind;
            openEditor(kind);
            return true;
        }
        if (page == PAGE_FAN || page == PAGE_PROBE || page == PAGE_TIMER) {
            onSelect();
            return true;
        }
        return false;
    }

    function onMenu() as Boolean {
        SettingsMenu.open();
        return true;
    }


    function openEditor(kind as Symbol) as Void {
        var d = Ct.getData();
        if (d == null) {
            return;
        }
        var view = new EditView(kind, d);
        WatchUi.pushView(view, new EditDelegate(view), WatchUi.SLIDE_UP);
    }

    // The timer editor works even before the first poll (it reads timer state live).
    function openTimer() as Void {
        var view = new TimerEditView();
        WatchUi.pushView(view, new TimerEditDelegate(view), WatchUi.SLIDE_UP);
    }
}

module SettingsMenu {
    function open() as Void {
        var menu = new WatchUi.Menu2({ :title => "Settings" });
        var units = ["Watch default", "Celsius °C", "Fahrenheit °F"];
        menu.addItem(new WatchUi.MenuItem("Units", units[Ct.getUnitPref()], :units, null));
        menu.addItem(new WatchUi.MenuItem("Theme", Theme.light() ? "Light" : "Dark", :theme, null));
        WatchUi.pushView(menu, new SettingsMenuDelegate(), WatchUi.SLIDE_UP);
    }
}

class SettingsMenuDelegate extends WatchUi.Menu2InputDelegate {
    function initialize() {
        Menu2InputDelegate.initialize();
    }

    function onSelect(item as WatchUi.MenuItem) as Void {
        WatchUi.popView(WatchUi.SLIDE_IMMEDIATE);
        if (item.getId() == :units) {
            UnitsMenu.open();
        } else {
            ThemeMenu.open();
        }
    }
}

module ThemeMenu {
    function open() as Void {
        var menu = new WatchUi.Menu2({ :title => "Theme" });
        var cur = Theme.get();
        menu.addItem(new WatchUi.MenuItem("Dark", cur == Theme.DARK ? "selected" : null, Theme.DARK, null));
        menu.addItem(new WatchUi.MenuItem("Light", cur == Theme.LIGHT ? "selected" : "best without backlight", Theme.LIGHT, null));
        WatchUi.pushView(menu, new ThemeMenuDelegate(), WatchUi.SLIDE_UP);
    }
}

class ThemeMenuDelegate extends WatchUi.Menu2InputDelegate {
    function initialize() {
        Menu2InputDelegate.initialize();
    }

    function onSelect(item as WatchUi.MenuItem) as Void {
        Theme.set(item.getId() as Number);
        WatchUi.popView(WatchUi.SLIDE_DOWN);
    }
}

module UnitsMenu {
    function open() as Void {
        var menu = new WatchUi.Menu2({ :title => "Units" });
        var cur = Ct.getUnitPref();
        var ids = [Ct.UNIT_WATCH, Ct.UNIT_C, Ct.UNIT_F];
        var names = ["Watch default", "Celsius °C", "Fahrenheit °F"];
        for (var i = 0; i < ids.size(); i++) {
            menu.addItem(new WatchUi.MenuItem(names[i], ids[i] == cur ? "selected" : null, ids[i], null));
        }
        WatchUi.pushView(menu, new UnitsMenuDelegate(), WatchUi.SLIDE_UP);
    }
}

class UnitsMenuDelegate extends WatchUi.Menu2InputDelegate {
    function initialize() {
        Menu2InputDelegate.initialize();
    }

    function onSelect(item as WatchUi.MenuItem) as Void {
        Ct.setUnitPref(item.getId() as Number);
        WatchUi.popView(WatchUi.SLIDE_DOWN);
    }
}
