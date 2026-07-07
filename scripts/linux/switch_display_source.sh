#!/usr/bin/env bash
current="$(ddcutil getvcp 60 --terse | awk '{print $NF}')"
if [[ "$current" != "x0f" ]]; then
    ddcutil setvcp 60 0x0f
fi
