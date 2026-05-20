import tempfile
import unittest
import zipfile
from pathlib import Path

from bugfix_automation.infra.file_metadata import file_metadata
from bugfix_automation.infra.uploads import safe_upload_name, validate_xlsx


class ServiceExtractionTest(unittest.TestCase):
    def test_file_metadata_reports_hash_and_original_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stored.xlsx"
            path.write_bytes(b"demo")

            metadata = file_metadata(path, original_name="bugs.xlsx")

        self.assertEqual(metadata["original_name"], "bugs.xlsx")
        self.assertEqual(metadata["stored_name"], "stored.xlsx")
        self.assertEqual(metadata["size"], 4)
        self.assertEqual(metadata["sha256"], "2a97516c354b68848cdbd8f54a226a0a55b21ed138e207ad6c5cbb9c00aa5aea")

    def test_upload_helpers_sanitize_and_validate_xlsx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = root / "valid.xlsx"
            with zipfile.ZipFile(valid, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types></Types>")

            name = safe_upload_name("bad/name ?.xlsx")

            validate_xlsx(valid)

        self.assertTrue(name.startswith("name-"))
        self.assertTrue(name.endswith(".xlsx"))


if __name__ == "__main__":
    unittest.main()
