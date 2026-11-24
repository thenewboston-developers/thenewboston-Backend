import base64
import json
import tempfile
import unittest
from pathlib import Path

from configure_posthog import configure_posthog


class ConfigurePostHogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / '.env'
        self.original = (
            '# Keep this comment\nDATABASE=unchanged\nTHENEWBOSTON_SETTING_POSTHOG_HOST=https://old.example\n'
        )
        self.path.write_text(self.original)
        self.path.chmod(0o640)

    def encode(self, api_key='phc_example', host='https://ingest.example'):
        return base64.b64encode(json.dumps({'api_key': api_key, 'host': host}).encode()).decode()

    def test_preserves_unrelated_settings_permissions_and_is_repeatable(self):
        configure_posthog(self.encode(), self.path)
        first_result = self.path.read_text()
        configure_posthog(self.encode(), self.path)
        self.assertEqual(self.path.read_text(), first_result)
        self.assertIn('# Keep this comment\nDATABASE=unchanged\n', first_result)
        self.assertEqual(first_result.count('THENEWBOSTON_SETTING_POSTHOG_HOST='), 1)
        self.assertIn('THENEWBOSTON_SETTING_POSTHOG_ENABLED=true\n', first_result)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)

    def test_invalid_configuration_leaves_existing_file_untouched(self):
        for encoded in [
            self.encode(api_key='invalid'),
            self.encode(host='http://example.com'),
            self.encode(host='https://example.com\nINJECTED=true'),
        ]:
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                configure_posthog(encoded, self.path)
            self.assertEqual(self.path.read_text(), self.original)


if __name__ == '__main__':
    unittest.main()
