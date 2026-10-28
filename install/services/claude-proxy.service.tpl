[Unit]
Description=Claude proxy local (hermes-kit) : API Anthropic sur le port 8000 via Claude Code
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=__PROXY_DIR__
ExecStart=__NODE__ __PROXY_DIR__/server.js
Environment=PATH=__PATH__
Environment=HOME=__HOME__
Environment=PORT=8000
Environment=CLAUDE_BIN=__CLAUDE_BIN__
Environment=NODE_ENV=production
Environment=CLAUDE_TIMEOUT_MS=1800000
Environment=CLAUDE_KEEPALIVE_MS=30000
Environment=CLAUDE_KEEPALIVE_MAX_SILENCE_MS=0
Environment=CLAUDE_CODE_PROMPT_CACHE_TTL=1h
Environment=CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=5m
Environment=CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000
Environment=CLAUDE_SESSION_TTL_MS=604800000
Environment=DISABLE_AUTOUPDATER=1
Environment=BASH_MAX_OUTPUT_LENGTH=8000
UnsetEnvironment=ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_TOKEN
Restart=always
RestartSec=3
KillMode=process
KillSignal=SIGTERM
TimeoutStopSec=20

[Install]
WantedBy=default.target
