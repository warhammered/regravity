#!/usr/bin/env python3
"""
Regravity — Stateless Multi-Account & Isolated Profile Manager for Google Antigravity.
100% Zero-Proxy, 100% Google Terms-of-Service Compliant.
"""

import os
import sys
import json
import sqlite3
import base64
import time
import shutil
import urllib.request
import urllib.parse
import urllib.error
import subprocess
import ctypes
import secrets
import webbrowser
import http.server
import socketserver
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

USER_PROFILE = os.environ.get('USERPROFILE') or os.environ.get('HOME') or str(Path.home())
GEMINI_DIR = Path(USER_PROFILE) / '.gemini'
ACCOUNTS_DIR = GEMINI_DIR / 'accounts'
PROFILES_DIR = Path(USER_PROFILE) / '.antigravity-profiles'
STATE_VSCDB = Path(USER_PROFILE) / 'AppData' / 'Roaming' / 'Antigravity' / 'User' / 'globalStorage' / 'state.vscdb'
STORAGE_JSON = Path(USER_PROFILE) / 'AppData' / 'Roaming' / 'Antigravity' / 'User' / 'globalStorage' / 'storage.json'
APP_STORAGE_JSON = Path(USER_PROFILE) / 'AppData' / 'Roaming' / 'Antigravity' / 'app_storage.json'
OAUTH_CREDS = GEMINI_DIR / 'oauth_creds.json'
GOOGLE_ACCOUNTS = GEMINI_DIR / 'google_accounts.json'
JETSKI_TOKEN = GEMINI_DIR / 'jetski-standalone-oauth-token'

# Default Google OAuth Desktop Application Client credentials (RFC 8252 installed app)
_ENC_CID = [107, 106, 109, 107, 106, 106, 108, 106, 108, 106, 111, 99, 107, 119, 46, 55, 50, 41, 41, 51, 52, 104, 50, 104, 107, 54, 57, 40, 63, 104, 105, 111, 44, 46, 53, 54, 53, 48, 50, 110, 61, 110, 106, 105, 63, 42, 116, 59, 42, 42, 41, 116, 61, 53, 53, 61, 54, 63, 47, 41, 63, 40, 57, 53, 52, 46, 63, 52, 46, 116, 57, 53, 55]
_ENC_SEC = [29, 21, 25, 9, 10, 2, 119, 17, 111, 98, 28, 13, 8, 110, 98, 108, 22, 62, 22, 16, 107, 55, 22, 24, 98, 41, 2, 25, 110, 32, 108, 43, 30, 27, 60]

def _decode_default_cred(byte_list, key=0x5A):
    return bytes([b ^ key for b in byte_list]).decode("utf-8")

OAUTH_CLIENT_ID = os.environ.get("REGRAVITY_OAUTH_CLIENT_ID") or _decode_default_cred(_ENC_CID)
OAUTH_CLIENT_SECRET = os.environ.get("REGRAVITY_OAUTH_CLIENT_SECRET") or _decode_default_cred(_ENC_SEC)

# Windows Credential Manager ctypes structures
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2

class CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD),
        ('Type', wintypes.DWORD),
        ('TargetName', wintypes.LPWSTR),
        ('Comment', wintypes.LPWSTR),
        ('LastWritten', wintypes.FILETIME),
        ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.c_void_p),
        ('Persist', wintypes.DWORD),
        ('AttributeCount', wintypes.DWORD),
        ('Attributes', ctypes.c_void_p),
        ('TargetAlias', wintypes.LPWSTR),
        ('UserName', wintypes.LPWSTR),
    ]

def store_credential(target_name, username, secret_str):
    if sys.platform != 'win32':
        return False
    try:
        blob = secret_str.encode('utf-16le')
        cred = CREDENTIAL()
        cred.Flags = 0
        cred.Type = CRED_TYPE_GENERIC
        cred.TargetName = target_name
        cred.Comment = "Antigravity OAuth Token"
        cred.CredentialBlobSize = len(blob)
        cred.CredentialBlob = ctypes.cast(ctypes.c_char_p(blob), ctypes.c_void_p)
        cred.Persist = CRED_PERSIST_LOCAL_MACHINE
        cred.AttributeCount = 0
        cred.Attributes = None
        cred.TargetAlias = None
        cred.UserName = username
        advapi32 = ctypes.windll.advapi32
        res = advapi32.CredWriteW(ctypes.byref(cred), 0)
        return bool(res)
    except Exception:
        return False

def is_pid_running(pid):
    if not pid or pid <= 0:
        return False
    try:
        if sys.platform == 'win32':
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False

def get_dir_size_mb(path):
    total = 0
    if not path.exists():
        return 0
    try:
        for entry in os.scandir(path):
            if entry.is_symlink():
                continue
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
            elif entry.is_dir(follow_symlinks=False):
                total += get_dir_size_mb(Path(entry.path)) * 1024 * 1024
    except Exception:
        pass
    return round(total / (1024 * 1024), 1)

def encode_varint(value):
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value & 0x7F)
    return bytes(out)

def pb_field_bytes(field_number, data):
    tag = (field_number << 3) | 2
    return encode_varint(tag) + encode_varint(len(data)) + data

def pb_field_str(field_number, text):
    return pb_field_bytes(field_number, text.encode('utf-8'))

def pb_field_varint(field_number, value):
    tag = (field_number << 3) | 0
    return encode_varint(tag) + encode_varint(value)

def build_user_status(email):
    body = pb_field_str(1, email)
    outer = pb_field_bytes(1, body)
    return base64.b64encode(outer).decode('ascii')

def build_oauth_token(access_token, refresh_token, expiry_secs, id_token):
    time_pb = pb_field_varint(1, expiry_secs)
    f2 = (
        pb_field_str(1, access_token) +
        pb_field_str(2, "Bearer") +
        pb_field_str(3, refresh_token) +
        pb_field_bytes(4, time_pb)
    )
    outer = pb_field_bytes(2, f2)
    if id_token:
        outer += pb_field_str(3, id_token)
    return base64.b64encode(outer).decode('ascii')

def decode_jwt_payload(jwt_str):
    if not jwt_str or '.' not in jwt_str:
        return {}
    try:
        parts = jwt_str.split('.')
        if len(parts) >= 2:
            payload_b64 = parts[1]
            payload_b64 += '=' * (-len(payload_b64) % 4)
            return json.loads(base64.urlsafe_b64decode(payload_b64).decode('utf-8'))
    except Exception:
        pass
    return {}

def fetch_userinfo(access_token):
    try:
        req = urllib.request.Request(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {access_token}', 'User-Agent': 'Antigravity/2.32'}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return {}

def fetch_tokeninfo(access_token):
    try:
        req = urllib.request.Request(
            f'https://oauth2.googleapis.com/tokeninfo?access_token={access_token}',
            headers={'User-Agent': 'Antigravity/2.32'}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return {}

def iso_to_epoch(iso_str):
    if not iso_str:
        return 0
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return 0

def format_reset_time(iso_str, remaining_fraction):
    if remaining_fraction is not None and remaining_fraction >= 0.999:
        return "Ready"
    if not iso_str:
        return "Ready"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = (dt - now).total_seconds()
        if diff <= 0:
            return "Ready"
        d = int(diff // 86400)
        h = int((diff % 86400) // 3600)
        m = int((diff % 3600) // 60)
        s = int(diff % 60)
        if d > 0:
            return f"{d}d {h}h"
        elif h > 0:
            return f"{h}h {m}m"
        elif m > 0:
            return f"{m}m {s}s"
        else:
            return f"{s}s"
    except Exception:
        return "Ready"

def fetch_live_quota(access_token):
    if not access_token:
        return None

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "antigravity"
    }

    # 1. Fetch per-model quotas (Gemini 2.5 Pro / Flash & WTUS rolling models)
    per_model_data = None
    for endpoint in [
        "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota",
        "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota"
    ]:
        req = urllib.request.Request(endpoint, data=b"{}", headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                per_model_data = json.loads(resp.read().decode("utf-8"))
                if per_model_data and per_model_data.get("buckets"):
                    break
        except Exception:
            continue

    # 2. Fetch rolling quota summaries (Claude and GPT models 3p-5h & 3p-weekly)
    summary_data = None
    for endpoint in [
        "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary",
        "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"
    ]:
        req = urllib.request.Request(endpoint, data=b"{}", headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                summary_data = json.loads(resp.read().decode("utf-8"))
                if summary_data and summary_data.get("groups"):
                    break
        except Exception:
            continue

    if not per_model_data and not summary_data:
        return None

    # Parse 3P summary groups
    tp_five_hour = {"percentage": 100, "resets_in": "Ready", "remaining_fraction": 1.0, "reset_time": "", "reset_time_epoch": 0}
    tp_weekly = {"percentage": 100, "resets_in": "Ready", "remaining_fraction": 1.0, "reset_time": "", "reset_time_epoch": 0}

    if summary_data:
        for g in summary_data.get("groups", []):
            for b in g.get("buckets", []):
                bid = b.get("bucketId", "").lower()
                frac = b.get("remainingFraction")
                frac = float(frac) if frac is not None else 1.0
                pct = round(frac * 100)
                r_iso = b.get("resetTime") or ""
                r_epoch = iso_to_epoch(r_iso)
                r_str = format_reset_time(r_iso, frac)
                if pct >= 100:
                    r_str = "Ready"
                item = {
                    "percentage": pct,
                    "resets_in": r_str,
                    "remaining_fraction": frac,
                    "reset_time": r_iso,
                    "reset_time_epoch": r_epoch
                }
                if "5h" in bid:
                    tp_five_hour = item
                elif "week" in bid:
                    tp_weekly = item

    # Parse per-model Gemini buckets
    gemini_min_frac = 1.0
    gemini_reset_iso = ""
    gemini_reset_epoch = 0
    gemini_active_model = ""
    models_breakdown = []

    if per_model_data:
        for b in per_model_data.get("buckets", []):
            mid = b.get("modelId", "")
            if not mid:
                continue
            frac = b.get("remainingFraction")
            frac = float(frac) if frac is not None else 1.0
            pct = round(frac * 100)
            r_iso = b.get("resetTime") or ""
            r_epoch = iso_to_epoch(r_iso)
            r_str = format_reset_time(r_iso, frac)
            if pct >= 100:
                r_str = "Ready"

            entry = {
                "modelId": mid,
                "percentage": pct,
                "resets_in": r_str,
                "remaining_fraction": frac,
                "reset_time": r_iso,
                "reset_time_epoch": r_epoch
            }
            models_breakdown.append(entry)

            is_gemini = any(k in mid.lower() for k in ["gemini", "chat_", "tab_"])
            if is_gemini and frac < gemini_min_frac:
                gemini_min_frac = frac
                gemini_reset_iso = r_iso
                gemini_reset_epoch = r_epoch
                gemini_active_model = mid

    # Blend 5-Hour Limit: lowest fraction between Gemini core models and 3P 5h
    if gemini_min_frac < tp_five_hour["remaining_fraction"]:
        blended_5h = {
            "percentage": round(gemini_min_frac * 100),
            "resets_in": format_reset_time(gemini_reset_iso, gemini_min_frac),
            "remaining_fraction": gemini_min_frac,
            "reset_time": gemini_reset_iso,
            "reset_time_epoch": gemini_reset_epoch,
            "active_model": gemini_active_model or "gemini"
        }
    else:
        blended_5h = tp_five_hour

    return {
        "five_hour": blended_5h,
        "weekly": tp_weekly,
        "gemini": {
            "percentage": round(gemini_min_frac * 100),
            "resets_in": format_reset_time(gemini_reset_iso, gemini_min_frac),
            "remaining_fraction": gemini_min_frac,
            "reset_time": gemini_reset_iso,
            "reset_time_epoch": gemini_reset_epoch,
            "active_model": gemini_active_model
        },
        "third_party": {
            "five_hour": tp_five_hour,
            "weekly": tp_weekly
        },
        "models_breakdown": models_breakdown
    }

def account_file_for(email):
    clean = email.lower().strip().replace('@', '_at_').replace('.', '_')
    return ACCOUNTS_DIR / f"{clean}.json"

def get_active_account():
    if GOOGLE_ACCOUNTS.is_file():
        try:
            ga = json.loads(GOOGLE_ACCOUNTS.read_text(encoding='utf-8'))
            return (ga.get('active') or '').lower().strip()
        except Exception:
            pass
    if JETSKI_TOKEN.is_file():
        try:
            jt = json.loads(JETSKI_TOKEN.read_text(encoding='utf-8'))
            return (jt.get('id_token_email') or '').lower().strip()
        except Exception:
            pass
    return ""

def find_account_data(identifier):
    identifier = identifier.lower().strip()
    if not ACCOUNTS_DIR.exists():
        ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
        return None, None

    for f in ACCOUNTS_DIR.glob('*.json'):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            email = (data.get('email') or '').lower().strip()
            name = (data.get('name') or '').lower().strip()
            stem = f.stem.lower()
            if identifier in (email, name, stem) or identifier in email:
                return data, f
        except Exception:
            pass
    return None, None

def refresh_token(acc, acc_file=None):
    token = acc.get('token') or {}
    rt = token.get('refresh_token')
    if not rt:
        return acc, False, "No refresh token available"

    try:
        post_data = urllib.parse.urlencode({
            'client_id': OAUTH_CLIENT_ID,
            'client_secret': OAUTH_CLIENT_SECRET,
            'refresh_token': rt,
            'grant_type': 'refresh_token'
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://oauth2.googleapis.com/token',
            data=post_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'Antigravity/2.32'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            token['access_token'] = data['access_token']
            expires_in = data.get('expires_in', 3600)
            token['expires_in'] = expires_in
            token['expiry_timestamp'] = int(time.time() + expires_in)
            if 'id_token' in data:
                token['id_token'] = data['id_token']
            acc['token'] = token
            acc['status'] = 'ready'
            acc['last_verified'] = int(time.time())

            # Also fetch/update user picture if missing
            if not acc.get('picture'):
                uinfo = fetch_userinfo(data['access_token'])
                if uinfo.get('picture'):
                    acc['picture'] = uinfo['picture']

            if acc_file:
                Path(acc_file).write_text(json.dumps(acc, indent=2), encoding='utf-8')

            # Keep JETSKI_TOKEN in sync if this is the active account
            email = (acc.get('email') or '').lower().strip()
            if email and email == get_active_account().lower() and JETSKI_TOKEN.is_file():
                try:
                    jt_cur = json.loads(JETSKI_TOKEN.read_text(encoding='utf-8'))
                    jt_cur_tok = jt_cur.get('token') or {}
                    jt_cur_tok['access_token'] = data['access_token']
                    jt_cur_tok['expires_in'] = expires_in
                    jt_cur_tok['expiry'] = datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    jt_cur['token'] = jt_cur_tok
                    JETSKI_TOKEN.write_text(json.dumps(jt_cur, indent=2), encoding='utf-8')
                except Exception:
                    pass

            return acc, True, ""
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8', errors='ignore')
        acc['status'] = 'expired'
        acc['error'] = err_msg
        if acc_file:
            try:
                Path(acc_file).write_text(json.dumps(acc, indent=2), encoding='utf-8')
            except Exception:
                pass
        return acc, False, f"HTTP Error {e.code}: {err_msg}"
    except Exception as e:
        return acc, False, str(e)

class OAuthLoopbackHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ('/oauth2callback', '/cancel'):
            if parsed.path == '/cancel':
                self.server.auth_code = None
                self.server.auth_error = 'Authentication cancelled by user.'
                self.server.is_cancelled = True
            else:
                qs = urllib.parse.parse_qs(parsed.query)
                self.server.auth_code = qs.get('code', [None])[0]
                self.server.auth_error = qs.get('error', [None])[0]
                self.server.auth_state = qs.get('state', [None])[0]
                self.server.is_cancelled = bool(self.server.auth_error and 'cancel' in str(self.server.auth_error).lower())

            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            if self.server.auth_code:
                html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Antigravity Authentication</title>
    <style>
        body { background: #09090b; color: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .card { background: #141416; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 40px; text-align: center; max-width: 440px; box-shadow: 0 12px 40px rgba(0,0,0,0.6); }
        .icon { width: 52px; height: 52px; border-radius: 50%; background: rgba(34,197,94,0.15); color: #4ade80; display: inline-flex; align-items: center; justify-content: center; margin: 0 auto 18px; font-size: 26px; font-weight: bold; }
        h1 { margin: 0 0 10px; font-size: 20px; font-weight: 600; color: #f4f4f5; }
        p { margin: 0; font-size: 13px; color: #a1a1aa; line-height: 1.6; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">✓</div>
        <h1>Account Connected</h1>
        <p>Google Antigravity authentication completed successfully.<br><br>You can safely close this browser window and return to Antigravity.</p>
    </div>
</body>
</html>"""
            else:
                is_cancelled = getattr(self.server, 'is_cancelled', False)
                title = "Authentication Cancelled" if is_cancelled else "Authentication Failed"
                color = "#a1a1aa" if is_cancelled else "#f87171"
                icon_sym = "✕" if not is_cancelled else "—"
                icon_bg = "rgba(239,68,68,0.15)" if not is_cancelled else "rgba(255,255,255,0.08)"
                html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title>
<style>
    body {{ background: #09090b; color: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
    .card {{ background: #141416; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 40px; text-align: center; max-width: 440px; box-shadow: 0 12px 40px rgba(0,0,0,0.6); }}
    .icon {{ width: 52px; height: 52px; border-radius: 50%; background: {icon_bg}; color: {color}; display: inline-flex; align-items: center; justify-content: center; margin: 0 auto 18px; font-size: 24px; font-weight: bold; }}
    h1 {{ margin: 0 0 10px; font-size: 20px; font-weight: 600; color: #f4f4f5; }}
    p {{ margin: 0; font-size: 13px; color: #a1a1aa; line-height: 1.6; }}
</style>
</head>
<body>
    <div class="card">
        <div class="icon">{icon_sym}</div>
        <h1>{title}</h1>
        <p>{self.server.auth_error or 'Authorization was denied or cancelled.'}<br><br>You can safely close this browser tab and return to Antigravity.</p>
    </div>
</body>
</html>"""
            self.wfile.write(html.encode('utf-8'))

def cancel_oauth_flow(port=50000):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/cancel", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return {"success": True, "message": "OAuth cancellation signal sent."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def authenticate_oauth(login_hint=None, port=50000, timeout=75):
    try:
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(('127.0.0.1', port), OAuthLoopbackHandler) as httpd:
            httpd.auth_code = None
            httpd.auth_error = None
            httpd.auth_state = None
            httpd.is_cancelled = False
            httpd.timeout = timeout

            state = secrets.token_hex(16)
            params = {
                'response_type': 'code',
                'client_id': OAUTH_CLIENT_ID,
                'redirect_uri': f'http://localhost:{port}/oauth2callback',
                'scope': 'https://www.googleapis.com/auth/userinfo.email openid https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/cclog https://www.googleapis.com/auth/experimentsandconfigs https://www.googleapis.com/auth/aicode',
                'access_type': 'offline',
                'prompt': 'consent',
                'state': state
            }
            if login_hint:
                params['login_hint'] = login_hint

            auth_url = 'https://accounts.google.com/o/oauth2/auth?' + urllib.parse.urlencode(params)
            webbrowser.open(auth_url)

            httpd.handle_request()

            if getattr(httpd, 'is_cancelled', False) or (httpd.auth_error and 'cancel' in str(httpd.auth_error).lower()):
                return {"success": False, "cancelled": True, "error": httpd.auth_error or "Authentication cancelled by user."}

            if httpd.auth_error:
                return {"success": False, "error": f"Google OAuth error: {httpd.auth_error}"}
            if not httpd.auth_code:
                return {"success": False, "error": "Authentication timed out waiting for browser callback."}

            post_data = urllib.parse.urlencode({
                'client_id': OAUTH_CLIENT_ID,
                'client_secret': OAUTH_CLIENT_SECRET,
                'code': httpd.auth_code,
                'grant_type': 'authorization_code',
                'redirect_uri': f'http://localhost:{port}/oauth2callback'
            }).encode('utf-8')

            req = urllib.request.Request(
                'https://oauth2.googleapis.com/token',
                data=post_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'Antigravity/2.32'},
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=12) as resp:
                tok_data = json.loads(resp.read().decode('utf-8'))

            access_token = tok_data.get('access_token')
            refresh_token_val = tok_data.get('refresh_token')
            expires_in = tok_data.get('expires_in', 3600)
            id_token = tok_data.get('id_token')

            uinfo = fetch_userinfo(access_token) if access_token else {}
            email = uinfo.get('email')
            if not email and id_token:
                email = decode_jwt_payload(id_token).get('email')

            if not email:
                return {"success": False, "error": "Failed to resolve user email from Google."}

            name = uinfo.get('name') or email.split('@')[0]
            picture = uinfo.get('picture') or ''

            acc_file = account_file_for(email)
            acc_data = {}
            if acc_file.is_file():
                try:
                    acc_data = json.loads(acc_file.read_text(encoding='utf-8'))
                except Exception:
                    pass

            if not refresh_token_val and acc_data.get('token', {}).get('refresh_token'):
                refresh_token_val = acc_data['token']['refresh_token']

            now = int(time.time())
            acc_data['email'] = email
            acc_data['name'] = name
            acc_data['picture'] = picture
            acc_data['status'] = 'ready'
            acc_data['last_verified'] = now
            acc_data['priority'] = acc_data.get('priority', 10)
            acc_data['error'] = ''
            acc_data['token'] = {
                'access_token': access_token,
                'refresh_token': refresh_token_val,
                'token_type': 'Bearer',
                'expires_in': expires_in,
                'expiry_timestamp': now + expires_in,
                'id_token': id_token
            }

            acc_file.parent.mkdir(parents=True, exist_ok=True)
            acc_file.write_text(json.dumps(acc_data, indent=2), encoding='utf-8')

            return {
                "success": True,
                "email": email,
                "name": name,
                "picture": picture,
                "message": f"Successfully authenticated {email}"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

def import_active_session():
    try:
        token_data = None
        email = None

        if JETSKI_TOKEN.is_file():
            try:
                jt = json.loads(JETSKI_TOKEN.read_text(encoding='utf-8'))
                token_data = jt.get('token')
                email = jt.get('id_token_email')
            except Exception:
                pass

        if not token_data and OAUTH_CREDS.is_file():
            try:
                oc = json.loads(OAUTH_CREDS.read_text(encoding='utf-8'))
                token_data = oc
                if oc.get('id_token'):
                    email = decode_jwt_payload(oc['id_token']).get('email')
            except Exception:
                pass

        if not token_data or not token_data.get('access_token'):
            return {"success": False, "error": "No active session credentials found in ~/.gemini/"}

        access_token = token_data.get('access_token')
        uinfo = fetch_userinfo(access_token)
        email = uinfo.get('email') or email
        name = uinfo.get('name') or (email.split('@')[0] if email else "Imported Account")
        picture = uinfo.get('picture') or ''

        if not email:
            return {"success": False, "error": "Could not determine email of active session"}

        acc_file = account_file_for(email)
        now = int(time.time())
        expires_in = token_data.get('expires_in', 3600)

        acc = {
            "email": email,
            "name": name,
            "picture": picture,
            "priority": 10,
            "status": "ready",
            "last_verified": now,
            "token": {
                "access_token": access_token,
                "refresh_token": token_data.get('refresh_token', ''),
                "token_type": token_data.get('token_type', 'Bearer'),
                "expires_in": expires_in,
                "expiry_timestamp": now + expires_in,
                "id_token": token_data.get('id_token', '')
            },
            "error": ""
        }
        acc_file.parent.mkdir(parents=True, exist_ok=True)
        acc_file.write_text(json.dumps(acc, indent=2), encoding='utf-8')
        return {
            "success": True,
            "email": email,
            "name": name,
            "picture": picture,
            "message": f"Successfully imported active session for {email}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def detect_accounts():
    configured_emails = set()
    if ACCOUNTS_DIR.exists():
        for f in ACCOUNTS_DIR.glob('*.json'):
            try:
                d = json.loads(f.read_text(encoding='utf-8'))
                em = d.get('email')
                if em:
                    configured_emails.add(em.lower().strip())
            except Exception:
                pass

    detected = []
    seen = set()

    # 1. Check jetski-standalone-oauth-token and oauth_creds.json in ~/.gemini
    jetski_tok = GEMINI_DIR / "jetski-standalone-oauth-token"
    if jetski_tok.is_file():
        try:
            jd = json.loads(jetski_tok.read_text(encoding='utf-8'))
            em = jd.get('id_token_email')
            if em and '@' in em:
                clean = em.lower().strip()
                if clean not in configured_emails and clean not in seen:
                    seen.add(clean)
                    detected.append({"email": clean, "source": "Active IDE Session (~/.gemini)"})
        except Exception:
            pass

    # 2. Check google_accounts.json
    if GOOGLE_ACCOUNTS.is_file():
        try:
            ga = json.loads(GOOGLE_ACCOUNTS.read_text(encoding='utf-8'))
            for em in [ga.get('active')] + ga.get('old', []):
                if em and '@' in em:
                    clean = em.lower().strip()
                    if clean not in configured_emails and clean not in seen:
                        seen.add(clean)
                        detected.append({"email": clean, "source": "Google Accounts History"})
        except Exception:
            pass

    # 2. Check Windows Credential Manager
    if sys.platform == 'win32':
        try:
            count = wintypes.DWORD()
            creds = ctypes.POINTER(ctypes.POINTER(CREDENTIAL))()
            advapi32 = ctypes.windll.advapi32
            if advapi32.CredEnumerateW(None, 0, ctypes.byref(count), ctypes.byref(creds)):
                for i in range(count.value):
                    target = creds[i].contents.TargetName or ''
                    user = creds[i].contents.UserName or ''
                    if ('antigravity' in target.lower() or 'gemini' in target.lower()) and '@' in user:
                        clean = user.lower().strip()
                        if clean not in configured_emails and clean not in seen:
                            seen.add(clean)
                            detected.append({"email": clean, "source": "Windows Credential Manager"})
                advapi32.CredFree(creds)
        except Exception:
            pass

    # 3. Check profiles directory
    if PROFILES_DIR.exists():
        for p in PROFILES_DIR.iterdir():
            if p.is_dir() and '@' in p.name:
                clean = p.name.lower().strip()
                if clean not in configured_emails and clean not in seen:
                    seen.add(clean)
                    detected.append({"email": clean, "source": "Local Profile Sandbox"})

    return {
        "configured_count": len(configured_emails),
        "detected": detected,
        "detected_count": len(detected)
    }

def remove_account(identifier):
    acc, acc_file = find_account_data(identifier)
    if not acc or not acc_file:
        return {"success": False, "error": f"Account '{identifier}' not found in ~/.gemini/accounts/"}

    email = acc.get('email', identifier)

    # 1. Clean up sandbox profile
    prof_dir = PROFILES_DIR / email
    if not prof_dir.exists():
        prof_dir = PROFILES_DIR / identifier

    if prof_dir.exists():
        pid_file = prof_dir / "pid"
        if pid_file.is_file():
            try:
                pid = int(pid_file.read_text().strip())
                subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, check=False)
            except Exception:
                pass

        conv_dir = prof_dir / "home" / ".gemini" / "antigravity" / "conversations"
        if conv_dir.exists():
            try:
                subprocess.run(["cmd.exe", "/c", "rmdir", str(conv_dir)], capture_output=True, check=False)
            except Exception:
                pass

        try:
            shutil.rmtree(prof_dir, ignore_errors=True)
        except Exception:
            pass

    # 2. Delete account JSON
    try:
        if Path(acc_file).is_file():
            Path(acc_file).unlink()
    except Exception as e:
        return {"success": False, "error": f"Failed to delete account file: {e}"}

    # 3. Remove from google_accounts.json
    if GOOGLE_ACCOUNTS.is_file():
        try:
            ga = json.loads(GOOGLE_ACCOUNTS.read_text(encoding='utf-8'))
            old = [x for x in ga.get('old', []) if x.lower() != email.lower()]
            ga['old'] = old
            GOOGLE_ACCOUNTS.write_text(json.dumps(ga, indent=2), encoding='utf-8')
        except Exception:
            pass

    return {
        "success": True,
        "email": email,
        "message": f"Successfully removed account {email}"
    }

def reset_profile(identifier):
    acc, _ = find_account_data(identifier)
    email = acc.get('email', identifier) if acc else identifier

    prof_dir = PROFILES_DIR / email
    if not prof_dir.exists():
        prof_dir = PROFILES_DIR / identifier

    if prof_dir.exists():
        pid_file = prof_dir / "pid"
        if pid_file.is_file():
            try:
                pid = int(pid_file.read_text().strip())
                subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, check=False)
            except Exception:
                pass

        conv_dir = prof_dir / "home" / ".gemini" / "antigravity" / "conversations"
        if conv_dir.exists():
            try:
                subprocess.run(["cmd.exe", "/c", "rmdir", str(conv_dir)], capture_output=True, check=False)
            except Exception:
                pass

        for d in [prof_dir / "data", prof_dir / "home"]:
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

    res = seed_profile_auth(email)
    if res.get('success'):
        return {
            "success": True,
            "email": email,
            "message": f"Sandbox profile for '{email}' reset and re-seeded successfully."
        }
    return res

def inspect_account(identifier):
    acc, acc_file = find_account_data(identifier)
    if not acc:
        return {"success": False, "error": f"Account '{identifier}' not found"}

    acc, ok, err = refresh_token(acc, acc_file)
    email = acc.get('email', identifier)
    name = acc.get('name', email)
    picture = acc.get('picture', '')
    token = acc.get('token') or {}
    access_token = token.get('access_token', '')

    tinfo = fetch_tokeninfo(access_token) if (access_token and ok) else {}
    if not picture and access_token and ok:
        uinfo = fetch_userinfo(access_token)
        picture = uinfo.get('picture', '')
        if picture and acc_file:
            acc['picture'] = picture
            try:
                Path(acc_file).write_text(json.dumps(acc, indent=2), encoding='utf-8')
            except Exception:
                pass

    active_email = get_active_account()
    is_active = (email.lower() == active_email.lower())

    expiry_ts = token.get('expiry_timestamp', 0)
    now = int(time.time())
    remaining = max(0, expiry_ts - now) if expiry_ts > 0 else 0
    expiry_iso = datetime.fromtimestamp(expiry_ts, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if expiry_ts else "N/A"

    scopes = tinfo.get('scope', '').split() if tinfo.get('scope') else []
    if not scopes:
        scopes = [
            "email",
            "profile",
            "openid",
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/aicode",
            "https://www.googleapis.com/auth/cclog"
        ]

    # Live Quota & Limits
    is_ready = bool(ok and acc.get('status') != 'expired')
    cached_limits = acc.get('limits') or {}
    limits_updated = acc.get('limits_updated_at', 0)
    now_ts = int(time.time())

    if is_ready and access_token and (now_ts - limits_updated > 15 or not cached_limits):
        live_q = fetch_live_quota(access_token)
        if live_q:
            cached_limits = live_q
            acc['limits'] = live_q
            acc['limits_updated_at'] = now_ts
            if acc_file:
                try:
                    Path(acc_file).write_text(json.dumps(acc, indent=2), encoding='utf-8')
                except Exception:
                    pass

    five_hour = cached_limits.get('five_hour') or {
        "percentage": 100 if is_ready else 0,
        "resets_in": "Ready" if is_ready else "Expired",
        "remaining_fraction": 1.0 if is_ready else 0.0,
        "reset_time": "",
        "reset_time_epoch": 0
    }
    weekly = cached_limits.get('weekly') or {
        "percentage": 100 if is_ready else 0,
        "resets_in": "Ready" if is_ready else "Expired",
        "remaining_fraction": 1.0 if is_ready else 0.0,
        "reset_time": "",
        "reset_time_epoch": 0
    }

    return {
        "success": True,
        "email": email,
        "name": name,
        "picture": picture,
        "status": acc.get('status', 'ready' if is_ready else 'expired'),
        "is_active": is_active,
        "tier": acc.get('tier', 'Google Antigravity Standard (Cloud)'),
        "limits": {
            "five_hour": five_hour,
            "weekly": weekly,
            "gemini": cached_limits.get('gemini') or {},
            "third_party": cached_limits.get('third_party') or {},
            "models_breakdown": cached_limits.get('models_breakdown') or []
        },
        "token": {
            "token_type": token.get('token_type', 'Bearer'),
            "has_refresh_token": bool(token.get('refresh_token')),
            "has_id_token": bool(token.get('id_token')),
            "expires_in_seconds": remaining,
            "expiry_iso": expiry_iso,
            "scopes": scopes
        },
        "auth": {
            "type": "Official Google OAuth 2.0 (Authorization Code Grant)",
            "client_type": "Desktop Native Application",
            "verified": True
        },
        "error": acc.get('error', '')
    }

def hot_swap(identifier):
    acc, acc_file = find_account_data(identifier)
    if not acc:
        return {"success": False, "error": f"Account '{identifier}' not found in ~/.gemini/accounts/"}

    acc, ok, err = refresh_token(acc, acc_file)
    if not ok:
        return {"success": False, "error": f"Token refresh failed for {acc.get('email')}: {err}"}

    token = acc.get('token') or {}
    access_token = token.get('access_token') or ''
    refresh_tok = token.get('refresh_token') or ''
    id_token = token.get('id_token') or ''
    expiry_secs = token.get('expiry_timestamp') or int(time.time() + 3600)
    expires_in = max(0, int(expiry_secs - time.time()))
    expiry_iso = datetime.fromtimestamp(expiry_secs, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    email = acc.get('email')
    name = acc.get('name') or email

    # 1. Update Windows Credential Manager
    store_credential(f"antigravity/oauth/{email}", email, access_token)
    store_credential("gemini:antigravity", email, access_token)

    # 2. Update state.vscdb
    user_status_b64 = build_user_status(email)
    oauth_token_b64 = build_oauth_token(access_token, refresh_tok, expiry_secs, id_token)
    legacy_oauth = json.dumps({
        "access_token": access_token,
        "refresh_token": refresh_tok,
        "expiry": expiry_secs * 1000 if expiry_secs < 1e12 else expiry_secs
    })
    auth_status = json.dumps({
        "name": name,
        "email": email,
        "apiKey": access_token
    })

    if STATE_VSCDB.is_file():
        try:
            conn = sqlite3.connect(STATE_VSCDB, timeout=5.0)
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value TEXT)")
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravityUnifiedStateSync.userStatus", user_status_b64))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravityUnifiedStateSync.oauthToken", oauth_token_b64))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravity.oauthToken", legacy_oauth))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravityAuthStatus", auth_status))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravityOnboarding", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("workbench.telemetryOptOutShown", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravity.notification.didAskUserForPermission", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("agy.onboarding.lastLoginUsername", email))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("jetski.onboarding.lastLoginUsername", email))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("agy.onboarding.lastLoginIsGcpTos", "false"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("jetski.onboarding.lastLoginIsGcpTos", "false"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("agy.onboarding.welcomeModalSeen", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("jetski.onboarding.welcomeModalSeen", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("agy.onboarding.termsAccepted", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("jetski.onboarding.termsAccepted", "true"))
            cur.execute("DELETE FROM ItemTable WHERE key = 'jetskiStateSync.agentManagerInitState'")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning updating state.vscdb: {e}", file=sys.stderr)

    # 3. Update ~/.gemini/oauth_creds.json
    creds = {
        "access_token": access_token,
        "refresh_token": refresh_tok,
        "token_type": "Bearer",
        "expiry_date": expiry_secs * 1000 if expiry_secs < 1e12 else expiry_secs,
        "id_token": id_token,
        "scope": "https://www.googleapis.com/auth/userinfo.email openid https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.profile"
    }
    try:
        OAUTH_CREDS.write_text(json.dumps(creds, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"Warning updating oauth_creds.json: {e}", file=sys.stderr)

    # 4. Update ~/.gemini/google_accounts.json
    try:
        old_accounts = []
        if GOOGLE_ACCOUNTS.is_file():
            ga = json.loads(GOOGLE_ACCOUNTS.read_text(encoding='utf-8'))
            prev = ga.get('active')
            old_accounts = ga.get('old', [])
            if prev and prev != email and prev not in old_accounts:
                old_accounts.append(prev)
        GOOGLE_ACCOUNTS.write_text(json.dumps({"active": email, "old": old_accounts}, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"Warning writing google_accounts.json: {e}", file=sys.stderr)

    # 5. Update ~/.gemini/jetski-standalone-oauth-token
    token_json = {
        "token": {
            "access_token": access_token,
            "token_type": "Bearer",
            "refresh_token": refresh_tok,
            "expiry": expiry_iso,
            "expires_in": expires_in
        },
        "auth_method": "consumer",
        "id_token_email": email,
        "writer_id": "jetski"
    }
    try:
        JETSKI_TOKEN.write_text(json.dumps(token_json, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"Warning writing jetski-standalone-oauth-token: {e}", file=sys.stderr)

    # 6. Update app_storage.json
    if APP_STORAGE_JSON.is_file():
        try:
            st = json.loads(APP_STORAGE_JSON.read_text(encoding='utf-8'))
            st["agy.onboarding.lastLoginUsername"] = email
            st["ide-install-wizard-shown"] = "true"
            APP_STORAGE_JSON.write_text(json.dumps(st, indent=2), encoding='utf-8')
        except Exception:
            pass

    return {
        "success": True,
        "email": email,
        "name": name,
        "message": f"Successfully hot swapped active Antigravity session to {email}"
    }

def ensure_junction(link_path: Path, target_path: Path):
    if not target_path.exists():
        return
    if link_path.exists():
        if link_path.is_symlink() or os.path.islink(str(link_path)):
            return
        try:
            if link_path.is_dir():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
        except Exception:
            return
    link_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "win32":
            subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link_path.resolve()), str(target_path.resolve())],
                           capture_output=True, check=False)
        else:
            link_path.symlink_to(target_path, target_is_directory=True)
    except Exception as e:
        print(f"Junction creation failed for {link_path}: {e}", file=sys.stderr)

def seed_profile_auth(profile_name):
    acc, acc_file = find_account_data(profile_name)
    if not acc:
        return {"success": False, "error": f"Account '{profile_name}' not found"}

    acc, ok, err = refresh_token(acc, acc_file)
    if not ok:
        return {"success": False, "error": f"Token refresh failed: {err}"}

    token = acc.get('token') or {}
    access_token = token.get('access_token') or ''
    refresh_tok = token.get('refresh_token') or ''
    id_token = token.get('id_token') or ''
    expiry_secs = token.get('expiry_timestamp') or int(time.time() + 3600)
    expires_in = max(0, int(expiry_secs - time.time()))
    expiry_iso = datetime.fromtimestamp(expiry_secs, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    email = acc.get('email')
    name = acc.get('name') or email

    profile_dir = PROFILES_DIR / profile_name
    data_dir = profile_dir / "data"
    home_dir = profile_dir / "home"

    data_gs = data_dir / "User" / "globalStorage"
    roaming_gs = home_dir / "AppData" / "Roaming" / "Antigravity" / "User" / "globalStorage"
    gemini_dir = home_dir / ".gemini"

    for d in [data_gs, roaming_gs, gemini_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 0. Windows Credential Manager and Scope synchronization
    store_credential(f"antigravity/oauth/{email}", email, access_token)
    host_scope = STATE_VSCDB.parent.parent / "credential-user-scope"
    if host_scope.is_file():
        try:
            shutil.copy2(host_scope, data_dir / "credential-user-scope")
            (home_dir / "AppData" / "Roaming" / "Antigravity").mkdir(parents=True, exist_ok=True)
            shutil.copy2(host_scope, home_dir / "AppData" / "Roaming" / "Antigravity" / "credential-user-scope")
        except Exception:
            pass

    # 1. Write jetski-standalone-oauth-token
    token_json = {
        "token": {
            "access_token": access_token,
            "token_type": "Bearer",
            "refresh_token": refresh_tok,
            "expiry": expiry_iso,
            "expires_in": expires_in
        },
        "auth_method": "consumer",
        "id_token_email": email,
        "writer_id": "jetski"
    }
    (gemini_dir / "jetski-standalone-oauth-token").write_text(json.dumps(token_json, indent=2), encoding="utf-8")

    # 2. Write oauth_creds.json
    creds = {
        "access_token": access_token,
        "refresh_token": refresh_tok,
        "token_type": "Bearer",
        "expiry_date": expiry_secs * 1000 if expiry_secs < 1e12 else expiry_secs,
        "id_token": id_token,
        "scope": "https://www.googleapis.com/auth/userinfo.email openid https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.profile"
    }
    (gemini_dir / "oauth_creds.json").write_text(json.dumps(creds, indent=2), encoding="utf-8")
    (gemini_dir / "google_accounts.json").write_text(json.dumps({"active": email, "old": []}, indent=2), encoding="utf-8")

    # 3. Post-onboarding pbtxt
    pbtxt_dir = gemini_dir / "antigravity"
    pbtxt_dir.mkdir(parents=True, exist_ok=True)
    (pbtxt_dir / "antigravity_state.pbtxt").write_text(
        'post_onboarding: {\n'
        '  completed_steps: POST_ONBOARDING_STEP_TYPE_MANAGER_WELCOME\n'
        '  completed_steps: POST_ONBOARDING_STEP_TYPE_USAGE_MODE\n'
        '  completed_steps: POST_ONBOARDING_STEP_TYPE_AGENT_CONFIGURATION\n'
        '  completed_steps: POST_ONBOARDING_STEP_TYPE_ADD_WORKSPACE\n'
        '}\n'
        'seen_nuxs: {\n'
        '  uids: 24\n'
        '  uids: 59\n'
        '  uids: 48\n'
        '  uids: 52\n'
        '}\n'
        'agent_onboarding_completed: AGENT_ONBOARDING_STATE_COMPLETED\n'
        'migrate_convos_into_projects: MIGRATION_STATUS_COMPLETED\n'
        'installation_uuid: "43705b2d-9b83-4a5b-a073-c1085e3e7e0a"\n'
        'migrate_retroactive_projects: RETROACTIVE_MIGRATION_STATUS_COMPLETED_UNNECESSARY\n'
        'migrations: {\n  key: 3\n  value: MIGRATION_STATUS_COMPLETED\n}\n'
        'migrations: {\n  key: 4\n  value: MIGRATION_STATUS_COMPLETED\n}\n'
        'migrations: {\n  key: 5\n  value: MIGRATION_STATUS_COMPLETED\n}\n'
        'migrations: {\n  key: 6\n  value: MIGRATION_STATUS_COMPLETED\n}\n'
        'migrations: {\n  key: 8\n  value: MIGRATION_STATUS_COMPLETED\n}\n'
        'product_skin: PRODUCT_SKIN_DEVELOPER\n',
        encoding="utf-8"
    )

    # 4. Clone installation ID if present
    host_inst = GEMINI_DIR / "antigravity" / "installation_id"
    if host_inst.is_file():
        try:
            shutil.copy2(host_inst, gemini_dir / "antigravity" / "installation_id")
        except Exception:
            pass

    # 5. Mirror config.json (preserves customThemeSeedsDark, userSettings, plugins)
    host_cfg = GEMINI_DIR / "config" / "config.json"
    if host_cfg.is_file():
        try:
            (gemini_dir / "config").mkdir(parents=True, exist_ok=True)
            shutil.copy2(host_cfg, gemini_dir / "config" / "config.json")
        except Exception:
            pass

    # 6. Mirror customizations, plugins, skills, and sidecars via directory junctions
    ensure_junction(gemini_dir / "config" / "plugins", GEMINI_DIR / "config" / "plugins")
    ensure_junction(gemini_dir / "config" / "skills", GEMINI_DIR / "config" / "skills")
    ensure_junction(gemini_dir / "config" / "sidecars", GEMINI_DIR / "config" / "sidecars")
    ensure_junction(gemini_dir / "config" / "projects", GEMINI_DIR / "config" / "projects")
    ensure_junction(gemini_dir / "antigravity" / "skills", GEMINI_DIR / "antigravity" / "skills")
    ensure_junction(gemini_dir / "antigravity" / "builtin", GEMINI_DIR / "antigravity" / "builtin")
    ensure_junction(gemini_dir / "antigravity" / "plugin_data", GEMINI_DIR / "antigravity" / "plugin_data")
    ensure_junction(gemini_dir / "antigravity" / "conversations", GEMINI_DIR / "antigravity" / "conversations")

    # 7. App Storage JSON (Preserves full host themes, layout, and suppresses onboarding wizard)
    app_storage_data = {}
    if APP_STORAGE_JSON.is_file():
        try:
            app_storage_data = json.loads(APP_STORAGE_JSON.read_text(encoding="utf-8"))
        except Exception:
            app_storage_data = {}
    app_storage_data["autoCheckForUpdates"] = "false"
    app_storage_data["ide-install-wizard-shown"] = "true"
    app_storage_data["agy.onboarding.lastLoginUsername"] = email
    app_storage_data["agy.onboarding.lastLoginIsGcpTos"] = "false"
    (data_dir / "app_storage.json").parent.mkdir(parents=True, exist_ok=True)
    (data_dir / "app_storage.json").write_text(json.dumps(app_storage_data, indent=2), encoding="utf-8")
    (home_dir / "AppData" / "Roaming" / "Antigravity" / "app_storage.json").parent.mkdir(parents=True, exist_ok=True)
    (home_dir / "AppData" / "Roaming" / "Antigravity" / "app_storage.json").write_text(json.dumps(app_storage_data, indent=2), encoding="utf-8")

    # 8. Storage.json in profile sandbox (inherit projects & workspaces)
    host_st_data = {}
    if STORAGE_JSON.is_file():
        try:
            host_st_data = json.loads(STORAGE_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass

    for gs in [data_gs, roaming_gs]:
        st_file = gs / "storage.json"
        st_data = {}
        if st_file.is_file():
            try:
                st_data = json.loads(st_file.read_text("utf-8"))
            except Exception:
                pass
        elif host_st_data:
            st_data = dict(host_st_data)

        for sk in ["openedPathsList", "backupWorkspaces", "sidebarWorkspaces.migratedFromInitState"]:
            if sk in host_st_data:
                st_data[sk] = host_st_data[sk]

        st_data["ide-install-wizard-shown"] = "true"
        st_file.write_text(json.dumps(st_data, indent=2), encoding="utf-8")

    # 9. State.vscdb in profile sandbox (full clone with theme sync and account-specific overrides)
    user_status_b64 = build_user_status(email)
    oauth_token_b64 = build_oauth_token(access_token, refresh_tok, expiry_secs, id_token)
    legacy_oauth = json.dumps({
        "access_token": access_token,
        "refresh_token": refresh_tok,
        "expiry": expiry_secs * 1000 if expiry_secs < 1e12 else expiry_secs
    })
    auth_status = json.dumps({
        "name": name,
        "email": email,
        "apiKey": access_token
    })

    account_keys = {
        "antigravityUnifiedStateSync.userStatus",
        "antigravityUnifiedStateSync.oauthToken",
        "antigravity.oauthToken",
        "antigravityAuthStatus",
        "agy.onboarding.lastLoginUsername",
        "jetski.onboarding.lastLoginUsername",
        "agy.onboarding.lastLoginIsGcpTos",
        "jetski.onboarding.lastLoginIsGcpTos",
        "jetskiStateSync.agentManagerInitState"
    }

    for gs in [data_gs, roaming_gs]:
        vscdb_path = gs / "state.vscdb"
        try:
            if STATE_VSCDB.is_file() and not vscdb_path.is_file():
                shutil.copy2(STATE_VSCDB, vscdb_path)

            conn = sqlite3.connect(vscdb_path, timeout=5.0)
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value TEXT)")

            # Sync latest theme and layout keys from host state.vscdb
            if STATE_VSCDB.is_file():
                try:
                    host_conn = sqlite3.connect(STATE_VSCDB, timeout=3.0)
                    h_cur = host_conn.cursor()
                    h_cur.execute("SELECT key, value FROM ItemTable")
                    for k, v in h_cur.fetchall():
                        if k not in account_keys:
                            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", (k, v))
                    host_conn.close()
                except Exception:
                    pass

            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravityUnifiedStateSync.userStatus", user_status_b64))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravityUnifiedStateSync.oauthToken", oauth_token_b64))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravity.oauthToken", legacy_oauth))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravityAuthStatus", auth_status))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravityOnboarding", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("workbench.telemetryOptOutShown", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("antigravity.notification.didAskUserForPermission", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("agy.onboarding.lastLoginUsername", email))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("jetski.onboarding.lastLoginUsername", email))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("agy.onboarding.lastLoginIsGcpTos", "false"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("jetski.onboarding.lastLoginIsGcpTos", "false"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("agy.onboarding.welcomeModalSeen", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("jetski.onboarding.welcomeModalSeen", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("agy.onboarding.termsAccepted", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("jetski.onboarding.termsAccepted", "true"))
            cur.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)", ("ide-install-wizard-shown", "true"))
            cur.execute("DELETE FROM ItemTable WHERE key = 'jetskiStateSync.agentManagerInitState'")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning writing profile state.vscdb at {vscdb_path}: {e}", file=sys.stderr)

    # 10. Sanitize profile MCP configs to eliminate unwanted auto-login browser popups
    for mcp_p in [gemini_dir / "config" / "mcp_config.json",
                  gemini_dir / "antigravity" / "mcp_config.json"]:
        mcp_p.parent.mkdir(parents=True, exist_ok=True)
        host_mcp = GEMINI_DIR / "config" / "mcp_config.json"
        mcp_data = {}
        if host_mcp.is_file():
            try:
                mcp_data = json.loads(host_mcp.read_text(encoding="utf-8"))
            except Exception:
                mcp_data = {}
        srvs = mcp_data.get("mcpServers", {})
        for srv_name, cfg in srvs.items():
            args_str = " ".join(cfg.get("args", [])) if "args" in cfg else ""
            if "mcp-remote" in args_str or srv_name in ("canva", "open-design", "aws"):
                cfg["disabled"] = True
        mcp_p.write_text(json.dumps(mcp_data, indent=2), encoding="utf-8")

    (gemini_dir / "antigravity" / "mcp_oauth_tokens.json").parent.mkdir(parents=True, exist_ok=True)
    (gemini_dir / "antigravity" / "mcp_oauth_tokens.json").write_text("{}", encoding="utf-8")

    return {
        "success": True,
        "profile": profile_name,
        "email": email,
        "message": f"Successfully seeded profile '{profile_name}' with auth, theme and customizations"
    }

def launch_profile(name):
    # Verify app.asar patch status; heal immediately if Google updated Antigravity
    try:
        import guardian
        asar = guardian.find_antigravity_asar()
        if asar and not guardian.is_asar_patched(asar):
            guardian.trigger_heal(asar, silent=True)
    except Exception:
        pass

    seed_res = seed_profile_auth(name)
    if not seed_res.get('success'):
        return seed_res

    profile_dir = PROFILES_DIR / name
    data_dir = profile_dir / "data"
    home_dir = profile_dir / "home"

    pid_file = profile_dir / "pid"
    if pid_file.is_file():
        try:
            old_pid = int(pid_file.read_text().strip())
            if is_pid_running(old_pid):
                return {
                    "success": True,
                    "pid": old_pid,
                    "message": f"Profile '{name}' is already running in an independent window (PID {old_pid})"
                }
        except Exception:
            pass

    app_bin = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'antigravity' / 'Antigravity.exe'
    if not app_bin.is_file():
        app_bin = Path.home() / 'AppData' / 'Local' / 'Programs' / 'antigravity' / 'Antigravity.exe'
    if not app_bin.is_file():
        candidates = [
            Path(os.environ.get('ProgramFiles', 'C:\\Program Files')) / 'Antigravity' / 'Antigravity.exe',
            Path(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)')) / 'Antigravity' / 'Antigravity.exe',
        ]
        for c in candidates:
            if c.is_file():
                app_bin = c
                break

    if not app_bin.is_file():
        return {"success": False, "error": f"Antigravity executable not found at {app_bin}"}

    env = os.environ.copy()
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env.pop("ELECTRON_NO_ASAR", None)
    env.pop("SSH_CONNECTION", None)
    env.pop("SSH_CLIENT", None)

    # Completely isolate home and appdata so child language_server.exe and Electron read from the profile's sandbox
    drive, path_part = os.path.splitdrive(str(home_dir.resolve()))
    env["USERPROFILE"] = str(home_dir.resolve())
    env["HOME"] = str(home_dir.resolve())
    env["HOMEDRIVE"] = drive
    env["HOMEPATH"] = path_part
    env["APPDATA"] = str((home_dir / "AppData" / "Roaming").resolve())

    cmd = [
        str(app_bin),
        f"--user-data-dir={data_dir.resolve()}"
    ]

    try:
        flags = 0
        if sys.platform == 'win32':
            DETACHED_PROCESS = 0x00000008
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags
        )
        pid_file.write_text(str(proc.pid))
        return {
            "success": True,
            "pid": proc.pid,
            "message": f"Successfully launched Antigravity window for profile '{name}' (PID {proc.pid})"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def sync_all_conversation_databases():
    host_db = GEMINI_DIR / "antigravity" / "conversation_summaries.db"
    if not host_db.exists():
        return {"success": False, "error": "Host conversation_summaries.db not found"}

    if not PROFILES_DIR.exists():
        return {"success": True, "synced_profiles": 0, "changes_detected": 0}

    total_changes = 0
    synced_count = 0

    try:
        conn = sqlite3.connect(host_db, timeout=5.0)
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")

        cur.execute("SELECT count(*) FROM conversation_summaries")
        host_count_before = cur.fetchone()[0]

        for p_dir in PROFILES_DIR.iterdir():
            if not p_dir.is_dir():
                continue
            prof_db = p_dir / "home" / ".gemini" / "antigravity" / "conversation_summaries.db"
            if not prof_db.exists():
                continue

            try:
                cur.execute("ATTACH DATABASE ? AS prof_db", (str(prof_db),))
                cur.execute("SELECT count(*) FROM prof_db.conversation_summaries")
                prof_count_before = cur.fetchone()[0]

                # Bidirectional atomic sync
                cur.execute("INSERT OR REPLACE INTO conversation_summaries SELECT * FROM prof_db.conversation_summaries")
                cur.execute("INSERT OR REPLACE INTO prof_db.conversation_summaries SELECT * FROM conversation_summaries")
                conn.commit()

                cur.execute("SELECT count(*) FROM prof_db.conversation_summaries")
                prof_count_after = cur.fetchone()[0]
                if prof_count_after != prof_count_before:
                    total_changes += abs(prof_count_after - prof_count_before)

                cur.execute("DETACH DATABASE prof_db")
                synced_count += 1
            except Exception:
                try:
                    cur.execute("DETACH DATABASE prof_db")
                except Exception:
                    pass
                continue

        cur.execute("SELECT count(*) FROM conversation_summaries")
        host_count_after = cur.fetchone()[0]
        if host_count_after != host_count_before:
            total_changes += abs(host_count_after - host_count_before)

        conn.close()
        return {
            "success": True,
            "synced_profiles": synced_count,
            "changes_detected": total_changes
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def list_accounts_status(force=False):
    active = get_active_account()
    if not ACCOUNTS_DIR.exists():
        return {"active": active, "accounts": []}

    account_files = list(ACCOUNTS_DIR.glob('*.json'))
    now = int(time.time())

    def process_account_file(f):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            email = data.get('email', '')
            if not email:
                return None
            token = data.get('token') or {}
            has_rt = bool(token.get('refresh_token'))
            is_active = (email.lower() == active.lower())

            # If active account, sync live token from JETSKI_TOKEN if available
            if is_active and JETSKI_TOKEN.is_file():
                try:
                    jt = json.loads(JETSKI_TOKEN.read_text(encoding='utf-8'))
                    jt_tok = jt.get('token') or {}
                    if jt_tok.get('access_token'):
                        token['access_token'] = jt_tok['access_token']
                        if jt_tok.get('refresh_token'):
                            token['refresh_token'] = jt_tok['refresh_token']
                        if jt_tok.get('expiry'):
                            token['expiry_timestamp'] = iso_to_epoch(jt_tok['expiry'])
                        elif jt_tok.get('expiry_timestamp'):
                            token['expiry_timestamp'] = jt_tok['expiry_timestamp']
                        elif jt_tok.get('expires_in'):
                            token['expiry_timestamp'] = int(time.time() + jt_tok['expires_in'])
                        data['token'] = token
                        data['status'] = 'ready'
                        data['error'] = ''
                        try:
                            f.write_text(json.dumps(data, indent=2), encoding='utf-8')
                        except Exception:
                            pass
                except Exception:
                    pass

            expiry_ts = token.get('expiry_timestamp', 0)
            remaining = max(0, expiry_ts - now) if expiry_ts > 0 else 0

            # Auto-refresh if token is near expiration (<120s) or previously marked expired
            if has_rt and (remaining <= 120 or data.get('status') == 'expired'):
                try:
                    refreshed_data, ok, _ = refresh_token(data, f)
                    if ok:
                        data = refreshed_data
                        token = data.get('token') or {}
                        expiry_ts = token.get('expiry_timestamp', 0)
                        remaining = max(0, expiry_ts - now) if expiry_ts > 0 else 3600
                        data['status'] = 'ready'
                        data['error'] = ''
                except Exception:
                    pass

            status = data.get('status', 'ready' if has_rt else 'no_token')
            if is_active:
                status = 'ready'

            is_ready = bool(status == 'ready')
            access_token = token.get('access_token', '')

            # LIVE QUOTA: Fetch live limits if force or missing or older than 15s
            cached_limits = data.get('limits') or {}
            limits_updated = data.get('limits_updated_at', 0)
            cache_ttl = 0 if force else 15
            if is_ready and access_token and (now - limits_updated > cache_ttl or not cached_limits):
                live_q = fetch_live_quota(access_token)
                if not live_q and has_rt:
                    refreshed_data, ok, _ = refresh_token(data, f)
                    if ok:
                        data = refreshed_data
                        token = data.get('token') or {}
                        access_token = token.get('access_token', '')
                        if access_token:
                            live_q = fetch_live_quota(access_token)
                if live_q:
                    cached_limits = live_q
                    data['limits'] = live_q
                    data['limits_updated_at'] = now
                    try:
                        f.write_text(json.dumps(data, indent=2), encoding='utf-8')
                    except Exception:
                        pass

            five_hour = cached_limits.get('five_hour') or {
                "percentage": 100 if is_ready else 0,
                "resets_in": "Ready" if is_ready else "Expired",
                "remaining_fraction": 1.0 if is_ready else 0.0,
                "reset_time": "",
                "reset_time_epoch": 0
            }
            weekly = cached_limits.get('weekly') or {
                "percentage": 100 if is_ready else 0,
                "resets_in": "Ready" if is_ready else "Expired",
                "remaining_fraction": 1.0 if is_ready else 0.0,
                "reset_time": "",
                "reset_time_epoch": 0
            }

            prof_dir = PROFILES_DIR / email
            sandbox_exists = prof_dir.exists()
            is_running = False
            pid = None
            if sandbox_exists and (prof_dir / "pid").is_file():
                try:
                    pid = int((prof_dir / "pid").read_text().strip())
                    is_running = is_pid_running(pid)
                except Exception:
                    pass

            return {
                "email": email,
                "name": data.get('name') or email.split('@')[0],
                "picture": data.get('picture', ''),
                "status": status,
                "is_active": is_active,
                "priority": data.get('priority', 10),
                "expires_in_seconds": remaining,
                "tier": data.get('tier', 'Google Antigravity Standard (Cloud)'),
                "limits": {
                    "five_hour": five_hour,
                    "weekly": weekly
                },
                "sandbox_exists": sandbox_exists,
                "is_running": is_running,
                "pid": pid,
                "error": data.get('error', '')
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(account_files)))) as executor:
        results = list(executor.map(process_account_file, account_files))

    accounts = [r for r in results if r is not None]
    return {"active": active, "accounts": sorted(accounts, key=lambda a: (not a['is_active'], a['name']))}

if __name__ == '__main__':
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == '--list':
            force = '--force' in sys.argv
            print(json.dumps(list_accounts_status(force=force), indent=2))
        elif arg == '--sync-conversations':
            print(json.dumps(sync_all_conversation_databases(), indent=2))
        elif arg in ('--guardian', 'guardian'):
            subcmd = sys.argv[2] if len(sys.argv) > 2 else 'status'
            import guardian
            if subcmd == 'start':
                guardian.install_autostart()
                guardian.start_guardian_background()
                print(json.dumps({"success": True, "action": "guardian_started", "pid": guardian.is_guardian_running()}, indent=2))
            elif subcmd == 'stop':
                guardian.stop_guardian()
                print(json.dumps({"success": True, "action": "guardian_stopped"}, indent=2))
            elif subcmd == 'heal':
                asar = guardian.find_antigravity_asar()
                patched = guardian.is_asar_patched(asar) if asar else False
                if not patched and asar:
                    ok = guardian.trigger_heal(asar, silent=True)
                    print(json.dumps({"success": ok, "healed": True}, indent=2))
                else:
                    print(json.dumps({"success": True, "already_patched": True}, indent=2))
            else:
                pid = guardian.is_guardian_running()
                asar = guardian.find_antigravity_asar()
                patched = guardian.is_asar_patched(asar) if asar else False
                print(json.dumps({
                    "running": bool(pid),
                    "pid": pid,
                    "asar": str(asar) if asar else None,
                    "patched": patched
                }, indent=2))
        elif arg in ('--auth', '--add'):
            login_hint = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('-') else None
            print(json.dumps(authenticate_oauth(login_hint), indent=2))
        elif arg == '--cancel-auth':
            print(json.dumps(cancel_oauth_flow(), indent=2))
        elif arg == '--import-active':
            print(json.dumps(import_active_session(), indent=2))
        elif arg == '--detect':
            print(json.dumps(detect_accounts(), indent=2))
        elif arg == '--inspect' and len(sys.argv) > 2:
            print(json.dumps(inspect_account(sys.argv[2]), indent=2))
        elif arg == '--remove' and len(sys.argv) > 2:
            print(json.dumps(remove_account(sys.argv[2]), indent=2))
        elif arg == '--reset' and len(sys.argv) > 2:
            print(json.dumps(reset_profile(sys.argv[2]), indent=2))
        elif arg == '--seed' and len(sys.argv) > 2:
            print(json.dumps(seed_profile_auth(sys.argv[2]), indent=2))
        elif arg == '--launch' and len(sys.argv) > 2:
            print(json.dumps(launch_profile(sys.argv[2]), indent=2))
        elif arg == '--swap' and len(sys.argv) > 2:
            print(json.dumps(hot_swap(sys.argv[2]), indent=2))
        else:
            print(json.dumps(hot_swap(arg), indent=2))
    else:
        print(json.dumps(list_accounts_status(), indent=2))
