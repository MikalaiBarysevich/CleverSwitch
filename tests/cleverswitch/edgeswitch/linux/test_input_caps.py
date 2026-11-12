from cleverswitch.edgeswitch.linux.input_caps import has_bit, is_keyboard, is_pointer

# Real sysfs values: a keyboard's key bitmap and a mouse's key/rel bitmaps.
KEYBOARD_KEYS = "1000000000007 ff9f207ac14057ff febeffdfffefffff fffffffffffffffe"
MOUSE_KEYS = "1f0000 0 0 0 0"
MOUSE_REL = "1943"


def test_has_bit_counts_words_from_the_right():
    assert has_bit("1 0", 64)
    assert not has_bit("1 0", 0)
    assert has_bit("3", 1)


def test_has_bit_beyond_bitmap_is_false():
    assert not has_bit("ff", 64)
    assert not has_bit("", 0)


def test_has_bit_with_garbage_is_false():
    assert not has_bit("zz", 0)


def test_classifies_keyboard_and_mouse():
    assert is_keyboard(KEYBOARD_KEYS)
    assert not is_keyboard(MOUSE_KEYS)
    assert is_pointer(MOUSE_KEYS, MOUSE_REL)
    assert not is_pointer(KEYBOARD_KEYS, "0")


def test_pointer_needs_both_axes():
    assert not is_pointer(MOUSE_KEYS, "1")
