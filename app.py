"""
ShieldLabs Demo Target — NepalStartup API
==========================================
DELIBERATELY VULNERABLE. LOCAL DEMO ONLY.
NEVER DEPLOY THIS TO THE INTERNET.
"""

from flask import Flask, request, redirect, jsonify, Response
import sqlite3
import hashlib
import os
import pickle
import base64
import jwt as pyjwt
import datetime

app = Flask(__name__)

# VULN 1: Hardcoded secrets
SECRET_KEY      = "supersecretkey123"
JWT_SECRET      = "jwt_secret_do_not_share"
DATABASE_URL    = "sqlite:///users.db"
AWS_ACCESS_KEY  = "AKIAIOSFODNN7HARDCODED"
STRIPE_KEY      = "hardcoded-secret-for-testing-1234567890abcdef"
ADMIN_PASSWORD  = "admin123"

DB_PATH = "demo_users.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            email TEXT,
            role TEXT,
            credit_card TEXT
        )
    """)
    conn.execute("""
        INSERT OR IGNORE INTO users VALUES
        (1,'admin','admin123','admin@nepalstartup.com','admin','4532-1234-5678-9012'),
        (2,'alice','pass1','alice@nepalstartup.com','user','4916-8765-4321-0987'),
        (3,'bob','secret','bob@nepalstartup.com','user','5425-2334-3010-9903'),
        (4,'carol','letmein','carol@nepalstartup.com','moderator','3714-496353-98431')
    """)
    conn.commit()
    conn.close()


def get_db():
    return sqlite3.connect(DB_PATH)


@app.route('/')
def index():
    return jsonify({
        "app": "NepalStartup API v1.0",
        "status": "running",
        "endpoints": {
            "search": "/search?id=1",
            "login":  "POST /login",
            "user":   "/user?name=admin",
            "ping":   "/ping?host=google.com",
            "token":  "POST /token",
            "verify": "/verify?token=xxx",
            "redirect": "/redirect?url=https://google.com",
            "load":   "/load?data=hex_encoded"
        }
    })


# VULN 2: SQL Injection — /search?id=1
@app.route('/search')
def search_user():
    user_id = request.args.get('id', '1')
    conn = get_db()
    query = f"SELECT id, username, email, role FROM users WHERE id = {user_id}"
    try:
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        return jsonify({
            "query": query,
            "count": len(rows),
            "users": [
                {"id": r[0], "username": r[1], "email": r[2], "role": r[3]}
                for r in rows
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e), "query": query}), 500
    finally:
        conn.close()


# VULN 3: SQL Injection — /user?name=admin
@app.route('/user')
def get_user():
    name = request.args.get('name', '')
    conn = get_db()
    query = f"SELECT * FROM users WHERE username = '{name}'"
    try:
        cursor = conn.execute(query)
        row = cursor.fetchone()
        if row:
            return jsonify({
                "id": row[0], "username": row[1],
                "email": row[3], "role": row[4]
            })
        return jsonify({"error": "user not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# VULN 4: Weak MD5 hashing + SQL injection in login
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')
    hashed = hashlib.md5(password.encode()).hexdigest()
    conn = get_db()
    query = f"SELECT * FROM users WHERE username='{username}'"
    cursor = conn.execute(query)
    user = cursor.fetchone()
    conn.close()
    if user and user[2] == password:
        token = pyjwt.encode(
            {"user": username, "role": user[4]},
            JWT_SECRET,
            algorithm="HS256"
        )
        return jsonify({
            "status": "success",
            "token": token,
            "user_data": {
                "id": user[0], "username": user[1],
                "email": user[3], "role": user[4]
            }
        })
    return jsonify({"status": "failed"}), 401


# VULN 5: Weak JWT — no expiry, weak secret
@app.route('/token', methods=['POST'])
def generate_token():
    data = request.get_json() or {}
    user = data.get('user', 'anonymous')
    token = pyjwt.encode(
        {"user": user, "admin": True},
        JWT_SECRET,
        algorithm="HS256"
    )
    return jsonify({"token": token})


@app.route('/verify')
def verify_token():
    token = request.args.get('token', '')
    try:
        payload = pyjwt.decode(
            token,
            options={"verify_signature": False}
        )
        return jsonify({"valid": True, "payload": payload})
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})


# VULN 6: Command injection
@app.route('/ping')
def ping_host():
    host = request.args.get('host', 'localhost')
    result = os.popen(f"ping -n 1 {host}").read()
    return jsonify({"host": host, "result": result})


# VULN 7: Insecure deserialization
@app.route('/load')
def load_session():
    data = request.args.get('data', '')
    try:
        obj = pickle.loads(bytes.fromhex(data))
        return jsonify({"loaded": str(obj)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# VULN 8: Unvalidated redirect
@app.route('/redirect')
def redirect_user():
    url = request.args.get('url', '/')
    return redirect(url)


# NUCLEI TRIGGER 1: Exposed .env
@app.route('/.env')
def expose_env():
    env_content = """# NepalStartup Production Config
DATABASE_URL=postgresql://admin:SuperSecret123@db.internal:5432/prod
SECRET_KEY=flask-secret-key-production-xyz789
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
STRIPE_SECRET_KEY=sk_live_hardcoded-secret-for-testing
SENDGRID_API_KEY=SG.hardcoded-secret-for-testing
DEBUG=True
ALLOWED_HOSTS=*
"""
    return Response(env_content, mimetype='text/plain', status=200)


# NUCLEI TRIGGER 2: Exposed .git config
@app.route('/.git/config')
def expose_git_config():
    git_config = """[core]
    repositoryformatversion = 0
    filemode = false
    bare = false
[remote "origin"]
    url = https://github.com/nepalstartup/internal-api.git
    fetch = +refs/heads/*:refs/refs/remotes/origin/*
[user]
    email = dev@nepalstartup.com
    name = Nepal Startup Dev
"""
    return Response(git_config, mimetype='text/plain', status=200)


# NUCLEI TRIGGER 3: Debug page
@app.route('/debug')
def debug_page():
    return jsonify({
        "debug": True,
        "config": {
            "SECRET_KEY": SECRET_KEY,
            "DATABASE_URL": DATABASE_URL,
            "ADMIN_PASSWORD": ADMIN_PASSWORD,
        },
        "env_vars": dict(os.environ)
    })


# NUCLEI TRIGGER 4: Backup SQL file
@app.route('/backup.sql')
def expose_backup():
    backup_content = """-- NepalStartup Database Backup
-- WARNING: Contains sensitive data

INSERT INTO users VALUES (1,'admin','admin123','4532-1234-5678-9012');
INSERT INTO users VALUES (2,'alice','password1','4916-8765-4321-0987');
INSERT INTO users VALUES (3,'bob','secret','5425-2334-3010-9903');
"""
    return Response(backup_content, mimetype='text/plain', status=200)


# VULN 9: Weak crypto (MD5 for integrity)
@app.route('/encrypt')
def encrypt_data():
    data = request.args.get('data', 'sensitive_data')
    encoded = base64.b64encode(data.encode()).decode()
    checksum = hashlib.md5(data.encode()).hexdigest()
    return jsonify({
        "encrypted": encoded,
        "checksum": checksum,
        "algorithm": "base64+md5"
    })


if __name__ == '__main__':
    init_db()
    print("=" * 60)
    print("🚨 SHIELDLABS DEMO TARGET — http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)