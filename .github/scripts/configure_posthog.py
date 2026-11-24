"""Install the public PostHog configuration without changing other production settings."""

import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def configure_posthog(encoded_configuration, path):
    configuration = json.loads(base64.b64decode(encoded_configuration, validate=True))
    api_key = configuration['api_key']
    host = configuration['host']
    if not isinstance(api_key, str) or not re.fullmatch(r'phc_[A-Za-z0-9]+', api_key):
        raise ValueError('A valid public PostHog project token is required')
    if not isinstance(host, str) or any(character.isspace() for character in host):
        raise ValueError('A valid HTTPS PostHog ingestion host is required')
    parsed_host = urlsplit(host)
    if (
        parsed_host.scheme != 'https'
        or not parsed_host.hostname
        or parsed_host.username
        or parsed_host.password
        or parsed_host.query
        or parsed_host.fragment
        or parsed_host.path not in ('', '/')
    ):
        raise ValueError('A valid HTTPS PostHog ingestion host is required')

    values = {
        'THENEWBOSTON_SETTING_POSTHOG_API_KEY': api_key,
        'THENEWBOSTON_SETTING_POSTHOG_HOST': host.rstrip('/'),
        'THENEWBOSTON_SETTING_POSTHOG_ENABLED': 'true',
    }
    existing_stat = path.stat()
    lines = [line for line in path.read_text().splitlines() if line.split('=', 1)[0].strip() not in values]
    lines.extend(f'{key}={value}' for key, value in values.items())
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write('\n'.join(lines) + '\n')
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.chmod(temporary_path, existing_stat.st_mode & 0o777)
        os.chown(temporary_path, existing_stat.st_uid, existing_stat.st_gid)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


if __name__ == '__main__':
    configure_posthog(sys.stdin.read().strip(), Path('/etc/thenewboston/.env'))
    print('PostHog production configuration updated')
