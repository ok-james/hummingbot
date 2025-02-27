import binascii
import json
from abc import ABC, abstractmethod

from eth_account import Account
from eth_keyfile.keyfile import (
    DKLEN,
    SCRYPT_P,
    SCRYPT_R,
    Random,
    _pbkdf2_hash,
    _scrypt_hash,
    big_endian_to_int,
    encode_hex_no_prefix,
    encrypt_aes_ctr,
    get_default_work_factor_for_kdf,
    int_to_big_endian,
    keccak,
)
from pydantic import SecretStr

from hummingbot.client.settings import CONF_DIR_PATH

PASSWORD_VERIFICATION_WORD = "HummingBot"
PASSWORD_VERIFICATION_PATH = CONF_DIR_PATH / ".password_verification"


class BaseSecretsManager(ABC):
    def __init__(self, password: str):
        # 保存的是当前用户每次登录时输入的密码，不一定是正确的密码，会通过 decrypt_secret_value 方法来反解 .password_verification 中的内容进行判断
        self._password = password

    @property
    def password(self) -> SecretStr:
        # SecretStr 是 Pydantic 中的一个数据类型，用于表示敏感信息，例如密码、API 密钥等。它继承自 str，并添加了一些额外的验证和安全措施。
        # https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr
        return SecretStr(self._password)

    @abstractmethod
    def encrypt_secret_value(self, attr: str, value: str):
        pass

    @abstractmethod
    def decrypt_secret_value(self, attr: str, value: str) -> str:
        pass


class ETHKeyFileSecretManger(BaseSecretsManager):
    def encrypt_secret_value(self, attr: str, value: str):
        if self._password is None:
            raise ValueError(f"Could not encrypt secret attribute {attr} because no password was provided.")
        # 返回字符串编码后的字节，默认是编码成 utf-8
        password_bytes = self._password.encode()
        value_bytes = value.encode()
        keyfile_json = _create_v3_keyfile_json(value_bytes, password_bytes)
        json_str = json.dumps(keyfile_json)
        encrypted_value = binascii.hexlify(json_str.encode()).decode()
        # 使用 password_bytes 对 value_bytes 进行加密后的结果
        return encrypted_value

    def decrypt_secret_value(self, attr: str, value: str) -> str:
        if self._password is None:
            raise ValueError(f"Could not decrypt secret attribute {attr} because no password was provided.")
        value = binascii.unhexlify(value)
        decrypted_value = Account.decrypt(value.decode(), self._password).decode()
        return decrypted_value


def store_password_verification(secrets_manager: BaseSecretsManager):
    # 使用密码对 PASSWORD_VERIFICATION_WORD 所对应的字符串进行加密，然后将加密后的结果保存到 .password_verification 文件中
    encrypted_word = secrets_manager.encrypt_secret_value(PASSWORD_VERIFICATION_WORD, PASSWORD_VERIFICATION_WORD)
    with open(PASSWORD_VERIFICATION_PATH, "w") as f:
        f.write(encrypted_word)


def validate_password(secrets_manager: BaseSecretsManager) -> bool:
    valid = False
    with open(PASSWORD_VERIFICATION_PATH, "r") as f:
        encrypted_word = f.read()
    try:
        # 使用密码对保存的校验内容进行解密，并与 PASSWORD_VERIFICATION_WORD 进行对比，判断密码是否正确
        decrypted_word = secrets_manager.decrypt_secret_value(PASSWORD_VERIFICATION_WORD, encrypted_word)
        valid = decrypted_word == PASSWORD_VERIFICATION_WORD
    except ValueError as e:
        if str(e) != "MAC mismatch":
            raise e
    return valid


def _create_v3_keyfile_json(message_to_encrypt, password, kdf="pbkdf2", work_factor=None):
    """
    Encrypt message by a given password.
    Most of this code is copied from eth_key_file.key_file, removed address and is from json result.
    """
    salt = Random.get_random_bytes(16)

    if work_factor is None:
        work_factor = get_default_work_factor_for_kdf(kdf)

    if kdf == "pbkdf2":
        derived_key = _pbkdf2_hash(
            password,
            hash_name="sha256",
            salt=salt,
            iterations=work_factor,
            dklen=DKLEN,
        )
        kdfparams = {
            "c": work_factor,
            "dklen": DKLEN,
            "prf": "hmac-sha256",
            "salt": encode_hex_no_prefix(salt),
        }
    elif kdf == "scrypt":
        derived_key = _scrypt_hash(
            password,
            salt=salt,
            buflen=DKLEN,
            r=SCRYPT_R,
            p=SCRYPT_P,
            n=work_factor,
        )
        kdfparams = {
            "dklen": DKLEN,
            "n": work_factor,
            "r": SCRYPT_R,
            "p": SCRYPT_P,
            "salt": encode_hex_no_prefix(salt),
        }
    else:
        raise NotImplementedError("KDF not implemented: {0}".format(kdf))

    iv = big_endian_to_int(Random.get_random_bytes(16))
    encrypt_key = derived_key[:16]
    ciphertext = encrypt_aes_ctr(message_to_encrypt, encrypt_key, iv)
    mac = keccak(derived_key[16:32] + ciphertext)

    return {
        "crypto": {
            "cipher": "aes-128-ctr",
            "cipherparams": {
                "iv": encode_hex_no_prefix(int_to_big_endian(iv)),
            },
            "ciphertext": encode_hex_no_prefix(ciphertext),
            "kdf": kdf,
            "kdfparams": kdfparams,
            "mac": encode_hex_no_prefix(mac),
        },
        "version": 3,
        "alias": "",  # Add this line to include the 'alias' field with an empty string value
    }
