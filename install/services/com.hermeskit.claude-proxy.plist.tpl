<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.hermeskit.claude-proxy</string>
  <key>ProgramArguments</key>
  <array>
    <string>__NODE__</string>
    <string>__PROXY_DIR__/server.js</string>
  </array>
  <key>WorkingDirectory</key><string>__PROXY_DIR__</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>__PATH__</string>
    <key>HOME</key><string>__HOME__</string>
    <key>PORT</key><string>8000</string>
    <key>CLAUDE_BIN</key><string>__CLAUDE_BIN__</string>
    <key>NODE_ENV</key><string>production</string>
    <key>CLAUDE_TIMEOUT_MS</key><string>1800000</string>
    <key>CLAUDE_KEEPALIVE_MS</key><string>30000</string>
    <key>CLAUDE_KEEPALIVE_MAX_SILENCE_MS</key><string>0</string>
    <key>CLAUDE_CODE_PROMPT_CACHE_TTL</key><string>1h</string>
    <key>CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL</key><string>5m</string>
    <key>CLAUDE_CODE_AUTO_COMPACT_WINDOW</key><string>150000</string>
    <key>CLAUDE_SESSION_TTL_MS</key><string>604800000</string>
    <key>DISABLE_AUTOUPDATER</key><string>1</string>
    <key>BASH_MAX_OUTPUT_LENGTH</key><string>8000</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>3</integer>
  <key>StandardOutPath</key><string>__HOME__/Library/Logs/hermes-kit-proxy.log</string>
  <key>StandardErrorPath</key><string>__HOME__/Library/Logs/hermes-kit-proxy.log</string>
</dict>
</plist>
