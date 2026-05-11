import base64
import hashlib
import string
from unittest.mock import patch
from spotifysync.auth import challenge


def test_challenge_verifier_secure_length():
    verifier, _ = challenge()
    assert len(verifier) == 128


def test_challenge_verifier_charset():
    verifier, _ = challenge()
    assert set(verifier).issubset(string.ascii_letters + string.digits)


def test_challenge_known_calculation_correct():
    test_str = (
        "qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM1234567890" * 2 + "asdf"
    )
    test_code_challenge = "sm25XTU7ZYHTRlY_9n6C3AjSt6Cyb4-7LdPZfgj4JDw"
    with patch("secrets.choice", side_effect=list(test_str)):
        verifier, code_challenge = challenge()
    assert verifier == test_str
    assert code_challenge == test_code_challenge


def test_challenge_calculation_correct():
    verifier, code_challenge = challenge()
    assert code_challenge == base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().replace("=", "")


def test_challenge_unpadded():
    _, code_challenge = challenge()
    assert code_challenge[-1] != "="


def test_challenge_unique():
    results = [challenge() for _ in range(1000)]
    verifiers = [result[0] for result in results]
    challenges = [result[1] for result in results]
    assert len(verifiers) == len(set(verifiers))
    assert len(challenges) == len(set(challenges))
