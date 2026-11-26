"""Run with unittest. SQLite by default; TEST_POSTGRES=1 uses an isolated PG schema."""
import base64
import io
import os
import sys
import unittest
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text

schema = None
admin_engine = None
if os.getenv("TEST_POSTGRES") == "1":
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    url = URL.create("postgresql+psycopg", username=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"), host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")), database=os.getenv("DB_NAME"))
    schema = "chat_test_" + uuid4().hex
    admin_engine = create_engine(url)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    os.environ["DATABASE_URL"] = url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
else:
    os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET_KEY"] = "automated-tests-only-" + uuid4().hex
os.environ["APP_ENV"] = "test"
from app import app, db
from models import User, AuthSession, Messages, Contact, RateLimit


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True)
        cls.context = app.app_context()
        cls.context.push()
        if schema:
            result = app.test_cli_runner().invoke(args=["migrate"])
            if result.exit_code:
                raise result.exception
        else:
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.engine.dispose()
        cls.context.pop()
        if schema:
            with admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin_engine.dispose()

    def setUp(self):
        db.session.remove()
        # Only isolated test storage is ever cleared.
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()
        self.a = app.test_client()
        self.b = app.test_client()
        self.c = app.test_client()

    def post(self, client, path, payload=None, method="POST", **kwargs):
        cookie = client.get_cookie("csrf_access_token")
        headers = {"X-CSRF-TOKEN": cookie.value} if cookie else {}
        return client.open(path, method=method, json=payload, headers=headers, **kwargs)

    def register(self, client, handle="alice", **overrides):
        data = dict(name=handle.title(), username=handle, email=f"{handle}@example.com", password="test-password-123", phone_no="", dob=None)
        data.update(overrides)
        return self.post(client, "/users/register", data)

    def login(self, client, name="alice", **overrides):
        data = dict(email=f"{name}@example.com", password="test-password-123")
        data.update(overrides)
        return self.post(client, "/users/login", data)

    def account(self, client, name="alice"):
        response = self.register(client, name)
        self.assertEqual(response.status_code, 201, response.json)
        uid = response.json["user_id"]
        self.assertEqual(self.login(client, name).status_code, 200)
        return uid

    def conversation(self):
        a = self.account(self.a)
        b = self.account(self.b, "bob")
        self.assertEqual(self.post(self.a, "/contacts", {"user_id": b}).status_code, 201)
        response = self.post(self.a, "/chats", {"user_id": b})
        self.assertEqual(response.status_code, 201, response.json)
        return a, b, response.json["chat_id"]

    def test_required_email_and_invalid_registration(self):
        for overrides in ({"email": ""}, {"email": None}, {"email": "invalid"}, {"name": []}, {"username": "!bad"}, {"phone_no": 123}, {"phone_no": "??????????"}, {"dob": "2026-02-30"}, {"dob": "2999-01-01"}, {"password": "short"}):
            response = self.register(self.a, **overrides)
            self.assertEqual(response.status_code, 400, (overrides, response.json))
        self.assertEqual(User.query.count(), 0)

    def test_signup_normalizes_optional_phone_and_hashes_password(self):
        self.assertEqual(self.register(self.a, phone_no="  ", email="ALICE@EXAMPLE.COM").status_code, 201)
        user = User.query.one()
        self.assertEqual(user.email, "alice@example.com")
        self.assertIsNone(user.phone_no)
        self.assertNotEqual(user.password, "test-password-123")
        self.assertEqual(self.login(self.a, email="ALICE@EXAMPLE.COM").status_code, 200)

    def test_case_insensitive_uniqueness(self):
        self.register(self.a)
        self.assertEqual(self.register(self.b, "bob", username="ALICE").status_code, 409)
        self.assertEqual(self.register(self.b, "bob", email="ALICE@EXAMPLE.COM").status_code, 409)

    def test_login_session_restore_logout_revokes_token(self):
        self.account(self.a)
        response = self.a.get("/users/me")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password", response.json)
        access = self.a.get_cookie("access_token_cookie").value
        self.assertIn("HttpOnly", next(value for value in self.login(self.b).headers.getlist("Set-Cookie") if value.startswith("access_token_cookie=")))
        self.assertEqual(self.post(self.a, "/users/logout").status_code, 200)
        self.assertEqual(self.a.get("/users/me").status_code, 401)
        self.a.set_cookie("access_token_cookie", access)
        self.assertEqual(self.a.get("/users/me").status_code, 401)
        self.assertEqual(self.b.get("/users/me").status_code, 200)

    def test_invalid_login_and_csrf(self):
        self.account(self.a)
        self.assertEqual(self.login(self.b, password="wrong-password").status_code, 401)
        self.assertEqual(self.a.put("/users/me", json={"name": "Changed"}).status_code, 401)
        self.assertEqual(self.b.get("/users/me").status_code, 401)

    def test_search_username_and_email_and_persistent_contacts(self):
        a = self.account(self.a)
        b = self.account(self.b, "bob")
        self.assertEqual(self.a.get("/users").json, {"users": []})
        for query in ("BOB", "bob@example.com", "@bob"):
            users = self.a.get("/users", query_string={"q": query}).json["users"]
            self.assertEqual([u["user_id"] for u in users], [b])
            self.assertNotIn("phone_no", users[0])
        self.assertEqual(self.a.get("/users?q=%25").json["users"], [])
        self.assertEqual(self.post(self.a, "/contacts", {"user_id": a}).status_code, 400)
        self.assertEqual(self.post(self.a, "/contacts", {"user_id": b}).status_code, 201)
        self.assertEqual(self.post(self.a, "/contacts", {"user_id": b}).status_code, 200)
        db.session.remove()
        self.assertEqual(self.a.get("/contacts").json["contacts"][0]["user_id"], b)
        self.assertEqual(self.b.get("/contacts").json["contacts"], [])
        self.assertEqual(self.post(self.a, f"/contacts/{b}", method="DELETE").status_code, 200)
        self.assertEqual(Contact.query.count(), 0)

    def test_profile_persistence_clear_optional_and_sensitive_changes(self):
        self.account(self.a)
        data = dict(name="Updated", username="updated.user", phone_no="1234567890", dob="2000-01-01", bio="My bio")
        self.assertEqual(self.post(self.a, "/users/me", data, method="PUT").status_code, 200)
        db.session.remove()
        user = self.a.get("/users/me").json
        self.assertEqual(user["bio"], "My bio")
        self.assertEqual(user["username"], "updated.user")
        self.assertEqual(self.post(self.a, "/users/me", {"phone_no": "", "dob": "", "bio": ""}, method="PUT").status_code, 200)
        self.assertIsNone(self.a.get("/users/me").json["dob"])
        self.assertEqual(self.post(self.a, "/users/me", {"email": "new@example.com"}, method="PUT").status_code, 400)
        self.assertEqual(self.post(self.a, "/users/me", {"email": "new@example.com", "current_password": "bad-password"}, method="PUT").status_code, 403)
        self.assertEqual(self.post(self.a, "/users/me", {"email": "new@example.com", "new_password": "new-password-123", "current_password": "test-password-123"}, method="PUT").status_code, 200)
        self.assertEqual(self.login(self.b, email="new@example.com", password="new-password-123").status_code, 200)

    def test_settings_persist_and_are_isolated(self):
        self.account(self.a)
        self.account(self.b, "bob")
        settings = {"theme": "dark", "message_notifications": False, "sound_enabled": False}
        self.assertEqual(self.post(self.a, "/users/me/settings", settings, method="PUT").json, settings)
        db.session.remove()
        self.assertEqual(self.a.get("/users/me/settings").json, settings)
        self.assertEqual(self.b.get("/users/me/settings").json["theme"], "light")
        self.assertEqual(self.post(self.a, "/users/me/settings", {"sound_enabled": "yes"}, method="PUT").status_code, 400)

    def test_chat_access_send_reply_edit_delete_and_pagination(self):
        a, b, chat = self.conversation()
        self.account(self.c, "carol")
        path = f"/chats/{chat}/messages"
        self.assertEqual(self.c.get(path).status_code, 403)
        self.assertEqual(self.post(self.a, "/chats", {"user_id": b}).status_code, 200)
        message = self.post(self.a, path, {"content": "hello"})
        self.assertEqual(message.status_code, 201, message.json)
        mid = message.json["message_id"]
        self.assertEqual(self.post(self.b, f"/messages/{mid}", {"content": "stolen"}, method="PUT").status_code, 403)
        reply = self.post(self.b, path, {"content": "reply", "reply_to_message_id": mid})
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(self.post(self.a, f"/messages/{mid}", {"content": "edited"}, method="PUT").status_code, 200)
        db.session.remove()
        self.assertEqual(self.b.get(path).json["messages"][0]["content"], "edited")
        self.assertTrue(self.a.get(path+"?limit=1").json["has_more"])
        self.assertEqual(self.a.get(path+"?limit=bad").status_code, 400)
        self.assertEqual(self.post(self.a, f"/messages/{mid}", method="DELETE").status_code, 200)
        self.assertIsNone(self.b.get(path).json["messages"][0]["reply_to_message_id"])

    def test_blocking_prevents_messages_and_search_and_can_be_reversed(self):
        a, b, chat = self.conversation()
        self.assertEqual(self.post(self.a, f"/users/me/blocked/{b}", method="PUT").status_code, 200)
        self.assertEqual(self.a.get("/users/me/blocked").json["users"][0]["user_id"], b)
        self.assertEqual(self.post(self.b, f"/chats/{chat}/messages", {"content": "blocked"}).status_code, 403)
        self.assertEqual(self.a.get("/users?q=bob").json["users"], [])
        self.post(self.a, f"/users/me/blocked/{b}", method="DELETE")
        self.assertEqual(self.post(self.b, f"/chats/{chat}/messages", {"content": "unblocked"}).status_code, 201)

    def test_attachments_persist_and_are_private(self):
        a, b, chat = self.conversation()
        self.account(self.c, "carol")
        csrf = self.a.get_cookie("csrf_access_token").value
        upload = self.a.post(f"/chats/{chat}/attachments", data={"file": (io.BytesIO(b"test contents"), "notes.txt")}, headers={"X-CSRF-TOKEN": csrf})
        self.assertEqual(upload.status_code, 201, upload.json)
        aid = upload.json["attachment_id"]
        self.assertEqual(self.b.get(f"/attachments/{aid}").status_code, 403)
        self.assertEqual(self.post(self.a, f"/chats/{chat}/messages", {"attachment_id": aid}).status_code, 201)
        db.session.remove()
        response = self.b.get(f"/attachments/{aid}")
        self.assertEqual(response.data, b"test contents")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertEqual(self.c.get(f"/attachments/{aid}").status_code, 403)

    def test_avatar_validation_and_storage(self):
        self.account(self.a)
        from PIL import Image
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2)).save(buffer, format="PNG")
        image = "data:image/png;base64,"+base64.b64encode(buffer.getvalue()).decode()
        response = self.post(self.a, "/users/me", {"profile_picture": image}, method="PUT")
        self.assertEqual(response.status_code, 200, response.json)
        db.session.remove()
        self.assertEqual(self.a.get("/users/me").json["profile_picture"], image)
        self.assertEqual(self.post(self.a, "/users/me", {"profile_picture": "data:image/png;base64,bm90IGFuIGltYWdl"}, method="PUT").status_code, 400)

    def test_malformed_json_and_limits_and_security_headers(self):
        self.assertEqual(self.a.post("/users/register", json=[1]).status_code, 400)
        self.assertEqual(self.a.post("/users/register", data="{broken", content_type="application/json").status_code, 400)
        response = self.a.get("/")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.a.get("/health/ready").status_code, 200)
        for _ in range(20):
            self.a.post("/users/register", json={"name": "invalid"})
        self.assertEqual(self.register(self.a).status_code, 429)

    def test_unread_markers_persist_and_cannot_cross_chats(self):
        a, b, chat = self.conversation()
        response = self.post(self.a, f"/chats/{chat}/messages", {"content": "Unread"})
        mid = response.json["message_id"]
        self.assertEqual(self.b.get("/chats").json["chats"][0]["unread"], 1)
        self.assertEqual(self.post(self.b, f"/chats/{chat}/read", {"message_id": mid}).status_code, 200)
        db.session.remove()
        self.assertEqual(self.b.get("/chats").json["chats"][0]["unread"], 0)
        self.assertEqual(self.a.get(f"/chats/{chat}/messages").json["messages"][0]["status"], "seen")
        self.assertEqual(self.post(self.b, f"/chats/{chat}/read", {"message_id": mid + 10000}).status_code, 400)

    def test_password_change_revokes_other_sessions(self):
        self.account(self.a)
        self.assertEqual(self.login(self.b).status_code, 200)
        response = self.post(self.a, "/users/me", {"new_password": "different-password", "current_password": "test-password-123"}, method="PUT")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.b.get("/users/me").status_code, 401)
        self.assertEqual(self.a.get("/users/me").status_code, 200)
        self.assertEqual(self.login(self.c).status_code, 401)
        self.assertEqual(self.login(self.c, password="different-password").status_code, 200)

    def test_cleanup_keeps_active_uploads_and_sessions(self):
        a, b, chat = self.conversation()
        csrf = self.a.get_cookie("csrf_access_token").value
        upload = self.a.post(f"/chats/{chat}/attachments", data={"file": (io.BytesIO(b"pending"), "pending.txt")}, headers={"X-CSRF-TOKEN": csrf})
        result = app.test_cli_runner().invoke(args=["cleanup"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.a.get("/users/me").status_code, 200)
        self.assertEqual(self.a.get(f"/attachments/{upload.json['attachment_id']}").status_code, 200)

    def test_cross_chat_reply_and_malformed_message_are_rejected(self):
        a, b, chat = self.conversation()
        c = self.account(self.c, "carol")
        self.post(self.a, "/contacts", {"user_id": c})
        other = self.post(self.a, "/chats", {"user_id": c}).json["chat_id"]
        mid = self.post(self.a, f"/chats/{chat}/messages", {"content": "Private to Bob"}).json["message_id"]
        self.assertEqual(self.post(self.a, f"/chats/{other}/messages", {"content": "wrong conversation", "reply_to_message_id": mid}).status_code, 400)
        self.assertEqual(self.post(self.a, f"/chats/{chat}/messages", {"content": []}).status_code, 400)
        self.assertEqual(self.post(self.a, f"/chats/{chat}/messages", {"content": "x"*10001}).status_code, 400)
        self.assertEqual(self.post(self.a, "/chats", {"user_id": str(b)}).status_code, 400)

    def test_concurrent_direct_chat_creation_does_not_duplicate(self):
        if not schema:
            self.skipTest("PostgreSQL concurrency check")
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        a = self.account(self.a)
        b = self.account(self.b, "bob")
        self.post(self.a, "/contacts", {"user_id": b})
        access = self.a.get_cookie("access_token_cookie").value
        csrf = self.a.get_cookie("csrf_access_token").value
        barrier = Barrier(2)
        def create():
            with app.test_client() as client:
                client.set_cookie("access_token_cookie", access)
                client.set_cookie("csrf_access_token", csrf)
                barrier.wait(timeout=10)
                response = client.post("/chats", json={"user_id": b}, headers={"X-CSRF-TOKEN": csrf})
                return response.status_code, response.json
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: create(), range(2)))
        self.assertEqual(sorted(status for status, _ in responses), [200, 201], responses)
        self.assertEqual(responses[0][1]["chat_id"], responses[1][1]["chat_id"])

    def test_migrations_are_idempotent(self):
        if not schema:
            self.skipTest("PostgreSQL migration integration check")
        self.account(self.a)
        result = app.test_cli_runner().invoke(args=["migrate"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("up to date", result.output)
        self.assertEqual(self.a.get("/users/me").json["email"], "alice@example.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)
