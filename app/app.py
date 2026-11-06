"""Pocket Lab: intentionally vulnerable, single-player, local training application.

Every intended weakness has a LAB-VULN comment. Container isolation is separate
from these deliberate application flaws. No command execution or external plugins.
"""
import argparse
import base64
import hashlib
import html
import json
import os
import secrets
import sqlite3
import threading
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from contextlib import contextmanager
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from catalog import BY_ID, CHALLENGES, TOP10

ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
FLAGS = {cid: f"FLAG{{pocket_{cid}_practice}}" for cid in BY_ID}
MAX_BODY = 65536


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def b64(value):
    return base64.b64encode(json.dumps(value, ensure_ascii=False).encode()).decode()


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Lab:
    def __init__(self, data_dir, internal_port=9091):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "lab.sqlite3"
        self.lock = threading.RLock()
        self.internal_port = internal_port
        self.init_db()

    @contextmanager
    def db(self):
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    def init_db(self, reset=False):
        with self.lock, self.db() as db:
            if reset:
                # Only lab tables are reset. No filesystem deletion or shell commands.
                for table in ("sessions", "orders", "reviews", "coupon_uses", "solved", "audit", "settings", "products", "users"):
                    db.execute(f"DROP TABLE IF EXISTS {table}")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT,
                  nickname TEXT, role TEXT, email TEXT, wallet INTEGER);
                CREATE TABLE IF NOT EXISTS products (
                  id INTEGER PRIMARY KEY, name TEXT, price INTEGER, icon TEXT, description TEXT);
                CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id));
                CREATE TABLE IF NOT EXISTS orders (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id),
                  product_id INTEGER REFERENCES products(id), quantity INTEGER,
                  unit_price INTEGER, total INTEGER, status TEXT, paid INTEGER DEFAULT 0,
                  refund_count INTEGER DEFAULT 0, address TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT);
                CREATE TABLE IF NOT EXISTS coupon_uses (user_id INTEGER, code TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS solved (id TEXT PRIMARY KEY, solved_at TEXT);
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, event TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            """)
            if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                return
            db.executemany("INSERT INTO users VALUES (?,?,?,?,?,?,?)", [
                (1, "alice", "Alice123!", "Alice", "user", "alice@example.lab", 100000),
                (2, "bob", "Bob123!", "Bob", "user", "bob@example.lab", 100000),
                (3, "admin", "Admin123!", "管理员", "admin", "admin@example.lab", 100000),
            ])
            db.executemany("INSERT INTO products VALUES (?,?,?,?,?)", [
                (1, "云朵机械键盘", 29900, "keyboard", "轻盈手感 / 奶油配色 / 桌面常驻"),
                (2, "口袋随行杯", 8900, "cup", "保温 6 小时 / 350ml / 练习搭子"),
                (3, "像素桌面灯", 15900, "lamp", "暖光三档 / 随心调节 / 夜间模式"),
            ])
            db.executemany("INSERT INTO orders (id,user_id,product_id,quantity,unit_price,total,status,paid,address,created) VALUES (?,?,?,?,?,?,?,?,?,?)", [
                (1001, 1, 2, 1, 8900, 8900, "paid", 8900, "靶场城 1 号（虚构）", now()),
                (1002, 2, 1, 1, 29900, 29900, "paid", 29900, "Bob 的虚构私人地址 · LAB-ONLY", now()),
            ])
            db.executemany("INSERT INTO settings VALUES (?,?)", [("failed_logins", "0"), ("plugin_discount", "0")])
            db.execute("INSERT INTO audit (event,created) VALUES (?,?)", ("lab_initialized", now()))

    def solve(self, db, cid):
        db.execute("INSERT OR IGNORE INTO solved VALUES (?,?)", (cid, now()))
        return FLAGS[cid]


class InternalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metadata":
            self.send_error(404)
            return
        body = json.dumps({"service": "lab-only-metadata", "fake_cloud_key": "DEMO-NOT-A-REAL-KEY", "flag": FLAGS["ssrf"]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "PocketLab/1.0"

    @property
    def lab(self):
        return self.server.lab

    def log_message(self, fmt, *args):
        # Access logs are intentionally not structured security events (audit task).
        if os.getenv("LAB_QUIET") != "1":
            print(f"[access] {self.address_string()} {fmt % args}", flush=True)

    def send(self, status, value, content_type="application/json; charset=utf-8", headers=None):
        body = json.dumps(value, ensure_ascii=False).encode() if content_type.startswith("application/json") else value.encode() if isinstance(value, str) else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, val in headers or []:
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError(400, "无效 Content-Length")
        if size < 0 or size > MAX_BODY:
            raise ApiError(413, "请求体上限 64 KiB")
        raw = self.rfile.read(size).decode("utf-8")
        try:
            if "application/x-www-form-urlencoded" in self.headers.get("Content-Type", ""):
                return {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
            value = json.loads(raw or "{}")
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeError):
            raise ApiError(400, "请提交 JSON 对象")

    def cookies(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            pass
        return {k: v.value for k, v in cookie.items()}

    def user(self, db, required=True):
        row = db.execute("SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=?", (self.cookies().get("sid", ""),)).fetchone()
        if required and not row:
            raise ApiError(401, "请先登录演示账号")
        return dict(row) if row else None

    def own_order(self, db, oid, uid):
        row = db.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (oid, uid)).fetchone()
        if not row:
            raise ApiError(404, "订单不存在或不属于当前账号")
        return dict(row)

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def dispatch(self):
        try:
            parts = urllib.parse.urlsplit(self.path)
            path = parts.path
            query = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query, keep_blank_values=True).items()}
            if self.command == "GET" and path in ("/", "/static/style.css", "/static/app.js"):
                filename, ctype = {
                    "/": ("index.html", "text/html; charset=utf-8"),
                    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
                    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
                }[path]
                return self.send(200, (ROOT / "static" / filename).read_bytes(), ctype)
            data = self.body() if self.command == "POST" else {}
            with self.lab.lock, self.lab.db() as db:
                result = self.route(db, self.command, path, query, data)
            if result is not None:
                self.send(200, result)
        except ApiError as exc:
            self.send(exc.status, {"error": exc.message})
        except (ValueError, TypeError, KeyError, sqlite3.Error) as exc:
            self.send(400, {"error": "参数无效", "detail": str(exc)[:300]})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            self.send(500, {"error": "靶场内部异常，请查看容器日志"})

    def route(self, db, method, path, q, data):
        if method == "GET" and path == "/health":
            db.execute("SELECT 1")
            return {"status": "ok", "version": VERSION}
        if method == "GET" and path == "/robots.txt":
            self.send(200, "User-agent: *\nDisallow: /debug\nDisallow: /api/legacy-template\n", "text/plain; charset=utf-8")
            return
        if method == "GET" and path == "/api/challenges":
            solved = {r["id"]: r["solved_at"] for r in db.execute("SELECT * FROM solved")}
            items = [{k: v for k, v in c.items() if k not in ("solution", "fix")} | {"solved": c["id"] in solved, "solved_at": solved.get(c["id"])} for c in CHALLENGES]
            return {"items": items, "categories": TOP10, "solved": len(solved), "total": len(items), "single_player": True}
        if method == "GET" and path == "/api/me":
            user = self.user(db, False)
            if user:
                user.pop("password")
            return {"user": user, "version": VERSION, "internal_preview_url": f"http://127.0.0.1:{self.lab.internal_port}/metadata"}
        if method == "POST" and path == "/api/login":
            username, password = str(data.get("username", "")), str(data.get("password", ""))
            # LAB-VULN sqli: intentionally concatenated credentials.
            sql = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
            row = db.execute(sql).fetchone()
            if not row:
                # LAB-VULN audit: metric increments without any security event/alert.
                db.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='failed_logins'")
                # Return explicitly so the failed-login counter is committed.
                self.send(401, {"error": "用户名或密码错误"})
                return
            token = secrets.token_urlsafe(24)
            db.execute("INSERT INTO sessions VALUES (?,?)", (token, row["id"]))
            exact = db.execute("SELECT id FROM users WHERE username=? AND password=?", (username, password)).fetchone()
            result = {"message": "登录成功", "username": row["username"]}
            if not exact:
                result["flag"] = self.lab.solve(db, "sqli")
            self.send(200, result, headers=[("Set-Cookie", f"sid={token}; Path=/; HttpOnly; SameSite=Lax"), ("Set-Cookie", f"profile={b64({'role': row['role']})}; Path=/; SameSite=Lax")])
            return
        if method == "POST" and path == "/api/logout":
            db.execute("DELETE FROM sessions WHERE token=?", (self.cookies().get("sid", ""),))
            self.send(200, {"message": "已退出"}, headers=[("Set-Cookie", "sid=; Path=/; Max-Age=0"), ("Set-Cookie", "profile=; Path=/; Max-Age=0")])
            return
        if method == "POST" and path == "/api/lab/reset":
            if data.get("confirm") != "RESET":
                raise ApiError(400, "重置需提交 confirm=RESET")
            # Close this transaction before opening the reset transaction.
            db.commit()
            self.lab.init_db(reset=True)
            self.send(200, {"message": "已恢复全部虚构数据；请重新登录"}, headers=[("Set-Cookie", "sid=; Path=/; Max-Age=0"), ("Set-Cookie", "profile=; Path=/; Max-Age=0")])
            return
        if method == "POST" and path == "/api/submit":
            flag = str(data.get("flag", "")).strip()
            cid = next((k for k, v in FLAGS.items() if secrets.compare_digest(flag, v)), None)
            if not cid:
                raise ApiError(400, "FLAG 不正确")
            return {"message": "通关记录已保存", "id": cid, "flag": self.lab.solve(db, cid)}
        if method == "GET" and path == "/debug":
            # LAB-VULN debug: public secrets and a plaintext demo backup.
            return {"debug": True, "demo_secret": "lab-only-do-not-use", "database": str(self.lab.db_path), "backup": [dict(r) for r in db.execute("SELECT * FROM users")], "flag": self.lab.solve(db, "debug")}
        if method == "GET" and path == "/api/products":
            return {"items": [dict(r) for r in db.execute("SELECT * FROM products")]}
        if method == "GET" and path == "/api/legacy-template":
            # LAB-VULN component: the bundled LegacyTemplate 0.1-demo trusts paths.
            # The outer fixtures boundary protects host/container files, not the template root.
            fixture_root = (ROOT / "fixtures").resolve()
            target = (fixture_root / "templates" / q.get("name", "welcome.txt")).resolve()
            if not target.is_relative_to(fixture_root) or not target.is_file():
                raise ApiError(400, "教学沙箱只允许读取 fixtures 中的虚构文件")
            result = {"component": "LegacyTemplate 0.1-demo (自制教学组件，无对应 CVE)", "content": target.read_text(encoding="utf-8")}
            if not target.is_relative_to(fixture_root / "templates"):
                result["flag"] = self.lab.solve(db, "component")
            return result
        if method == "POST" and path == "/api/reset/request":
            return {"message": "模拟重置通知已生成", "reset_id": secrets.token_hex(12), "next": "/api/reset/confirm"}
        if method == "POST" and path == "/api/reset/confirm":
            # LAB-VULN reset: no reset token validation.
            username = str(data.get("username", ""))
            password = str(data.get("new_password", ""))
            if not 1 <= len(password) <= 100:
                raise ApiError(400, "新密码长度为 1 至 100")
            target = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not target:
                raise ApiError(404, "演示账号不存在")
            user = self.user(db, False)
            db.execute("UPDATE users SET password=? WHERE username=?", (password, username))
            result = {"message": "密码已重置"}
            if not user or user["id"] != target["id"]:
                result["flag"] = self.lab.solve(db, "reset")
            return result
        if method == "GET" and path == "/api/audit/status":
            failures = int(db.execute("SELECT value FROM settings WHERE key='failed_logins'").fetchone()[0])
            events = [dict(r) for r in db.execute("SELECT * FROM audit")]
            result = {"failed_logins": failures, "security_events": 0, "alerts": 0, "events": events}
            if failures >= 5:
                result["flag"] = self.lab.solve(db, "audit")
            return result
        if method == "GET" and path == "/reviews":
            # LAB-VULN xss: user-controlled content is inserted without escaping.
            rows = db.execute("SELECT r.content,u.nickname FROM reviews r JOIN users u ON u.id=r.user_id ORDER BY r.id DESC").fetchall()
            messages = "".join(f"<article><strong>{html.escape(r['nickname'])}</strong><div>{r['content']}</div></article>" for r in rows)
            page = f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>商品留言 · Pocket Lab</title><link rel="stylesheet" href="/static/style.css"><main class="review-page"><a href="/">← 返回靶场</a><h1>商品留言</h1><p>此页用于存储型 XSS 练习；证明请求执行后返回首页查看进度。</p>{messages or "<p>暂时没有留言。</p>"}</main></html>'
            self.send(200, page, "text/html; charset=utf-8")
            return

        user = self.user(db)
        uid = user["id"]
        if method == "POST" and path == "/api/xss-proof":
            return {"message": "浏览器证明请求已收到（本靶场不提供防作弊）", "flag": self.lab.solve(db, "xss")}
        if method == "POST" and path == "/api/profile":
            # LAB-VULN mass: all model attributes, including role, are writable.
            for field in ("nickname", "email", "role"):
                if field in data:
                    db.execute(f"UPDATE users SET {field}=? WHERE id=?", (str(data[field])[:200], uid))
            result = {"message": "资料已更新"}
            if user["role"] != "admin" and data.get("role") == "admin":
                result["flag"] = self.lab.solve(db, "mass")
            return result
        if method == "GET" and path == "/api/profile/email":
            # LAB-VULN csrf: mutating GET, no token or Origin verification.
            email = q.get("email", "")[:150]
            if "@" not in email:
                raise ApiError(400, "请输入邮箱")
            db.execute("UPDATE users SET email=? WHERE id=?", (email, uid))
            result = {"message": "邮箱已更新", "email": email}
            if email.endswith("@attacker.lab"):
                result["flag"] = self.lab.solve(db, "csrf")
            return result
        if method == "GET" and path == "/api/vip":
            # LAB-VULN cookie: unsigned client data used for authorization.
            try:
                profile = json.loads(base64.b64decode(self.cookies().get("profile", "")))
            except Exception:
                raise ApiError(400, "profile Cookie 不是有效的 Base64 JSON")
            if isinstance(profile, dict) and profile.get("role") == "admin":
                return {"tier": "admin", "flag": self.lab.solve(db, "cookie")}
            return {"tier": "standard", "message": "当前会员没有管理权益"}
        if method == "GET" and path == "/api/preview":
            url = q.get("url", "")
            parsed = urllib.parse.urlsplit(url)
            # Outer teaching sandbox: real HTTP, only this app's fake internal server.
            if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port != self.lab.internal_port or parsed.path != "/metadata" or parsed.username or parsed.password:
                raise ApiError(400, f"出口沙箱仅开放 http://127.0.0.1:{self.lab.internal_port}/metadata")
            # LAB-VULN ssrf: ordinary customer can proxy a privileged internal API.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url, timeout=3) as response:
                payload = json.loads(response.read(8192))
            return {"preview": payload, "flag": self.lab.solve(db, "ssrf")}
        if method == "POST" and path == "/api/plugins/install":
            # LAB-VULN supply: trust unsigned, unreviewed declarative plugin rules.
            discount = int(data.get("discount_percent", 0))
            if not 0 <= discount <= 100:
                raise ApiError(400, "折扣范围 0 至 100")
            db.execute("UPDATE settings SET value=? WHERE key='plugin_discount'", (str(discount),))
            return {"message": "未验证的规则已启用（本地清单演示，不执行代码）", "discount_percent": discount, "flag": self.lab.solve(db, "supply")}
        if method == "GET" and path == "/api/exports/customers":
            # LAB-VULN crypto: reversible encoding called encryption; fast MD5.
            rows = [{"username": r["username"], "password_md5": hashlib.md5(r["password"].encode()).hexdigest(), "fake_id": f"DEMO-{r['id']:04d}"} for r in db.execute("SELECT * FROM users")]
            return {"scheme": "base64", "ciphertext": b64({"customers": rows, "recovery_note": FLAGS["crypto"]})}
        if method == "GET" and path == "/api/orders":
            return {"items": [dict(r) for r in db.execute("SELECT o.*,p.name FROM orders o JOIN products p ON p.id=o.product_id WHERE o.user_id=? ORDER BY o.id DESC", (uid,))]}
        if method == "GET" and path.startswith("/api/orders/") and path.count("/") == 3:
            oid = int(path.rsplit("/", 1)[1])
            # LAB-VULN idor: missing ownership constraint on detail view.
            row = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
            if not row:
                raise ApiError(404, "订单不存在")
            result = dict(row)
            if row["user_id"] != uid:
                result["flag"] = self.lab.solve(db, "idor")
            return result
        if method == "POST" and path == "/api/orders":
            product = db.execute("SELECT * FROM products WHERE id=?", (int(data.get("product_id", 1)),)).fetchone()
            if not product:
                raise ApiError(404, "商品不存在")
            # LAB-VULN price/negative: client supplies price; quantity may be negative.
            quantity = int(data.get("quantity", 1))
            price = int(data.get("unit_price_cents", product["price"]))
            if not -100 <= quantity <= 100 or not 0 <= price <= 1000000:
                raise ApiError(400, "练习资源范围：数量 -100 至 100，单价 0 至 1000000 分")
            discount = int(db.execute("SELECT value FROM settings WHERE key='plugin_discount'").fetchone()[0])
            total = price * quantity * (100 - discount) // 100
            order_id = db.execute("INSERT INTO orders (user_id,product_id,quantity,unit_price,total,status,address,created) VALUES (?,?,?,?,?,'pending',?,?)", (uid, product["id"], quantity, price, total, "练习订单虚构地址", now())).lastrowid
            flags = []
            if quantity > 0 and price < product["price"]:
                flags.append(self.lab.solve(db, "price"))
            if quantity < 0:
                db.execute("UPDATE users SET wallet=wallet-? WHERE id=?", (total, uid))
                flags.append(self.lab.solve(db, "negative"))
            return {"order_id": order_id, "total_cents": total, "status": "pending", "flags": flags}
        if method == "POST" and path == "/api/coupons/redeem":
            if data.get("code") != "WELCOME50":
                raise ApiError(400, "优惠券无效")
            # LAB-VULN coupon: no uniqueness or one-time-use check.
            db.execute("INSERT INTO coupon_uses VALUES (?,?,?)", (uid, "WELCOME50", now()))
            db.execute("UPDATE users SET wallet=wallet+5000 WHERE id=?", (uid,))
            count = db.execute("SELECT COUNT(*) FROM coupon_uses WHERE user_id=?", (uid,)).fetchone()[0]
            result = {"message": "已到账 50 元", "redeem_count": count}
            if count >= 2:
                result["flag"] = self.lab.solve(db, "coupon")
            return result
        if method == "POST" and path == "/api/risk/check":
            try:
                score = int(data.get("risk_score", 0))
                return {"approved": score < 80, "reason": "常规评分", "score": score}
            except (ValueError, TypeError):
                # LAB-VULN failopen: parser/service failure defaults to approval.
                return {"approved": True, "reason": "风控异常，默认放行", "flag": self.lab.solve(db, "failopen")}
        if method == "POST" and path == "/api/payments/callback":
            order = self.own_order(db, int(data.get("order_id", 0)), uid)
            if data.get("status") != "paid":
                raise ApiError(400, "回调状态应为 paid")
            paid = int(data.get("amount_cents", 0))
            # LAB-VULN payment: unauthenticated gateway origin and no amount matching.
            db.execute("UPDATE orders SET status='paid',paid=? WHERE id=?", (paid, order["id"]))
            result = {"message": "回调已接收", "status": "paid"}
            if paid < order["total"]:
                result["flag"] = self.lab.solve(db, "payment")
            return result
        if method == "POST" and path.startswith("/api/orders/"):
            parts = path.split("/")
            if len(parts) != 5 or parts[4] not in ("pay", "ship", "refund"):
                raise ApiError(404, "接口不存在")
            order = self.own_order(db, int(parts[3]), uid)
            action = parts[4]
            if action == "pay":
                if order["status"] != "pending" or order["total"] <= 0:
                    raise ApiError(409, "正常模拟支付要求正金额待付款订单")
                if user["wallet"] < order["total"]:
                    raise ApiError(409, "钱包余额不足")
                db.execute("UPDATE users SET wallet=wallet-? WHERE id=?", (order["total"], uid))
                db.execute("UPDATE orders SET status='paid',paid=? WHERE id=?", (order["total"], order["id"]))
                return {"message": "模拟支付完成", "paid_cents": order["total"]}
            if action == "ship":
                # LAB-VULN workflow: shipping does not require a successful payment.
                db.execute("UPDATE orders SET status='shipped' WHERE id=?", (order["id"],))
                result = {"message": "已模拟发货", "status": "shipped"}
                if order["status"] == "pending":
                    result["flag"] = self.lab.solve(db, "workflow")
                return result
            if order["paid"] <= 0:
                raise ApiError(409, "请先完成正常模拟支付")
            # LAB-VULN refund: refunded state and total refund are never checked.
            db.execute("UPDATE users SET wallet=wallet+? WHERE id=?", (order["paid"], uid))
            db.execute("UPDATE orders SET status='refunded',refund_count=refund_count+1 WHERE id=?", (order["id"],))
            result = {"message": "退款已到账", "refund_cents": order["paid"], "refund_count": order["refund_count"] + 1}
            if order["refund_count"] >= 1:
                result["flag"] = self.lab.solve(db, "refund")
            return result
        if method == "POST" and path == "/api/reviews":
            content = str(data.get("content", ""))[:4000]
            db.execute("INSERT INTO reviews (user_id,content) VALUES (?,?)", (uid, content))
            return {"message": "留言已保存；在独立留言页查看", "url": "/reviews"}
        raise ApiError(404, "接口不存在")


def create_servers(data_dir, host="127.0.0.1", port=8080, internal_port=9091):
    internal = ThreadingHTTPServer(("127.0.0.1", internal_port), InternalHandler)
    try:
        lab = Lab(data_dir, internal.server_port)
        public = ThreadingHTTPServer((host, port), Handler)
        public.lab = lab
        return public, internal
    except Exception:
        internal.server_close()
        raise


def main():
    parser = argparse.ArgumentParser(description="本地 OWASP 漏洞教学靶场")
    parser.add_argument("--host", default=os.getenv("LAB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("LAB_PORT", "8080")))
    parser.add_argument("--internal-port", type=int, default=int(os.getenv("LAB_INTERNAL_PORT", "9091")))
    parser.add_argument("--data", default=os.getenv("LAB_DATA_DIR", str(ROOT.parent / "data")))
    args = parser.parse_args()
    public, internal = create_servers(args.data, args.host, args.port, args.internal_port)
    thread = threading.Thread(target=internal.serve_forever, daemon=True)
    thread.start()
    print(f"Pocket Lab {VERSION}: http://{args.host}:{public.server_port} · local training only", flush=True)
    try:
        public.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        public.server_close()
        internal.shutdown()
        internal.server_close()


if __name__ == "__main__":
    main()
