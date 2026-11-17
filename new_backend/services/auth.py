import base64
import hashlib
import hmac
import json
import os
import secrets
import time


# The AJ Fast Food account is the one wired to the real sales,
# inventory and recipe data. Every other account gets an empty
# ("blank") workspace with the same pages but no data yet.
DEMO_EMAIL = os.environ.get("DINETRACK_DEMO_EMAIL", "admin@ajfastfood.com")
DEMO_PASSWORD = os.environ.get("DINETRACK_DEMO_PASSWORD", "ajfastfood123")
DEMO_WORKSPACE = "ajfastfood"
BLANK_WORKSPACE = "blank"

TOKEN_TTL_SECONDS = 7 * 24 * 3600

PBKDF2_ITERATIONS = 200_000


# ---------------------------------------------------------
# PASSWORDS
# ---------------------------------------------------------

def hash_password(password, salt=None):

    salt = salt or secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS
    ).hex()

    return salt, digest


def verify_password(password, salt, expected):

    _, digest = hash_password(password, salt)

    return hmac.compare_digest(digest, expected)


# ---------------------------------------------------------
# USER STORE (data/users.json, keyed by lower-cased email)
# ---------------------------------------------------------

class UserStore:

    def __init__(self, path, secret_path):

        self.path = path
        self.secret = self._load_secret(secret_path)
        self.users = self._load()

        self._seed_demo_account()

    def _load_secret(self, secret_path):

        if os.path.exists(secret_path):
            with open(secret_path, "r") as f:
                return f.read().strip().encode()

        secret = secrets.token_hex(32)

        with open(secret_path, "w") as f:
            f.write(secret)

        return secret.encode()

    def _load(self):

        if not os.path.exists(self.path):
            return {}

        with open(self.path, "r") as f:
            return json.load(f)

    def _save(self):

        with open(self.path, "w") as f:
            json.dump(self.users, f, indent=2)

    def _seed_demo_account(self):

        email = DEMO_EMAIL.lower()

        if email in self.users:
            return

        salt, digest = hash_password(DEMO_PASSWORD)

        self.users[email] = {
            "email": email,
            "name": "AJ Fast Food Admin",
            "restaurant_name": "AJ Fast Food",
            "workspace": DEMO_WORKSPACE,
            "salt": salt,
            "password_hash": digest,
            "created_at": int(time.time())
        }

        self._save()

    def create(self, name, restaurant_name, email, password):

        email = email.strip().lower()

        if email in self.users:
            raise ValueError("An account with this email already exists")

        salt, digest = hash_password(password)

        self.users[email] = {
            "email": email,
            "name": name.strip(),
            "restaurant_name": restaurant_name.strip(),
            "workspace": BLANK_WORKSPACE,
            "salt": salt,
            "password_hash": digest,
            "created_at": int(time.time())
        }

        self._save()

        return self.users[email]

    def authenticate(self, email, password):

        user = self.users.get(email.strip().lower())

        if not user or not verify_password(password, user["salt"], user["password_hash"]):
            return None

        return user

    def get(self, email):

        return self.users.get(email.lower())

    # -----------------------------------------------------
    # TOKENS — "<base64 payload>.<hmac signature>"
    # -----------------------------------------------------

    def issue_token(self, user):

        payload = json.dumps({
            "email": user["email"],
            "exp": int(time.time()) + TOKEN_TTL_SECONDS
        }).encode()

        body = base64.urlsafe_b64encode(payload).decode()
        sig = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()

        return f"{body}.{sig}"

    def user_for_token(self, token):

        try:
            body, sig = token.split(".", 1)
        except ValueError:
            return None

        expected = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(sig, expected):
            return None

        payload = json.loads(base64.urlsafe_b64decode(body.encode()))

        if payload["exp"] < time.time():
            return None

        return self.get(payload["email"])


def public_user(user):

    return {
        "email": user["email"],
        "name": user["name"],
        "restaurant_name": user["restaurant_name"],
        "workspace": user["workspace"]
    }
