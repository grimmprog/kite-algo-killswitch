"""Property-based tests for credential encryption round-trip (Property 3).

Uses Hypothesis to verify:
- Any non-empty plaintext string survives encrypt→decrypt cycle unchanged
- Covers unicode, special characters, and varying lengths

**Validates: Requirements 3.3, 4.2, 5.2**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume

from src.broker.token_encryption import TokenEncryption


# ============================================================
# Strategies
# ============================================================

# Generate non-empty strings: ASCII, unicode, special chars, varying lengths
non_empty_text_strategy = st.text(
    alphabet=st.characters(
        codec="utf-8",
        categories=(
            "L",   # Letters (all scripts)
            "N",   # Numbers
            "P",   # Punctuation
            "S",   # Symbols
            "Z",   # Separators (spaces)
        ),
    ),
    min_size=1,
    max_size=1000,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def encryption():
    """Create a TokenEncryption instance with a freshly generated key."""
    key = TokenEncryption.generate_key()
    return TokenEncryption(key)


# ============================================================
# Property 3: Credential Encryption Round-Trip
# ============================================================


class TestCredentialEncryptionRoundTripProperty:
    """Property-based tests for credential encryption round-trip.

    **Validates: Requirements 3.3, 4.2, 5.2**

    Property: For any non-empty plaintext credential string (access token,
    TOTP key, or client ID), encrypting with TokenEncryption.encrypt() and
    then decrypting with TokenEncryption.decrypt() SHALL produce the original
    plaintext string.
    """

    @given(plaintext=non_empty_text_strategy)
    @settings(max_examples=200, deadline=None)
    def test_encrypt_decrypt_round_trip_preserves_plaintext(self, plaintext: str):
        """For any non-empty string, decrypt(encrypt(s)) == s.

        **Validates: Requirements 3.3, 4.2, 5.2**

        Property: For any non-empty plaintext credential string, encrypting
        with TokenEncryption.encrypt() and then decrypting with
        TokenEncryption.decrypt() SHALL produce the original plaintext string.
        """
        key = TokenEncryption.generate_key()
        enc = TokenEncryption(key)

        ciphertext = enc.encrypt(plaintext)
        decrypted = enc.decrypt(ciphertext)

        assert decrypted == plaintext, (
            f"Round-trip failed: original={plaintext!r}, decrypted={decrypted!r}"
        )

    @given(plaintext=st.text(min_size=1, max_size=500))
    @settings(max_examples=200, deadline=None)
    def test_encrypt_decrypt_with_full_unicode(self, plaintext: str):
        """Encryption round-trip works for full unicode range strings.

        **Validates: Requirements 3.3, 4.2, 5.2**

        Property: For any non-empty unicode string (including surrogates filtered
        by hypothesis), the encrypt→decrypt cycle produces the original string.
        """
        key = TokenEncryption.generate_key()
        enc = TokenEncryption(key)

        ciphertext = enc.encrypt(plaintext)
        decrypted = enc.decrypt(ciphertext)

        assert decrypted == plaintext, (
            f"Unicode round-trip failed: original={plaintext!r}, decrypted={decrypted!r}"
        )

    @given(plaintext=non_empty_text_strategy)
    @settings(max_examples=200, deadline=None)
    def test_ciphertext_differs_from_plaintext(self, plaintext: str):
        """Encrypted output is never identical to the plaintext input.

        **Validates: Requirements 3.3, 4.2, 5.2**

        Property: For any non-empty plaintext, the ciphertext produced by
        encrypt() SHALL differ from the plaintext (encryption actually transforms
        the data).
        """
        key = TokenEncryption.generate_key()
        enc = TokenEncryption(key)

        ciphertext = enc.encrypt(plaintext)

        assert ciphertext != plaintext, (
            f"Ciphertext should differ from plaintext: {plaintext!r}"
        )
