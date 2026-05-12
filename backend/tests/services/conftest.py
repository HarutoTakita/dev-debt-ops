"""サービス層ユニットテスト用 conftest。

グローバルの setup_db (autouse) をオーバーライドし、
DB 接続なしで純粋なユニットテストが実行できるようにする。
"""

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture(autouse=True)
def setup_db():
    """DB 接続不要なユニットテスト用に setup_db を無効化する。"""
    yield


@pytest.fixture(scope="module")
def rsa_key_pair():
    """テスト用 RSA 鍵ペアをモジュール単位で生成する（低コストのため 2048bit）。"""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_key = private_key.public_key()
    return pem, public_key
