import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const NAME = 'io.github.mikalaibarysevich.CleverSwitch';
const PATH = '/io/github/mikalaibarysevich/CleverSwitch';
const IFACE = 'io.github.mikalaibarysevich.CleverSwitch.EdgeSwitch';
const TOLERANCE = 1;
const M = Clutter.ModifierType;
const STATE_MASK = M.SHIFT_MASK | M.CONTROL_MASK | M.MOD1_MASK | M.MOD4_MASK | M.SUPER_MASK |
    M.BUTTON1_MASK | M.BUTTON2_MASK | M.BUTTON3_MASK | M.BUTTON4_MASK | M.BUTTON5_MASK;

// Tracks the cursor only while CleverSwitch owns its bus name, and calls it only when the held keys or the
// outer edges under the cursor change. Same edge rule as CleverSwitch: right and bottom are exclusive.
export default class CleverSwitchEdgeExtension extends Extension {
    enable() {
        this._watch = Gio.bus_watch_name(Gio.BusType.SESSION, NAME, Gio.BusNameWatcherFlags.NONE,
            () => this._start(), () => this._stop());
    }

    disable() {
        this._stop();
        if (this._watch) {
            Gio.bus_unwatch_name(this._watch);
            this._watch = 0;
        }
    }

    _start() {
        this._stop();
        this._tracker = global.backend.get_cursor_tracker();
        this._positionId = this._tracker.connect('position-invalidated', () => this._sample());
        this._tracker.track_position?.();
        this._monitorsId = Main.layoutManager.connect('monitors-changed', () => {
            this._bounds = this._computeBounds();
            this._sample();
        });
        this._bounds = this._computeBounds();
        this._state = -1;
        this._edges = -1;
        this._sample();
    }

    _stop() {
        if (this._tracker) {
            this._tracker.disconnect(this._positionId);
            this._tracker.untrack_position?.();
            this._tracker = null;
        }
        if (this._monitorsId) {
            Main.layoutManager.disconnect(this._monitorsId);
            this._monitorsId = 0;
        }
    }

    _computeBounds() {
        const monitors = Main.layoutManager.monitors;
        if (!monitors.length)
            return null;
        return {
            left: Math.min(...monitors.map(m => m.x)),
            top: Math.min(...monitors.map(m => m.y)),
            right: Math.max(...monitors.map(m => m.x + m.width)),
            bottom: Math.max(...monitors.map(m => m.y + m.height)),
        };
    }

    _sample() {
        const [x, y, mods] = global.get_pointer();
        const state = mods & STATE_MASK;
        if (state !== this._state) {
            this._state = state;
            this._call('State', state);
        }
        const b = this._bounds;
        let edges = 0;
        if (b) {
            if (x <= b.left + TOLERANCE)
                edges |= 1;
            if (x >= b.right - 1 - TOLERANCE)
                edges |= 2;
            if (y <= b.top + TOLERANCE)
                edges |= 4;
            if (y >= b.bottom - 1 - TOLERANCE)
                edges |= 8;
        }
        if (edges !== this._edges) {
            this._edges = edges;
            this._call('Edges', edges);
        }
    }

    _call(method, value) {
        Gio.DBus.session.call(NAME, PATH, IFACE, method, new GLib.Variant('(u)', [value]), null,
            Gio.DBusCallFlags.NO_AUTO_START, -1, null, null);
    }
}
