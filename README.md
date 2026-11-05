# Eragon Router

Connect Claude Code, Codex, Pi Agent, or OpenCode to your model Gateway from one interactive launcher. Choose a client, enter your Gateway URL and API key, and find the model you want to use.

## Get started

You need:

- macOS or Linux with Bash 3.2+, `curl`, and `jq`.
- A Gateway URL and an API key with access to your chosen model, provided by your administrator.
- One of the supported clients installed. You only need the client you plan to use.

| Client | Minimum supported version |
| --- | --- |
| Claude Code | 2.1.302 |
| Codex | 0.160.0 |
| Pi Agent | 0.73.1 |
| OpenCode | 1.3.7 |

1. Install the CLI with npm:

   ```bash
   npm install -g https://github.com/eragon-corp/eragon-router/archive/refs/heads/main.tar.gz
   ```

   This installs directly from the public GitHub repository. No npm registry release is required. Node.js and npm are needed for this installation method; the router itself runs in Bash.

2. Open a terminal in your project folder and run:

   ```bash
   eragon-router
   ```

Check the installed version with `eragon-router --version`. To update, run the same installation command again. To uninstall, run `npm uninstall -g eragon-router`; saved credentials and optional Memory registrations remain until you remove them separately.

### Standalone script

If you prefer to avoid npm, download and run the same launcher directly:

```bash
mkdir -p "$HOME/Downloads"
curl -fsSL https://raw.githubusercontent.com/eragon-corp/eragon-router/main/eragon.sh \
  -o "$HOME/Downloads/eragon.sh"
bash ~/Downloads/eragon.sh
```

Both entry points accept the same options and use the same saved settings.

The launcher guides you through these steps:

1. **Enter your Gateway URL.** Use the HTTPS base URL supplied by your administrator. No Gateway address is built in.
2. **Choose a client.** Select Claude Code, Codex, Pi Agent, or OpenCode.
3. **Enter your API key.** Input is hidden, so nothing appears as you type or paste. With an Eragon Gateway, you can instead [sign in with your browser](#sign-in-to-choose-a-key) and choose one of your keys, or create one for this machine.
4. **Choose a model.** Enter a number, or type `/keyword` to search.
5. **Choose whether to remember your key.** Enter `y` to save it locally, or press Enter to use it for this run only. A key created for this machine during sign-in is the exception: Enter saves it, because Eragon cannot show its secret again.
6. **Set up Eragon Memory (optional).** Choose `2` to automatically install the Memory bridge and connect it to this client, or press Enter to skip setup.

Your selected client then opens in your current project folder.

## Next time you run it

Run the same command:

```bash
eragon-router
```

If you remembered credentials, press Enter at the Gateway prompt to reuse the saved address. After choosing a client, you can use the saved key or update it:

```text
API key saved for this Gateway:
  1) Use saved key
  2) Update saved key
  3) Choose from your Eragon keys (sign in with your browser)
  q) Quit
Key action [1]:
```

Press Enter to continue with the saved key. Choose `2` to enter a replacement. Updates apply only to the selected Gateway; other saved Gateways keep their own keys. Cancelling or failing to load the model list preserves the old key. Option `3` appears only for an Eragon Gateway; see [Sign in to choose a key](#sign-in-to-choose-a-key).

To use a different Gateway, enter its URL at the first prompt. A key saved for another Gateway is not automatically reused.

## Find a model

The model menu shows models available through your Gateway and key. Models that explicitly declare incompatible capabilities are excluded.

| Input | Action |
| --- | --- |
| A model number | Select that model from the current results |
| Enter | Select the first displayed model |
| `/keyword` | Search model IDs, ignoring letter case |
| `/` | Clear the search |
| `m` | Show all usable models, including unverified entries |

For example, enter `/sonnet` to find IDs containing `sonnet`. Search runs locally and does not send additional requests to the Gateway.

Models with incomplete compatibility information appear without a status label. A model marked **capabilities declared; not tested** has the required metadata but has not been tested by the launcher. A displayed model is not a guarantee that every client feature will work. Ask your administrator which models are supported for your client.

## Manage your API key

Saving is optional. Remembered Gateway URLs and keys are stored in a **local plaintext file**:

```text
~/.config/eragon-router/credentials.json
```

If `XDG_CONFIG_HOME` is set, the file is stored under that directory instead. The launcher sets the directory permissions to `700` and the file permissions to `600`, limiting access to your user account. This is not encrypted storage; anyone with sufficient local privileges can read it.

You can update a saved key from the interactive menu, or go directly to the replacement flow:

```bash
eragon-router --update-key
```

To remove **all** remembered Gateway credentials:

```bash
eragon-router --forget-key
```

This keeps any stored Eragon sign-in; use `--logout` to forget that.

Keys are not displayed or placed in command arguments. Do not paste a key into a terminal command, commit it to a repository, or include it in a support request.

## Sign in to choose a key

If your Gateway belongs to Eragon (its URL ends in `/gw`), you can sign in with a browser where you already use Eragon, then choose one of your own Gateway keys, or create a new one for this machine without copying its secret:

```bash
eragon-router --login
```

You can also pick **Choose from your Eragon keys (sign in with your browser)** in the key menu. Pressing Enter there still uses your saved key, or asks you to paste one, as before.

1. **Approve this machine.** The launcher prints a link and a code, and opens the link in your browser:

   ```text
   Open  https://your-eragon.example.com/cli?code=ABCD-EFGH
   Code  ABCD-EFGH

   Approve "eragon-router (you@your-laptop)" in your browser. Waiting… (Ctrl-C to cancel)
   ```

   Check that the code matches, then approve. If the browser is not signed in to Eragon, the web app asks you to sign in first. The code expires after about 15 minutes. This is the same approval as `eragon login`; the launcher never reads your browser's cookies.

   If no key is saved for this Gateway, the approval page also offers to **create a Gateway key for this machine**, turned on. Choose the key's name, model access, budget and expiry as on the Keys page, then approve. The launcher receives the key, prints `Created <name> …<last4> for this machine.`, and skips steps 2 and 3. Turn the option off to approve the sign-in only. If you may not create Gateway keys, the page says why and offers the sign-in only.
2. **Choose a key.** The launcher lists the Gateway keys you created that are still active. Each entry shows the key's name, the last four characters of its secret, its model access, spend and budget, and when it was last used. Keys created by other people, keys provisioned by a partner, and expired or revoked keys are not listed; the launcher prints how many of your own keys it hid. Choose `n` to create a new key for this machine instead (see below).
3. **Provide the secret.** A key marked **saved here** uses the key this launcher already saved for this Gateway. For any other key, paste its secret when asked. Input is hidden, and the launcher refuses a secret that does not end with the four characters shown. Eragon's key list never includes secrets, so use the secret you kept when you created the key.

The model menu and the remember prompt then work as usual. If you have no active keys, the launcher offers to create one:

```text
You have no active Gateway keys.
  1) Create a key for this machine (approve in your browser)
  2) Paste a key
  q) Quit
Key action [1]:
```

On a remote or headless machine, add `--no-browser` (or set `ERAGON_NO_BROWSER=1`) and open the printed link on any device where you can sign in to Eragon.

The launcher finds your Eragon address by removing `/gw` from the Gateway URL. If your Gateway URL does not end in `/gw`, pass the address with `--eragon-url https://your-eragon.example.com`, or set `ERAGON_URL`.

### Create a key for this machine

A new sign-in asks for a key for this machine when none is saved for this Gateway, as step 1 describes. Once you are signed in, choosing `n` in the key list, or `1` when you have no active keys, asks Eragon for a key without a new sign-in, and keeps your sign-in as it is. The launcher prints a new link and code:

```text
Open  https://your-eragon.example.com/cli?code=WXYZ-2345
Code  WXYZ-2345

Approve and create the key in your browser. Waiting… (Ctrl-C to cancel)
```

In the browser, check the code, choose the key's settings, and approve. Only a person at the browser can create the key, with the same permissions and limits as the Keys page. The launcher only asks: it never creates, edits or revokes a key itself. If you may not create Gateway keys, the approval page says why, and you can only deny the request.

Either way, the key goes straight to this machine, exactly once, and is used like a pasted key: hidden, never placed in command arguments, and never printed. After the model menu the launcher asks:

```text
Eragon cannot show this key's secret again. Saving uses an owner-only plaintext file.
Save this key on this machine? [Y/n]:
```

Press Enter to save it, or enter `n` to use it for this run only. Every other key keeps the `[y/N]` prompt.

Each key created this way appears on the Keys page in the web app, at `https://your-eragon.example.com/ai-gateway/keys` (your own Eragon address), under the name you chose. Revoke it there when you no longer need it, for example when you retire the machine.

An Eragon server without this feature still signs you in, and then lists your keys as before. Choosing to create a key there prints `This Eragon cannot create keys during sign-in yet.` with the Keys page address: create a key in the web app, then paste it.

### What the sign-in stores

After you approve, the launcher stores an Eragon CLI credential for that Eragon address, with your email address and the time you signed in. It goes into the same local file as saved keys, `~/.config/eragon-router/credentials.json`. Like saved keys, it is **plaintext**, protected only by owner-only permissions (`600` for the file, `700` for its directory). It is not encrypted.

This credential acts as you. It can do what you can do through the Eragon web API, apart from a few actions Eragon reserves for the browser, such as approving devices and creating Gateway keys. The launcher uses it only to read your profile and list your keys, but anyone who can read the file could use it for more. Treat the file like a password. The credential is never placed in command arguments or passed to the client you launch. Creating a key for this machine does not use it: that request is approved in the browser, like the sign-in itself.

Next time, the launcher reuses the stored sign-in while Eragon still accepts it, and starts a new sign-in when it does not. If you already signed in to the same Eragon with the `eragon` command-line tool, the launcher can reuse that sign-in too. It reads that tool's file and never changes it.

To forget the stored sign-ins on this machine:

```bash
eragon-router --logout
```

`--logout` forgets every stored sign-in, or only one when `--eragon-url`, `ERAGON_URL` or `--endpoint` names an Eragon. It deletes the local copy only: the machine stays listed in Eragon, and the credential remains valid, until you revoke it in the web app under **Settings → Command line**. Saved Gateway keys and the `eragon` tool's own sign-in are left alone. `--forget-key` still removes saved Gateway keys only.

## Connect Eragon Memory

The launcher can install and connect [Eragon Context MCP](https://github.com/eragon-corp/eragon-context-mcp) for your selected client. At the Memory prompt, choose `2`:

```text
Set up Eragon Memory? Requires an Eragon Gateway with Memory access.
  1) Skip setup (default)
  2) Install or reconnect Memory
Memory setup [1]:
```

Or request automatic setup directly:

```bash
eragon-router --memory
```

Memory setup requires **Node.js 22.19+ and npm**, an Eragon Gateway, and a personal key with the required Memory permissions. Pi also needs built-in MCP support; update Pi if the launcher reports it is missing. Installing the bridge does not grant additional access to your key.

The launcher downloads a pinned bridge version into `${XDG_DATA_HOME:-$HOME/.local/share}/eragon-router/memory`, reuses that installation on later runs, and registers it only with the selected client. It does not require a global npm install. Reconnecting updates that client's Memory registration to the selected Gateway. If installation or registration fails, the launcher stops with an error instead of starting a client with incomplete setup.

Setup writes a **persistent MCP registration without your API key**. Other client configuration is preserved; the bridge installer keeps backups of configuration files it writes directly. The model provider remains configured by the router. Start future sessions through the router so the cached bridge is on PATH and receives the selected key. Choosing “Skip setup” does not remove or disable a previously registered Memory connection.

Codex, Pi, and OpenCode receive the same selected key as `ERAGON_API_KEY`; Claude Code's bridge uses its `ANTHROPIC_AUTH_TOKEN`. Saved-key updates take effect on the next launch. The launcher sends no test inference or Memory save request during setup.

Try this in the client after setup:

```text
What do you know about how I like to work? Cite any Eragon memories you rely on, and say so if there are none.
```

## Optional shortcuts

Choose a client without the client menu:

```bash
eragon-router --client codex
```

The available client names are `claude`, `codex`, `pi`, and `opencode`.

Start with a model search already applied:

```bash
eragon-router --search sonnet
```

If your administrator supplied an exact model ID, use it directly:

```bash
eragon-router --model example/coder
```

Replace `example/coder` with your actual model ID. This skips the model list and compatibility screening. If the model has a known context limit, add `--context-window TOKENS` using the value supplied by your administrator.

Use `--endpoint URL` to skip the Gateway prompt. Supply the HTTPS base URL without `/v1`; Codex, Pi, and OpenCode also accept a trailing `/v1`.

For scripts and secret-manager integrations, the launcher accepts `ERAGON_CLIENT`, `ERAGON_ENDPOINT`, `ERAGON_MODEL`, `ERAGON_API_KEY`, and `ERAGON_CONTEXT_WINDOW`. Command-line options override matching environment settings; an environment key overrides a saved key. Noninteractive launches require an explicit endpoint, model, and an environment or matching saved key. Browser sign-in also reads `ERAGON_URL` and `ERAGON_NO_BROWSER`; `--login` needs an interactive terminal and replaces an environment key for that launch.

See all options with:

```bash
eragon-router --help
```

## Troubleshooting

| Message or issue | What to do |
| --- | --- |
| `Missing jq`, `Missing curl`, or a missing client | Install the named tool, then run the launcher again. |
| A client version warning | Update that client. Check which installation your terminal finds if you have multiple versions. |
| `Could not load models` or a TLS connection error | Check the Gateway URL, network access, and key permissions. Use the real URL supplied by your administrator. |
| A model is missing | Try `/keyword` or `m`. Ask your administrator whether your key has access and whether the model supports your client. |
| Your Gateway does not offer a model list | Use `--model` with the exact ID supplied by your administrator. |
| `Your input exceeds the context window` | Start a fresh session with a shorter summary, or select a model with a larger supported context. If the displayed capacity is wrong, ask your administrator for the actual limit and use `--context-window`. |
| The client starts but requests or tool calls fail | Confirm that the Gateway supports the selected client's API and that the key can use the selected model. |
| `Declined in the browser. Nothing was stored.` | The sign-in or key request was denied in the browser. Run `eragon-router --login` again and approve it, after checking that the code matches. If you may not create Gateway keys, a key request can only be denied: paste a key instead, or ask an organization owner. |
| `The code expired before it was approved.` | Approve within about 15 minutes of starting. Run `eragon-router --login` again for a new code. |
| `Your saved sign-in to … is no longer accepted.` | The sign-in was revoked, or your organization no longer allows the way you signed in. The launcher forgets it and starts a new sign-in. |
| `Cannot tell which Eragon serves this Gateway` | Your Gateway URL does not end in `/gw`. Pass `--eragon-url https://your-eragon.example.com`, or set `ERAGON_URL`. |
| `You have no active Gateway keys.` | Press Enter to create a key for this machine and approve it in your browser, or choose `2` to paste a key. |
| `This Eragon cannot create keys during sign-in yet.` | Your Eragon server does not support creating keys from the launcher yet. Create a key in the web app at the address shown, then paste it. |
| `Unexpected key from …` | Eragon sent a key the launcher could not check, so it used and stored nothing, not even the sign-in. Revoke the new key on the Keys page at the address shown, then try again. |

The Gateway must support Anthropic Messages for Claude Code, Responses for Codex, or Chat Completions for Pi and OpenCode, including streaming and tool calls. Eragon Router configures the client; it does not translate between these APIs. Model availability, usage charges, and access permissions are managed by your Gateway. Pi may display a zero cost estimate for custom models; Gateway usage can still be billed.

## Privacy

Your chosen client sends the conversation and any project context it uses to your configured Gateway. Eragon Router does not add telemetry or change the client's own session storage, logging, or data policies. It does not modify the client's persistent login files. Optional Memory setup writes the MCP registration described above. Optional browser sign-in contacts your Eragon address only to sign in, read your profile, list your Gateway keys, and receive a key you approve for this machine.

When requesting support, share the client name, version, and error message. Remove API keys and sensitive project content first.

For Gateway configuration, capacity handling, compatibility records, and contributor tests, see the [technical reference](docs/technical-reference.md).
