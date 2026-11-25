import re

FILTERED = '[Filtered]'

# Access and refresh tokens minted by SimpleJWT have JSON object headers and payloads.
TOKEN_RE = re.compile(r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*')
# Guest capabilities are Django-signed UUID strings: a 51-character JSON/base64 payload, a base62 timestamp,
# and a SHA256 signature. Scrub copies in arbitrary stack locals as well as their named headers.
GUEST_TOKEN_RE = re.compile(r'I[A-Za-z0-9_-]{50}:[A-Za-z0-9]+:[A-Za-z0-9_-]{43}')
SENSITIVE_KEYS = {
    'access_token',
    'accesstoken',
    'authorization',
    'guest_token',
    'guesttoken',
    'proxy_authorization',
    'raw_token',
    'refresh_token',
    'refreshtoken',
    'sec_websocket_protocol',
    'token',
    'x_guest_token',
}


def is_sensitive_key(value):
    if not isinstance(value, str):
        return False
    # Sentry serializes bytes in ASGI header pairs to their repr before calling before_send.
    if value.startswith(("b'", 'b"')) and value[-1:] == value[1]:
        value = value[2:-1]
    return value.lower().replace('-', '_').removeprefix('http_') in SENSITIVE_KEYS


def hide_tokens(value):
    """Copy a serialized Sentry event, redacting credentials in headers, named fields and stack-local copies."""
    if isinstance(value, str):
        value = TOKEN_RE.sub(FILTERED, value) if 'eyJ' in value else value
        return GUEST_TOKEN_RE.sub(FILTERED, value) if ':' in value else value

    if isinstance(value, dict):
        return {
            hide_tokens(key): FILTERED if is_sensitive_key(key) else hide_tokens(item) for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        if len(value) == 2 and is_sensitive_key(value[0]):
            return [value[0], FILTERED]
        return [hide_tokens(item) for item in value]

    return value


def hide_tokens_from_sentry(event, hint):
    # Sentry has already normalized and bounded the event before these hooks run. Its default scrubber masks
    # recognized header dictionaries, but not ASGI byte-pairs or credentials copied into arbitrary stack locals.
    # Keep the existing scrubber too: it covers other sensitive fields independently of these token formats.
    return hide_tokens(event)
