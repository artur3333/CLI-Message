import time
import secrets
import hashlib
import re


def timestamp():
    timestamp = int(time.time())
    return timestamp


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(32)

    pass_salt = password + salt
    pass_hash = hashlib.sha256(pass_salt.encode()).hexdigest()

    return pass_hash, salt


def validate_username(username):
    if not username:
        return False, "Username cannot be empty."

    if len(username) < 3:
        return False, "Username must be at least 3 characters long."

    if len(username) > 20:
        return False, "Username cannot be longer than 20 characters."

    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return False, "Username can only contain letters, numbers, and underscores."

    return True, ""


def validate_password(password):
    if not password:
        return False, "Password cannot be empty."

    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    
    return True, ""


def verify_password(password, hashed_password, salt):
    new_hash, _ = hash_password(password, salt)
    if new_hash == hashed_password:
        return True
    
    return False


def generate_token():
    return secrets.token_hex(32)

def generate_invite_code():
    return secrets.token_urlsafe(8)
