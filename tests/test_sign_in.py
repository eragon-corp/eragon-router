"""Browser sign-in, choosing one of your own Gateway keys, and creating one for
this machine during the device flow (ERA-4108). Fixtures only: no network."""
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ERAGON = "https://gateway.example.com"
GATEWAY = ERAGON + "/gw"
KEY = "esk_fixture-secret"  # last four characters: "cret"
NEW = "ecli_fixture-new-sign-in"
SAVED = "ecli_fixture-saved-sign-in"
CLI = "ecli_fixture-cli-sign-in"
ME = {"userId": "usr_me", "email": "me@example.com", "orgRole": "member"}
LINK = ERAGON + "/cli?code=ABCD-EFGH"
START = "POST " + ERAGON + "/v1/auth/device/start"
TOKEN = "POST " + ERAGON + "/v1/auth/device/token"
CREATED = "Created eragon-router (me@laptop) …cret for this machine."
CANNOT = ("This Eragon cannot create keys during sign-in yet. Create one at "
          + ERAGON + "/ai-gateway/keys, then paste it.")
UNUSABLE = ("Unexpected key from " + ERAGON + ". Nothing was stored; revoke the new key at "
            + ERAGON + "/ai-gateway/keys.")
# The start answer of an Eragon that can mint a key: it echoes the request.
SIGN_IN_ECHO = {"gatewayKey": True, "signIn": True}
KEY_ONLY_ECHO = {"gatewayKey": True, "signIn": False}


def start(**overrides):
    body = {"deviceCode": "edc_fixture-device-code", "userCode": "ABCD-EFGH",
            "verificationUri": ERAGON + "/cli", "verificationUriComplete": LINK,
            "expiresIn": 900, "interval": 5}
    body.update(overrides)
    return {"body": body}


def poll(status, **fields):
    return {"body": dict(status=status, **fields)}


def key(name, last4, **fields):
    record = {"id": "key_" + name.lower().replace(" ", "_"), "name": name, "createdBy": "usr_me",
              "provisionedBy": None, "status": "active", "revokedAt": None, "expiresAt": None,
              "secretLast4": last4, "allModels": True, "allowedPublicModelCount": 12,
              "allowedSmartRoutingGroups": [], "budget": None, "spendUsd": 0, "lastUsedAt": None,
              "createdAt": "2026-10-01T00:00:00.000Z"}
    record.update(fields)
    return record


def created(name="eragon-router (me@laptop)", secret=KEY, last4="cret", **fields):
    """The Gateway key an issued answer hands over, exactly once."""
    record = {"id": "key_created", "name": name, "secret": secret, "secretLast4": last4, "expiresAt": None}
    record.update(fields)
    return record


def eragon(polls=(), me=None, keys=(), **start_fields):
    return {"start": start(**start_fields), "polls": list(polls),
            "me": {NEW: {"body": ME}} if me is None else me, "keys": {"body": list(keys)}}


def stored(token, email="me@example.com"):
    return {"token": token, "email": email, "createdAt": "2026-10-01T00:00:00Z"}


class SignInTests(unittest.TestCase):
    def run_launcher(self, models=None, **options):
        options.setdefault("fixtureKey", KEY)
        catalogue = {"data": [{"id": "claude-sonnet-5"}]} if models is None else models
        request = dict(script=(ROOT / "eragon.sh").read_text(), models=json.dumps(catalogue), **options)
        result = subprocess.run([sys.executable, str(ROOT / "tests/pty_runner.py")],
                                input=json.dumps(request), text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        reply = json.loads(result.stdout)
        # Keys, sign-in tokens and device codes are never printed or echoed.
        for secret in ["fixture-secret", "ecli_", "edc_"]:
            self.assertNotIn(secret, reply["output"])
        return reply

    def test_fresh_sign_in_chooses_the_saved_key(self):
        saved = {"last_endpoint": GATEWAY, "keys": {GATEWAY: KEY}}
        keys = [key("Laptop", "cret", spendUsd=12.4, lastUsedAt="2026-11-01T09:30:00.000Z",
                    budget={"softBudgetUsd": None, "maxBudgetUsd": 50, "renewal": "30d"}),
                key("CI runner", "zzzz", allModels=False, allowedPublicModelCount=3, spendUsd=3.1,
                    allowedSmartRoutingGroups=["org:fast", "org:cheap"])]
        fixture = eragon([poll("pending"), poll("slow_down", interval=5), poll("issued", token=NEW)], keys=keys)
        reply = self.run_launcher(args=["--login"], savedCredentials=saved, eragon=fixture,
                                  environment={"DISPLAY": ":0"}, expectOpened=True)
        self.assertEqual(reply["exit"], 0, reply["output"])
        output = reply["output"]
        self.assertIn("Open  " + LINK, output)
        self.assertIn("Code  ABCD-EFGH", output)
        self.assertIn('Approve "eragon-router (', output)
        self.assertIn("in your browser. Waiting… (Ctrl-C to cancel)", output)
        self.assertIn("Signed in to https://gateway.example.com as me@example.com.", output)
        self.assertIn("  1) CI runner …zzzz\r\n     3 models +2 routing groups · $3.10 spent · never used", output)
        self.assertIn("  2) Laptop …cret · saved here\r\n     all models · $12.40 of $50 / 30d · last used 2026-11-01\r\n"
                      "  n) Create a new key for this machine (approve in your browser)\r\n  q) Quit\r\n", output)
        # A key is saved for this Gateway, so the sign-in asks for none, and
        # Enter still picks the saved-here key.
        self.assertEqual(reply["starts"], [{}])
        self.assertIn("Key number [2]: ", output)
        self.assertNotIn("Paste the secret", output)
        self.assertNotIn("Remember API key locally", output)
        self.assertIn('LAUNCHED {"model": "claude-sonnet-5"', output)
        self.assertEqual(reply["sleeps"], ["5", "5", "10"])
        self.assertEqual(reply["requests"], [
            "POST " + ERAGON + "/v1/auth/device/start"] + ["POST " + ERAGON + "/v1/auth/device/token"] * 3 + [
            "GET " + ERAGON + "/v1/me", "GET " + ERAGON + "/v1/gateway-keys", "GET " + GATEWAY + "/v1/models"])
        self.assertEqual(reply["opened"], [("open " if sys.platform == "darwin" else "xdg-open ") + LINK])
        self.assertEqual(reply["labels"][0], output.split('Approve "', 1)[1].split('"', 1)[0])
        self.assertEqual(set(reply["signIns"]), {ERAGON})
        sign_in = reply["signIns"][ERAGON]
        self.assertEqual({k: sign_in[k] for k in ["token", "email"]}, {"token": NEW, "email": "me@example.com"})
        self.assertRegex(sign_in["createdAt"], r"\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z")
        self.assertEqual(reply["savedEndpoints"], [GATEWAY])

    def test_saved_sign_in_is_reused_without_device_calls(self):
        saved = {"last_endpoint": GATEWAY, "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        fixture = eragon(me={SAVED: {"body": ME}}, keys=[key("Laptop", "cret")])
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1,
                                  savedCredentials=saved, eragon=fixture, pastes=[KEY])
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("Using your saved sign-in to https://gateway.example.com as me@example.com.", reply["output"])
        self.assertEqual(reply["requests"], ["GET " + ERAGON + "/v1/me", "GET " + ERAGON + "/v1/gateway-keys"])
        self.assertEqual(reply["sleeps"], [])
        self.assertIn("Paste the secret for Laptop (…cret): ", reply["output"])
        self.assertIn("Remember API key locally", reply["output"])
        self.assertIn("LAUNCHED", reply["output"])
        self.assertEqual(reply["signIns"], saved["sign_ins"])

    def test_eragon_cli_sign_in_is_reused_and_left_untouched(self):
        cli = {"version": 1, "credentials": [
            {"url": "https://other.example.com", "token": "ecli_fixture-other", "createdAt": "2026-10-01T00:00:00.000Z"},
            {"url": ERAGON, "token": CLI, "email": "me@example.com", "createdAt": "2026-10-01T00:00:00.000Z"}]}
        fixture = eragon(me={CLI: {"body": ME}}, keys=[key("Laptop", "cret")])
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1,
                                  cliCredentials=cli, eragon=fixture, pastes=[KEY])
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("Using your eragon CLI sign-in to https://gateway.example.com as me@example.com.", reply["output"])
        self.assertEqual(reply["requests"], ["GET " + ERAGON + "/v1/me", "GET " + ERAGON + "/v1/gateway-keys"])
        self.assertTrue(reply["cliUnchanged"])
        # Reused for this launch only: the router keeps no copy of it.
        self.assertNotIn("signIns", reply)

    def test_rejected_saved_sign_in_is_replaced_by_a_new_one(self):
        other = stored("ecli_fixture-other-deployment")
        saved = {"last_endpoint": GATEWAY, "keys": {},
                 "sign_ins": {ERAGON: stored("ecli_fixture-revoked"), "https://other.example.com": other}}
        fixture = eragon([poll("issued", token=NEW)], keys=[key("Laptop", "cret")])
        reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                  savedCredentials=saved, eragon=fixture, pastes=[KEY])
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("Your saved sign-in to https://gateway.example.com is no longer accepted.", reply["output"])
        self.assertEqual(reply["requests"], ["GET " + ERAGON + "/v1/me", "POST " + ERAGON + "/v1/auth/device/start",
                                             "POST " + ERAGON + "/v1/auth/device/token", "GET " + ERAGON + "/v1/me",
                                             "GET " + ERAGON + "/v1/gateway-keys"])
        self.assertEqual(reply["signIns"]["https://other.example.com"], other)
        self.assertEqual(reply["signIns"][ERAGON]["token"], NEW)
        # The rejected entry is dropped even when the new sign-in does not finish.
        reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                  savedCredentials=saved, eragon=eragon([poll("denied")]))
        self.assertEqual(reply["exit"], 1)
        self.assertEqual(reply["signIns"], {"https://other.example.com": other})

    def test_unavailable_eragon_is_an_error_not_a_sign_out(self):
        saved = {"last_endpoint": GATEWAY, "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        for answer, message in [({"network": True}, "Could not reach https://gateway.example.com."),
                                ({"code": 503, "body": "unavailable"}, "(HTTP 503)")]:
            with self.subTest(answer=answer):
                reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1,
                                          savedCredentials=saved, eragon=eragon(me={SAVED: answer}))
                self.assertEqual(reply["exit"], 1)
                self.assertIn(message, reply["output"])
                self.assertEqual(reply["requests"], ["GET " + ERAGON + "/v1/me"])
                self.assertEqual(reply["signIns"], saved["sign_ins"])

    def test_unfinished_sign_ins_store_nothing(self):
        cases = [([poll("pending"), poll("denied")], {}, "Declined in the browser. Nothing was stored."),
                 ([poll("expired")], {}, "The code expired before it was approved. Run with --login again."),
                 ([poll("unknown")], {}, "The code expired before it was approved. Run with --login again."),
                 ([poll("pending")] * 3, {"expiresIn": 10}, "The code expired before it was approved."),
                 ([poll("issued")], {}, "Unexpected answer from https://gateway.example.com while waiting"),
                 ([poll("approved")], {}, "while waiting for approval (HTTP 200)."),
                 ([{"code": 500, "body": "<html>"}], {}, "while waiting for approval (HTTP 500)."),
                 ([poll("issued", token=NEW)], {"me": {}}, "Approved, but Eragon did not accept the new sign-in. Nothing was stored.")]
        for polls, extra, message in cases:
            with self.subTest(message=message, polls=polls):
                me = extra.pop("me", None)
                reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                          eragon=eragon(polls, me=me, **extra))
                self.assertEqual(reply["exit"], 1, reply["output"])
                self.assertIn(message, reply["output"])
                self.assertNotIn("LAUNCHED", reply["output"])
                # No credential directory was created: nothing was stored.
                self.assertNotIn("signIns", reply)
                self.assertNotIn("savedEndpoints", reply)
        self.assertEqual(reply["sleeps"], ["5"])

    def test_code_expires_on_the_client_clock_too(self):
        reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                  eragon=eragon([poll("pending")] * 5, expiresIn=10))
        self.assertEqual(reply["exit"], 1)
        self.assertIn("The code expired before it was approved.", reply["output"])
        self.assertEqual(reply["sleeps"], ["5", "5"])
        self.assertEqual(reply["requests"].count("POST " + ERAGON + "/v1/auth/device/token"), 1)

    def test_ctrl_c_while_waiting_restores_the_terminal_and_stores_nothing(self):
        reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                  eragon=eragon([poll("issued", token=NEW)]), interruptWaiting=True,
                                  environment={"FIXTURE_REAL_SLEEP": "1"})
        self.assertEqual(reply["exit"], 130)
        self.assertNotIn("Signed in", reply["output"])
        self.assertNotIn("signIns", reply)

    def test_too_many_pending_sign_ins(self):
        fixture = eragon()
        fixture["start"] = {"code": 429, "body": {"error": "too many sign-ins in progress"}}
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1, eragon=fixture)
        self.assertEqual(reply["exit"], 1)
        self.assertIn("Too many sign-ins are waiting for approval", reply["output"])
        self.assertEqual(reply["requests"], ["POST " + ERAGON + "/v1/auth/device/start"])

    def test_browser_is_optional(self):
        fixture = eragon([poll("issued", token=NEW)], keys=[key("Laptop", "cret")])
        for options in [{"args": ["--login", "--no-browser", "--model", "coder"]},
                        {"args": ["--login", "--model", "coder"], "environment": {"DISPLAY": ":0", "ERAGON_NO_BROWSER": "1"}}]:
            with self.subTest(options=options):
                reply = self.run_launcher(noCatalogue=1, eragon=fixture, pastes=[KEY], expectStorage=True, **options)
                self.assertEqual(reply["exit"], 0, reply["output"])
                self.assertIn("Open  " + LINK, reply["output"])
                self.assertEqual(reply["opened"], [])
        # Only https:// links are ever opened; the link is still printed.
        fixture = eragon([poll("issued", token=NEW)], keys=[key("Laptop", "cret")],
                         verificationUriComplete="http://gateway.example.com/cli?code=ABCD-EFGH")
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1, eragon=fixture,
                                  pastes=[KEY], environment={"DISPLAY": ":0"}, expectStorage=True)
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("Open  http://gateway.example.com/cli?code=ABCD-EFGH", reply["output"])
        self.assertEqual(reply["opened"], [])

    def test_label_is_ascii_without_controls_and_capped(self):
        reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                  eragon=eragon([poll("denied")]), environment={"USER": "Jos\u00e9\u001b[31m" + "x" * 200})
        self.assertEqual(reply["exit"], 1)
        label = reply["labels"][0]
        self.assertTrue(label.startswith("eragon-router (Jos[31mxxx"), label)
        self.assertEqual(len(label), 120)
        self.assertIn('Approve "' + label + '"', reply["output"])

    def test_only_your_own_active_keys_are_listed(self):
        keys = [key("Mine", "cret"),
                key("Expired", "exp1", status="expired", expiresAt="2026-01-01T00:00:00.000Z"),
                key("Revoked", "rev1", status="revoked", revokedAt="2026-01-01T00:00:00.000Z"),
                key("Colleague", "col1", createdBy="usr_colleague"),
                key("Partner", "par1", provisionedBy="key_partner"),
                key("Nobody", "nob1", createdBy=None),
                key("Evil\u001b[2J\u0007\u202eName", "evl1"),
                {"name": "Older server", "createdBy": "usr_me", "revokedAt": None, "secretLast4": None}]
        saved = {"last_endpoint": GATEWAY, "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        fixture = eragon(me={SAVED: {"body": dict(ME, orgRole="owner")}}, keys=keys)
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1, savedCredentials=saved,
                                  eragon=fixture, keyNumbers=["2"], pastes=[KEY])
        self.assertEqual(reply["exit"], 0, reply["output"])
        output = reply["output"]
        self.assertIn("  1) Evil[2JName …evl1\r\n", output)
        self.assertIn("  2) Mine …cret\r\n     all models · $0 spent · never used\r\n", output)
        self.assertIn("  3) Older server\r\n  n) Create a new key for this machine (approve in your browser)\r\n"
                      "  q) Quit\r\n2 expired or revoked keys hidden.\r\n", output)
        for hidden in ["Colleague", "Partner", "Nobody", "Expired", "Revoked", "\x1b", "\x07", "\u202e"]:
            self.assertNotIn(hidden, output)
        self.assertIn("LAUNCHED", output)

    def test_pasted_secret_must_match_the_last_four(self):
        saved = {"last_endpoint": GATEWAY, "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        fixture = eragon(me={SAVED: {"body": ME}}, keys=[key("Laptop", "cret"), key("Old key", None)])
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1, savedCredentials=saved,
                                  eragon=fixture, keyNumbers=["1"], pastes=["esk_wrong-key-0000", "", KEY],
                                  rememberChoice="y")
        self.assertEqual(reply["exit"], 0, reply["output"])
        output = reply["output"]
        self.assertEqual(output.count("Paste the secret for Laptop (…cret): "), 3)
        self.assertIn("That key does not end with …cret. Paste the matching key, or enter q to quit.", output)
        self.assertIn("Paste the key, or enter q to quit.", output)
        self.assertNotIn("esk_wrong-key-0000", output)
        self.assertIn("LAUNCHED", output)
        self.assertEqual(reply["savedEndpoints"], [GATEWAY])
        # A key minted before last-four were kept is accepted as pasted.
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1, savedCredentials=saved,
                                  eragon=fixture, keyNumbers=["2"], pastes=[KEY])
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("Paste the secret for Old key: ", reply["output"])
        self.assertNotIn("does not end with", reply["output"])
        self.assertIn("LAUNCHED", reply["output"])
        # q quits at the hidden prompt; Ctrl-C there restores the terminal and stores nothing.
        for pastes, status in [(["q"], 0), (["INTERRUPT"], 130)]:
            with self.subTest(pastes=pastes):
                reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1, savedCredentials=saved,
                                          eragon=fixture, keyNumbers=["1"], pastes=pastes)
                self.assertEqual(reply["exit"], status)
                self.assertNotIn("LAUNCHED", reply["output"])
                self.assertEqual(reply["savedEndpoints"], [])
                self.assertEqual(reply["signIns"], saved["sign_ins"])

    def test_key_number_must_be_listed(self):
        saved = {"last_endpoint": GATEWAY, "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        fixture = eragon(me={SAVED: {"body": ME}}, keys=[key("Laptop", "cret")])
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1, savedCredentials=saved,
                                  eragon=fixture, keyNumbers=["2", "0", "x", "1"], pastes=[KEY])
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertEqual(reply["output"].count("Enter one of the key numbers above, n or q."), 3)
        self.assertIn("LAUNCHED", reply["output"])
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1, savedCredentials=saved,
                                  eragon=fixture, keyNumbers=["q"])
        self.assertEqual(reply["exit"], 0)
        self.assertNotIn("Paste the secret", reply["output"])
        self.assertNotIn("LAUNCHED", reply["output"])

    def test_two_keys_sharing_last_four_are_not_claimed(self):
        saved = {"last_endpoint": GATEWAY, "keys": {GATEWAY: KEY}, "sign_ins": {ERAGON: stored(SAVED)}}
        keys = [key("Laptop", "cret"), key("Old laptop", "cret", status="revoked")]
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1, savedCredentials=saved,
                                  eragon=eragon(me={SAVED: {"body": ME}}, keys=keys), pastes=[KEY])
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertNotIn("saved here", reply["output"])
        self.assertIn("Paste the secret for Laptop (…cret): ", reply["output"])

    def test_no_usable_keys_offer_to_create_or_paste_one(self):
        saved = {"last_endpoint": GATEWAY, "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        fixture = eragon(me={SAVED: {"body": ME}}, keys=[key("Gone", "gone", status="revoked")])
        message = ("You have no active Gateway keys.\r\n1 expired or revoked key hidden.\r\n"
                   "  1) Create a key for this machine (approve in your browser)\r\n  2) Paste a key\r\n  q) Quit\r\n")
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1, savedCredentials=saved,
                                  eragon=fixture, keyActions=["x", "2"])
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn(message, reply["output"])
        self.assertIn("Enter 1, 2 or q.", reply["output"])
        self.assertIn("Personal API Key", reply["output"])
        self.assertIn("Remember API key locally (owner-only plaintext file)? [y/N]: ", reply["output"])
        self.assertIn("LAUNCHED", reply["output"])
        self.assertEqual(reply["starts"], [])
        reply = self.run_launcher(args=["--login", "--model", "coder"], noCatalogue=1, savedCredentials=saved,
                                  eragon=fixture, keyActions=["q"])
        self.assertEqual(reply["exit"], 1)
        self.assertNotIn("LAUNCHED", reply["output"])
        self.assertNotIn("POST " + ERAGON + "/v1/gateway-keys", reply["requests"])

    def test_eragon_address_needs_gw_or_an_override(self):
        endpoint = "https://llm.example.com/api"
        reply = self.run_launcher(args=["--login", "--endpoint", endpoint, "--model", "coder"], noCatalogue=1,
                                  expectedEndpoint=endpoint, eragon=eragon())
        self.assertEqual(reply["exit"], 1)
        self.assertIn("does not end in /gw. Use --eragon-url", reply["output"])
        self.assertEqual(reply["requests"], [])
        override = "https://eragon.example.com"
        saved = {"last_endpoint": "", "keys": {}, "sign_ins": {override: stored(SAVED)}}
        fixture = eragon(me={SAVED: {"body": ME}}, keys=[key("Laptop", "cret")])
        for options in [{"args": ["--login", "--endpoint", endpoint, "--eragon-url", override + "/", "--model", "coder"]},
                        {"args": ["--login", "--endpoint", endpoint, "--model", "coder"], "environment": {"ERAGON_URL": override}}]:
            with self.subTest(options=options):
                reply = self.run_launcher(noCatalogue=1, expectedEndpoint=endpoint, expectedEragonUrl=override,
                                          savedCredentials=saved, eragon=fixture, pastes=[KEY], **options)
                self.assertEqual(reply["exit"], 0, reply["output"])
                self.assertIn("Using your saved sign-in to https://eragon.example.com as me@example.com.", reply["output"])
                self.assertEqual(reply["requests"][0], "GET " + override + "/v1/me")
        for value in ["http://eragon.example.com", "https://eragon.example.com/?next=x"]:
            with self.subTest(value=value):
                reply = self.run_launcher(args=["--eragon-url", value, "--model", "coder"], noCatalogue=1, eragon=eragon())
                self.assertEqual(reply["exit"], 1)
                self.assertIn("Eragon URL must be an HTTPS base URL", reply["output"])
                self.assertEqual(reply["requests"], [])

    def test_gateway_v1_suffix_still_finds_eragon(self):
        saved = {"last_endpoint": "", "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        reply = self.run_launcher(args=["--login", "--client", "codex", "--endpoint", GATEWAY + "/v1/", "--model", "coder"],
                                  noCatalogue=1, savedCredentials=saved, pastes=[KEY],
                                  eragon=eragon(me={SAVED: {"body": ME}}, keys=[key("Laptop", "cret")]))
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("CODEX_LAUNCHED", reply["output"])

    def test_login_needs_a_terminal(self):
        reply = self.run_launcher(args=["--login", "--model", "coder"], noninteractive=True,
                                  environment={"ERAGON_API_KEY": KEY})
        self.assertEqual(reply["exit"], 1)
        self.assertIn("Signing in needs an interactive terminal.", reply["output"])
        self.assertEqual(reply["requests"], [])

    def test_key_menus_offer_sign_in_and_enter_keeps_the_default(self):
        signed_in = {ERAGON: stored(SAVED)}
        fixture = eragon(me={SAVED: {"body": ME}}, keys=[key("Laptop", "cret")])
        reply = self.run_launcher(args=["--model", "coder"], noCatalogue=1, eragon=fixture, keyActions=["2"],
                                  savedCredentials={"last_endpoint": "", "keys": {}, "sign_ins": signed_in}, pastes=[KEY])
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("API key for this Gateway:\r\n  1) Paste a key\r\n"
                      "  2) Choose from your Eragon keys (sign in with your browser)\r\n  q) Quit\r\n", reply["output"])
        self.assertIn("Paste the secret for Laptop (…cret): ", reply["output"])
        self.assertNotIn("Personal API Key", reply["output"])
        reply = self.run_launcher(args=["--model", "coder"], noCatalogue=1, eragon=fixture, keyActions=["3"],
                                  savedCredentials={"last_endpoint": GATEWAY, "keys": {GATEWAY: KEY}, "sign_ins": signed_in})
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("  2) Update saved key\r\n  3) Choose from your Eragon keys (sign in with your browser)\r\n", reply["output"])
        self.assertIn("1) Laptop …cret · saved here", reply["output"])
        self.assertIn("Using the key saved here for Laptop.", reply["output"])
        self.assertNotIn("Paste the secret", reply["output"])
        # Enter keeps today's default: the saved key, without any sign-in.
        reply = self.run_launcher(args=["--model", "coder"], noCatalogue=1, eragon=fixture,
                                  savedCredentials={"last_endpoint": GATEWAY, "keys": {GATEWAY: KEY}, "sign_ins": signed_in})
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertEqual(reply["requests"], [])
        self.assertIn("LAUNCHED", reply["output"])

    def test_other_gateways_keep_todays_key_prompts(self):
        endpoint = "https://llm.example.com/api"
        reply = self.run_launcher(args=["--endpoint", endpoint, "--model", "coder"], noCatalogue=1,
                                  expectedEndpoint=endpoint, keyActions=["invalid", ""],
                                  savedCredentials={"last_endpoint": endpoint, "keys": {endpoint: KEY}})
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("API key saved for this Gateway:\r\n  1) Use saved key\r\n  2) Update saved key\r\n  q) Quit\r\n", reply["output"])
        self.assertIn("Enter 1, 2 or q.", reply["output"])
        self.assertNotIn("Eragon keys", reply["output"])
        reply = self.run_launcher(args=["--endpoint", endpoint, "--model", "coder"], noCatalogue=1, expectedEndpoint=endpoint)
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("Personal API Key", reply["output"])
        self.assertNotIn("Key action", reply["output"])
        self.assertNotIn("Eragon keys", reply["output"])

    def test_environment_keys_and_noninteractive_launches_are_unchanged(self):
        reply = self.run_launcher(args=["--model", "coder"], environment={"ERAGON_API_KEY": KEY})
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertNotIn("Key action", reply["output"])
        self.assertNotIn("Eragon keys", reply["output"])
        reply = self.run_launcher(args=["--model", "coder"], noninteractive=True, environment={"ERAGON_API_KEY": KEY})
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertEqual(reply["requests"], [])

    def test_inherited_variables_cannot_export_sign_in_secrets(self):
        planted = {name: "ecli_fixture-planted" for name in [
            "eragon_token", "stored_sign_in", "credential_secret", "hidden_input", "poll_request", "start_request",
            "http_response", "http_body", "credential_json", "saved_credentials", "saved_key", "key_rows", "new_key"]}
        # A pasted key, then a key created for this machine: the fake curl
        # checks that neither secret reaches its environment on any request.
        for polls, pastes in [([poll("issued", token=NEW)], [KEY]),
                              ([poll("issued", token=NEW, gatewayKey=created())], [])]:
            with self.subTest(created="gatewayKey" in polls[0]["body"]):
                fixture = eragon(polls, keys=[key("Laptop", "cret")], **SIGN_IN_ECHO)
                reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder", "--memory"], noCatalogue=1,
                                          eragon=fixture, pastes=pastes, environment=planted, expectMemoryData=True,
                                          expectMemoryRegistration=True)
                self.assertEqual(reply["exit"], 0, reply["output"])
                self.assertIn("FIXTURE_MEMORY_REGISTERED", reply["output"])
                self.assertIn("LAUNCHED", reply["output"])
                self.assertEqual(reply["signIns"][ERAGON]["token"], NEW)

    def test_logout_forgets_only_router_sign_ins(self):
        other = "https://other.example.com"
        sign_ins = {ERAGON: stored(SAVED), other: stored("ecli_fixture-other")}
        saved = {"last_endpoint": GATEWAY, "keys": {GATEWAY: KEY}, "sign_ins": sign_ins}
        cli = {"version": 1, "credentials": [{"url": ERAGON, "token": CLI, "createdAt": "2026-10-01T00:00:00.000Z"}]}
        cases = [({"args": ["--logout"]}, None, [ERAGON, other]),
                 ({"args": ["--logout"], "provideEndpoint": False}, None, [ERAGON, other]),
                 ({"args": ["--logout", "--eragon-url", other + "/"]}, {ERAGON: sign_ins[ERAGON]}, [other]),
                 ({"args": ["--logout"], "environment": {"ERAGON_URL": other}}, {ERAGON: sign_ins[ERAGON]}, [other]),
                 ({"args": ["--logout", "--endpoint", GATEWAY + "/v1/"]}, {other: sign_ins[other]}, [ERAGON])]
        for options, remaining, forgotten in cases:
            with self.subTest(options=options):
                reply = self.run_launcher(savedCredentials=saved, cliCredentials=cli, noninteractive=True, **options)
                self.assertEqual(reply["exit"], 0, reply["output"])
                for url in [ERAGON, other]:
                    (self.assertIn if url in forgotten else self.assertNotIn)(
                        "Forgot the Eragon sign-in for " + url + ".", reply["output"])
                self.assertIn("until you revoke it in the web app under Settings → Command line.", reply["output"])
                self.assertEqual(reply.get("signIns"), remaining)
                self.assertEqual(reply["savedEndpoints"], [GATEWAY])
                self.assertEqual(reply["lastEndpoint"], GATEWAY)
                self.assertTrue(reply["cliUnchanged"])
                self.assertEqual(reply["requests"], [])
        reply = self.run_launcher(args=["--logout"], noninteractive=True)
        self.assertEqual(reply["exit"], 0)
        self.assertIn("No Eragon sign-in is saved.", reply["output"])
        reply = self.run_launcher(args=["--logout", "--endpoint", "https://llm.example.com/api"], noninteractive=True)
        self.assertEqual(reply["exit"], 1)
        self.assertIn("Use --eragon-url", reply["output"])

    def test_forget_key_still_forgets_only_gateway_keys(self):
        sign_ins = {ERAGON: stored(SAVED)}
        saved = {"last_endpoint": GATEWAY, "keys": {GATEWAY: KEY}, "sign_ins": sign_ins}
        reply = self.run_launcher(args=["--forget-key"], savedCredentials=saved, provideEndpoint=False, noninteractive=True)
        self.assertEqual(reply["exit"], 0)
        self.assertIn("Remembered Gateway credentials removed.", reply["output"])
        self.assertIn("use --logout to forget them", reply["output"])
        self.assertEqual(reply["savedEndpoints"], [])
        self.assertEqual(reply["lastEndpoint"], "")
        self.assertEqual(reply["signIns"], sign_ins)
        reply = self.run_launcher(args=["--forget-key", "--logout"], savedCredentials=saved, noninteractive=True)
        self.assertEqual(reply["exit"], 0)
        self.assertNotIn("savedEndpoints", reply)
        self.assertNotIn("signIns", reply)
        self.assertIn("Settings → Command line", reply["output"])

    def test_invalid_saved_sign_ins_are_reported(self):
        for sign_ins in ["not an object", {ERAGON: {"email": "me@example.com"}}, {ERAGON: {"token": "ecli_x\r\nX: y"}}]:
            with self.subTest(sign_ins=sign_ins):
                saved = {"last_endpoint": GATEWAY, "keys": {GATEWAY: KEY}, "sign_ins": sign_ins}
                reply = self.run_launcher(args=["--model", "coder"], savedCredentials=saved, noninteractive=True)
                self.assertEqual(reply["exit"], 1)
                self.assertIn("Invalid saved credentials. Use --forget-key to remove them.", reply["output"])
        # --forget-key still clears a damaged file entirely.
        reply = self.run_launcher(args=["--forget-key"], noninteractive=True,
                                  savedCredentials={"last_endpoint": GATEWAY, "keys": {GATEWAY: KEY}, "sign_ins": "bad"})
        self.assertEqual(reply["exit"], 0)
        self.assertNotIn("savedEndpoints", reply)

    # Creating a Gateway key for this machine in the device flow (ERA-4108).

    def test_sign_in_creates_a_key_for_this_machine(self):
        fixture = eragon([poll("pending"), poll("issued", token=NEW, gatewayKey=created())], **SIGN_IN_ECHO)
        # No key saved for this Gateway, or one that is not an esk_ key: the sign-in asks for one.
        for saved in [None, {"last_endpoint": GATEWAY, "keys": {GATEWAY: "sk-legacy-key-0000"}}]:
            with self.subTest(saved=saved):
                options = {} if saved is None else {"savedCredentials": saved}
                reply = self.run_launcher(args=["--login", "--no-browser"], eragon=fixture, expectStorage=True, **options)
                self.assertEqual(reply["exit"], 0, reply["output"])
                output = reply["output"]
                self.assertEqual(reply["starts"], [{"gatewayKey": True}])
                self.assertIn('Approve "eragon-router (', output)
                self.assertIn("Signed in to https://gateway.example.com as me@example.com.\r\n" + CREATED + "\r\n", output)
                # The key is used directly: no key list, no paste, no hidden prompt.
                for absent in ["Choose one of your Gateway keys", "Paste the secret", "Personal API Key",
                               "Remember API key locally"]:
                    self.assertNotIn(absent, output)
                self.assertIn('LAUNCHED {"model": "claude-sonnet-5"', output)
                # It reached the Gateway as a header on stdin (the fake curl checks the
                # value), and Eragon was never asked to list or create keys.
                self.assertEqual(reply["requests"], [START, TOKEN, TOKEN, "GET " + ERAGON + "/v1/me",
                                                     "GET " + GATEWAY + "/v1/models"])
                self.assertEqual(reply["signIns"][ERAGON]["token"], NEW)
                # Enter at the save prompt saved it; the runner checks the stored value.
                self.assertIn("Eragon cannot show this key's secret again. Saving uses an owner-only plaintext file.\r\n"
                              "Save this key on this machine? [Y/n]: \r\n", output)
                self.assertIn("Gateway and key remembered locally.", output)
                self.assertEqual(reply["savedEndpoints"], [GATEWAY])

    def test_a_key_the_sign_in_did_not_ask_for_is_ignored(self):
        saved = {"last_endpoint": GATEWAY, "keys": {GATEWAY: KEY}}
        fixture = eragon([poll("issued", token=NEW, gatewayKey=created(secret="esk_fixture-unasked", last4="sked"))],
                         keys=[key("Laptop", "cret")])
        reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                  savedCredentials=saved, eragon=fixture)
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertEqual(reply["starts"], [{}])
        self.assertNotIn("Created", reply["output"])
        self.assertNotIn("unasked", reply["output"])
        self.assertIn("Using the key saved here for Laptop.", reply["output"])
        self.assertIn("LAUNCHED", reply["output"])

    def test_key_only_request_from_the_key_list_keeps_the_sign_in(self):
        saved = {"last_endpoint": GATEWAY, "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        # A token in a key-only answer is not asked for, and is ignored.
        for issued in [poll("issued", gatewayKey=created()),
                       poll("issued", token="ecli_fixture-unasked", gatewayKey=created())]:
            with self.subTest(token="token" in issued["body"]):
                fixture = eragon([poll("pending"), issued], me={SAVED: {"body": ME}},
                                 keys=[key("CI runner", "zzzz")], **KEY_ONLY_ECHO)
                reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                          savedCredentials=saved, eragon=fixture, keyNumbers=["n"], saveChoices=["n"])
                self.assertEqual(reply["exit"], 0, reply["output"])
                output = reply["output"]
                self.assertIn("  1) CI runner …zzzz\r\n     all models · $0 spent · never used\r\n"
                              "  n) Create a new key for this machine (approve in your browser)\r\n  q) Quit\r\n"
                              "Key number [1]: n\r\n", output)
                self.assertIn("Open  " + LINK + "\r\nCode  ABCD-EFGH\r\n\r\n"
                              "Approve and create the key in your browser. Waiting… (Ctrl-C to cancel)\r\n", output)
                self.assertIn(CREATED, output)
                self.assertNotIn("Paste the secret", output)
                self.assertEqual(reply["starts"], [{"gatewayKey": True, "signIn": False}])
                self.assertEqual(reply["requests"], ["GET " + ERAGON + "/v1/me", "GET " + ERAGON + "/v1/gateway-keys",
                                                     START, TOKEN, TOKEN])
                self.assertEqual(reply["sleeps"], ["5", "5"])
                self.assertIn("LAUNCHED", output)
                # The stored sign-in is kept as it was, and "n" kept the key off the disk.
                self.assertEqual(reply["signIns"], saved["sign_ins"])
                self.assertEqual(reply["savedEndpoints"], [])

    def test_no_usable_keys_create_one_by_default(self):
        saved = {"last_endpoint": GATEWAY, "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        fixture = eragon([poll("issued", gatewayKey=created())], me={SAVED: {"body": ME}},
                         keys=[key("Gone", "gone", status="revoked")], **KEY_ONLY_ECHO)
        reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                  savedCredentials=saved, eragon=fixture)
        self.assertEqual(reply["exit"], 0, reply["output"])
        output = reply["output"]
        self.assertIn("  1) Create a key for this machine (approve in your browser)\r\n  2) Paste a key\r\n  q) Quit\r\n"
                      "Key action [1]: \r\nOpen  " + LINK, output)
        self.assertIn("Approve and create the key in your browser.", output)
        self.assertIn(CREATED, output)
        self.assertNotIn("Personal API Key", output)
        self.assertEqual(reply["starts"], [{"gatewayKey": True, "signIn": False}])
        self.assertEqual(reply["signIns"], saved["sign_ins"])
        self.assertEqual(reply["savedEndpoints"], [GATEWAY])
        self.assertIn("LAUNCHED", output)

    def test_older_eragon_without_the_echo(self):
        saved = {"last_endpoint": GATEWAY, "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        # A key alone is never polled without its echo: an older Eragon would
        # answer it with a sign-in. Nor is one echoed as a sign-in. The message,
        # then the same menu; Eragon is not asked twice.
        for echo in [{}, SIGN_IN_ECHO]:
            with self.subTest(key_only_echo=echo):
                fixture = eragon(me={SAVED: {"body": ME}}, keys=[key("Laptop", "cret")], **echo)
                reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                          savedCredentials=saved, eragon=fixture, keyNumbers=["n", "n", "1"], pastes=[KEY])
                self.assertEqual(reply["exit"], 0, reply["output"])
                output = reply["output"]
                self.assertEqual(output.count("Key number [1]: n\r\n" + CANNOT + "\r\n"), 2)
                self.assertNotIn("Open  ", output)
                self.assertEqual(reply["starts"], [{"gatewayKey": True, "signIn": False}])
                self.assertEqual(reply["requests"], ["GET " + ERAGON + "/v1/me", "GET " + ERAGON + "/v1/gateway-keys", START])
                self.assertEqual(reply["sleeps"], [])
                self.assertIn("Paste the secret for Laptop (…cret): ", output)
                # Every other key keeps the opt-in remember prompt.
                self.assertIn("Remember API key locally (owner-only plaintext file)? [y/N]: ", output)
                self.assertNotIn("Save this key on this machine", output)
                self.assertIn("LAUNCHED", output)
                self.assertEqual(reply["signIns"], saved["sign_ins"])
        # A sign-in is polled as before. With no key in the answer the key list
        # follows: an older Eragon, a person who turned the key off, or null.
        for echo, issued in [({}, poll("issued", token=NEW)),
                             (SIGN_IN_ECHO, poll("issued", token=NEW)),
                             (SIGN_IN_ECHO, poll("issued", token=NEW, gatewayKey=None))]:
            with self.subTest(echo=echo, issued=issued):
                fixture = eragon([issued], keys=[key("Laptop", "cret")], **echo)
                reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                          eragon=fixture, pastes=[KEY], expectStorage=True)
                self.assertEqual(reply["exit"], 0, reply["output"])
                self.assertEqual(reply["starts"], [{"gatewayKey": True}])
                self.assertEqual(reply["requests"], [START, TOKEN, "GET " + ERAGON + "/v1/me",
                                                     "GET " + ERAGON + "/v1/gateway-keys"])
                self.assertIn("Paste the secret for Laptop (…cret): ", reply["output"])
                self.assertIn("Remember API key locally (owner-only plaintext file)? [y/N]: ", reply["output"])
                self.assertNotIn("Created ", reply["output"])
                self.assertEqual(reply["signIns"][ERAGON]["token"], NEW)
        # After a sign-in an older Eragon ignored, creating a key is not tried.
        fixture = eragon([poll("issued", token=NEW)], keys=[])
        reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                  eragon=fixture, keyActions=["", "2"], expectStorage=True)
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertIn("Key action [1]: \r\n" + CANNOT + "\r\nKey action [1]: 2\r\n", reply["output"])
        self.assertEqual(reply["starts"], [{"gatewayKey": True}])
        self.assertIn("Personal API Key", reply["output"])
        self.assertIn("LAUNCHED", reply["output"])

    def test_unusable_created_keys_store_nothing(self):
        cases = {"last four do not match": created(last4="zzzz"),
                 "not an esk_ key": created(secret="sk-fixture-secret"),
                 "line break": created(secret=KEY + "\r\nX-cret"),
                 "too short": created(secret="esk_ret", last4="_ret"),
                 "no last four": created(last4=None),
                 "short last four": created(last4="ret"),
                 "empty last four": created(last4=""),
                 "no name": created(name=None),
                 "not an object": KEY,
                 "false": False}
        for case, bad in cases.items():
            with self.subTest(case=case):
                # With a sign-in: refused before /v1/me, so not even the sign-in is stored.
                fixture = eragon([poll("issued", token=NEW, gatewayKey=bad)], **SIGN_IN_ECHO)
                reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                          eragon=fixture)
                self.assertEqual(reply["exit"], 1, reply["output"])
                self.assertIn(UNUSABLE, reply["output"])
                self.assertNotIn("Signed in", reply["output"])
                self.assertNotIn("LAUNCHED", reply["output"])
                self.assertEqual(reply["requests"], [START, TOKEN])
                self.assertNotIn("signIns", reply)
                self.assertNotIn("savedEndpoints", reply)
        saved = {"last_endpoint": GATEWAY, "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        for case, issued, message in [("bad prefix", poll("issued", gatewayKey=created(secret="sk-fixture-secret")), UNUSABLE),
                                      ("mismatch", poll("issued", gatewayKey=created(last4="zzzz")), UNUSABLE),
                                      ("no key", poll("issued"), "Unexpected answer from " + ERAGON +
                                       " while waiting for approval. Nothing was stored.")]:
            with self.subTest(case="key only: " + case):
                fixture = eragon([issued], me={SAVED: {"body": ME}}, keys=[], **KEY_ONLY_ECHO)
                reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                          savedCredentials=saved, eragon=fixture)
                self.assertEqual(reply["exit"], 1, reply["output"])
                self.assertIn(message, reply["output"])
                self.assertNotIn("LAUNCHED", reply["output"])
                self.assertEqual(reply["signIns"], saved["sign_ins"])
                self.assertEqual(reply["savedEndpoints"], [])

    def test_unfinished_key_requests_keep_the_sign_in(self):
        saved = {"last_endpoint": GATEWAY, "keys": {}, "sign_ins": {ERAGON: stored(SAVED)}}
        cases = [([poll("denied")], {}, 1, "Declined in the browser. Nothing was stored."),
                 ([poll("expired")], {}, 1, "The code expired before it was approved."),
                 ([poll("issued", gatewayKey=created())], {"interruptWaiting": True,
                                                          "environment": {"FIXTURE_REAL_SLEEP": "1"}}, 130, "Waiting…")]
        for polls, extra, status, message in cases:
            with self.subTest(message=message):
                fixture = eragon(polls, me={SAVED: {"body": ME}}, keys=[], **KEY_ONLY_ECHO)
                reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                          savedCredentials=saved, eragon=fixture, **extra)
                self.assertEqual(reply["exit"], status, reply["output"])
                self.assertIn(message, reply["output"])
                self.assertNotIn("Created", reply["output"])
                self.assertNotIn("LAUNCHED", reply["output"])
                self.assertEqual(reply["signIns"], saved["sign_ins"])
                self.assertEqual(reply["savedEndpoints"], [])

    def test_created_key_is_saved_unless_declined(self):
        fixture = eragon([poll("issued", token=NEW, gatewayKey=created())], **SIGN_IN_ECHO)
        for choices, kept in [([""], True), (["Y"], True), (["n"], False), (["NO"], False), (["maybe", "y"], True)]:
            with self.subTest(choices=choices):
                reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder"], noCatalogue=1,
                                          eragon=fixture, saveChoices=choices, expectStorage=True)
                self.assertEqual(reply["exit"], 0, reply["output"])
                output = reply["output"]
                self.assertEqual(output.count("Save this key on this machine? [Y/n]: "), len(choices))
                self.assertEqual(output.count("Enter y or n."), len(choices) - 1)
                self.assertNotIn("Remember API key locally", output)
                self.assertEqual(reply["savedEndpoints"], [GATEWAY] if kept else [])
                self.assertEqual("Gateway and key remembered locally." in output, kept)
                self.assertIn("LAUNCHED", output)
        # --remember-key saves it without asking.
        reply = self.run_launcher(args=["--login", "--no-browser", "--model", "coder", "--remember-key"], noCatalogue=1,
                                  eragon=fixture, expectStorage=True)
        self.assertEqual(reply["exit"], 0, reply["output"])
        self.assertNotIn("Save this key on this machine", reply["output"])
        self.assertEqual(reply["savedEndpoints"], [GATEWAY])


if __name__ == "__main__":
    unittest.main()
