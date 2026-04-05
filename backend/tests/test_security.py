from tradingbot.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_round_trip() -> None:
    secret = hash_password("swing-breakout")
    assert verify_password("swing-breakout", secret)
    assert not verify_password("wrong-password", secret)


def test_token_round_trip() -> None:
    token = create_access_token("admin@example.com")
    assert decode_access_token(token) == "admin@example.com"

