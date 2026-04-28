#!/bin/bash

# 1. Define variables
APP_NAME="cleverswitch"
INSTALL_PATH="$HOME/.local/bin/$APP_NAME"
PLIST_LABEL="com.user.$APP_NAME"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

# 2. Resolve the absolute path of the installed executable.
# Prefer the canonical install location so the plist survives PATH changes
# and stale binaries elsewhere on PATH. Fall back to `which` for manual installs.
if [ -x "$INSTALL_PATH" ]; then
    BINARY_PATH="$INSTALL_PATH"
else
    BINARY_PATH=$(which $APP_NAME)
fi

if [ -z "$BINARY_PATH" ]; then
    echo "Error: $APP_NAME not found at $INSTALL_PATH or on your PATH."
    echo "Please install with install.command first."
    exit 1
fi

echo "Found $APP_NAME at: $BINARY_PATH"

# 3. Create the Launch Agent .plist file
cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$BINARY_PATH</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/$APP_NAME.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/$APP_NAME.err.log</string>
</dict>
</plist>
EOF

# 4. Set correct permissions
chmod 644 "$PLIST_PATH"

# 5. Load the agent
# Unload first in case it's already running an old version
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo "Successfully installed and started $APP_NAME startup agent."
echo "Logs can be found at /tmp/$APP_NAME.out.log"
