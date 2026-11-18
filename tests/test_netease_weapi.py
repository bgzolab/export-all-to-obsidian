"""Known-vector and round-trip tests for the weapi encryption layer."""

from __future__ import annotations

import base64
import json

from Crypto.Cipher import AES

from netease.weapi import (
    IV,
    MODULUS,
    NONCE,
    PUBKEY,
    aes_cbc_base64,
    rsa_encrypt,
    weapi_encrypt,
)

PAYLOAD = {
    'csrf_token': '',
    'uid': 1912423534,
    'limit': 1000,
    'offset': 0,
    'type': 0,
}
SECRET = '1234567890abcdef'
# Captured once from the reference algorithm; it pins the wire format so an
# accidental change to padding, base64 or RSA byte order fails loudly.
EXPECTED_PARAMS = (
    'mxmKo6zvEizoahgflf3DYtGWGx9DXmZx6CUhHCTpq5047hc5TbByCwiO14t7yxXNkJwaTcSxl9vbLynd7LLu'
    'ilxWpYqnaI+ExEFMz2eeJ9LRycxt/u79tK0f07yxMH8rSFAtxzmQO/M84sS0aD44ag=='
)
EXPECTED_ENC_SEC_KEY = (
    'bc05a756cb87b1a2674efda9e90a27d641dcbbe2e6b7be3b61193e47315c298183d409578ac80502bd441d'
    '82bf1611d6d9238bcaf64794d096417b726373fdd8cf4a9e9d31d198d6d785ffa3d0a2e8c621b4d6c0'
    '19fabe0ca6f3a815d9f2a4875a0bcab968f331f394566e1162603ed1dd002aa89b47fd8dcbc77d2c6976efed'
)


def _decrypt_base64(text: str, key: str) -> str:
    encrypted = base64.b64decode(text)
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, IV.encode('utf-8'))
    padded = cipher.decrypt(encrypted)
    padding = padded[-1]
    assert 1 <= padding <= 16
    assert padded[-padding:] == bytes([padding]) * padding
    return padded[:-padding].decode('utf-8')


def test_weapi_encrypt_matches_known_vector():
    result = weapi_encrypt(PAYLOAD, secret=SECRET)

    assert result == {
        'params': EXPECTED_PARAMS,
        'encSecKey': EXPECTED_ENC_SEC_KEY,
    }


def test_two_aes_layers_decrypt_back_to_payload():
    result = weapi_encrypt(PAYLOAD, secret=SECRET)

    inner = _decrypt_base64(result['params'], SECRET)
    plain = _decrypt_base64(inner, NONCE)

    assert json.loads(plain) == PAYLOAD


def test_fixed_secret_is_deterministic():
    first = weapi_encrypt(PAYLOAD, secret=SECRET)
    second = weapi_encrypt(PAYLOAD, secret=SECRET)

    assert first == second


def test_generated_secret_changes_ciphertext():
    first = weapi_encrypt(PAYLOAD)
    second = weapi_encrypt(PAYLOAD)

    assert first['params'] != second['params']
    assert len(first['encSecKey']) == 256
    assert len(second['encSecKey']) == 256
    int(first['encSecKey'], 16)
    int(second['encSecKey'], 16)


def test_rsa_encrypt_is_modular_exponentiation_of_reversed_secret():
    # rsa_encrypt reverses its input first, matching the upstream web client.
    encrypted = rsa_encrypt(SECRET)
    expected = pow(
        int.from_bytes(SECRET[::-1].encode('utf-8'), 'big'),
        int(PUBKEY, 16),
        int(MODULUS, 16),
    )

    assert len(encrypted) == 256
    assert int(encrypted, 16) == expected


def test_aes_cbc_base64_uses_pkcs7_padding():
    empty = base64.b64decode(aes_cbc_base64('', NONCE))
    exact_block = base64.b64decode(aes_cbc_base64('x' * 16, NONCE))

    assert len(empty) == 16
    assert len(exact_block) == 32
    assert _decrypt_base64(aes_cbc_base64('', NONCE), NONCE) == ''
    assert _decrypt_base64(aes_cbc_base64('x' * 16, NONCE), NONCE) == 'x' * 16
