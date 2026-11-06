"""HTTP integration checks. LAB_TEST_URL targets an isolated disposable container.
These tests intentionally RESET that instance between tests. Never target shared data.
"""
import base64
import http.cookiejar
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from app import create_servers
from catalog import CHALLENGES


class LabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.remote = os.getenv("LAB_TEST_URL")
        if cls.remote:
            cls.base = cls.remote.rstrip("/")
        else:
            cls.temp = tempfile.TemporaryDirectory()
            cls.public, cls.internal = create_servers(cls.temp.name, port=0, internal_port=0)
            for server in (cls.public, cls.internal):
                threading.Thread(target=server.serve_forever, daemon=True).start()
            cls.base = f"http://127.0.0.1:{cls.public.server_port}"

    @classmethod
    def tearDownClass(cls):
        if not cls.remote:
            for server in (cls.public, cls.internal):
                server.shutdown()
                server.server_close()
            cls.temp.cleanup()

    def setUp(self):
        self.jar = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.jar))
        self.call("/api/lab/reset", {"confirm": "RESET"})

    def call(self, path, data=None, status=200, headers=None):
        request = urllib.request.Request(self.base + path,
                    data=json.dumps(data).encode() if data is not None else None,
                    headers={"Content-Type": "application/json", **(headers or {})})
        try:
            response = self.client.open(request, timeout=8)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            self.assertEqual(response.status, status, path)
            raw = response.read().decode()
            return json.loads(raw) if "application/json" in response.headers.get("Content-Type", "") else raw

    def login(self, username="alice", password="Alice123!"):
        return self.call("/api/login", {"username": username, "password": password})

    def order(self, **values):
        return self.call("/api/orders", {"product_id": 1, "quantity": 1, **values})["order_id"]

    def wallet(self):
        return self.call("/api/me")["user"]["wallet"]

    def solved(self):
        return {c["id"] for c in self.call("/api/challenges")["items"] if c["solved"]}

    def test_01_catalog_covers_2025_and_2021(self):
        data = self.call("/api/challenges")
        self.assertEqual(data["total"], 20)
        self.assertEqual({c["category"] for c in data["items"]}, {f"A{i:02}" for i in range(1, 11)})
        self.assertEqual({c["owasp2021"] for c in CHALLENGES} - {"—"}, {f"A{i:02}" for i in range(1, 11)})
        self.assertNotIn("solution", data["items"][0])
        self.assertNotIn("FLAG{", json.dumps(data))

    def test_02_pages_health_and_static(self):
        self.assertEqual(self.call("/health")["status"], "ok")
        self.assertIn("口袋漏洞靶场", self.call("/"))
        self.assertIn(".hero", self.call("/static/style.css"))
        self.assertIn("use strict", self.call("/static/app.js"))

    def test_03_authentication_and_logout(self):
        self.call("/api/orders", status=401)
        self.login()
        self.assertEqual(self.call("/api/me")["user"]["username"], "alice")
        self.assertNotIn("password", self.call("/api/me")["user"])
        self.call("/api/logout", {})
        self.assertIsNone(self.call("/api/me")["user"])

    def test_04_idor_returns_other_users_private_order(self):
        self.login()
        mine = self.call("/api/orders")["items"]
        self.assertEqual([o["id"] for o in mine], [1001])
        data = self.call("/api/orders/1002")
        self.assertEqual(data["user_id"], 2)
        self.assertIn("Bob", data["address"])
        self.assertIn("idor", self.solved())

    def test_05_mass_assignment_changes_role(self):
        self.login()
        self.call("/api/profile", {"nickname": "Test"})
        self.assertNotIn("mass", self.solved())
        self.call("/api/profile", {"role": "admin"})
        self.assertEqual(self.call("/api/me")["user"]["role"], "admin")
        self.assertIn("mass", self.solved())

    def test_06_ssrf_is_real_http_but_limited_to_internal_fixture(self):
        self.login()
        url = self.call("/api/me")["internal_preview_url"]
        data = self.call("/api/preview?" + urllib.parse.urlencode({"url": url}))
        self.assertEqual(data["preview"]["service"], "lab-only-metadata")
        self.assertIn("ssrf", self.solved())
        for forbidden in ("http://example.com", "file:///etc/passwd", "http://127.0.0.1:22/metadata", "http://169.254.169.254/metadata"):
            self.call("/api/preview?" + urllib.parse.urlencode({"url": forbidden}), status=400)

    def test_07_debug_exposes_demo_passwords_without_login(self):
        self.assertIn("/debug", self.call("/robots.txt"))
        data = self.call("/debug")
        self.assertEqual(data["backup"][0]["password"], "Alice123!")
        self.assertIn("debug", self.solved())

    def test_08_unsigned_plugin_changes_checkout(self):
        self.login()
        before = self.call("/api/orders", {"product_id": 1, "quantity": 1})
        self.call("/api/plugins/install", {"name": "evil-demo", "verified": False, "source": "untrusted.lab", "discount_percent": 100})
        after = self.call("/api/orders", {"product_id": 1, "quantity": 1})
        self.assertEqual(before["total_cents"], 29900)
        self.assertEqual(after["total_cents"], 0)
        self.assertIn("supply", self.solved())

    def test_09_base64_export_leaks_recoverable_data(self):
        self.login()
        data = self.call("/api/exports/customers")
        self.assertNotIn("crypto", self.solved())
        decoded = json.loads(base64.b64decode(data["ciphertext"]))
        self.assertEqual(decoded["customers"][0]["username"], "alice")
        self.call("/api/submit", {"flag": decoded["recovery_note"]})
        self.assertIn("crypto", self.solved())

    def test_10_sql_injection_bypasses_password(self):
        self.call("/api/login", {"username": "alice", "password": "wrong"}, status=401)
        data = self.login("alice' -- ", "wrong")
        self.assertEqual(data["username"], "alice")
        self.assertIn("sqli", self.solved())

    def test_11_stored_xss_is_unescaped_not_auto_marked(self):
        self.login()
        payload = '<img src=x onerror="fetch(\'/api/xss-proof\',{method:\'POST\'})">'
        self.call("/api/reviews", {"content": payload})
        page = self.call("/reviews")
        self.assertIn(payload, page)
        self.assertNotIn("xss", self.solved())
        # This checks the proof endpoint, not JavaScript execution. Browser check is separate.
        self.call("/api/xss-proof", {})
        self.assertIn("xss", self.solved())

    def test_12_client_price_changes_real_order_total(self):
        self.login()
        data = self.call("/api/orders", {"product_id": 1, "quantity": 1, "unit_price_cents": 1})
        self.assertEqual(data["total_cents"], 1)
        self.assertEqual(self.call(f"/api/orders/{data['order_id']}")["total"], 1)
        self.assertIn("price", self.solved())

    def test_13_negative_quantity_increases_wallet(self):
        self.login()
        before = self.wallet()
        self.order(quantity=-1)
        self.assertEqual(self.wallet() - before, 29900)
        self.assertIn("negative", self.solved())

    def test_14_coupon_replay_increases_balance_twice(self):
        self.login()
        before = self.wallet()
        self.call("/api/coupons/redeem", {"code": "WELCOME50"})
        self.assertNotIn("coupon", self.solved())
        self.call("/api/coupons/redeem", {"code": "WELCOME50"})
        self.assertEqual(self.wallet() - before, 10000)
        self.assertIn("coupon", self.solved())

    def test_15_password_reset_without_token_takes_over_bob(self):
        self.login()
        self.call("/api/reset/confirm", {"username": "bob", "new_password": "Changed123!"})
        self.login("bob", "Changed123!")
        self.assertEqual(self.call("/api/me")["user"]["username"], "bob")
        self.assertIn("reset", self.solved())

    def test_16_unsigned_cookie_grants_admin_vip(self):
        self.login()
        self.assertEqual(self.call("/api/vip")["tier"], "standard")
        for cookie in self.jar:
            if cookie.name == "profile":
                cookie.value = "eyJyb2xlIjoiYWRtaW4ifQ=="
        self.assertEqual(self.call("/api/vip")["tier"], "admin")
        self.assertEqual(self.call("/api/me")["user"]["role"], "user")
        self.assertIn("cookie", self.solved())

    def test_17_failed_logins_have_no_security_audit(self):
        for _ in range(5):
            self.call("/api/login", {"username": "alice", "password": "wrong"}, status=401)
        data = self.call("/api/audit/status")
        self.assertEqual(data["failed_logins"], 5)
        self.assertEqual(data["security_events"], 0)
        self.assertEqual(data["alerts"], 0)
        self.assertIn("audit", self.solved())

    def test_18_exception_bypasses_risk_rejection(self):
        self.login()
        self.assertFalse(self.call("/api/risk/check", {"risk_score": 99})["approved"])
        self.assertNotIn("failopen", self.solved())
        self.assertTrue(self.call("/api/risk/check", {"risk_score": "timeout"})["approved"])
        self.assertIn("failopen", self.solved())

    def test_19_forged_callback_marks_high_price_order_paid(self):
        self.login()
        oid = self.order()
        self.call("/api/payments/callback", {"order_id": oid, "status": "paid", "amount_cents": 1})
        order = self.call(f"/api/orders/{oid}")
        self.assertEqual(order["status"], "paid")
        self.assertEqual(order["paid"], 1)
        self.assertEqual(order["total"], 29900)
        self.assertIn("payment", self.solved())

    def test_20_shipping_skips_payment(self):
        self.login()
        oid = self.order()
        self.call(f"/api/orders/{oid}/ship", {})
        order = self.call(f"/api/orders/{oid}")
        self.assertEqual(order["status"], "shipped")
        self.assertEqual(order["paid"], 0)
        self.assertIn("workflow", self.solved())

    def test_21_refund_replay_credits_balance_twice(self):
        self.login()
        before = self.wallet()
        oid = self.order()
        self.call(f"/api/orders/{oid}/pay", {})
        self.assertEqual(self.wallet(), before - 29900)
        self.call(f"/api/orders/{oid}/refund", {})
        self.assertEqual(self.wallet(), before)
        self.assertNotIn("refund", self.solved())
        self.call(f"/api/orders/{oid}/refund", {})
        self.assertEqual(self.wallet(), before + 29900)
        self.assertIn("refund", self.solved())

    def test_22_mutating_get_needs_no_csrf_token(self):
        self.login()
        self.call("/api/profile/email?email=alice%40attacker.lab", headers={"Origin": "http://external.example"})
        self.assertEqual(self.call("/api/me")["user"]["email"], "alice@attacker.lab")
        self.assertIn("csrf", self.solved())

    def test_23_legacy_component_traversal_stays_in_fixture_boundary(self):
        self.assertIn("正常的模板目录", self.call("/api/legacy-template?name=welcome.txt")["content"])
        self.assertNotIn("component", self.solved())
        self.assertIn("bob@example.lab", self.call("/api/legacy-template?name=../customers-demo.csv")["content"])
        self.assertIn("component", self.solved())
        for path in ("../../../app.py", "/etc/passwd", "../../../../Windows/win.ini"):
            self.call("/api/legacy-template?" + urllib.parse.urlencode({"name": path}), status=400)

    def test_24_reset_restores_passwords_balance_and_progress(self):
        self.login()
        old_session = next(c.value for c in self.jar if c.name == "sid")
        self.call("/api/coupons/redeem", {"code": "WELCOME50"})
        self.call("/debug")
        self.order(quantity=-1)
        self.call("/api/lab/reset", {"confirm": "RESET"})
        self.assertIsNone(self.call("/api/me", headers={"Cookie": "sid=" + old_session})["user"])
        self.assertEqual(self.call("/api/challenges")["solved"], 0)
        self.login()
        self.assertEqual(self.wallet(), 100000)
        self.assertEqual(len(self.call("/api/orders")["items"]), 1)
        self.assertEqual(self.call("/api/audit/status")["failed_logins"], 0)

    def test_25_order_action_owner_boundary_is_retained(self):
        self.login()
        self.call("/api/orders/1002/refund", {}, status=404)
        self.call("/api/orders/1002/pay", {}, status=404)

    def test_26_invalid_inputs_do_not_crash_server(self):
        self.call("/api/lab/reset", {}, status=400)
        self.call("/api/submit", {"flag": "invalid"}, status=400)
        self.login()
        self.call("/api/orders", {"product_id": 999}, status=404)
        self.call("/api/orders", {"quantity": 10000000}, status=400)
        self.call("/api/orders/1001/pay", {}, status=409)
        self.assertEqual(self.call("/health")["status"], "ok")

    def test_27_progress_is_shared_with_fresh_client(self):
        self.call("/debug")
        self.jar = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.jar))
        self.assertIn("debug", self.solved())


if __name__ == "__main__":
    os.environ["LAB_QUIET"] = "1"
    unittest.main(verbosity=2)
