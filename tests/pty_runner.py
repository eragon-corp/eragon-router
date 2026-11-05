# Test fixtures only. No real credentials or network requests.

import os, sys, json, tempfile, pathlib, pty, select, time, termios, subprocess, shutil, shlex
request = json.load(sys.stdin)
REAL_JQ = shutil.which('jq')
assert REAL_JQ, 'jq is required to run the launcher tests'
# The Gateway key the fixture clients expect; sign-in tests use an esk_ key.
KEY = request.get('fixtureKey', 'fixture-secret')
with tempfile.TemporaryDirectory() as directory:
    root = pathlib.Path(directory)
    (root / "eragon.sh").write_text(request["script"])
    log = root / "log"
    log.mkdir()
    curl = root / "curl"
    curl.write_text(r"""#!/usr/bin/env python3
import os, sys, json, pathlib
log = pathlib.Path(os.environ['FIXTURE_LOG'])
args = sys.argv[1:]
url = args[args.index('--url') + 1]
stdin = sys.stdin.read()
with open(log / 'curl.jsonl', 'a') as record:
    record.write(json.dumps({'argv': sys.argv, 'url': url, 'post': '--data-binary' in args}) + '\n')
assert all('fixture-secret' not in arg for arg in sys.argv)
# Sign-in tokens (ecli_) and device codes (edc_) never travel as arguments.
assert all('ecli_' not in arg and 'edc_' not in arg for arg in sys.argv), 'sign-in secret in curl arguments'
assert all('ecli_' not in value and 'edc_' not in value for value in os.environ.values()), 'sign-in secret in curl environment'
assert all('fixture-secret' not in value for value in os.environ.values()), 'Gateway key in curl environment'
assert sys.argv[1] == '-q'
assert '--location' not in sys.argv and '-L' not in sys.argv
assert args[args.index('--proto') + 1] == '=https'
assert 'eragon_key' not in os.environ
assert 'ERAGON_API_KEY' not in os.environ
if url.endswith('/v1/models'):
    assert os.environ.get('EXPECT_NO_CATALOGUE') != '1'
    assert url == os.environ['EXPECTED_ENDPOINT'] + '/v1/models'
    assert stdin == 'Authorization: Bearer fixture-secret\n'
    if os.environ.get('CURL_FAIL') == '1': sys.exit(22)
    print('FIXTURE_CATALOGUE_REQUEST', file=sys.stderr)
    print(os.environ['MODEL_RESPONSE'])
    sys.exit(0)
# Eragon sign-in endpoints, answered from the request's "eragon" fixture.
assert os.environ.get('FIXTURE_ERAGON'), 'unexpected request to ' + url
eragon = json.loads(pathlib.Path(os.environ['FIXTURE_ERAGON']).read_text())
base = os.environ['EXPECTED_ERAGON_URL']
assert url.startswith(base + '/v1/'), url
path = url[len(base):]
post = '--data-binary' in args
write_out = args[args.index('--write-out') + 1]
def answer(entry):
    if entry.get('network'):
        print('curl: (7) Failed to connect (fixture)', file=sys.stderr); sys.exit(7)
    body = entry.get('body', '')
    sys.stdout.write(body if isinstance(body, str) else json.dumps(body))
    sys.stdout.write(write_out.replace('\\n', '\n').replace('%{http_code}', str(entry.get('code', 200))))
    sys.exit(0)
def bearer():
    assert stdin.startswith('Authorization: Bearer ') and stdin.count('\n') == 1 and stdin.endswith('\n'), 'token must arrive as one header on stdin'
    return stdin[len('Authorization: Bearer '):-1]
if path == '/v1/auth/device/start':
    assert post and args[args.index('--data-binary') + 1] == '@-'
    started = json.loads(stdin)
    label = started['label']
    assert label.startswith('eragon-router (') and label.isascii() and label.isprintable() and len(label) <= 120, label
    # Only the contract's fields: gatewayKey:true asks for a key, and signIn:false
    # (a key alone, no sign-in) is only ever sent with it.
    assert set(started) <= {'label', 'gatewayKey', 'signIn'}, started
    assert started.get('gatewayKey', True) is True and started.get('signIn', False) is False, started
    assert 'signIn' not in started or 'gatewayKey' in started, started
    with open(log / 'labels', 'a') as record: record.write(label + '\n')
    with open(log / 'starts', 'a') as record: record.write(json.dumps(started) + '\n')
    # One answer per start, in order ("starts"), or the same one each time ("start").
    counter = log / 'start-count'
    index = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(index + 1))
    starts = eragon['starts'] if 'starts' in eragon else [eragon['start']]
    entry = starts[min(index, len(starts) - 1)]
    body = entry.get('body')
    (log / 'device-code').write_text(body['deviceCode'] if isinstance(body, dict) and 'deviceCode' in body else '')
    answer(entry)
if path == '/v1/auth/device/token':
    assert post and args[args.index('--data-binary') + 1] == '@-'
    assert json.loads(stdin) == {'deviceCode': (log / 'device-code').read_text()}
    counter = log / 'polls'
    index = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(index + 1))
    polls = eragon.get('polls', [])
    answer(polls[index] if index < len(polls) else {'code': 500, 'body': {'error': 'fixture exhausted'}})
if path == '/v1/me':
    assert not post
    answer(eragon.get('me', {}).get(bearer(), {'code': 401, 'body': {'error': 'unauthorized'}}))
if path == '/v1/gateway-keys':
    assert not post, 'the router must never create Gateway keys'
    assert bearer() in eragon.get('me', {}), 'keys listed with an unconfirmed sign-in'
    answer(eragon.get('keys', {'body': []}))
raise AssertionError('unexpected request to ' + url)
""")
    # Polling waits are recorded, and skipped unless a test needs real time.
    sleep = root / "sleep"
    sleep.write_text('#!/bin/sh\nprintf \'%s\\n\' "$1" >> "$FIXTURE_LOG/sleeps"\n'
                     'if [ "${FIXTURE_REAL_SLEEP:-0}" = 1 ]; then exec /bin/sleep "$1"; fi\n')
    # Never open a real browser: record what would have been opened.
    for opener in ["open", "xdg-open"]:
        (root / opener).write_text('#!/bin/sh\nprintf \'%s %s\\n\' "${0##*/}" "$*" >> "$FIXTURE_LOG/opened"\n')
    # The real jq, behind a guard: a Gateway key, sign-in token or device code
    # passed as a jq argument is recorded, and the run then fails, even where
    # the launcher ignores jq's exit status.
    jq = root / "jq"
    jq.write_text('#!/bin/sh\ncase "$*" in *fixture-secret*|*ecli_fixture*|*edc_fixture*)\n'
                  '  printf \'%s\\n\' "$*" >> "$FIXTURE_LOG/jq-argv-secrets" ;;\nesac\n'
                  'exec ' + shlex.quote(REAL_JQ) + ' "$@"\n')
    claude = root / "claude"
    claude.write_text("""#!/usr/bin/env python3
import os, sys, json
if sys.argv[1:] == ['--version']:
    print(os.environ.get('FIXTURE_CLAUDE_VERSION', '2.1.302')); sys.exit(0)
assert os.environ['ANTHROPIC_AUTH_TOKEN'] == 'fixture-secret'
assert 'ANTHROPIC_API_KEY' not in os.environ
assert 'ERAGON_API_KEY' not in os.environ
assert 'eragon_key' not in os.environ
assert 'ERAGON_API_KEY' not in os.environ
assert sys.argv[3] == '--settings'
settings = json.loads(sys.argv[4])
expected = {'ANTHROPIC_BASE_URL': os.environ['EXPECTED_ENDPOINT']}
profile = os.environ.get('EXPECTED_PROFILE') or ('native' if sys.argv[2].startswith('claude-') else 'basic')
compat = {'CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS': '1', 'CLAUDE_CODE_DISABLE_THINKING': '1',
          'CLAUDE_CODE_EFFORT_LEVEL': 'auto', 'DISABLE_PROMPT_CACHING': '1'}
if profile == 'basic':
    expected.update(compat)
    for name, value in compat.items(): assert os.environ.get(name) == value
else:
    for name in compat: assert name not in os.environ
capacity = {'CLAUDE_CODE_AUTO_COMPACT_WINDOW': os.environ['CLAUDE_CODE_AUTO_COMPACT_WINDOW'],
            'CLAUDE_CODE_MAX_OUTPUT_TOKENS': os.environ['CLAUDE_CODE_MAX_OUTPUT_TOKENS'],
            'CLAUDE_AUTOCOMPACT_PCT_OVERRIDE': '90', 'DISABLE_COMPACT': '', 'DISABLE_AUTO_COMPACT': ''}
expected.update(capacity)
assert settings == {'env': expected}
assert 'DISABLE_COMPACT' not in os.environ
assert 'DISABLE_AUTO_COMPACT' not in os.environ
print('CAPACITY ' + json.dumps(capacity))
assert all('fixture-secret' not in arg for arg in sys.argv)
print('LAUNCHED ' + json.dumps({'model': sys.argv[2], 'url': settings['env']['ANTHROPIC_BASE_URL']}))
""")
    codex = root / "codex"
    codex.write_text("""#!/usr/bin/env python3
import os, sys, json
if sys.argv[1:] == ['--version']:
    print(os.environ.get('FIXTURE_CODEX_VERSION', 'codex-cli 0.160.0')); sys.exit(0)
assert os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'
assert os.environ['ERAGON_API_KEY'] == os.environ['ERAGON_ROUTER_TOKEN']
assert os.environ['ERAGON_GATEWAY_URL'] == os.environ['EXPECTED_ENDPOINT']
for key in ['eragon_key', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY']:
    assert key not in os.environ, key
assert all('fixture-secret' not in arg for arg in sys.argv)
assert sys.argv[1] == '--no-daemon' and sys.argv[2] == '--model'
assert all(sys.argv[i] == '-c' for i in range(4,len(sys.argv),2))
values = dict(arg.split('=', 1) for arg in sys.argv[5::2])
assert values['model_provider'] == '\"eragon_router\"'
provider = values['model_providers.eragon_router']
assert 'base_url=\"' + os.environ['EXPECTED_ENDPOINT'] + '/v1\"' in provider
assert 'env_key=\"ERAGON_ROUTER_TOKEN\"' in provider
assert 'wire_api=\"responses\"' in provider
assert 'requires_openai_auth=false' in provider
assert 'supports_websockets=false' in provider
assert 'fixture-secret' not in provider
assert values['web_search'] == '\"disabled\"'
assert values['model_auto_compact_token_limit_scope'] == '\"total\"'
context = int(values['model_context_window'])
assert int(values['model_auto_compact_token_limit']) == context // 5 * 4
print('CODEX_LAUNCHED ' + json.dumps({'model': sys.argv[3], 'context': context, 'config': values}))
""")
    pi = root / "pi"
    pi.write_text("""#!/usr/bin/env python3
import os, sys, json, pathlib
if sys.argv[1:] == ['--version']:
    print(os.environ.get('FIXTURE_PI_VERSION', '0.73.1'), file=sys.stderr); sys.exit(0)
if sys.argv[1:] == ['--help']:
    print('--no-mcp' if os.environ.get('FIXTURE_PI_MCP', '1') == '1' else 'no MCP support'); sys.exit(0)
assert os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'
assert os.environ['ERAGON_API_KEY'] == os.environ['ERAGON_ROUTER_TOKEN']
assert os.environ['ERAGON_GATEWAY_URL'] == os.environ['EXPECTED_ENDPOINT']
for name in ['eragon_key','ANTHROPIC_BASE_URL','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_API_KEY','OPENAI_API_KEY']:
    assert name not in os.environ, name
assert all('fixture-secret' not in arg for arg in sys.argv)
assert sys.argv[1] == '--extension' and sys.argv[3:5] == ['--provider','eragon_router']
source = pathlib.Path(sys.argv[2]).read_text()
assert 'fixture-secret' not in source and 'registerProvider' in source
assert 'process.env.ERAGON_ROUTER_PI_CONFIG' in source
config = json.loads(os.environ['ERAGON_ROUTER_PI_CONFIG'])
assert 'fixture-secret' not in json.dumps(config)
assert config['baseUrl'] == os.environ['EXPECTED_ENDPOINT'] + '/v1'
assert config['api'] == 'openai-completions'
assert config['apiKey'] == ('$ERAGON_ROUTER_TOKEN' if int(os.environ.get('FIXTURE_PI_VERSION','0.73.1').split('.')[0]) >= 1 else 'ERAGON_ROUTER_TOKEN')
assert config['models'][0]['id'] == sys.argv[6]
assert sys.argv[7:] == ['--thinking', 'off']
print('PI_LAUNCHED ' + json.dumps(config))
sys.exit(int(os.environ.get('FIXTURE_PI_EXIT', '0')))
""")
    opencode = root / "opencode"
    opencode.write_text("""#!/usr/bin/env python3
import os, sys, json
if sys.argv[1:] == ['--version']:
    print(os.environ.get('FIXTURE_OPENCODE_VERSION', '1.3.7')); sys.exit(0)
if int(os.environ.get('FIXTURE_OPENCODE_VERSION','1.3.7').split('.')[0]) >= 2:
    assert sys.argv[1:3] == ['mini', '--standalone']
    sys.argv = [sys.argv[0]] + sys.argv[3:]
assert os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'
assert os.environ['ERAGON_API_KEY'] == os.environ['ERAGON_ROUTER_TOKEN']
assert os.environ['ERAGON_GATEWAY_URL'] == os.environ['EXPECTED_ENDPOINT']
for name in ['eragon_key','ANTHROPIC_BASE_URL','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_API_KEY','OPENAI_API_KEY']:
    assert name not in os.environ, name
assert all('fixture-secret' not in arg for arg in sys.argv)
config = json.loads(os.environ['OPENCODE_CONFIG_CONTENT'])
assert 'fixture-secret' not in json.dumps(config)
assert sys.argv[1] == '--model' and sys.argv[2] == config['model'] == config['small_model']
p = config['provider']['eragon_router']
assert p['npm'] == '@ai-sdk/openai-compatible'
assert p['options'] == {'baseURL':os.environ['EXPECTED_ENDPOINT'] + '/v1','apiKey':'{env:ERAGON_ROUTER_TOKEN}'}
model = p['models'][sys.argv[2].split('/',1)[1]]
assert model['limit']['output'] <= model['limit']['context'] // 4
assert config['compaction']['auto'] is True
assert config['compaction']['reserved'] == model['limit']['context'] - model['limit']['context'] // 5 * 4
print('OPENCODE_LAUNCHED ' + json.dumps(config))
""")
    for client_path in [claude, codex, pi, opencode]:
        source = client_path.read_text()
        check = """
if os.environ.get('EXPECT_MEMORY_ON_PATH') == '1':
    import shutil, pathlib
    assert shutil.which('eragon-context-mcp') == str(pathlib.Path(os.environ['XDG_DATA_HOME']) / 'eragon-router' / 'memory' / 'node_modules' / '.bin' / 'eragon-context-mcp')
assert not any('ecli_' in value or 'edc_' in value for value in os.environ.values()), 'sign-in secret in client environment'
"""
        marker = "assert os.environ['ANTHROPIC_AUTH_TOKEN'] == 'fixture-secret'" if client_path == claude else "assert os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'"
        client_path.write_text(source.replace(marker, check + marker, 1))
    node = root / 'node'
    node.write_text("#!/usr/bin/env python3\nimport os\nprint(os.environ.get('FIXTURE_NODE_VERSION', 'v22.23.2'))\n")
    bridge_installer = root / 'bridge-installer.py'
    bridge_installer.write_text("""#!/usr/bin/env python3
import os, sys, json, pathlib
assert sys.argv[1:3] == ['install','--agent'] and sys.argv[4] == '--url'
assert len(sys.argv) == 6 and sys.argv[3] in ['claude-code','codex','pi','opencode']
assert sys.argv[5] == os.environ['EXPECTED_ENDPOINT']
assert all('fixture-secret' not in arg for arg in sys.argv)
assert 'eragon_key' not in os.environ
assert not any('ecli_' in value or 'edc_' in value for value in os.environ.values())
if sys.argv[3] == 'claude-code':
    assert os.environ['ANTHROPIC_AUTH_TOKEN'] == 'fixture-secret'
    assert 'ERAGON_API_KEY' not in os.environ
else:
    assert os.environ['ERAGON_API_KEY'] == 'fixture-secret'
    assert 'ANTHROPIC_AUTH_TOKEN' not in os.environ
if os.environ.get('FIXTURE_REGISTER_FAIL') == '1': sys.exit(1)
p = pathlib.Path(os.environ['XDG_CONFIG_HOME']) / 'memory-registration.json'
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({'agent':sys.argv[3], 'url':sys.argv[5], 'command':'eragon-context-mcp'}))
print('FIXTURE_MEMORY_REGISTERED')
""")
    npm = root / 'npm'
    npm.write_text("""#!/usr/bin/env python3
import os, sys, pathlib, shutil
assert sys.argv[1:3] == ['install','--prefix']
assert '--ignore-scripts' in sys.argv and '--no-audit' in sys.argv and '--no-fund' in sys.argv
assert sys.argv[-1] == 'https://github.com/eragon-corp/eragon-context-mcp/archive/575d1617d181f2fcaefa91f648dee111a2959cb1.tar.gz'
for name in ['ERAGON_API_KEY','ERAGON_ROUTER_TOKEN','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_API_KEY','OPENAI_API_KEY','eragon_key']:
    assert name not in os.environ, name
assert not any('ecli_' in value or 'edc_' in value for value in os.environ.values())
assert all('fixture-secret' not in arg for arg in sys.argv)
if os.environ.get('FIXTURE_NPM_FAIL') == '1': sys.exit(1)
p = pathlib.Path(sys.argv[3]) / 'node_modules' / '.bin' / 'eragon-context-mcp'
p.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(pathlib.Path(__file__).with_name('bridge-installer.py'), p)
p.chmod(0o700)
print('FIXTURE_MEMORY_INSTALLED')
""")
    node.chmod(0o700); npm.chmod(0o700)
    memory_bridge = root / 'memory-bridge.py'
    memory_bridge.write_text("import os, sys\nassert os.environ['ERAGON_API_KEY'] == 'fixture-secret'\nassert sys.argv[1] == '--url'\nassert sys.argv[2] == " + repr(request.get('expectedEndpoint', 'https://gateway.example.com/gw')) + "\nassert 'ANTHROPIC_BASE_URL' not in os.environ\nprint('MEMORY_CHILD_AUTH_MATCHED')\n")
    for client_path in [codex, pi, opencode]:
        source = client_path.read_text()
        # Exercise a real subprocess; Codex forwards only the installed bridge's
        # env_vars allowlist, while the Gateway URL is an explicit --url argument.
        check = """
if os.environ.get('CHECK_MEMORY_CHILD') == '1':
    import subprocess, pathlib
    child_env = ({'ERAGON_API_KEY':os.environ['ERAGON_API_KEY']} if pathlib.Path(__file__).name == 'codex' else dict(os.environ))
    subprocess.run([sys.executable, str(pathlib.Path(__file__).with_name('memory-bridge.py')),
                    '--url', os.environ['ERAGON_GATEWAY_URL']], env=child_env, check=True)
"""
        source = source.replace("assert os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'", "assert os.environ['ERAGON_ROUTER_TOKEN'] == 'fixture-secret'\n" + check, 1)
        client_path.write_text(source)
    for path in [curl, claude, codex, pi, opencode, bridge_installer, npm, memory_bridge, jq]:
        path.write_text(path.read_text().replace('fixture-secret', KEY))
    for path in [curl, claude, codex, pi, opencode, sleep, jq, root / 'open', root / 'xdg-open']: path.chmod(0o700)
    environment = dict(os.environ, PATH=directory + os.pathsep + os.environ['PATH'],
        MODEL_RESPONSE=request['models'], CURL_FAIL=str(request.get('curlFail', 0)),
        ANTHROPIC_API_KEY='stale', CLAUDE_CODE_DISABLE_THINKING='1')
    # Do not accidentally use credentials/config from the developer's shell.
    for name in ['ERAGON_API_KEY', 'ERAGON_ENDPOINT', 'ERAGON_MODEL', 'eragon_key', 'endpoint', 'selected', 'ERAGON_COMPATIBILITY_FILE', 'ERAGON_CONTEXT_WINDOW', 'CLAUDE_CODE_AUTO_COMPACT_WINDOW', 'CLAUDE_CODE_MAX_OUTPUT_TOKENS', 'CLAUDE_AUTOCOMPACT_PCT_OVERRIDE', 'FIXTURE_CLAUDE_VERSION', 'FIXTURE_CODEX_VERSION', 'ERAGON_CLIENT', 'ERAGON_ROUTER_TOKEN', 'ERAGON_GATEWAY_URL', 'CHECK_MEMORY_CHILD', 'ERAGON_ROUTER_PI_CONFIG', 'OPENCODE_CONFIG_CONTENT', 'FIXTURE_PI_VERSION', 'FIXTURE_OPENCODE_VERSION', 'FIXTURE_PI_EXIT', 'FIXTURE_PI_MCP', 'FIXTURE_NODE_VERSION', 'FIXTURE_NPM_FAIL', 'FIXTURE_REGISTER_FAIL',
                 'ERAGON_URL', 'ERAGON_NO_BROWSER', 'ERAGON_CREDENTIALS', 'DISPLAY', 'WAYLAND_DISPLAY', 'FIXTURE_REAL_SLEEP', 'FIXTURE_ERAGON']:
        environment.pop(name, None)
    if request.get('provideEndpoint', True):
        environment['ERAGON_ENDPOINT'] = 'https://gateway.example.com/gw'
    # The eragon CLI's own credential file, which the router may only read.
    cli_file = root / 'eragon-cli' / 'credentials.json'
    if 'cliCredentials' in request:
        cli_file.parent.mkdir(mode=0o700)
        cli_file.write_text(json.dumps(request['cliCredentials'], indent=2) + '\n')
        cli_file.chmod(0o600)
        cli_bytes = cli_file.read_bytes()
        environment['ERAGON_CREDENTIALS'] = str(cli_file)
    environment.update(request.get('environment', {}))
    environment['FIXTURE_LOG'] = str(log)
    environment['EXPECTED_ERAGON_URL'] = request.get('expectedEragonUrl', 'https://gateway.example.com')
    if 'eragon' in request:
        (log / 'eragon.json').write_text(json.dumps(request['eragon']))
        environment['FIXTURE_ERAGON'] = str(log / 'eragon.json')
    environment['EXPECTED_ENDPOINT'] = request.get('expectedEndpoint', 'https://gateway.example.com/gw')
    environment['EXPECT_MEMORY_ON_PATH'] = '1' if request.get('expectMemoryOnPath') else '0'
    environment['CHECK_MEMORY_CHILD'] = '1' if request.get('checkMemoryChild') else '0'
    environment['EXPECT_NO_CATALOGUE'] = str(request.get('noCatalogue', 0))
    environment['EXPECTED_PROFILE'] = request.get('expectedProfile', '')
    environment['TMPDIR'] = directory
    environment['XDG_CONFIG_HOME'] = str(root / 'config')
    environment['XDG_DATA_HOME'] = str(root / 'data')
    if request.get('memoryCached'):
        cached = root / 'data' / 'eragon-router' / 'memory'
        binary = cached / 'node_modules' / '.bin' / 'eragon-context-mcp'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(bridge_installer.read_bytes()); binary.chmod(0o700)
        (cached / 'source-revision').write_text('575d1617d181f2fcaefa91f648dee111a2959cb1\n')
    credential_dir = root / 'config' / 'eragon-router'
    credential_file = credential_dir / 'credentials.json'
    if 'savedCredentials' in request:
        credential_dir.mkdir(parents=True, mode=0o700)
        credential_file.write_text(json.dumps(request['savedCredentials']))
        credential_file.chmod(0o600)
    if request.get('symlinkCredentials'):
        credential_dir.mkdir(parents=True, mode=0o700)
        credential_file.symlink_to(root / 'eragon.sh')
    def inspect_storage():
        result = {}
        if credential_file.exists() and not credential_file.is_symlink():
            saved = json.loads(credential_file.read_text())
            if 'expectedSavedKeys' in request:
                assert saved['keys'] == request['expectedSavedKeys']
            else:
                assert all(value == KEY for value in saved['keys'].values())
            assert credential_file.stat().st_mode & 0o777 == 0o600
            assert credential_dir.stat().st_mode & 0o777 == 0o700
            result['savedEndpoints'] = sorted(saved['keys'])
            result['lastEndpoint'] = saved['last_endpoint']
            if 'sign_ins' in saved:
                result['signIns'] = saved['sign_ins']
        # Every curl call is recorded: what was requested, and proof that no
        # sign-in token or device code was ever a process argument.
        calls_log = log / 'curl.jsonl'
        calls = [json.loads(line) for line in calls_log.read_text().splitlines()] if calls_log.exists() else []
        for call in calls:
            assert all('ecli_' not in arg and 'edc_' not in arg for arg in call['argv']), call['argv']
        assert not (log / 'jq-argv-secrets').exists(), 'a secret was a jq argument'
        result['requests'] = [('POST ' if call['post'] else 'GET ') + call['url'] for call in calls]
        for name in ['sleeps', 'labels']:
            result[name] = (log / name).read_text().splitlines() if (log / name).exists() else []
        # What each device sign-in start asked for, label aside.
        starts = (log / 'starts').read_text().splitlines() if (log / 'starts').exists() else []
        result['starts'] = [{k: v for k, v in json.loads(line).items() if k != 'label'} for line in starts]
        opened = log / 'opened'
        if request.get('expectOpened'):
            # The browser opener runs detached; give it a moment to record.
            wait_until = time.monotonic() + 3
            while not opened.exists() and time.monotonic() < wait_until: time.sleep(.05)
        result['opened'] = opened.read_text().splitlines() if opened.exists() else []
        assert all('ecli_' not in line and 'edc_' not in line for line in result['opened'])
        if 'cliCredentials' in request:
            result['cliUnchanged'] = (cli_file.read_bytes() == cli_bytes and
                                      sorted(p.name for p in cli_file.parent.iterdir()) == ['credentials.json'])
        if request.get('relaunch'):
            again = subprocess.run(arguments, cwd=directory, env=environment,
                                   input='', capture_output=True, text=True, timeout=8)
            assert again.returncode == 0, again.stdout + again.stderr
            assert 'Personal API Key' not in again.stdout
            result['reloaded'] = True
        registration = root / 'config' / 'memory-registration.json'
        if registration.exists():
            assert 'fixture-secret' not in registration.read_text()
            result['memoryRegistration'] = json.loads(registration.read_text())
        return result

    expected_files = ['claude', 'codex', 'curl', 'eragon.sh', 'pi', 'opencode', 'memory-bridge.py', 'bridge-installer.py', 'node', 'npm',
                      'sleep', 'open', 'xdg-open', 'jq', 'log']
    if request.get('expectStorage') or 'savedCredentials' in request or request.get('symlinkCredentials') or request.get('expectMemoryRegistration'):
        expected_files.append('config')
    if 'cliCredentials' in request:
        expected_files.append('eragon-cli')
    if request.get('expectMemoryData') or request.get('memoryCached'):
        expected_files.append('data')
    if 'manifest' in request:
        manifest_path = root / 'compatibility.json'
        manifest_path.write_text(json.dumps(request['manifest']))
        environment['ERAGON_COMPATIBILITY_FILE'] = str(manifest_path)
        expected_files.append('compatibility.json')
    arguments = request.get('command', ['/bin/bash'] + request.get('bashOptions', ['-x']) + ['eragon.sh']) + request.get('args', [])
    if request.get('noninteractive'):
        result = subprocess.run(arguments, cwd=directory, env=environment,
                                input='', capture_output=True, text=True, timeout=8)
        assert sorted(path.name for path in root.iterdir()) == sorted(expected_files)
        print(json.dumps({'exit': result.returncode, 'output': result.stdout + result.stderr, **inspect_storage()}))
        sys.exit(0)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(directory)
        os.execvpe(arguments[0], arguments, environment)
    transcript = b''
    sent_key = False
    choices = iter(request.get('choices', ['']))
    prompts_seen = 0
    client_choices = iter(request.get('clientChoices', ['']))
    client_prompts_seen = 0
    sent_gateway = False
    sent_remember = False
    save_choices = iter(request.get("saveChoices", [""]))
    save_prompts_seen = 0
    memory_choices = iter(request.get("memoryChoices", [""]))
    memory_prompts_seen = 0
    key_actions = iter(request.get("keyActions", [""]))
    key_prompts_seen = 0
    key_numbers = iter(request.get("keyNumbers", [""]))
    key_number_prompts_seen = 0
    pastes = iter(request.get("pastes", []))
    paste_prompts_seen = 0
    interrupted_waiting = False
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], .1)
        if not ready: continue
        try: chunk = os.read(fd, 65536)
        except OSError: break
        if not chunk: break
        transcript += chunk
        if not sent_gateway and (b'Gateway URL: ' in transcript or b'Gateway URL [saved]: ' in transcript):
            os.write(fd, (request.get('gatewayInput', '') + '\n').encode()); sent_gateway = True
        if not sent_remember and b'Remember API key locally (owner-only plaintext file)? [y/N]: ' in transcript:
            os.write(fd, (request.get('rememberChoice', '') + '\n').encode()); sent_remember = True
        # A key created for this machine asks to be saved, yes by default.
        save_count = transcript.count(b'Save this key on this machine? [Y/n]: ')
        if save_count > save_prompts_seen:
            os.write(fd, (next(save_choices, '') + '\n').encode()); save_prompts_seen = save_count
        memory_count = transcript.count(b'Memory setup [1]: ')
        if memory_count > memory_prompts_seen:
            action = next(memory_choices, '')
            os.write(fd, b'\x03' if action == 'INTERRUPT' else (action + '\n').encode())
            memory_prompts_seen = memory_count
        key_count = transcript.count(b'Key action [1]: ')
        if key_count > key_prompts_seen:
            action = next(key_actions, '')
            os.write(fd, b'\x03' if action == 'INTERRUPT' else (action + '\n').encode())
            key_prompts_seen = key_count
        client_count = transcript.count(b'Client number [1]: ')
        if client_count > client_prompts_seen:
            os.write(fd, (next(client_choices, '') + '\n').encode()); client_prompts_seen = client_count
        if b'Personal API Key: ' in transcript and not sent_key:
            os.write(fd, b'\x03' if request.get('interrupt') else (KEY + '\n').encode()); sent_key = True
        number_count = transcript.count(b'Key number [')
        if number_count > key_number_prompts_seen:
            action = next(key_numbers, '')
            os.write(fd, b'\x03' if action == 'INTERRUPT' else (action + '\n').encode())
            key_number_prompts_seen = number_count
        # The secret prompt disables echo before it is printed, so a paste
        # written after it appears must not show up in the transcript.
        paste_count = transcript.count(b'Paste the secret for ')
        if paste_count > paste_prompts_seen:
            value = next(pastes, 'q')
            os.write(fd, b'\x03' if value == 'INTERRUPT' else (value + '\n').encode())
            paste_prompts_seen = paste_count
        if request.get('interruptWaiting') and not interrupted_waiting and b'Waiting' in transcript:
            os.write(fd, b'\x03'); interrupted_waiting = True
        count = transcript.count(b'Model number [1]: ')
        if count > prompts_seen:
            os.write(fd, (next(choices, '') + '\n').encode()); prompts_seen = count
    else:
        os.kill(pid, 9)
        raise RuntimeError('Launcher timed out')
    _, status = os.waitpid(pid, 0)
    assert termios.tcgetattr(fd)[3] & termios.ECHO, "Terminal echo was not restored"
    os.close(fd)
    assert sorted(path.name for path in root.iterdir()) == sorted(expected_files)
    print(json.dumps({'exit': os.waitstatus_to_exitcode(status), 'output': transcript.decode(), **inspect_storage()}))
