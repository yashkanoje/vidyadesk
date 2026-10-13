from leadagent.crypto import decrypt, encrypt


def test_round_trip_and_not_plaintext():
    token = encrypt("123456:ABC-bot-token")
    assert token != "123456:ABC-bot-token"
    assert decrypt(token) == "123456:ABC-bot-token"
