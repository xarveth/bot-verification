"""Offline tests for the LinkForge-style security layer.

No network, no MongoDB, no Turnstile keys needed: Mongo is faked
in-memory and Turnstile's HTTP call is mocked. Run:
    SECRET_KEY=test-secret python3 -m unittest discover -s tests -v
"""
import io
import json
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("SECRET_KEY", "test-secret-for-tests-only")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import _common as sec  # noqa: E402


CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
EDGE_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")
FIREFOX_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
              "Gecko/20100101 Firefox/133.0")
SAFARI_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 "
             "Mobile/15E148 Safari/604.1")


class FakeCollection:
    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        self.docs.append(dict(doc))
        return mock.Mock(inserted_id=len(self.docs))

    def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None

    def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                for k, v in update.get("$set", {}).items():
                    doc[k] = v
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                if "$push" in update:
                    for k, v in update["$push"].items():
                        doc.setdefault(k, []).append(v)
                return mock.Mock(matched_count=1)
        return mock.Mock(matched_count=0)

    def count_documents(self, query):
        # Only the created_at $gte shape used by check_rate_limit.
        count = 0
        for doc in self.docs:
            ok = True
            for k, v in query.items():
                if isinstance(v, dict) and "$gte" in v:
                    if not (doc.get(k) and doc[k] >= v["$gte"]):
                        ok = False
                elif doc.get(k) != v:
                    ok = False
            if ok:
                count += 1
        return count

    def create_index(self, *args, **kwargs):
        return "idx"


class FakeDB(dict):
    def __getitem__(self, name):
        if name not in self:
            self[name] = FakeCollection()
        return super().__getitem__(name)


class ChromeGateTests(unittest.TestCase):
    def test_real_chrome_passes(self):
        ok, version, _ = sec.is_chrome(
            CHROME_UA, '"Google Chrome";v="131", "Chromium";v="131"')
        self.assertTrue(ok)
        self.assertEqual(version, "131")

    def test_missing_sec_ch_ua_blocked(self):
        # Real Chrome always sends Sec-CH-UA; Brave can hide behind a
        # Chrome-looking UA when that header is missing, so a missing
        # header must not pass (live Brave test, 2026-11-16).
        ok, _, reason = sec.is_chrome(CHROME_UA)
        self.assertFalse(ok)
        self.assertEqual(reason, "sec-ch-ua-missing")

    def test_brave_brands_blocked(self):
        ok, _, reason = sec.is_chrome(
            CHROME_UA,
            '"Brave";v="131", "Chromium";v="131", "Not-A.Brand";v="24"')
        self.assertFalse(ok)

    def test_edge_firefox_safari_blocked(self):
        for ua in (EDGE_UA, FIREFOX_UA, SAFARI_UA, "", None):
            ok, _, _ = sec.is_chrome(ua)
            self.assertFalse(ok, ua)

    def test_sec_ch_ua_google_chrome_passes(self):
        ok, _, _ = sec.is_chrome(
            CHROME_UA, '"Google Chrome";v="131", "Chromium";v="131"')
        self.assertTrue(ok)

    def test_sec_ch_ua_edge_blocked(self):
        ok, _, reason = sec.is_chrome(
            EDGE_UA, '"Microsoft Edge";v="131", "Chromium";v="131"')
        self.assertFalse(ok)

    def test_chrome_block_page_mentions_chrome(self):
        self.assertIn("Google Chrome", sec.chrome_block_page())


class ChallengeTests(unittest.TestCase):
    def test_correct_answer_passes_wrong_fails(self):
        challenge = {"q": "What is 5 + 3?", "a": ["6", "8"], "correct": "8"}
        token = sec.sign_challenge(challenge, "sess-1")
        self.assertIsNotNone(token)
        ok, _ = sec.verify_challenge_answer(token, "sess-1", "8")
        self.assertTrue(ok)
        ok, reason = sec.verify_challenge_answer(token, "sess-1", "6")
        self.assertFalse(ok)
        self.assertEqual(reason, "wrong-answer")

    def test_challenge_bound_to_session_and_tamperproof(self):
        challenge = {"q": "What is 5 + 3?", "a": ["6", "8"], "correct": "8"}
        token = sec.sign_challenge(challenge, "sess-1")
        ok, _ = sec.verify_challenge_answer(token, "sess-2", "8")
        self.assertFalse(ok)
        tampered = token[:-4] + "0000"
        ok, _ = sec.verify_challenge_answer(tampered, "sess-1", "8")
        self.assertFalse(ok)

    def test_generated_challenge_is_from_known_list(self):
        challenge = sec.generate_challenge()
        self.assertIn(challenge["q"],
                      [c["q"] for c in sec.CHALLENGES])
        self.assertIn(challenge["correct"], challenge["a"])


class SessionTrackingTests(unittest.TestCase):
    def setUp(self):
        self.fake_db = FakeDB()
        self._patch = mock.patch.object(sec, "get_db", return_value=self.fake_db)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_create_session_persists_and_hashes_ip(self):
        session = sec.create_session("123", "tok-abc", "iphash1",
                                     CHROME_UA, True, "131")
        self.assertTrue(session["_persisted"])
        stored = self.fake_db["verification_sessions"].docs[0]
        self.assertEqual(stored["user_id"], "123")
        self.assertEqual(stored["status"], "created")
        self.assertEqual(stored["ip_hash"], "iphash1")
        # Raw token / IP must never be stored in the session doc.
        self.assertNotIn("tok-abc", json.dumps(stored, default=str))

    def test_hash_ip_is_deterministic_and_not_raw(self):
        h1, h2 = sec.hash_ip("1.2.3.4"), sec.hash_ip("1.2.3.4")
        self.assertEqual(h1, h2)
        self.assertNotIn("1.2.3.4", h1)
        self.assertNotEqual(h1, sec.hash_ip("5.6.7.8"))

    def test_token_used_flow(self):
        self.assertFalse(sec.is_token_used("tok-abc"))
        sec.mark_token_used("tok-abc", "123", "sess-1", sec.now())
        self.assertTrue(sec.is_token_used("tok-abc"))

    def test_rate_limit_counts_sessions(self):
        for _ in range(10):
            sec.create_session("123", "t", "same-ip", CHROME_UA, True, "131")
        limited, per_min, _ = sec.check_rate_limit("same-ip")
        self.assertTrue(limited)
        self.assertEqual(per_min, 10)
        limited, _, _ = sec.check_rate_limit("other-ip")
        self.assertFalse(limited)

    def test_update_session_and_attempts(self):
        session = sec.create_session("123", "t", "ip", CHROME_UA, True, "131")
        sec.update_session(session["session_id"], {"status": "verified"},
                           event="verified")
        sec.bump_attempts(session["session_id"])
        stored = sec.get_session(session["session_id"])
        self.assertEqual(stored["status"], "verified")
        self.assertEqual(stored["attempts"], 1)
        self.assertEqual(stored["events"][-1]["event"], "verified")


class TurnstileTests(unittest.TestCase):
    def test_skipped_when_not_configured(self):
        # No TURNSTILE_* keys in this test env.
        self.assertFalse(sec.TURNSTILE_ENABLED)
        ok, detail = sec.verify_turnstile("anything")
        self.assertTrue(ok)
        self.assertEqual(detail, "skipped-not-configured")

    def test_missing_token_fails_when_enabled(self):
        with mock.patch.object(sec, "TURNSTILE_ENABLED", True), \
             mock.patch.object(sec, "TURNSTILE_SECRET_KEY", "secret"):
            ok, _ = sec.verify_turnstile("")
            self.assertFalse(ok)

    def test_siteverify_success_and_failure(self):
        def fake_urlopen(req, timeout=10):
            body = self._turnstile_body
            resp = mock.Mock()
            resp.read.return_value = json.dumps(body).encode()
            resp.__enter__ = lambda s: resp
            resp.__exit__ = lambda *a: False
            return resp

        with mock.patch.object(sec, "TURNSTILE_ENABLED", True), \
             mock.patch.object(sec, "TURNSTILE_SECRET_KEY", "secret"), \
             mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self._turnstile_body = {"success": True}
            ok, _ = sec.verify_turnstile("tok")
            self.assertTrue(ok)
            self._turnstile_body = {"success": False, "error-codes": ["invalid-input-response"]}
            ok, detail = sec.verify_turnstile("tok")
            self.assertFalse(ok)
            self.assertIn("invalid-input-response", detail)


class MiscTests(unittest.TestCase):
    def test_get_client_ip_prefers_forwarded_for(self):
        headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8", "X-Real-IP": "9.9.9.9"}
        self.assertEqual(sec.get_client_ip(headers), "1.2.3.4")

    def test_parse_cookies_and_session_cookie(self):
        cookies = sec.parse_cookies({"Cookie": "bv_session=abc123; other=x"})
        self.assertEqual(cookies["bv_session"], "abc123")
        header = sec.session_cookie_header("abc123")
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)
        self.assertIn("bv_session=abc123", header)

    def test_no_hardcoded_secret_fallback_in_common(self):
        # _common must not contain the old public default.
        path = os.path.join(os.path.dirname(__file__), "..", "api", "_common.py")
        with io.open(path, encoding="utf-8") as f:
            self.assertNotIn("nexora-verify-secret-2024", f.read())

    def test_verify_page_detects_brave_client_side(self):
        # Brave's desktop UA mimics Chrome, so the page must also
        # check navigator.brave.isBrave() and report it on submit.
        path = os.path.join(os.path.dirname(__file__), "..", "api", "verify.py")
        with io.open(path, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("navigator.brave", source)
        self.assertIn("is_brave", source)
        self.assertIn("client_brands", source)


if __name__ == "__main__":
    unittest.main()
