"""Account passwords and opaque, revocable sessions; never store raw tokens."""
import hashlib
import hmac
import secrets


def hash_password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 200:
        raise ValueError("Password must contain 12–200 characters")
    salt = secrets.token_hex(16)
    result = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    return f"pbkdf2_sha256$600000${salt}${result}"


def verify_password(password, encoded):
    try:
        method, iterations, salt, expected = encoded.split("$")
        if method != "pbkdf2_sha256" or not isinstance(password, str) or len(password) > 200:
            return False
        result = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
        return hmac.compare_digest(result, expected)
    except (ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()
