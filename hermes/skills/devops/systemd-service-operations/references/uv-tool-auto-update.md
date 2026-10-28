# Case study: auto-update timer that never restarted the service

Real incident, Raspberry Pi, Open WebUI installed via `uv tool install` (not Docker, not git).

## Symptom

None visible. The timer fired daily at 03:00, exited `0/SUCCESS` every time, and the log
read `deja a jour: open-webui v0.11.0` day after day. Everything looked healthy.

## Actual problem

The original unit crammed the whole logic into `ExecStart` and compared only the
**open-webui version string**:

```ini
ExecStart=/bin/bash -c 'OLD=$(... uv tool list | grep "open-webui v"); \
  ... uv tool upgrade open-webui; \
  NEW=$(... uv tool list | grep "open-webui v"); \
  if [ "$OLD" != "$NEW" ]; then ... systemctl restart open-webui.service; \
  else echo "$(date) deja a jour: $NEW"; fi'
```

But `uv tool upgrade` bumps **transitive dependencies** nearly every run, even when
open-webui itself is unchanged. Sample from four consecutive days:

```
- starlette==1.3.1      + starlette==1.4.1
- sse-starlette==3.4.6  + sse-starlette==3.4.8
- langsmith==0.10.15    + langsmith==0.10.16
- huggingface-hub==1.26.0 + huggingface-hub==1.26.1
- pydantic-settings==2.14.2 + pydantic-settings==2.15.0
```

The venv on disk moved constantly. The process kept running code loaded at boot.
Measured drift: **service PID had been alive since 7 days earlier**, while dependencies
had changed on every one of those days. A minor `starlette` bump was live on disk and
would only take effect at some unrelated future restart, making any resulting breakage
impossible to attribute.

## Fix

Move logic to `/usr/local/bin/open-webui-update.sh`, keep the unit trivial, and restart on
**any** package add/remove, not just a version-string change. Template:
`templates/uv-tool-update.sh`.

## Parsing uv output correctly

`uv tool upgrade` marks lines three ways:

| Prefix | Meaning |
|--------|---------|
| `- pkg==ver` | removed (old version) |
| `+ pkg==ver` | added (new version) |
| `~ pkg==ver` | present, **not** a change, appears even on no-op runs |

So counting `~` gives false positives. Count only `-` / `+`:

```bash
grep -cE '^[[:space:]]*[-+] [a-zA-Z0-9._-]+=='
```

Verified against real captured output: 4 matches on a changed run, 0 on a no-op run.

## Testing the restart branch (this took two attempts)

**Attempt 1 : failed.** Tried to force a downgrade with:

```bash
uv tool install --force --with soupsieve==2.9.1 open-webui
```

`--with` writes the pin into the tool's *receipt*, so the next `uv tool upgrade` correctly
had nothing to do. The job logged "rien a faire" and the test proved nothing.

**Attempt 2 : worked.** Clear the pin, then downgrade **inside the venv** without touching
the receipt:

```bash
uv tool install --force open-webui                        # drop the --with pin
V=~/.local/share/uv/tools/open-webui
uv pip install --python $V/bin/python soupsieve==2.9.1    # downgrade in-place
```

Now `uv tool upgrade` sees a genuine delta. Result:

```
open-webui v0.11.0 inchangee mais 2 paquets modifies - restart
 - soupsieve==2.9.1
 + soupsieve==2.9.2
restart OK
```

`MainPID` went 1618 → 2059780. That PID change is the proof the fix works.

## Reusable lesson

To force the change-detection branch of any package-manager update job, mutate the
environment **below** the layer the tool inspects. Pinning at the manifest/receipt layer
suppresses the very change you are trying to trigger.
