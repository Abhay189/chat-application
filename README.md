# Chat application local setup (Windows PowerShell)

The frontend uses React/Vite; the backend uses Flask and PostgreSQL.

## Prerequisites

- Node.js compatible with the engines in `frontend/package-lock.json` (the installed Node 26.13.1 builds successfully).
- Python 3.12 and pip (verified with Python 3.12.6).
- A running PostgreSQL server (PostgreSQL 17 is installed locally and accepts connections on port 5432).

## Install dependencies

From the repository root:

```powershell
python -m venv backend/venv
backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Set-Location frontend
npm ci
Set-Location ..
```

## Set up PostgreSQL

The PostgreSQL tools are installed outside PATH. For this terminal:

```powershell
$env:Path = 'C:\Program Files\PostgreSQL\17\bin;' + $env:Path
psql -h 127.0.0.1 -U postgres -d postgres
```

Enter the PostgreSQL administrator password chosen during installation. Inside psql, run these statements individually:

```sql
CREATE ROLE chat_app LOGIN;
\password chat_app
CREATE DATABASE chat_application OWNER chat_app;
\q
```

The `\password` command prompts for a new application password without putting it into command history. If the role or database already exists, inspect it rather than recreating it.

Initialize the new, empty database from the repository root:

```powershell
psql -h 127.0.0.1 -U chat_app -d chat_application -v ON_ERROR_STOP=1 -1 -f backend/database/schema.sql
```

Do this once; the schema script is not idempotent. Do not import `seed.sql` for login testing: it contains plaintext passwords, while the application requires password hashes. Register users through the app instead.

If you do not know the existing postgres administrator password, use an existing authenticated pgAdmin connection or recover access before proceeding. The Windows account password is not necessarily the PostgreSQL password.

## Backend configuration

Copy `backend/.env.example` to `backend/.env` if the latter does not exist. A local `.env` with a generated JWT secret was created during the prerequisite review. Set:

```dotenv
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=chat_application
DB_USER=chat_app
DB_PASSWORD=your-application-role-password
JWT_SECRET_KEY=your-random-secret-at-least-32-characters
```

Keep the generated JWT secret if one is already present. `.env` is excluded from Git.

## Run

Terminal 1, from the repository root:

```powershell
backend/venv/Scripts/python.exe backend/app.py
```

Terminal 2, from the repository root:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open http://127.0.0.1:5173. Use this exact origin because the backend CORS configuration allows it. The frontend API URL is fixed to http://127.0.0.1:5000. Register two accounts to test chatting.

## Verification

`npm run build` and `backend/venv/Scripts/python.exe -m pip check` pass. The backend health route and CORS preflight pass using Flask's test client. These checks do not verify database credentials or tables. Existing frontend lint issues remain (12 errors and 2 warnings during review).
