#!/bin/bash

# 1. Define variables
APP_NAME="cleverswitch"
PLIST_LABEL="com.user.$APP_NAME"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

# 2. Find the absolute path of the installed executable
# This ensures we point to the correct pip-installed bin
BINARY_PATH=$(which $APP_NAME)

if [ -z "$BINARY_PATH" ]; then
    echo "Error: $APP_NAME not found. Please install it via pip first."
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
