ALTER TABLE users ALTER COLUMN profile_picture TYPE TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_unique ON users (lower(username));
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_unique ON users (lower(email));
ALTER TABLE chats ADD COLUMN IF NOT EXISTS direct_key VARCHAR(50);
CREATE UNIQUE INDEX IF NOT EXISTS chats_direct_key_unique ON chats(direct_key);
CREATE TABLE IF NOT EXISTS contacts (
 owner_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
 contact_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(owner_id,contact_id), CHECK(owner_id <> contact_id)
);
CREATE TABLE IF NOT EXISTS auth_sessions (
 jti VARCHAR(36) PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
 expires_at TIMESTAMP NOT NULL, revoked BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS auth_sessions_user_id_idx ON auth_sessions(user_id);
CREATE TABLE IF NOT EXISTS user_settings (
 user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
 theme VARCHAR(5) NOT NULL DEFAULT 'light' CHECK(theme IN ('light','dark')),
 message_notifications BOOLEAN NOT NULL DEFAULT TRUE, sound_enabled BOOLEAN NOT NULL DEFAULT TRUE
);
INSERT INTO user_settings(user_id) SELECT user_id FROM users ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS blocked_users (
 owner_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
 blocked_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
 PRIMARY KEY(owner_id,blocked_id), CHECK(owner_id <> blocked_id)
);
CREATE TABLE IF NOT EXISTS attachments (
 attachment_id SERIAL PRIMARY KEY, chat_id INTEGER NOT NULL REFERENCES chats(chat_id) ON DELETE CASCADE,
 owner_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
 filename VARCHAR(255) NOT NULL, mime_type VARCHAR(100) NOT NULL, data BYTEA NOT NULL
);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS attachment_id INTEGER REFERENCES attachments(attachment_id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS messages_attachment_unique ON messages(attachment_id);
CREATE TABLE IF NOT EXISTS rate_limits (key VARCHAR(128) PRIMARY KEY, bucket INTEGER NOT NULL, count INTEGER NOT NULL);
