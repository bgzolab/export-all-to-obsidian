"""weapi payload encryption used by the NetEase web client.

NetEase expects every weapi request body as ``params`` + ``encSecKey``:

1. JSON-encode the payload.
2. AES-128-CBC encrypt it twice with PKCS#7 padding: first with the fixed
   ``0CoJUm6Qyw8W8jud`` key, then with a random 16-byte secret; each layer is
   base64 encoded.
3. RSA-encrypt the reversed secret with the fixed public exponent/modulus and
   encode the result as a 256-character lowercase hex string.

The RSA step is a plain modular exponentiation, so no RSA library is needed.
Only AES comes from pycryptodome; see ``docs/design/netease-music.md``.
"""

from __future__ import annotations

import base64
import json
import secrets
from collections.abc import Mapping
from typing import Any

from Crypto.Cipher import AES

# Constants mirror the public web client. If NetEase rotates them, requests
# start failing with a non-200 ``code`` and this module needs an update.
NONCE = '0CoJUm6Qyw8W8jud'
IV = '0102030405060708'
PUBKEY = '010001'
MODULUS = (
    '00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152'
    'b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda'
    '92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe'
    '4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7'
)
SECRET_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
SECRET_LENGTH = 16
BLOCK_SIZE = 16


def aes_cbc_base64(text: str, key: str) -> str:
    """Encrypt UTF-8 text with AES-128-CBC/PKCS#7 and return base64."""
    raw = text.encode('utf-8')
    padding = BLOCK_SIZE - len(raw) % BLOCK_SIZE
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, IV.encode('utf-8'))
    encrypted = cipher.encrypt(raw + bytes([padding]) * padding)
    return base64.b64encode(encrypted).decode('ascii')


def rsa_encrypt(text: str) -> str:
    """RSA-encrypt the secret and return a fixed-width lowercase hex string."""
    message = int.from_bytes(text.encode('utf-8')[::-1], 'big')
    encrypted = pow(message, int(PUBKEY, 16), int(MODULUS, 16))
    # The upstream client always emits 256 characters; zfill keeps leading
    # zero bytes so the field width stays constant.
    return hex(encrypted)[2:].zfill(256)


def generate_secret() -> str:
    """Return a random 16-character AES key."""
    return ''.join(secrets.choice(SECRET_ALPHABET) for _ in range(SECRET_LENGTH))


def weapi_encrypt(
    payload: Mapping[str, Any],
    secret: str | None = None,
) -> dict[str, str]:
    """Return the encrypted ``params`` / ``encSecKey`` form for a payload.

    ``secret`` exists for deterministic tests; production callers omit it.
    The payload is serialized compactly because the upstream client uses
    ``JSON.stringify`` without spaces.
    """
    text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    key = secret or generate_secret()
    params = aes_cbc_base64(aes_cbc_base64(text, NONCE), key)
    # rsa_encrypt reverses its input, matching the upstream client.
    return {'params': params, 'encSecKey': rsa_encrypt(key)}
