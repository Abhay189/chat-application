from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(30),
        unique=True,
        nullable=False
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(255),
        nullable=False
    )

    phone_no = db.Column(
        db.String(10),
        unique=True,
        nullable=True
    )

    dob = db.Column(
        db.Date,
        nullable=True
    )

    profile_picture = db.Column(
        db.Text,
        nullable=True
    )

    bio = db.Column(
        db.Text,
        nullable=True
    )

class Chat(db.Model):
    __tablename__ = "chats"

    chat_id = db.Column(db.Integer, primary_key= True)

    direct_key = db.Column(db.String(50), unique=True)

    created_at= db.Column(
        db.DateTime,
        nullable = False,
        server_default = db.func.now()
    )

class Chat_participant(db.Model):
    __tablename__ = "chat_participants"

    chat_id = db.Column(
        db.Integer,
        db.ForeignKey("chats.chat_id",ondelete="CASCADE"),
        primary_key= True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id",ondelete="CASCADE"),
        primary_key=True
    )

    last_read_message_id = db.Column(db.Integer, nullable=False, default=0)

    joined_at = db.Column(
        db.DateTime,
        nullable = False,
        server_default =db.func.now()

    )

class Messages(db.Model):
    __tablename__ = "messages"

    message_id = db.Column(
        db.Integer,
        primary_key= True
    )

    chat_id = db.Column(
        db.Integer,
        db.ForeignKey("chats.chat_id",ondelete="CASCADE"),
        nullable = False
    )

    sender_id= db.Column(
        db.Integer,
        db.ForeignKey("users.user_id",ondelete="CASCADE"),
        nullable = False
    )

    content = db.Column(
        db.Text,
        nullable = False
    )

    message_type= db.Column(
        db.String(20),
        nullable = False
    )

    sent_at = db.Column(
        db.DateTime,
        server_default =db.func.now()
    )

    status = db.Column(
        db.String(20),
        nullable = False
    )

    attachment_id = db.Column(db.Integer, db.ForeignKey("attachments.attachment_id", ondelete="SET NULL"))

    reply_to_message_id = db.Column(
        db.Integer,
        db.ForeignKey("messages.message_id",ondelete="SET NULL"),
        nullable = True
    )

class Contact(db.Model):
    __tablename__ = "contacts"
    owner_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())


class AuthSession(db.Model):
    __tablename__ = "auth_sessions"
    jti = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked = db.Column(db.Boolean, nullable=False, default=False)


class UserSettings(db.Model):
    __tablename__ = "user_settings"
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    theme = db.Column(db.String(5), nullable=False, default="light")
    message_notifications = db.Column(db.Boolean, nullable=False, default=True)
    sound_enabled = db.Column(db.Boolean, nullable=False, default=True)


class BlockedUser(db.Model):
    __tablename__ = "blocked_users"
    owner_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    blocked_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)


class Attachment(db.Model):
    __tablename__ = "attachments"
    attachment_id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)


class RateLimit(db.Model):
    __tablename__ = "rate_limits"
    key = db.Column(db.String(128), primary_key=True)
    bucket = db.Column(db.Integer, nullable=False)
    count = db.Column(db.Integer, nullable=False)
