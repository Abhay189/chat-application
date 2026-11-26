"""Run browser checks against an isolated PostgreSQL schema and temporary servers."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text

root = Path(__file__).resolve().parents[2]
load_dotenv(root / "backend" / ".env")
url = URL.create("postgresql+psycopg", username=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"), host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")), database=os.getenv("DB_NAME"))
engine = create_engine(url)
schema = "chat_browser_" + uuid4().hex
processes = []
logs = []
try:
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    env = {**os.environ, "DATABASE_URL": url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False), "APP_ENV": "test", "JWT_SECRET_KEY": uuid4().hex+uuid4().hex, "CORS_ORIGINS": "http://localhost:5174", "VITE_API_URL": "http://localhost:5001"}
    subprocess.run([sys.executable, "-m", "flask", "--app", "app", "migrate"], cwd=root / "backend", env=env, check=True)
    for name, command, cwd in [
        ("api", [sys.executable, "-c", "from waitress import serve; from app import app; serve(app,host='127.0.0.1',port=5001)"], root / "backend"),
        ("vite", [shutil.which("node"), "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "5174", "--strictPort"], root / "frontend")]:
        log = open(root / "frontend" / f".browser-{name}.log", "w")
        logs.append(log)
        processes.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log))
    for endpoint in ("http://localhost:5001/health/ready", "http://localhost:5174"):
        for _ in range(100):
            try:
                urllib.request.urlopen(endpoint, timeout=1).close()
                break
            except Exception:
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("Temporary server failed; inspect frontend/.browser-*.log")
                time.sleep(.1)
        else:
            raise RuntimeError("Temporary server did not become ready")
    result = subprocess.run([shutil.which("node"), "node_modules/@playwright/test/cli.js", "test"], cwd=root / "frontend", env=env)
    code = result.returncode
finally:
    for process in reversed(processes):
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    for log in logs: log.close()
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    engine.dispose()
sys.exit(code)
