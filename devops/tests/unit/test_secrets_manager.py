"""
Unit tests for secrets manager.
"""

import pytest
from pathlib import Path
from devops_agent.core.secrets_manager import (
    SecretsManager,
    get_secrets_manager,
    get_secret,
    set_secret,
)


class TestSecretsManager:
    """Test secrets manager functionality."""
    
    @pytest.fixture
    def secrets_file(self, tmp_path):
        """Create a temporary secrets file."""
        return tmp_path / "test_secrets.enc"
    
    @pytest.fixture
    def manager(self, secrets_file):
        """Create a secrets manager instance."""
        return SecretsManager(
            secrets_file=secrets_file,
            passphrase="test-passphrase-123"
        )
    
    def test_set_and_get_secret(self, manager):
        """Test setting and getting a secret."""
        manager.set_secret("api_key", "secret_value_123")
        value = manager.get_secret("api_key")
        assert value == "secret_value_123"
    
    def test_get_nonexistent_secret(self, manager):
        """Test getting a non-existent secret."""
        value = manager.get_secret("nonexistent")
        assert value is None
        
        value = manager.get_secret("nonexistent", default="default_value")
        assert value == "default_value"
    
    def test_delete_secret(self, manager):
        """Test deleting a secret."""
        manager.set_secret("temp_key", "temp_value")
        assert manager.get_secret("temp_key") == "temp_value"
        
        manager.delete_secret("temp_key")
        assert manager.get_secret("temp_key") is None
    
    def test_list_secrets(self, manager):
        """Test listing secret keys."""
        manager.set_secret("key1", "value1")
        manager.set_secret("key2", "value2")
        
        keys = manager.list_secrets()
        assert "key1" in keys
        assert "key2" in keys
    
    def test_clear_all(self, manager):
        """Test clearing all secrets."""
        manager.set_secret("key1", "value1")
        manager.set_secret("key2", "value2")
        
        manager.clear_all()
        assert len(manager.list_secrets()) == 0
    
    def test_persistence(self, secrets_file):
        """Test secrets persist across instances."""
        manager1 = SecretsManager(
            secrets_file=secrets_file,
            passphrase="test-passphrase-123"
        )
        manager1.set_secret("persistent_key", "persistent_value")
        
        # Create new instance with same file
        manager2 = SecretsManager(
            secrets_file=secrets_file,
            passphrase="test-passphrase-123"
        )
        value = manager2.get_secret("persistent_key")
        assert value == "persistent_value"
    
    def test_env_var_precedence(self, manager, monkeypatch):
        """Test environment variable takes precedence."""
        manager.set_secret("test_key", "stored_value")
        
        # Set environment variable
        monkeypatch.setenv("TEST_KEY", "env_value")
        
        value = manager.get_secret("test_key")
        assert value == "env_value"
    
    def test_file_permissions(self, manager, secrets_file):
        """Test secrets file has restricted permissions."""
        manager.set_secret("test", "value")
        
        # Check file permissions (should be 0o600)
        import stat
        mode = secrets_file.stat().st_mode
        assert stat.S_IMODE(mode) == 0o600


class TestGlobalSecretsManager:
    """Test global secrets manager functions."""
    
    def test_get_and_set_secret(self):
        """Test global get/set functions."""
        set_secret("global_key", "global_value")
        value = get_secret("global_key")
        assert value == "global_value"
    
    def test_get_secrets_manager_singleton(self):
        """Test global manager is a singleton."""
        manager1 = get_secrets_manager()
        manager2 = get_secrets_manager()
        assert manager1 is manager2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
