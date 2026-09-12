"""Short-lived Telegram approval, bound to the browser that requested it."""
import hashlib
import hmac
import json
import re
import secrets

from app.config import get_settings

TTL = 180
COOKIE = "sensi_login"


def key(challenge: str) -> str | None:
    return f"web:login:{challenge}" if re.fullmatch(r"[A-Za-z0-9_-]{32}", challenge) else None


async def create(redis):
    challenge, proof = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1000000):06d}"
    await redis.set(key(challenge), json.dumps({
        "proof": hashlib.sha256(proof.encode()).hexdigest(), "code": code,
    }), ex=TTL)
    return challenge, proof, code


async def pending(redis, challenge):
    raw = await redis.get(key(challenge)) if key(challenge) else None
    return json.loads(raw) if raw else None


async def approve(redis, challenge, telegram_id, *, denied=False):
    if not key(challenge) or get_settings().role(telegram_id) not in {"sensi", "admin_team"}:
        return False
    # Check expiry and record the first decision atomically without extending its TTL.
    return bool(await redis.eval("""
        local raw = redis.call('GET', KEYS[1])
        if not raw then return 0 end
        local data = cjson.decode(raw)
        if data.telegram_id or data.denied then return 0 end
        if ARGV[2] == '1' then data.denied = true else data.telegram_id = tonumber(ARGV[1]) end
        redis.call('SET', KEYS[1], cjson.encode(data), 'KEEPTTL')
        return 1
    """, 1, key(challenge), telegram_id, "1" if denied else "0"))


async def consume(redis, cookie):
    challenge, _, proof = cookie.partition(".")
    if not key(challenge) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", proof):
        return "expired", None
    data = await pending(redis, challenge)
    if not data or not hmac.compare_digest(data["proof"], hashlib.sha256(proof.encode()).hexdigest()):
        return "expired", None
    if not data.get("telegram_id") and not data.get("denied"):
        return "pending", None
    # Only one poll can redeem an approved challenge, including concurrent polls.
    if not await redis.getdel(key(challenge)):
        return "expired", None
    if data.get("denied"):
        return "denied", None
    telegram_id = data["telegram_id"]
    if get_settings().role(telegram_id) not in {"sensi", "admin_team"}:
        return "denied", None
    return "approved", telegram_id
