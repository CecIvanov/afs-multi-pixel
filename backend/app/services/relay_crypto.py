"""The Relay envelope (spec §3.2): the storefront encrypts each Relay with a fresh
AES-256-GCM key and wraps that key with the app's RSA-OAEP (SHA-256) public key.
The key pair is made once, its private half stored encrypted (spec §6 ``AppKey``).
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import AppKey
from app.services.token_cipher import TokenCipher

APP_KEY_ID = 1
_OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


class RelayDecryptError(ValueError):
    """The body isn't an envelope this app's key can open."""


@dataclass(frozen=True)
class RelayKeyPair:
    public_key: str  # base64 SPKI DER, what WebCrypto importKey("spki") takes
    private_key: RSAPrivateKey


def relay_key_pair(db: Session, cipher: TokenCipher) -> RelayKeyPair:
    """The app's Relay key pair, made on first use. Concurrent first calls agree:
    the insert loses quietly and both read the stored row."""
    row = db.scalar(select(AppKey).where(AppKey.id == APP_KEY_ID))
    if row is None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        private = key.private_bytes(
            serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        db.execute(
            pg_insert(AppKey)
            .values(
                id=APP_KEY_ID,
                public_key=base64.b64encode(public).decode(),
                private_key_encrypted=cipher.encrypt(base64.b64encode(private).decode()),
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        db.commit()
        row = db.scalar(select(AppKey).where(AppKey.id == APP_KEY_ID))
    return RelayKeyPair(public_key=row.public_key, private_key=_load_private(cipher.decrypt(row.private_key_encrypted)))


@lru_cache(maxsize=4)
def _load_private(private_b64: str) -> RSAPrivateKey:
    key = serialization.load_der_private_key(base64.b64decode(private_b64), password=None)
    assert isinstance(key, RSAPrivateKey)
    return key


def decrypt_envelope(raw: str, private_key: RSAPrivateKey) -> dict[str, Any]:
    try:
        envelope = json.loads(raw)
        if not isinstance(envelope, dict) or envelope.get("v") != 1:
            raise RelayDecryptError("not a v1 envelope")
        aes_key = private_key.decrypt(base64.b64decode(envelope["k"]), _OAEP)
        plain = AESGCM(aes_key).decrypt(base64.b64decode(envelope["iv"]), base64.b64decode(envelope["d"]), None)
        payload = json.loads(plain)
    except RelayDecryptError:
        raise
    except (ValueError, KeyError, TypeError, InvalidTag, binascii.Error) as exc:
        raise RelayDecryptError(f"can't open the envelope: {exc.__class__.__name__}") from exc
    if not isinstance(payload, dict):
        raise RelayDecryptError("the envelope doesn't hold an object")
    return payload
