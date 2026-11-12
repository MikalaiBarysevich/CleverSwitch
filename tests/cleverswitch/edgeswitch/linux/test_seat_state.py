from cleverswitch.edgeswitch.linux.seat_state import SeatState
from cleverswitch.model.config.modifier import Modifier

LEFTCTRL, RIGHTCTRL, LEFTSHIFT, LEFTALT, LEFTMETA, KEY_A = 29, 97, 42, 56, 125, 30
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_SIDE = 0x110, 0x111, 0x112, 0x113


def test_pressed_ctrl_is_held():
    state = SeatState()
    assert state.on_key(LEFTCTRL, 1)
    assert state.modifiers == Modifier.CTRL


def test_left_and_right_merge():
    state = SeatState()
    state.on_key(LEFTCTRL, 1)
    state.on_key(RIGHTCTRL, 1)
    state.on_key(LEFTCTRL, 0)
    assert state.modifiers == Modifier.CTRL
    state.on_key(RIGHTCTRL, 0)
    assert state.modifiers == Modifier.NONE


def test_ctrl_on_two_keyboards_stays_held_until_both_release():
    state = SeatState()
    assert state.on_key(LEFTCTRL, 1)
    assert not state.on_key(LEFTCTRL, 2)
    assert not state.on_key(LEFTCTRL, 1)
    assert state.modifiers == Modifier.CTRL
    assert state.on_key(LEFTCTRL, 0)
    assert state.modifiers == Modifier.NONE


def test_other_keys_are_ignored():
    state = SeatState()
    assert not state.on_key(KEY_A, 1)
    assert state.modifiers == Modifier.NONE


def test_all_modifiers_combine():
    state = SeatState()
    for code in (LEFTCTRL, LEFTSHIFT, LEFTALT, LEFTMETA):
        state.on_key(code, 1)
    assert state.modifiers == Modifier.CTRL | Modifier.SHIFT | Modifier.ALT | Modifier.META


def test_main_buttons_are_tracked():
    state = SeatState()
    for code in (BTN_LEFT, BTN_RIGHT, BTN_MIDDLE):
        assert state.on_button(code, 1)
        assert state.buttons_held
        assert state.on_button(code, 0)
        assert not state.buttons_held


def test_side_buttons_are_tracked():
    state = SeatState()
    for code in (BTN_SIDE, 0x114, 0x115, 0x116):
        assert state.on_button(code, 1)
        assert state.buttons_held
        assert state.on_button(code, 0)
        assert not state.buttons_held


def test_clear():
    state = SeatState()
    state.on_key(LEFTCTRL, 1)
    state.on_button(BTN_LEFT, 1)
    state.clear_keys()
    state.clear_buttons()
    assert state.modifiers == Modifier.NONE
    assert not state.buttons_held


def test_a_side_button_held_on_two_devices_stays_held():
    state = SeatState()
    state.on_button(BTN_SIDE, 2)
    assert state.buttons_held
    state.on_button(BTN_SIDE, 1)
    assert state.buttons_held
    state.on_button(BTN_SIDE, 0)
    assert not state.buttons_held
