
from app.security import hash_password, verify_password


def test_hash_password_does_not_return_plaintext():
    password = "Test-Password-123!"

    hashed_password = hash_password(password)

    assert hashed_password != password


def test_correct_password_verifies_successfully():
    password = "Test-Password-123!"
    hashed_password = hash_password(password)

    assert verify_password(password, hashed_password) is True


def test_incorrect_password_fails_verification():
    hashed_password = hash_password("Test-Password-123!")

    assert verify_password("Wrong-Password", hashed_password) is False


def test_same_password_produces_different_hashes():
    password = "Test-Password-123!"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash


def test_malformed_hash_fails_verification():
    assert verify_password("any-password", "not-a-valid-hash") is False
