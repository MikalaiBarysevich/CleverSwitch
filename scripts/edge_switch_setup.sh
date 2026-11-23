#!/bin/bash
# Shared edge-switch setup for the installer scripts.
#
# Sourced, never executed. It defines its own _es_* helpers rather than relying on the caller's, uses only
# bash 3.2 features (macOS /bin/bash), and reads every prompt from stdin so a piped answer list works.

EDGE_CONFIG="$HOME/.config/cleverswitch/config.yaml"

_es_info() { printf "\033[1;34m==> %s\033[0m\n" "$*"; }
_es_ok() { printf "\033[1;32m==> %s\033[0m\n" "$*"; }
_es_warn() { printf "\033[1;33m==> %s\033[0m\n" "$*"; }

# Reads one answer into ES_ANSWER. Prompts go to stderr so they stay visible when stdin is piped.
# read returns non-zero at EOF even after copying characters, so the value is kept when there is one.
_es_read() {
    printf "\033[1;34m==> %s: \033[0m" "$1" >&2
    ES_ANSWER=""
    IFS= read -r ES_ANSWER || true
    ES_ANSWER="$(printf '%s' "$ES_ANSWER" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
}

_es_ask_yes_no() {
    while true; do
        _es_read "$1 [y/n]"
        case "$ES_ANSWER" in
            [Yy]*) return 0 ;;
            [Nn]*) return 1 ;;
            "") return 1 ;;
            *) printf "Please answer y or n.\n" >&2 ;;
        esac
    done
}

# Numbered choice; empty takes the default. Sets ES_MODIFIER to ctrl/alt/shift/meta.
_es_ask_modifier() {
    printf "\033[1;34m==> Modifier to hold:\033[0m\n" >&2
    printf "  1) ctrl\n  2) alt\n  3) shift\n  4) meta\n" >&2
    while true; do
        _es_read "Choose 1-4 [1]"
        case "$ES_ANSWER" in
            ""|1) ES_MODIFIER="ctrl"; return 0 ;;
            2) ES_MODIFIER="alt"; return 0 ;;
            3) ES_MODIFIER="shift"; return 0 ;;
            4) ES_MODIFIER="meta"; return 0 ;;
            *) printf "Choose 1, 2, 3 or 4.\n" >&2 ;;
        esac
    done
}

# Host 1..3, or an empty answer to leave the edge unmapped. $1 is the edge name. Sets ES_HOST.
# The label is spelled out because macOS ships bash 3.2, which lacks ${var^}.
_es_ask_host() {
    local edge="$1" value label
    case "$edge" in
        left) label="Left" ;;
        right) label="Right" ;;
        top) label="Top" ;;
        *) label="Bottom" ;;
    esac
    while true; do
        _es_read "$label edge -> host 1-3 (Enter to skip)"
        value="$ES_ANSWER"
        if [ -z "$value" ]; then
            ES_HOST=""
            return 0
        fi
        case "$value" in
            1|2|3)
                ES_HOST="$value"
                return 0
                ;;
            *) printf "Host must be 1, 2, 3 or empty.\n" >&2 ;;
        esac
    done
}

# Replaces every top-level edge_switch block with $1, keeping every other line. A commented-out entry and an
# indented one are not matched, so only real sections go. Portable: no sed -i, because BSD and GNU sed disagree.
_es_replace_block() {
    local block="$1" tmp_block tmp_out mode
    tmp_block="$(mktemp "${TMPDIR:-/tmp}/cs-edge.XXXXXX")" || return 1
    tmp_out="$(mktemp "${TMPDIR:-/tmp}/cs-edge.XXXXXX")" || { rm -f "$tmp_block"; return 1; }
    printf '%s\n' "$block" > "$tmp_block" || { rm -f "$tmp_block" "$tmp_out"; return 1; }

    # A block runs from its key to the last indented non-blank line; a column-0 line (key or comment) ends it.
    # Every real block is dropped and the new one takes the place of the first.
    if awk -v bf="$tmp_block" '
        BEGIN { while ((getline line < bf) > 0) block = block line "\n" }
        /^edge_switch:/ {
            if (!written) { printf "%s", block; written = 1 }
            skipping = 1
            next
        }
        skipping {
            if ($0 ~ /^[[:space:]]/ || $0 == "") { next }
            skipping = 0
            print ""
        }
        { print }
    ' "$EDGE_CONFIG" > "$tmp_out"; then
        mode="$(stat -c '%a' "$EDGE_CONFIG" 2>/dev/null || stat -f '%Lp' "$EDGE_CONFIG" 2>/dev/null || true)"
        mv "$tmp_out" "$EDGE_CONFIG" || { rm -f "$tmp_block" "$tmp_out"; return 1; }
        if [ -n "$mode" ]; then
            chmod "$mode" "$EDGE_CONFIG" 2>/dev/null || true
        fi
        rm -f "$tmp_block"
        return 0
    fi
    rm -f "$tmp_block" "$tmp_out"
    return 1
}

# Writes the edge_switch block. An existing section is left alone unless the user agrees to replace it.
# Sets ES_CONFIG_WRITTEN=1 when the file changed.
_es_write_config() {
    local block="$1"
    mkdir -p "$(dirname "$EDGE_CONFIG")" || return 1

    if [ -f "$EDGE_CONFIG" ] && grep -qE '^edge_switch:' "$EDGE_CONFIG"; then
        local sections
        sections="$(grep -cE '^edge_switch:' "$EDGE_CONFIG" || true)"
        if [ "${sections:-1}" -gt 1 ]; then
            _es_info "$EDGE_CONFIG has $sections edge_switch sections; replacing all of them with one."
        fi
        if ! _es_ask_yes_no "edge_switch is already configured in $EDGE_CONFIG. Replace it?"; then
            _es_info "Kept the existing edge_switch section."
            ES_CONFIG_WRITTEN=0
            return 0
        fi
        if _es_replace_block "$block"; then
            ES_CONFIG_WRITTEN=1
            return 0
        fi
        _es_warn "Could not rewrite $EDGE_CONFIG; add the block by hand instead."
        ES_CONFIG_WRITTEN=0
        return 0
    fi

    if [ -f "$EDGE_CONFIG" ]; then
        { printf '\n' >> "$EDGE_CONFIG" &&
            printf '# Edge switch (added by the installer)\n%s\n' "$block" >> "$EDGE_CONFIG"; } || return 1
    else
        printf '# CleverSwitch configuration (created by the installer)\n%s\n' "$block" > "$EDGE_CONFIG" || return 1
    fi
    ES_CONFIG_WRITTEN=1
}

_es_build_block() {
    local enabled=false
    if [ "$ES_COUNT" -gt 0 ]; then
        enabled=true
    fi
    printf 'edge_switch:\n  enabled: %s\n  modifier: %s\n' "$enabled" "$ES_MODIFIER"
    if [ "$ES_COUNT" -gt 0 ]; then
        printf '  edges:\n'
        if [ -n "$ES_LEFT" ]; then printf '    left: %s\n' "$ES_LEFT"; fi
        if [ -n "$ES_RIGHT" ]; then printf '    right: %s\n' "$ES_RIGHT"; fi
        if [ -n "$ES_TOP" ]; then printf '    top: %s\n' "$ES_TOP"; fi
        if [ -n "$ES_BOTTOM" ]; then printf '    bottom: %s\n' "$ES_BOTTOM"; fi
    fi
}

# Prints the block the user would have to add, for installs that cannot write it.
_es_print_block() {
    printf '\nAdd this to %s:\n\n' "$EDGE_CONFIG"
    _es_build_block | sed 's/^/    /'
    printf '\n'
}

_es_collect() {
    _es_ask_modifier
    _es_ask_host left
    ES_LEFT="$ES_HOST"
    _es_ask_host right
    ES_RIGHT="$ES_HOST"
    _es_ask_host top
    ES_TOP="$ES_HOST"
    _es_ask_host bottom
    ES_BOTTOM="$ES_HOST"
    ES_COUNT=0
    if [ -n "$ES_LEFT" ]; then ES_COUNT=$((ES_COUNT + 1)); fi
    if [ -n "$ES_RIGHT" ]; then ES_COUNT=$((ES_COUNT + 1)); fi
    if [ -n "$ES_TOP" ]; then ES_COUNT=$((ES_COUNT + 1)); fi
    if [ -n "$ES_BOTTOM" ]; then ES_COUNT=$((ES_COUNT + 1)); fi
}

_es_is_gnome() {
    case "$(printf '%s' "${XDG_CURRENT_DESKTOP:-}" | tr '[:upper:]' '[:lower:]')" in
        *gnome*) return 0 ;;
        *) return 1 ;;
    esac
}

_es_is_kde() {
    case "$(printf '%s' "${XDG_CURRENT_DESKTOP:-}" | tr '[:upper:]' '[:lower:]')" in
        *kde*|*plasma*) return 0 ;;
        *) return 1 ;;
    esac
}

_es_is_hyprland() {
    [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && return 0
    case "$(printf '%s' "${XDG_CURRENT_DESKTOP:-}" | tr '[:upper:]' '[:lower:]')" in
        *hyprland*) return 0 ;;
        *) return 1 ;;
    esac
}

_es_is_x11() {
    [ "${XDG_SESSION_TYPE:-}" = "x11" ] && return 0
    [ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && return 0
    return 1
}

# True when edge switch can work here, or when the session cannot be identified.
_es_supported() {
    if _es_is_x11 || _es_is_hyprland || _es_is_kde || _es_is_gnome; then
        return 0
    fi
    if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] && [ -n "${XDG_CURRENT_DESKTOP:-}" ]; then
        return 1
    fi
    return 0
}

_es_supported_note() {
    if _es_is_x11; then
        _es_info "X11 session: the X server reports the cursor, so no extra permission is needed."
    elif _es_is_hyprland; then
        _es_info "Hyprland: edge switch reads the keyboard through libinput, which needs part 2 of"
        _es_info "rules.d/42-cleverswitch.rules (installed above) or membership of the 'input' group."
    elif _es_is_kde; then
        _es_info "KDE Plasma: edge switch loads a small KWin script while it runs and reads the keyboard"
        _es_info "through libinput, which needs part 2 of rules.d/42-cleverswitch.rules (installed above)."
    elif _es_is_gnome; then
        _es_info "GNOME: edge switch needs the bundled GNOME Shell extension; see below."
    fi
}

_es_install_gnome_extension() {
    local src="$1"
    local uuid="cleverswitch@mikalaibarysevich.github.io"
    local dest="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$uuid"

    if [ -z "$src" ] || [ ! -d "$src/$uuid" ]; then
        _es_warn "The GNOME Shell extension is not in this archive; copy gnome-extension/$uuid from the"
        _es_warn "source tree. See 'Enabling edge switch on KDE / GNOME' in README.md."
        return 0
    fi
    mkdir -p "$(dirname "$dest")" || return 1
    rm -rf "$dest" || return 1
    cp -r "$src/$uuid" "$dest" || return 1
    _es_ok "GNOME Shell extension copied to $dest"
    _es_info "Log out and back in, then run:"
    _es_info "  gnome-extensions enable $uuid"
}

# Entry point for the Linux installers. $1 is the directory holding gnome-extension/, or empty.
es_configure_linux() {
    local extension_dir="${1:-}"
    if ! _es_supported; then
        _es_info "Edge switch is not available on this desktop: it works on X11, Hyprland, KDE Plasma 6"
        _es_info "and GNOME 45+ on Wayland, because only they share the cursor position."
        return 0
    fi
    if ! _es_ask_yes_no "Configure edge switch (switch hosts by holding a modifier at a screen edge)?"; then
        _es_info "Skipped. See 'Edge Switch' in README.md to set it up later."
        return 0
    fi

    _es_supported_note
    _es_collect
    if [ "$ES_COUNT" -eq 0 ]; then
        _es_warn "No edge was mapped, so there is nothing to write; edge switch stays off."
        _es_print_block
        return 0
    fi
    if ! _es_write_config "$(_es_build_block)"; then
        _es_warn "Could not write $EDGE_CONFIG; add the edge_switch section by hand."
    elif [ "${ES_CONFIG_WRITTEN:-0}" -eq 1 ]; then
        _es_ok "edge_switch written to $EDGE_CONFIG"
    fi
    if _es_is_gnome && ! _es_is_x11; then
        _es_install_gnome_extension "$extension_dir" ||
            _es_warn "Could not install the GNOME Shell extension; copy it by hand."
    fi
}

# Entry point for the macOS installers: no /dev/input, no widget, just the permission note.
es_configure_macos() {
    if ! _es_ask_yes_no "Configure edge switch (switch hosts by holding a modifier at a screen edge)?"; then
        _es_info "Skipped. See 'Edge Switch' in README.md to set it up later."
        return 0
    fi
    _es_collect
    if [ "$ES_COUNT" -eq 0 ]; then
        _es_warn "No edge was mapped, so there is nothing to write; edge switch stays off."
        _es_print_block
        return 0
    fi
    if ! _es_write_config "$(_es_build_block)"; then
        _es_warn "Could not write $EDGE_CONFIG; add the edge_switch section by hand."
    elif [ "${ES_CONFIG_WRITTEN:-0}" -eq 1 ]; then
        _es_ok "edge_switch written to $EDGE_CONFIG"
    fi
    _es_info "macOS asks for Input Monitoring once: System Settings -> Privacy & Security -> Input Monitoring."
    _es_info "CleverSwitch needs it anyway, so nothing else is required."
}
