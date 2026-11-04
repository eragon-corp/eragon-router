# Technical reference

For Gateway administrators and contributors. For setup and daily use, see the [customer guide](../README.md).

## Codex adapter

The Codex adapter uses a custom Responses provider via CLI `-c` overrides. Model setup does not run `codex login`, modify `config.toml` or `auth.json`, or put the key in command arguments. Optional `--memory` setup adds a non-secret MCP registration to `config.toml` through the bridge installer. The model key is exported as `ERAGON_ROUTER_TOKEN` and the provider receives only that environment variable's name. The same key is also exported as `ERAGON_API_KEY` for an already registered Memory bridge, with `ERAGON_GATEWAY_URL` set to the selected Gateway. Codex MCP configuration must allowlist `ERAGON_API_KEY` in `env_vars`; an explicit bridge `--url` must match the selected Gateway. `--no-daemon` keeps authentication in the launched process tree rather than relying on an already-running daemon's environment. Existing Codex sandbox and approval policies remain in effect.

The gateway must implement **`/v1/responses` with SSE streaming, function calls, and tool-result follow-ups**. A Chat Completions-only or Anthropic Messages-only gateway is insufficient; this script does not translate protocols. WebSocket transport and hosted web search are disabled for this adapter; reasoning summaries are set to `none`. A successful launch does not certify model/tool compatibility. See the [official provider configuration](https://learn.chatgpt.com/docs/config-file/config-advanced#custom-model-providers).

Codex screening requires explicit `capabilities.responses` or `supports_responses` (top level, under `capabilities`, or in `model_info`) in addition to the common capabilities to label a model as a candidate. Explicit false excludes it, including conflicting duplicate entries. Missing Responses metadata keeps it unverified. Claude compatibility certificates are ignored for Codex.

Capacity comes from the same catalogue fields and `--context-window` override. Codex accepts a declared limit of at least 4096 tokens, sets `model_context_window`, and compacts at 80% using `model_auto_compact_token_limit` with total-context accounting. Missing capacity produces a warning and a 125K assumption; supply the real limit for smaller models. Explicit `--model` still skips discovery, so configure its capacity explicitly when known:

```bash
bash ~/Downloads/eragon.sh --client codex \
  --endpoint https://gateway.example.com/gw \
  --model example/coder --context-window 64000
```

The Codex adapter does not apply Claude-specific output limits or a fabricated Codex output-limit setting. The selected model and gateway still govern output and reasoning support. Capacity settings help schedule compaction; they cannot prevent every overflow or make a gateway's smaller fallback model accept a larger request. Restart through the launcher after changing model or capacity.

## Pi Agent and OpenCode adapters

The client menu includes **3) Pi Agent** and **4) OpenCode**. Use `--client pi` or `--client opencode` to skip it. Both adapters require a gateway implementing **`/v1/chat/completions` with streaming, tool calls and tool-result follow-ups**. They use Chat Completions even for Claude or GPT model IDs; no protocol is inferred from the name. Metadata alone does not establish wire compatibility.

- Pi loads a small temporary provider extension through `--extension`. The extension registers the selected model from environment-provided JSON, with `contextWindow`, `maxTokens`, text input and thinking disabled. The API key is an environment reference (legacy Pi 0.x syntax, or explicit interpolation for Pi 1.x). Model setup does not modify `models.json` or `auth.json`. Optional Memory setup adds `mcp.json` through the bridge installer. The parent launcher removes the temporary extension on exit, including a failing client; forced `SIGKILL` can leave this non-secret file behind. Pi retains its native compaction settings. The configured minimum is 32K to leave room for Pi's default compaction reserve. The custom model's zero cost metadata means **pricing is unknown**, not free Gateway usage. See [Pi provider registration](https://pi.dev/docs/latest/custom-provider).
- OpenCode receives inline `OPENCODE_CONFIG_CONTENT` with a custom `@ai-sdk/openai-compatible` provider and `{env:ERAGON_ROUTER_TOKEN}` credential reference. It pins the main and small model to the selected model, declares text modalities and context/output limits, and enables compaction with a 20% reserve. Model setup uses inline configuration. Optional Memory setup adds a non-secret MCP entry to the user configuration through the bridge installer; no login file is written. Existing OpenCode settings still merge with inline config, and managed configuration can take precedence. See [OpenCode configuration](https://opencode.ai/docs/config/).

Both adapters inherit the selected key as `ERAGON_API_KEY` for an already configured Memory bridge, alongside the model provider's `ERAGON_ROUTER_TOKEN`. `ERAGON_GATEWAY_URL` follows the selected Gateway; stale Anthropic connection variables are cleared. With `--memory` or interactive opt-in, the bridge installer refreshes the selected client's MCP registration. Without opt-in, existing registrations remain unchanged.

Both adapters accept the common capacity fields or `--context-window`. Missing capacity warns and assumes 125K. Output is capped at the smaller of the declared limit, 8192, or one quarter of the context window. They require an explicit `capabilities.chat_completions` or `supports_chat_completions` (top level, under `capabilities`, or in `model_info`) along with the common capabilities to appear as a candidate. Missing protocol metadata stays unverified; explicit false excludes the model, including conflicts across duplicate IDs. Claude verification records are not used for either client.

The launcher does not install either coding client, call its login command, or add paid inference probes. Optional Memory setup installs the pinned bridge package locally with npm lifecycle scripts disabled. Pi must advertise built-in MCP support. OpenCode 2+ uses `mini --standalone` so its private server inherits the Memory key. Each client retains its normal session storage, logging and tool behavior; the launcher's credential handling does not disable those features. Real Gateway text/tool inference must still be verified separately.

## Fast capability screening

Startup makes **one catalogue request**, not a paid inference request per model. Screening uses that response locally; it never guesses compatibility from a model name.

- **Verified**: an exact record in your optional local compatibility file matches the endpoint SHA-256, model ID, installed Claude Code version, and adapter version.
- **Capabilities declared; not tested**: text input/output, tools and streaming are all explicitly declared. This is a candidate, not a certification.
- **Unverified**: required metadata is missing. Model items omit the `[unverified]` suffix; the list-level notice explains their status. Press `m` to show these models. If every model is unverified, they are displayed with a warning so minimal `/v1/models` endpoints remain usable.
- **Unsupported**: an explicit false for a required capability, text excluded from declared modalities, or a dedicated embedding/image/audio/video/rerank/moderation mode excludes the model. Negative declarations win conflicts, including duplicate model IDs.

Recognized fields include `capabilities.tools`, `capabilities.streaming`, `capabilities.text_input`, `capabilities.text_output`; `supports_function_calling` and `supports_streaming` at the top level, under `capabilities`, or in `model_info`; and `input_modalities` / `output_modalities` arrays at the top level or in `architecture`. `supported_modalities` is also recognized for input. Missing or malformed fields stay unknown. An ID-only catalogue does not supply enough metadata to certify even a Claude model.

Models named `claude-*` use the native profile by default. Other IDs use the basic profile: disable experimental betas, thinking and prompt caching, and select automatic effort. These Claude-specific settings are pinned through CLI settings to override saved project settings. A verified record can select a different profile for a custom alias. These profiles configure the client; they **do not translate protocols**. The gateway must expose Anthropic Messages for the selected model. Metadata alone cannot guarantee that tool execution works.

An explicit `--model` or `ERAGON_MODEL` bypasses catalogue screening and prints an unverified warning unless a matching verification record exists. It still applies the appropriate client profile.

### Claude Code context capacity and early compaction

The launcher reads positive integer `context_length`, `context_window`, and `max_input_tokens` values at the top level or in `model_info`. It uses the smallest declared limit across fields and duplicate routes. `--context-window` / `ERAGON_CONTEXT_WINDOW` can lower that bound; it cannot increase a declared bound. For explicit model IDs, discovery is still skipped, so supply the actual gateway limit yourself:

```bash
bash ~/Downloads/eragon.sh --endpoint https://gateway.example.com/gw \
  --model example/coder --context-window 200000
```

The launcher sets `CLAUDE_CODE_AUTO_COMPACT_WINDOW` to 80% of that limit, capped at 1M, and `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90` to compact earlier where the client supports proactive compaction. It caps most response requests at 8192 output tokens, or a smaller declared `max_output_tokens`. These values are pinned through CLI settings; inherited compaction-disable switches are cleared. This changes compaction timing, not the model's actual capacity. It deliberately does not use `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, whose effect for recognized Claude IDs requires disabling compaction. See the [Claude Code context configuration](https://code.claude.com/docs/en/model-config#context-window-and-auto-compaction).

Without capacity metadata, startup warns and uses a 100K compaction window plus the output cap. This is a conservative fallback, **not proof that the gateway supports that capacity**. The supported auto-compact window starts at 100K; with headroom, declared limits below 125K are refused. Use a larger model for those routes. Missing, stale or inaccurate metadata, a sudden large tool result, or a gateway fallback to a smaller model can still cause an overflow. The launcher makes no extra inference probes.

Use an up-to-date CLI (`claude update`); the launcher requires 2.1.302 or later as its supported baseline. Start a new session after changing model or capacity so the selected model's budget is reapplied. Existing oversized conversations may need a smaller summary in a new session; this cannot retroactively shrink an already rejected request. Capability verification records do not certify context capacity.

### Optional Claude Code compatibility records

The built-in verification list is empty. No model or endpoint is certified merely by installing this script. There are no extra remote manifest downloads, background probes, or on-disk model caches. The launcher remains a single downloadable file.

Copy [compatibility.example.json](../compatibility.example.json) to `compatibility.local.json` and set `ERAGON_COMPATIBILITY_FILE` to its path. The local filename is ignored by Git. After testing a real text stream, tool call, tool-result follow-up, multiple turns and cancellation, add a record like this (all values below are placeholders):

```json
{
  "schema_version": 1,
  "verified": [{
    "endpoint_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "model_id": "example/coder",
    "profile": "basic",
    "adapter_version": 1,
    "claude_code_version": "YOUR_INSTALLED_VERSION",
    "tested_at": "YOUR_TEST_DATE",
    "evidence": "YOUR_TEST_REPORT_PATH_OR_IDENTIFIER"
  }]
}
```

Hash the HTTPS endpoint with trailing slashes removed, **without a newline** (`printf %s "$ERAGON_ENDPOINT" | shasum -a 256`, or `sha256sum` on Linux). Use the first token from `claude --version` as `claude_code_version`. Do not put API keys or real endpoint URLs in records. Both `native` and `basic` profiles are supported. A conflicting pair of profiles is not treated as verified. Invalid schemas fail before catalogue requests.

Records are trusted, operator-maintained test results, not proof generated by the launcher. Rerun certification and remove stale records whenever the gateway configuration or upstream model changes. Hashes keep endpoint literals out of the file; they do not make a known endpoint secret.

## Eragon sign-in

Optional browser sign-in reuses Eragon's existing device authorization, the flow behind `eragon login`. A browser that is already signed in to Eragon approves the machine; the launcher never reads browser cookies. The resulting credential is used only to list the person's own Gateway keys. The server side already ships in Eragon and needs no changes for the launcher.

### Which Eragon

The Eragon address `B` is `--eragon-url`, else `ERAGON_URL` (the variable the `eragon` CLI uses), else the selected Gateway URL with trailing slashes, a trailing `/v1` and a trailing `/gw` removed. An explicit address is only stripped of trailing slashes, as the `eragon` CLI does. `B` must pass the same HTTPS rule as Gateway endpoints, with no extra exceptions. When `B` cannot be resolved, for example for a Gateway URL without `/gw`, the key prompts are exactly as before and `--login` fails with a message naming `--eragon-url`. An invalid explicit `--eragon-url` fails as well; an invalid `ERAGON_URL` only hides the sign-in option, unless `--login` is given.

### Endpoints used

| Request | Purpose |
| --- | --- |
| `POST B/v1/auth/device/start` with `{"label": …}` | Start a sign-in. The label is `eragon-router (<user>@<short-hostname>)`, reduced to printable ASCII and capped at 120 characters. HTTP 429 means too many pending sign-ins from this network. |
| `POST B/v1/auth/device/token` with `{"deviceCode": …}` | Poll every `interval` seconds (5 by default), adding 5 seconds after each `slow_down`. `issued` returns the `ecli_` token; `denied`, `expired` and `unknown` stop with a message. Any other answer, or `expiresIn` elapsing (900 seconds by default), is an error rather than a reason to keep polling. |
| `GET B/v1/me` | Confirm a token and read `userId` and `email`. A new token must pass before anything is stored. A stored token answered with 401 is dropped from the launcher's file; a network error or any other status stops the launch and changes nothing. |
| `GET B/v1/gateway-keys` | List keys. The launcher keeps keys with `createdBy` equal to the `/v1/me` `userId` and no `provisionedBy`, so an organization owner sees only their own keys. Of those, keys with `status` `active` are offered; the rest are counted as hidden. A missing `status` falls back to `revokedAt` and `expiresAt`. |

The launcher never calls `POST /v1/gateway-keys`, which refuses CLI credentials by design, and never creates, edits or revokes keys. With no active keys, it points to `B/ai-gateway/keys` and offers to paste a key instead.

Every field of the key list is optional. Missing or malformed fields drop out of the display, for example the spend. A key is **saved here** when the launcher's saved `esk_` key for the selected Gateway ends with the key's `secretLast4`, and no other of the person's keys, active or not, shares those four characters. Choosing a saved-here key reuses the saved secret. Any other key asks for its secret with hidden input; when `secretLast4` is known, a secret that does not end with it is refused. The chosen key then follows the normal model-list and remember-key flow.

### Storage layout

Sign-ins are stored in the launcher's existing `credentials.json` (directory `700`, file `600`, replaced atomically), in a separate `sign_ins` object keyed by `B`:

```json
{
  "last_endpoint": "https://gateway.example.com/gw",
  "keys": {"https://gateway.example.com/gw": "esk_…"},
  "sign_ins": {
    "https://gateway.example.com": {"token": "ecli_…", "email": "you@example.com", "createdAt": "2026-01-01T00:00:00Z"}
  }
}
```

A file without `sign_ins` loads as before. Releases before 0.2.0 validate only `last_endpoint` and `keys`, so they keep reading files written by this release and preserve `sign_ins` when they save a key; their `--forget-key` deletes the whole file, sign-ins included. In this release, `--forget-key` clears `keys` and `last_endpoint` but keeps valid sign-ins, and still deletes a damaged file entirely. `--logout` removes `sign_ins` entries (all of them, or one for `--eragon-url`, `ERAGON_URL` or `--endpoint`), leaves saved keys alone, and does not contact Eragon: revoking a credential happens in the web app under Settings → Command line.

### Reusing an `eragon` CLI sign-in

Before starting a new sign-in, the launcher tries its own stored sign-in for `B`, then the `eragon` CLI's credential for the same normalized URL, read from `${ERAGON_CREDENTIALS:-${XDG_CONFIG_HOME:-$HOME/.config}/eragon/credentials.json}` (`{"version":1,"credentials":[{"url","token",…}]}`). That file must be a regular file owned by the user. The launcher only reads it: it never writes, locks or copies from it, even when Eragon rejects the token there.

### Security notes

- The `ecli_` token is a personal credential: it can do what the person can do through the Eragon web API, apart from the few actions Eragon reserves for the browser. It is treated more strictly than a Gateway key.
- curl receives the token as an `Authorization` header on stdin (`--header @-`) and request bodies, including the device code, on stdin (`--data-binary @-`). Neither appears in any process's arguments. curl runs with `-q`, `--proto =https` and without following redirects.
- The token is never exported. It is absent from the environment of the launched client, the Memory installer and every helper. It is never printed, and error messages carry only HTTP status codes. Variable names that could hold it are unset at startup, so a same-named variable inherited from the environment cannot export it either.
- Server text (key names, email, user code, sign-in link) is stripped of control, escape and bidirectional formatting characters before printing. Menu lines fit 80 columns.
- The sign-in link is opened in the background with output silenced, using `open` on macOS or `xdg-open` on Linux when `DISPLAY` or `WAYLAND_DISPLAY` is set, and only for `https://` links. `--no-browser` or `ERAGON_NO_BROWSER=1` prints the link and code only. Failing to open a browser is not an error.
- Ctrl-C while waiting for approval exits with status 130 and stores nothing. Hidden prompts restore the terminal on every exit.

## Test

Python 3.9+ and jq are required. Tests use fake executables and fixture credentials in a real terminal; they make no network requests or paid model calls.

```bash
bash -n eragon.sh
python3 -m unittest discover -s tests -v
```

The tests cover hidden input, model selection, invalid input/catalogues, cancellation, terminal restoration, authentication failure, credential handling, and file writes. Sign-in tests (`tests/test_sign_in.py`) answer the Eragon endpoints from fixtures through a fake `curl` that records its arguments, a fake `sleep` that records polling intervals, and fake `open`/`xdg-open` commands. They check that tokens and device codes never appear in any recorded argument or child environment.

Optional checks against locally installed Pi and OpenCode (temporary isolated settings and fixture credentials, configuration loading only):

```bash
python3 tests/check_installed_clients.py
```

## Automatic Memory setup

`--memory` installs the public bridge revision `575d1617d181f2fcaefa91f648dee111a2959cb1` into a local npm prefix under `XDG_DATA_HOME` (default `~/.local/share/eragon-router/memory`). A successful installation records its source revision; matching cached installations skip npm. Package installation runs without Gateway credential environment variables and with `--ignore-scripts --no-audit --no-fund`. Node.js 22.19+ is required; npm is needed on a cache miss.

Registration runs `eragon-context-mcp install --agent <selected-agent> --url <selected-gateway>` without `--model`, preserving the router's provider selection. Only the selected client is changed. The installer manages non-secret MCP entries and backups; the key is supplied through the environment. Claude Code uses its native connection variables, while the other clients receive `ERAGON_API_KEY`. This does not change tool approval policies or grant Memory permissions. Re-run setup when switching Gateways to refresh any explicit MCP URL.

Interactive launches offer setup with Skip as the default. Noninteractive launches skip it unless `--memory` is supplied. Skipping setup leaves existing registrations intact. Install or registration errors stop the launch; successful registration does not prove live Memory permissions or tool execution.

Optional integration check with the pinned package from GitHub (network access and Node/npm required):

```bash
python3 tests/check_memory_setup.py
```

This runs the real installer in temporary directories with fixture client commands and a fixture key, verifies registrations and preserved configuration, then initializes the real MCP server and lists its tools. It does not invoke a model, read Memory, or save Memory.

## CLI packaging

The npm package exposes `eragon-router` directly from the executable `eragon.sh`. There is no JavaScript wrapper, runtime dependency, or npm lifecycle script. Bash retains the current project directory, environment, terminal, signal handling, and client exit status. The standalone download remains supported with the same options and credential storage.

Install from the public GitHub archive as shown in the README. The package name in `package.json` does not imply an npm registry release. Its explicit file allowlist includes only the launcher, customer documentation, compatibility example, and license. Local credentials and tests are not bundled.

Run `npm test` to check the launcher and packaging. When npm is available, the packaging tests create a tarball, install it into a temporary prefix, inspect its contents, and exercise the installed command with isolated fixture clients. They make no Gateway requests. Keep the `--version` value in `eragon.sh` aligned with `package.json`; the package test checks this.
