import base64
import json
import time

import jwt  # PyJWT, test-only: proves our tokens are standard JWTs
import pytest

from services.tokens import AUDIENCE, ISSUER, TokenError, TokenExpired, issue_token, verify_token

KEY = "test-signing-key-" + "x" * 40


def b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def test_issue_and_verify_roundtrip():
    token, claims = issue_token(KEY, 900)
    assert verify_token(token, KEY) == claims
    assert claims["exp"] - claims["iat"] == 900
    assert claims["sub"].startswith("s_") and claims["iss"] == ISSUER and claims["aud"] == AUDIENCE


def test_tokens_are_unique():
    assert issue_token(KEY, 900)[1]["sub"] != issue_token(KEY, 900)[1]["sub"]


def test_pyjwt_accepts_our_tokens_and_we_accept_pyjwt_tokens():
    token, claims = issue_token(KEY, 900)
    assert jwt.decode(token, KEY, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER) == claims
    now = int(time.time())
    theirs = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "s_x", "iat": now, "exp": now + 60}, KEY, "HS256"
    )
    assert verify_token(theirs, KEY)["sub"] == "s_x"


def test_expired_token():
    token, claims = issue_token(KEY, 60, now=1_000_000)
    assert verify_token(token, KEY, now=claims["exp"] + 29)  # within 30 s leeway
    with pytest.raises(TokenExpired):
        verify_token(token, KEY, now=claims["exp"] + 31)


def test_wrong_key_rejected():
    token, _ = issue_token(KEY, 900)
    with pytest.raises(TokenError, match="signature"):
        verify_token(token, "another-key")


def test_modified_payload_rejected():
    token, claims = issue_token(KEY, 900)
    header, _, signature = token.split(".")
    forged = b64({**claims, "exp": claims["exp"] + 86_400})
    with pytest.raises(TokenError, match="signature"):
        verify_token(f"{header}.{forged}.{signature}", KEY)


def test_modified_signature_rejected():
    token, _ = issue_token(KEY, 900)
    flipped = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(TokenError):
        verify_token(flipped, KEY)


def test_alg_none_rejected():
    _, claims = issue_token(KEY, 900)
    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."
    with pytest.raises(TokenError, match="algorithm"):
        verify_token(unsigned, KEY)


@pytest.mark.parametrize("field", ["iss", "aud"])
def test_wrong_issuer_or_audience_rejected(field):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "s",
        "iat": now,
        "exp": now + 60,
        field: "other",
    }
    with pytest.raises(TokenError, match="issuer or audience"):
        verify_token(jwt.encode(claims, KEY, "HS256"), KEY)


@pytest.mark.parametrize("token", ["", "abc", "a.b", "a.b.c.d", "!!!.###.$$$"])
def test_malformed_tokens_rejected(token):
    with pytest.raises(TokenError):
        verify_token(token, KEY)


def test_missing_claims_rejected():
    now = int(time.time())
    token = jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 60}, KEY, "HS256")
    with pytest.raises(TokenError, match="missing"):
        verify_token(token, KEY)
