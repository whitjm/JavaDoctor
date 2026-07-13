"""测试「密码与令牌」零件：app/core/security.py。

- 密码哈希：存进库的必须是密文，且能正确校验对错。
- JWT 令牌：签发的令牌能被解出用户身份，篡改/乱码令牌要被拒绝。
"""
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_哈希后不是明文():
    h = hash_password("123456")
    assert h != "123456"
    assert len(h) > 20


def test_正确密码校验通过():
    h = hash_password("mySecret123")
    assert verify_password("mySecret123", h) is True


def test_错误密码校验失败():
    h = hash_password("mySecret123")
    assert verify_password("wrongPass", h) is False


def test_同一密码两次哈希不同_但都能校验():
    # bcrypt 每次加盐，密文不同，但都能验证成功
    h1 = hash_password("samePass")
    h2 = hash_password("samePass")
    assert h1 != h2
    assert verify_password("samePass", h1)
    assert verify_password("samePass", h2)


def test_令牌可签发并解回身份():
    token = create_access_token(subject=42, role="admin")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_乱码令牌解码返回None():
    assert decode_access_token("not.a.valid.token") is None
