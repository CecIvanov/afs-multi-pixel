"""Encryption at rest for Conversions API tokens (spec §6): AES-256-GCM, tested
only through the token_cipher module's public functions."""

from __future__ import annotations

import pytest

from app.services.token_cipher import TokenDecryptError, create_token_cipher, load_token_key

KEY_HEX = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
TOKEN = "EAAJZBexampleConversionsApiToken0123456789"


@pytest.mark.unit
def test_round_trip_returns_the_original_token():
    cipher = create_token_cipher(load_token_key(KEY_HEX))

    blob = cipher.encrypt(TOKEN)

    assert blob != TOKEN
    assert cipher.decrypt(blob) == TOKEN


@pytest.mark.unit
def test_encrypting_twice_gives_different_blobs():
    cipher = create_token_cipher(load_token_key(KEY_HEX))

    assert cipher.encrypt(TOKEN) != cipher.encrypt(TOKEN)


@pytest.mark.unit
def test_a_different_key_cannot_decrypt():
    blob = create_token_cipher(load_token_key(KEY_HEX)).encrypt(TOKEN)
    other = create_token_cipher(load_token_key("ff" * 32))

    with pytest.raises(ValueError):
        other.decrypt(blob)


@pytest.mark.unit
@pytest.mark.parametrize(
    "mangle",
    [
        pytest.param(lambda b: b[:-4] + ("AAAA" if not b.endswith("AAAA") else "BBBB"), id="altered"),
        pytest.param(lambda b: b[:12], id="truncated"),
        pytest.param(lambda b: "not base64 at all!", id="garbage"),
        pytest.param(lambda b: "", id="empty"),
    ],
)
def test_an_altered_blob_fails_instead_of_returning_garbage(mangle):
    cipher = create_token_cipher(load_token_key(KEY_HEX))
    blob = cipher.encrypt(TOKEN)

    with pytest.raises(TokenDecryptError):
        cipher.decrypt(mangle(blob))


@pytest.mark.unit
def test_a_base64_key_works_like_the_same_key_in_hex():
    key_b64 = "ABEiM0RVZneImaq7zN3u/wARIjNEVWZ3iJmqu8zd7v8="  # the same 32 bytes as KEY_HEX
    blob = create_token_cipher(load_token_key(KEY_HEX)).encrypt(TOKEN)

    assert create_token_cipher(load_token_key(key_b64)).decrypt(blob) == TOKEN


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("", id="missing"),
        pytest.param("   ", id="blank"),
        pytest.param("00112233", id="too-short-hex"),
        pytest.param("c2hvcnQ=", id="too-short-base64"),
        pytest.param("not a key at all", id="garbage"),
    ],
)
def test_a_missing_or_wrong_length_key_is_refused(raw):
    with pytest.raises(ValueError, match="TOKEN_ENC_KEY"):
        load_token_key(raw)
