import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# These values can be set in environment variables; default values are used when unset.
DEFAULT_EXPONENT = int(os.getenv("RSA_PUBLIC_EXPONENT", "65537"))
DEFAULT_KEY_SIZE = int(os.getenv("RSA_KEY_SIZE", "2048"))


def generate_rsa_keys():
    """Generate a new RSA key pair and return the private/public keys."""
    private_key = rsa.generate_private_key(
        public_exponent=DEFAULT_EXPONENT,
        key_size=DEFAULT_KEY_SIZE,
    )
    public_key = private_key.public_key()
    return private_key, public_key


def encrypt_rsa(data: str, public_key) -> bytes:
    """Encrypt a UTF-8 string using the provided public key."""
    encrypted_data = public_key.encrypt(
        data.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return encrypted_data


def decrypt_rsa(encrypted_data: bytes, private_key) -> str:
    """Decrypt RSA-encrypted data and return it as a UTF-8 string."""
    decrypted_data = private_key.decrypt(
        encrypted_data,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return decrypted_data.decode("utf-8")
