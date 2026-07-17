"""Credential-safe formatting helpers for stream URLs and log messages."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REDACTED = "[REDACTED]"
_URL_IN_TEXT = re.compile(r"(?:https?|rtsp|rtp|udp)://[^\s<>'\"]+")
_QUERY_SECRET = re.compile(
    r"(?i)(?P<key>username|password)=(?P<value>[^&\s]+)"
)


def redact_url_credentials(value):
    """Hide credentials embedded in common Xtream URL forms."""
    if value is None:
        return None

    raw = str(value)
    try:
        parsed = urlsplit(raw)

        netloc = parsed.netloc
        if "@" in netloc:
            _userinfo, host = netloc.rsplit("@", 1)
            netloc = f"{REDACTED}@{host}"

        segments = parsed.path.split("/")
        nonempty = [index for index, part in enumerate(segments) if part]
        if nonempty:
            first = segments[nonempty[0]].lower()
            if first in {"live", "movie", "series"} and len(nonempty) >= 4:
                segments[nonempty[1]] = REDACTED
                segments[nonempty[2]] = REDACTED
            elif len(nonempty) == 3 and re.fullmatch(
                r"\d+(?:\.[A-Za-z0-9]+)?", segments[nonempty[2]]
            ):
                # Legacy Xtream form: /username/password/stream_id
                segments[nonempty[0]] = REDACTED
                segments[nonempty[1]] = REDACTED

        query = urlencode(
            [
                (key, REDACTED if key.lower() in {"username", "password"} else val)
                for key, val in parse_qsl(parsed.query, keep_blank_values=True)
            ],
            doseq=True,
        )
        return urlunsplit(
            (parsed.scheme, netloc, "/".join(segments), query, parsed.fragment)
        )
    except Exception:
        return _QUERY_SECRET.sub(lambda match: f"{match.group('key')}={REDACTED}", raw)


def redact_sensitive_text(value):
    """Redact any stream URLs or XC query credentials embedded in text."""
    if value is None:
        return None
    text = str(value)
    text = _URL_IN_TEXT.sub(
        lambda match: redact_url_credentials(match.group(0)), text
    )
    return _QUERY_SECRET.sub(
        lambda match: f"{match.group('key')}={REDACTED}", text
    )
