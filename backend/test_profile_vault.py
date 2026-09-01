from pathlib import Path
from tempfile import TemporaryDirectory

from profile_vault import decrypt_profile, vault_id, write_encrypted_profile
from secret_store import SecretStore


def test_encrypted_profile_round_trip_and_authentication():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        package = root / "profile.rsdwl"
        package.write_bytes(b"PK\x03\x04private-profile-payload")
        profile_id = "0123456789abcdef01234567"
        password = "correct horse profile vault"
        written = write_encrypted_profile(package, root, profile_id, password, profile_name="Test Profile")
        envelope = Path(written["path"])
        assert envelope.is_file()
        assert profile_id.encode("utf-8") not in envelope.read_bytes()
        assert b"private-profile-payload" not in envelope.read_bytes()
        assert b"Test Profile" not in envelope.read_bytes()
        assert envelope.name == f"{vault_id(profile_id)}.dws-profile-vault"
        restored = root / "restored.rsdwl"
        result = decrypt_profile(root, profile_id, password, restored)
        assert result["profile_id"] == profile_id
        assert restored.read_bytes() == package.read_bytes()


def test_wrong_profile_password_is_rejected_without_output():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        package = root / "profile.rsdwl"
        package.write_bytes(b"authenticated-profile")
        profile_id = "fedcba9876543210fedcba98"
        write_encrypted_profile(package, root, profile_id, "valid password phrase")
        output = root / "should-not-exist.rsdwl"
        try:
            decrypt_profile(root, profile_id, "incorrect password phrase", output)
        except ValueError as error:
            assert "authentication failed" in str(error).casefold()
        else:
            raise AssertionError("An incorrect Profile Vault password was accepted.")
        assert not output.exists()


def test_vault_password_is_encrypted_in_the_local_secret_store():
    with TemporaryDirectory() as temp:
        store = SecretStore(Path(temp))
        protected = store.protect_document({"profile_local_sync": {"vault_password": "local-only password"}})
        assert str(protected["profile_local_sync"]["vault_password"]).startswith("dws-secret://")
        assert "local-only password" not in (Path(temp) / "vault.json").read_text(encoding="utf-8")
        assert store.hydrate_document(protected)["profile_local_sync"]["vault_password"] == "local-only password"


if __name__ == "__main__":
    test_encrypted_profile_round_trip_and_authentication()
    test_wrong_profile_password_is_rejected_without_output()
    test_vault_password_is_encrypted_in_the_local_secret_store()
    print("encrypted Profile Vault tests passed")
