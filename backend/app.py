"""Chat API. Run migrations before serving; see README.md."""
import base64
import hashlib
import io
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_file
from flask_cors import CORS
from flask_jwt_extended import (JWTManager, create_access_token, decode_token,
    get_jwt, get_jwt_identity, jwt_required, set_access_cookies, unset_jwt_cookies)
from sqlalchemy import URL, func, or_, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from models import (db, User, Chat, Chat_participant, Messages, Contact,
    AuthSession, UserSettings, BlockedUser, Attachment, RateLimit)

load_dotenv(Path(__file__).resolve().parent / ".env")
app = Flask(__name__)
environment = os.getenv("APP_ENV", "development")
if environment not in ("development", "production", "test"):
    raise RuntimeError("APP_ENV must be development, production, or test.")
production = environment == "production"
database_uri = os.getenv("DATABASE_URL")
if database_uri:
    database_uri = re.sub(r"^postgres(?:ql)?://", "postgresql+psycopg://", database_uri)
secret = os.getenv("JWT_SECRET_KEY", "")
if len(secret) < 32 or secret.startswith("replace-"):
    raise RuntimeError("Set JWT_SECRET_KEY to a random secret of at least 32 characters.")
app.config.update(
    JWT_SECRET_KEY=secret, JWT_TOKEN_LOCATION=["cookies"],
    JWT_COOKIE_SECURE=production, JWT_COOKIE_SAMESITE="Lax",
    JWT_COOKIE_CSRF_PROTECT=True, JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=12),
    JWT_SESSION_COOKIE=False, MAX_CONTENT_LENGTH=7 * 1024 * 1024,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_DATABASE_URI=database_uri or URL.create(
        "postgresql+psycopg", username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"), host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "5432")), database=os.getenv("DB_NAME")),
    SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
)
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173").split(",") if x.strip()]
if production and not os.getenv("CORS_ORIGINS"):
    raise RuntimeError("Set CORS_ORIGINS to your HTTPS application origin in production.")
if "*" in origins:
    raise RuntimeError("CORS_ORIGINS must contain explicit origins.")
CORS(app, origins=origins, supports_credentials=True)
db.init_app(app)
jwt = JWTManager(app)


@app.cli.command("migrate")
def migrate():
    """Apply additive PostgreSQL migrations atomically without deleting user data."""
    with db.engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(9024751)"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(100) PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
        for path in sorted((Path(__file__).parent / "database" / "migrations").glob("*.sql")):
            if connection.execute(text("SELECT 1 FROM schema_migrations WHERE version=:v"), {"v": path.name}).scalar():
                continue
            connection.exec_driver_sql(path.read_text())
            connection.execute(text("INSERT INTO schema_migrations(version) VALUES (:v)"), {"v": path.name})
            click.echo(f"Applied {path.name}")
    click.echo("Database is up to date.")


@app.cli.command("cleanup")
def cleanup():
    """Remove expired sessions, old rate counters, and abandoned attachments."""
    AuthSession.query.filter(AuthSession.expires_at < datetime.now(timezone.utc)).delete()
    RateLimit.query.filter(RateLimit.bucket < int(time.time()) // 3600 - 24).delete()
    Attachment.query.filter(Attachment.created_at < datetime.now(timezone.utc) - timedelta(days=1), ~Attachment.attachment_id.in_(db.select(Messages.attachment_id).where(Messages.attachment_id.isnot(None)))).delete(synchronize_session=False)
    db.session.commit()


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    if production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.errorhandler(HTTPException)
def http_error(error):
    return jsonify(error=error.description), error.code


@app.errorhandler(IntegrityError)
def conflict(error):
    db.session.rollback()
    return {"error": "That username, email, phone, or relationship already exists. Refresh and try again."}, 409


@app.errorhandler(SQLAlchemyError)
def database_error(error):
    db.session.rollback()
    app.logger.error("Database request failed: %s", type(error).__name__)
    return {"error": "Database unavailable. Please try again shortly."}, 503


@app.errorhandler(Exception)
def unexpected_error(error):
    db.session.rollback()
    app.logger.error("Request failed: %s", type(error).__name__)
    return {"error": "Unexpected server error. Please try again."}, 500


def body():
    data = request.get_json()
    if not isinstance(data, dict) or not data:
        abort(400, description="A JSON object is required.")
    return data


def string(data, field, maximum, required=False):
    value = data.get(field, "")
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        abort(400, description=f"{field} must be text.")
    value = value.strip()
    if len(value) > maximum or (required and not value):
        abort(400, description=f"{field} is required and must be at most {maximum} characters." if required else f"{field} must be at most {maximum} characters.")
    return value


def password_value(data, field="password"):
    value = data.get(field)
    if not isinstance(value, str) or not 8 <= len(value) <= 128:
        abort(400, description="Password must contain 8 to 128 characters.")
    return value


def profile_values(data, partial=False):
    values = {}
    for field, maximum in (("name", 100), ("username", 30), ("email", 255), ("bio", 2000)):
        if partial and field not in data:
            continue
        value = string(data, field, maximum, required=field != "bio")
        if field == "username" and not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", value):
            abort(400, description="Username must be 3 to 30 letters, numbers, dots, underscores or hyphens.")
        if field == "email":
            value = value.lower()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
                abort(400, description="A valid email is required.")
        values[field] = value
    if not partial or "phone_no" in data:
        phone = string(data, "phone_no", 10)
        if phone and not re.fullmatch(r"[0-9]{10}", phone):
            abort(400, description="Phone must contain exactly 10 digits, or be blank.")
        values["phone_no"] = phone or None
    if not partial or "dob" in data:
        dob = string(data, "dob", 10)
        try:
            if dob and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", dob):
                raise ValueError()
            parsed = date.fromisoformat(dob) if dob else None
        except ValueError:
            abort(400, description="Date of birth must be a valid YYYY-MM-DD date.")
        if parsed and parsed > date.today():
            abort(400, description="Date of birth cannot be in the future.")
        values["dob"] = parsed
    if "profile_picture" in data:
        picture = string(data, "profile_picture", 3000000)
        if picture:
            match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", picture)
            if not match:
                abort(400, description="Profile photo must be a PNG, JPEG or WebP image.")
            try:
                from PIL import Image
                raw = base64.b64decode(match[2], validate=True)
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError()
                image = Image.open(io.BytesIO(raw))
                image.verify()
                if image.width * image.height > 16000000:
                    raise ValueError()
            except Exception:
                abort(400, description="Invalid profile image or image exceeds 2 MB / 16 megapixels.")
        values["profile_picture"] = picture or None
    return values


def unique_profile(values, user_id=None):
    for field in ("username", "email", "phone_no"):
        if not values.get(field):
            continue
        column = getattr(User, field)
        query = User.query.filter(func.lower(column) == values[field].lower())
        if user_id:
            query = query.filter(User.user_id != user_id)
        if query.first():
            abort(409, description=f"{field} already exists.")


def public_user(user):
    return {"user_id": user.user_id, "name": user.name, "username": user.username, "email": user.email}


def private_user(user):
    return {**public_user(user), "phone_no": user.phone_no,
        "dob": user.dob.isoformat() if user.dob else None,
        "bio": user.bio, "profile_picture": user.profile_picture}


def current_user():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        abort(401, description="Account no longer exists. Please log in again.")
    return user


@jwt.token_in_blocklist_loader
def revoked(_header, payload):
    session = db.session.get(AuthSession, payload["jti"])
    return session is None or session.revoked


@jwt.unauthorized_loader
def missing_token(_reason):
    return {"error": "Please log in again."}, 401


@jwt.invalid_token_loader
def invalid_token(_reason):
    return {"error": "Invalid session. Please log in again."}, 401


@jwt.expired_token_loader
@jwt.revoked_token_loader
def expired_token(_header, _payload):
    response = jsonify(error="Session ended. Please log in again.")
    unset_jwt_cookies(response)
    return response, 401


def rate_limit(label, maximum):
    # Atomic counters are shared by all server workers in PostgreSQL.
    bucket = int(time.time()) // 3600
    key = hashlib.sha256(f"{label}:{request.remote_addr}".encode()).hexdigest()
    if db.engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    statement = insert(RateLimit).values(key=key, bucket=bucket, count=1)
    statement = statement.on_conflict_do_update(index_elements=[RateLimit.key], set_={
        "bucket": bucket, "count": db.case((RateLimit.bucket == bucket, RateLimit.count + 1), else_=1)
    }).returning(RateLimit.count)
    count = db.session.execute(statement).scalar_one()
    db.session.commit()
    if count > maximum:
        abort(429, description="Too many attempts. Please try again in an hour.")


@app.get("/")
def home():
    return {"message": "Chat Application Backend Running!"}


@app.get("/health/ready")
def ready():
    db.session.execute(text("SELECT 1 FROM auth_sessions LIMIT 1"))
    return {"status": "ready"}


@app.post("/users/register")
def register_user():
    rate_limit("register", 20)
    data = body()
    values = profile_values(data)
    password = password_value(data)
    unique_profile(values)
    user = User(**values, password=generate_password_hash(password))
    db.session.add(user)
    db.session.flush()
    db.session.add(UserSettings(user_id=user.user_id))
    db.session.commit()
    return {"message": "Account created. Please log in.", "user_id": user.user_id}, 201


@app.post("/users/login")
def login_user():
    rate_limit("login", 60)
    data = body()
    email = string(data, "email", 255, True).lower()
    password = password_value(data)
    user = User.query.filter(func.lower(User.email) == email).first()
    # Hash check even for unknown accounts reduces account timing differences.
    stored = user.password if user else app.config["DUMMY_PASSWORD_HASH"]
    valid = check_password_hash(stored, password)
    if not user or not valid:
        abort(401, description="Invalid email or password.")
    token = create_access_token(identity=str(user.user_id))
    payload = decode_token(token)
    db.session.add(AuthSession(jti=payload["jti"], user_id=user.user_id,
        expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc)))
    db.session.commit()
    response = jsonify(**public_user(user), message="Login successful")
    set_access_cookies(response, token, max_age=12 * 3600)
    return response


app.config["DUMMY_PASSWORD_HASH"] = generate_password_hash(os.urandom(24).hex())


@app.post("/users/logout")
@jwt_required()
def logout():
    session = db.session.get(AuthSession, get_jwt()["jti"])
    session.revoked = True
    db.session.commit()
    response = jsonify(message="Logged out")
    unset_jwt_cookies(response)
    return response


@app.get("/users/me")
@jwt_required()
def get_current_user():
    return private_user(current_user())


@app.put("/users/me")
@jwt_required()
def update_current_user():
    user = current_user()
    data = body()
    values = profile_values(data, partial=True)
    if "email" in values and values["email"] != user.email:
        password = password_value(data, "current_password")
        if not check_password_hash(user.password, password):
            abort(403, description="Current password is incorrect.")
    if "new_password" in data:
        if not check_password_hash(user.password, password_value(data, "current_password")):
            abort(403, description="Current password is incorrect.")
        values["password"] = generate_password_hash(password_value(data, "new_password"))
        AuthSession.query.filter(AuthSession.user_id == user.user_id, AuthSession.jti != get_jwt()["jti"]).update({"revoked": True})
    unique_profile(values, user.user_id)
    for field, value in values.items():
        setattr(user, field, value)
    db.session.commit()
    return private_user(user)


def settings_for(user_id):
    settings = db.session.get(UserSettings, user_id)
    if settings is None:
        settings = UserSettings(user_id=user_id)
        db.session.add(settings)
        db.session.flush()
    return settings


@app.route("/users/me/settings", methods=["GET", "PUT"])
@jwt_required()
def settings():
    preferences = settings_for(current_user().user_id)
    if request.method == "PUT":
        data = body()
        if "theme" in data:
            if data["theme"] not in ("light", "dark"):
                abort(400, description="Invalid theme.")
            preferences.theme = data["theme"]
        for field in ("message_notifications", "sound_enabled"):
            if field in data:
                if not isinstance(data[field], bool):
                    abort(400, description=f"{field} must be true or false.")
                setattr(preferences, field, data[field])
    db.session.commit()
    return {"theme": preferences.theme, "message_notifications": preferences.message_notifications, "sound_enabled": preferences.sound_enabled}


def is_blocked(a, b):
    return BlockedUser.query.filter(or_(
        db.and_(BlockedUser.owner_id == a, BlockedUser.blocked_id == b),
        db.and_(BlockedUser.owner_id == b, BlockedUser.blocked_id == a))).first() is not None


@app.get("/users")
@jwt_required()
def search_users():
    rate_limit("search", 600)
    user_id = current_user().user_id
    query = request.args.get("q", "").strip().lstrip("@")
    if len(query) < 2:
        return {"users": []}
    if len(query) > 255:
        abort(400, description="Search is too long.")
    users = User.query.filter(User.user_id != user_id, or_(
        User.username.icontains(query, autoescape=True), User.email.icontains(query, autoescape=True)
    )).order_by(User.username).limit(30).all()
    saved = {row.contact_id for row in Contact.query.filter_by(owner_id=user_id)}
    return {"users": [{**public_user(user), "is_contact": user.user_id in saved} for user in users if not is_blocked(user_id, user.user_id)]}


@app.route("/contacts", methods=["GET", "POST"])
@jwt_required()
def contacts():
    user_id = current_user().user_id
    if request.method == "POST":
        target_id = body().get("user_id")
        if type(target_id) is not int or target_id == user_id:
            abort(400, description="Select another user to add.")
        target = db.session.get(User, target_id)
        if not target:
            abort(404, description="User not found.")
        if is_blocked(user_id, target_id):
            abort(403, description="Contact is blocked.")
        existing = db.session.get(Contact, (user_id, target_id))
        if not existing:
            db.session.add(Contact(owner_id=user_id, contact_id=target_id))
            db.session.commit()
        return {"contact": {**public_user(target), "is_contact": True}}, 200 if existing else 201
    users = db.session.query(User).join(Contact, Contact.contact_id == User.user_id).filter(Contact.owner_id == user_id).order_by(User.name).all()
    return {"contacts": [{**public_user(user), "is_contact": True} for user in users]}


@app.delete("/contacts/<int:target_id>")
@jwt_required()
def remove_contact(target_id):
    Contact.query.filter_by(owner_id=current_user().user_id, contact_id=target_id).delete()
    db.session.commit()
    return {"message": "Contact removed"}


@app.get("/users/me/blocked")
@jwt_required()
def blocked_users():
    users = db.session.query(User).join(BlockedUser, BlockedUser.blocked_id == User.user_id).filter(BlockedUser.owner_id == current_user().user_id).all()
    return {"users": [public_user(user) for user in users]}


@app.route("/users/me/blocked/<int:target_id>", methods=["PUT", "DELETE"])
@jwt_required()
def block_user(target_id):
    user_id = current_user().user_id
    if target_id == user_id or not db.session.get(User, target_id):
        abort(400, description="Select another existing user.")
    existing = db.session.get(BlockedUser, (user_id, target_id))
    if request.method == "PUT" and not existing:
        db.session.add(BlockedUser(owner_id=user_id, blocked_id=target_id))
    elif request.method == "DELETE" and existing:
        db.session.delete(existing)
    db.session.commit()
    return {"message": "Updated blocked users"}


@app.post("/chats")
@jwt_required()
def create_chat():
    user_id = current_user().user_id
    target_id = body().get("user_id")
    if type(target_id) is not int or target_id == user_id:
        abort(400, description="Select another user.")
    if not db.session.get(User, target_id):
        abort(404, description="User not found.")
    if is_blocked(user_id, target_id):
        abort(403, description="This conversation is blocked.")
    if not db.session.get(Contact, (user_id, target_id)):
        abort(400, description="Add this user to your contacts first.")
    key = ":".join(str(x) for x in sorted((user_id, target_id)))
    if db.engine.dialect.name == "postgresql":
        db.session.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"), {"a": min(user_id, target_id), "b": max(user_id, target_id)})
    existing = Chat.query.filter_by(direct_key=key).first()
    if not existing:
        existing = Chat.query.join(Chat_participant).filter(Chat_participant.user_id == user_id, Chat.chat_id.in_(db.select(Chat_participant.chat_id).where(Chat_participant.user_id == target_id))).first()
    if existing:
        return {"chat_id": existing.chat_id}, 200
    chat = Chat(direct_key=key)
    db.session.add(chat)
    db.session.flush()
    db.session.add_all([Chat_participant(chat_id=chat.chat_id, user_id=i) for i in (user_id, target_id)])
    db.session.commit()
    return {"chat_id": chat.chat_id}, 201


def chat_access(chat_id):
    user_id = current_user().user_id
    if not db.session.get(Chat_participant, (chat_id, user_id)):
        abort(403, description="You do not have access to this conversation.")
    other = Chat_participant.query.filter(Chat_participant.chat_id == chat_id, Chat_participant.user_id != user_id).first()
    return user_id, other.user_id if other else None


def message_json(message):
    return {"message_id": message.message_id, "sender_id": message.sender_id,
        "content": message.content, "message_type": message.message_type,
        "sent_at": message.sent_at.isoformat() + "Z", "status": message.status,
        "reply_to_message_id": message.reply_to_message_id, "attachment_id": message.attachment_id}


@app.get("/chats")
@jwt_required()
def get_chats():
    user_id = current_user().user_id
    rows = Chat_participant.query.filter_by(user_id=user_id).all()
    chats = []
    for row in rows:
        other = Chat_participant.query.filter(Chat_participant.chat_id == row.chat_id, Chat_participant.user_id != user_id).first()
        user = db.session.get(User, other.user_id) if other else None
        if user:
            latest = Messages.query.filter_by(chat_id=row.chat_id).order_by(Messages.message_id.desc()).first()
            chats.append({"chat_id": row.chat_id, "other_user": public_user(user),
                "blocked": is_blocked(user_id, user.user_id), "blocked_by_me": db.session.get(BlockedUser, (user_id, user.user_id)) is not None,
                "unread": Messages.query.filter(Messages.chat_id == row.chat_id, Messages.sender_id != user_id, Messages.message_id > row.last_read_message_id).count(), "latest_message": message_json(latest) if latest else None})
    return {"chats": sorted(chats, key=lambda c: c["latest_message"]["message_id"] if c["latest_message"] else 0, reverse=True)}


@app.route("/chats/<int:chat_id>/messages", methods=["GET", "POST"])
@jwt_required()
def messages(chat_id):
    user_id, other_id = chat_access(chat_id)
    if request.method == "GET":
        try:
            limit = int(request.args.get("limit", 50))
            before = int(request.args["before"]) if "before" in request.args else None
            if not 1 <= limit <= 100 or (before is not None and before < 1):
                raise ValueError()
        except ValueError:
            abort(400, description="Invalid message pagination.")
        query = Messages.query.filter_by(chat_id=chat_id)
        if before:
            query = query.filter(Messages.message_id < before)
        rows = query.order_by(Messages.message_id.desc()).limit(limit + 1).all()
        return {"messages": [message_json(m) for m in reversed(rows[:limit])], "has_more": len(rows) > limit}
    if other_id and is_blocked(user_id, other_id):
        abort(403, description="This conversation is blocked.")
    rate_limit("messages", 1200)
    data = body()
    content = string(data, "content", 10000)
    attachment_id = data.get("attachment_id")
    attachment = None
    if attachment_id is not None:
        if type(attachment_id) is not int:
            abort(400, description="Invalid attachment.")
        attachment = db.session.get(Attachment, attachment_id)
        if not attachment or attachment.chat_id != chat_id or attachment.owner_id != user_id:
            abort(400, description="Invalid attachment.")
        if Messages.query.filter_by(attachment_id=attachment_id).first():
            abort(409, description="Attachment already sent.")
    if not content and not attachment:
        abort(400, description="Message content is required.")
    reply_id = data.get("reply_to_message_id")
    if reply_id is not None:
        replied = db.session.get(Messages, reply_id) if type(reply_id) is int else None
        if not replied or replied.chat_id != chat_id:
            abort(400, description="Reply must reference a message in this conversation.")
    message = Messages(chat_id=chat_id, sender_id=user_id, content=content or attachment.filename,
        message_type="document" if attachment else "text", status="sent",
        reply_to_message_id=reply_id, attachment_id=attachment_id)
    db.session.add(message)
    db.session.commit()
    return message_json(message), 201


@app.post("/chats/<int:chat_id>/read")
@jwt_required()
def read_chat(chat_id):
    user_id, _ = chat_access(chat_id)
    marker = body().get("message_id")
    message = db.session.get(Messages, marker) if type(marker) is int else None
    if not message or message.chat_id != chat_id:
        abort(400, description="Invalid read marker.")
    participant = db.session.get(Chat_participant, (chat_id, user_id))
    participant.last_read_message_id = max(participant.last_read_message_id, marker)
    Messages.query.filter(Messages.chat_id == chat_id, Messages.sender_id != user_id, Messages.message_id <= marker).update({"status": "seen"})
    db.session.commit()
    return {"message": "Marked read"}


@app.route("/messages/<int:message_id>", methods=["PUT", "DELETE"])
@jwt_required()
def change_message(message_id):
    message = db.session.get(Messages, message_id)
    if not message:
        abort(404, description="Message not found.")
    chat_access(message.chat_id)
    if message.sender_id != current_user().user_id:
        abort(403, description="You can only change your own messages.")
    if request.method == "PUT":
        message.content = string(body(), "content", 10000, True)
        db.session.commit()
        return message_json(message)
    # Keep reply quotes valid on databases whose old schema lacks ORM cascades.
    Messages.query.filter_by(reply_to_message_id=message_id).update({"reply_to_message_id": None})
    attachment = db.session.get(Attachment, message.attachment_id) if message.attachment_id else None
    db.session.delete(message)
    if attachment:
        db.session.delete(attachment)
    db.session.commit()
    return {"message": "Message deleted"}


@app.post("/chats/<int:chat_id>/attachments")
@jwt_required()
def upload_attachment(chat_id):
    user_id, other_id = chat_access(chat_id)
    if other_id and is_blocked(user_id, other_id):
        abort(403, description="This conversation is blocked.")
    rate_limit("uploads", 100)
    file = request.files.get("file")
    if not file:
        abort(400, description="Select a file.")
    raw = file.read(5 * 1024 * 1024 + 1)
    filename = secure_filename(file.filename or "")[:255]
    if not filename or not raw or len(raw) > 5 * 1024 * 1024:
        abort(400, description="File must be between 1 byte and 5 MB.")
    attachment = Attachment(chat_id=chat_id, owner_id=user_id, filename=filename,
        mime_type="application/octet-stream", data=raw)
    db.session.add(attachment)
    db.session.commit()
    return {"attachment_id": attachment.attachment_id, "filename": filename}, 201


@app.get("/attachments/<int:attachment_id>")
@jwt_required()
def download_attachment(attachment_id):
    attachment = db.session.get(Attachment, attachment_id)
    if not attachment:
        abort(404, description="Attachment not found.")
    user_id, _ = chat_access(attachment.chat_id)
    if attachment.owner_id != user_id and not Messages.query.filter_by(attachment_id=attachment_id).first():
        abort(403, description="Attachment has not been sent.")
    return send_file(io.BytesIO(attachment.data), mimetype="application/octet-stream", as_attachment=True, download_name=attachment.filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
