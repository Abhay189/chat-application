# Chat application

React/Vite frontend, Flask API, and PostgreSQL 17. User accounts, hashed passwords, login sessions, contacts, profile photos, settings, conversations, messages, unread markers, blocks, and attachments are stored in PostgreSQL.

## Run on this computer

The dependencies and database migrations have already been installed/applied during the readiness work. Stop the old backend with Ctrl+C before restarting; the new session implementation requires logging in again.

From the repository root, terminal 1:

```powershell
backend/venv/Scripts/python.exe -m flask --app backend/app.py migrate
backend/venv/Scripts/python.exe backend/serve.py
```

Terminal 2:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open **http://127.0.0.1:5173**. Use the same hostname for frontend and backend locally; mixing localhost and 127.0.0.1 breaks cookie authentication. Development cookies use HTTP; production cookies require HTTPS.

## Fresh installation

Use Python 3.12+, a Node version supported by Vite (the lockfile declares supported engines; Node 26.13.1 was tested), and PostgreSQL 17. From the repository root:

```powershell
python -m venv backend/venv
backend/venv/Scripts/python.exe -m pip install --upgrade pip
backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd frontend
npm ci
cd ..
```

Create a dedicated database role and database using an administrator connection:

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h 127.0.0.1 -U postgres -d postgres
```

Run each statement individually:

```sql
CREATE ROLE chat_app LOGIN;
\password chat_app
CREATE DATABASE chat_application OWNER chat_app;
\q
```

Copy `backend/.env.example` to `backend/.env` if it does not exist. Fill in the database password and generate a secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set that value as `JWT_SECRET_KEY`; keep it stable across restarts. Environment variables override `.env`. The application fails startup if the secret is missing or too short. Do not commit `.env`. Never use a PostgreSQL administrator role for the running app.

Apply migrations, for either a new or existing database:

```powershell
backend/venv/Scripts/python.exe -m flask --app backend/app.py migrate
```

Migrations run atomically, track applied versions, and preserve existing records. Back up before upgrades. Case-insensitive username/email indexes deliberately reject an upgrade if existing records differ only in case; resolve those duplicates before retrying. `database/schema.sql` is the legacy initial schema; use migrations for complete setup. `database/seed.sql` contains legacy sample plaintext passwords and should not be imported; register accounts in the app.

## Using the app

- Registration requires name, username, a valid email format, and a password of 8 to 128 characters. Phone and date of birth are optional. Usernames and emails are unique without regard to case.
- Log in with email/password. A 12-hour HttpOnly cookie restores the session after refresh. CSRF protection applies to authenticated writes. Logout revokes the session in PostgreSQL. Password changes revoke other sessions.
- Open **+** to manage contacts. Search at least two characters of a username or email, add the person, then choose the chat icon. Contacts are private to each account. Removing a contact preserves message history.
- Messages synchronize by polling (about 2.5 seconds in the open conversation and 4 seconds for the chat list). Send, reply, edit, delete, and download attachments. Only senders can change their messages; only participants can read a conversation or its files. Attachments are limited to 5 MB and stored as bytes in PostgreSQL.
- Edit name, username, email, phone, date of birth, biography, photo, and password in Profile. Changing email or password requires the current password. Profile photos accept PNG/JPEG/WebP, at most 2 MB and 16 megapixels.
- Theme, notification, and sound preferences persist per account. Browser notifications require browser permission and an open application tab; these are background-tab alerts, not offline push notifications. Browsers require user interaction before allowing sound. Block users from a conversation and unblock from Settings.

## Verification

```powershell
npm --prefix frontend run lint
npm --prefix frontend run build
backend/venv/Scripts/python.exe -m pip check
backend/venv/Scripts/python.exe -m unittest discover -s backend/tests -v
```

PostgreSQL integration tests use a random isolated schema, never your account tables:

```powershell
$env:TEST_POSTGRES='1'
backend/venv/Scripts/python.exe -m unittest discover -s backend/tests -v
Remove-Item Env:TEST_POSTGRES
```

Browser tests start temporary servers on ports 5001 and 5174, use an isolated schema, and clean up afterward:

```powershell
backend/venv/Scripts/python.exe backend/tests/run_browser.py
```

The browser tests default to installed Microsoft Edge. On other systems install Chromium with `cd frontend; npx playwright install chromium`, and set `PLAYWRIGHT_CHANNEL=chromium` before invoking the runner. Test artifacts are in `frontend/test-results`. The test role needs permission to create/drop schemas in its test database. Do not run integration tests against a deployment without an isolated testing database and role.

Readiness evidence: 19 API/integration tests, two browser scenarios covering desktop/mobile and two separate users, frontend lint/build, dependency consistency, and production dependency vulnerability audits. Tests create synthetic accounts in temporary schemas and remove them; they do not change your real accounts.

## Production deployment

See [deploy/README.md](deploy/README.md). The repository includes a Waitress entry point and an HTTPS nginx example, but no public deployment has been configured or load-tested. Required email addresses are not email ownership verification. Email verification/recovery delivery, offline push, and end-to-end encryption are not implemented. Consider these product requirements before public launch; do not market features that are absent.
