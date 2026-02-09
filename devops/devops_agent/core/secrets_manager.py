"""
Secrets Manager - Encrypted storage for sensitive credentials.

Provides:
- Encrypted secrets storage using Fernet (symmetric encryption)
- Automatic encryption/decryption
- Secure key derivation from passphrase
- Environment variable fallback
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from base64 import urlsafe_b64encode
from hashlib import pbkdf2_hmac

try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class SecretsManager:
    """
    Manages encrypted secrets storage.
    
    Usage:
        manager = SecretsManager()
        manager.set_secret("github_token", "ghp_xxxxx")
        token = manager.get_secret("github_token")
    """
    
    def __init__(
        self,
        secrets_file: Path = None,
        passphrase: str = None,
    ):
        """
        Initialize secrets manager.
        
        Args:
            secrets_file: Path to encrypted secrets file
            passphrase: Passphrase for encryption (or use SECRETS_PASSPHRASE env var)
        """
        self.secrets_file = secrets_file or Path.home() / ".devops_agent" / "secrets.enc"
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Get passphrase from env or parameter
        self.passphrase = passphrase or os.getenv("SECRETS_PASSPHRASE")
        
        if not self.passphrase:
            # Use a default (NOT SECURE - user should set SECRETS_PASSPHRASE)
            self.passphrase = "default-insecure-passphrase-change-me"
        
        self._cipher = self._get_cipher()
        self._secrets_cache: Optional[Dict[str, str]] = None
    
    def _get_cipher(self):
        """Get Fernet cipher from passphrase."""
        if not CRYPTO_AVAILABLE:
            return None
        
        # Derive key from passphrase using PBKDF2
        key = pbkdf2_hmac(
            'sha256',
            self.passphrase.encode(),
            b'devops-agent-salt',  # Static salt (ideally should be random and stored)
            100000,  # iterations
            dklen=32
        )
        
        # Fernet requires base64-encoded 32-byte key
        fernet_key = urlsafe_b64encode(key)
        return Fernet(fernet_key)
    
    def _load_secrets(self) -> Dict[str, str]:
        """Load and decrypt secrets from file."""
        if self._secrets_cache is not None:
            return self._secrets_cache
        
        if not self.secrets_file.exists():
            self._secrets_cache = {}
            return self._secrets_cache
        
        try:
            encrypted_data = self.secrets_file.read_bytes()
            
            if self._cipher:
                decrypted_data = self._cipher.decrypt(encrypted_data)
                self._secrets_cache = json.loads(decrypted_data.decode())
            else:
                # Fallback: unencrypted (NOT RECOMMENDED)
                self._secrets_cache = json.loads(encrypted_data.decode())
            
            return self._secrets_cache
        except Exception as e:
            raise RuntimeError(f"Failed to load secrets: {e}")
    
    def _save_secrets(self, secrets: Dict[str, str]):
        """Encrypt and save secrets to file."""
        try:
            data = json.dumps(secrets).encode()
            
            if self._cipher:
                encrypted_data = self._cipher.encrypt(data)
            else:
                # Fallback: unencrypted (NOT RECOMMENDED)
                encrypted_data = data
            
            # Write with restricted permissions
            self.secrets_file.write_bytes(encrypted_data)
            self.secrets_file.chmod(0o600)  # Owner read/write only
            
            self._secrets_cache = secrets
        except Exception as e:
            raise RuntimeError(f"Failed to save secrets: {e}")
    
    def set_secret(self, key: str, value: str):
        """
        Store a secret.
        
        Args:
            key: Secret identifier
            value: Secret value
        """
        secrets = self._load_secrets()
        secrets[key] = value
        self._save_secrets(secrets)
    
    def get_secret(self, key: str, default: str = None) -> Optional[str]:
        """
        Retrieve a secret.
        
        Args:
            key: Secret identifier
            default: Default value if not found
            
        Returns:
            Secret value or default
        """
        # First check environment variable (takes precedence)
        env_value = os.getenv(key.upper())
        if env_value:
            return env_value
        
        # Then check encrypted storage
        secrets = self._load_secrets()
        return secrets.get(key, default)
    
    def delete_secret(self, key: str):
        """
        Delete a secret.
        
        Args:
            key: Secret identifier
        """
        secrets = self._load_secrets()
        if key in secrets:
            del secrets[key]
            self._save_secrets(secrets)
    
    def list_secrets(self) -> list[str]:
        """
        List all secret keys (not values).
        
        Returns:
            List of secret keys
        """
        secrets = self._load_secrets()
        return list(secrets.keys())
    
    def clear_all(self):
        """Delete all secrets."""
        self._save_secrets({})


# Global instance
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get the global secrets manager instance."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager


def get_secret(key: str, default: str = None) -> Optional[str]:
    """
    Get a secret from the global secrets manager.
    
    Args:
        key: Secret identifier
        default: Default value if not found
        
    Returns:
        Secret value or default
    """
    return get_secrets_manager().get_secret(key, default)


def set_secret(key: str, value: str):
    """
    Set a secret in the global secrets manager.
    
    Args:
        key: Secret identifier
        value: Secret value
    """
    get_secrets_manager().set_secret(key, value)
