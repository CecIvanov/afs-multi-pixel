"""Encryption at rest for Meta Conversions API tokens and the Relay private key.

AES-256-GCM with a 32-byte key. The stored blob is base64(iv[12] | tag[16] |
ciphertext), the same layout as AdFeed Studio's meta-connector crypto.ts.
"""

from __future__ import annotations

import base64
import binascii
import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

IV_LEN = 12
TAG_LEN = 16
KEY_LEN = 32
_HEX_KEY = re.compile(r"^[0-9a-fA-F]{64}$")


class TokenDecryptError(ValueError):
    """The blob wasn't made by this key, or was altered."""


def load_token_key(raw: str | None) -> bytes:
    """Parse TOKEN_ENC_KEY (64 hex characters, or base64 of 32 bytes). Raises if it's
    missing or invalid, so a misconfigured deploy fails closed instead of storing plaintext."""
    value = (raw or "").strip()
    if not value:
        raise ValueError("TOKEN_ENC_KEY is required to encrypt Conversions API tokens")
    if _HEX_KEY.match(value):
        return bytes.fromhex(value)
    try:
        key = base64.b64decode(value, validate=True)
    except binascii.Error:
        key = b""
    if len(key) != KEY_LEN:
        raise ValueError("TOKEN_ENC_KEY must be 64 hex characters or base64 of exactly 32 bytes")
    return key


class TokenCipher:
    def __init__(self, key: bytes) -> None:
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        iv = os.urandom(IV_LEN)
        sealed = self._aead.encrypt(iv, plaintext.encode("utf-8"), None)  # ciphertext | tag
        ct, tag = sealed[:-TAG_LEN], sealed[-TAG_LEN:]
        return base64.b64encode(iv + tag + ct).decode("ascii")

    def decrypt(self, blob: str) -> str:
        try:
            buf = base64.b64decode(blob, validate=True)
        except binascii.Error as exc:
            raise TokenDecryptError("token ciphertext isn't base64") from exc
        if len(buf) < IV_LEN + TAG_LEN:
            raise TokenDecryptError("token ciphertext is too short")
        iv, tag, ct = buf[:IV_LEN], buf[IV_LEN : IV_LEN + TAG_LEN], buf[IV_LEN + TAG_LEN :]
        try:
            return self._aead.decrypt(iv, ct + tag, None).decode("utf-8")
        except InvalidTag as exc:
            raise TokenDecryptError("token ciphertext doesn't match this key") from exc


def create_token_cipher(key: bytes) -> TokenCipher:
    return TokenCipher(key)


def token_cipher_from_settings() -> TokenCipher:
    """The cipher for this environment, keyed by TOKEN_ENC_KEY."""
    return create_token_cipher(load_token_key(get_settings().token_enc_key))
