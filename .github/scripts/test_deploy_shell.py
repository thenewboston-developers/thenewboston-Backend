import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / 'workflows' / 'backend-deploy.yml'

# Execute the actual remote deployment script with harmless commands. Docker deliberately drains stdin, just as
# compose exec -T can do while bash -s is reading the SSH heredoc from the same descriptor.
PRELUDE = r"""
cd() { :; }
git() {
    if [ "$1" = rev-parse ]; then
        printf '%040d\n' 0
    fi
}
sudo() { cat >/dev/null; }
make() { printf 'make:%s\n' "$1" >> "$DEPLOY_TEST_LOG"; }
docker() {
    local checked_command
    for checked_command in "$@"; do
        case "$checked_command" in
            verify_product_analytics|verify_websocket_authentication|verify_casino|verify_tribes|announce_frontend_deployment)
                printf '%s\n' "$checked_command" >> "$DEPLOY_TEST_LOG"
                cat >/dev/null
                if [ "$checked_command" = "$DEPLOY_TEST_FAIL" ]; then
                    return 23
                fi
                return 0
                ;;
        esac
    done
    return 24
}
"""


class DeployShellTests(unittest.TestCase):
    def run_deploy(self, announce='', fail=''):
        workflow = WORKFLOW.read_text()
        match = re.search(r"<< 'EOF'\n(.*?)\n\s*EOF(?:\n|$)", workflow, re.DOTALL)
        self.assertIsNotNone(match, 'The remote deployment heredoc must be present')
        script = PRELUDE + textwrap.dedent(match.group(1))
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'commands.log'
            result = subprocess.run(
                ['bash', '-s'],
                input=script,
                text=True,
                capture_output=True,
                timeout=10,
                env={
                    **os.environ,
                    'DEPLOY_TEST_LOG': str(log),
                    'DEPLOY_TEST_FAIL': fail,
                    'POSTHOG_CONFIG': 'synthetic-configuration',
                    'ANNOUNCE_PREVIOUS_ID': announce,
                },
            )
            return result, log.read_text().splitlines()

    def test_checks_and_cleanup_run_when_docker_consumes_stdin(self):
        result, commands = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            commands,
            [
                'make:deploy',
                'verify_product_analytics',
                'verify_websocket_authentication',
                'verify_casino',
                'verify_tribes',
                'make:deploy-cleanup',
            ],
        )

    def test_announcement_does_not_consume_cleanup(self):
        result, commands = self.run_deploy(announce='7')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            commands,
            [
                'make:deploy',
                'verify_product_analytics',
                'verify_websocket_authentication',
                'verify_casino',
                'verify_tribes',
                'announce_frontend_deployment',
                'make:deploy-cleanup',
            ],
        )

    def test_failed_verification_stops_before_announcement(self):
        result, commands = self.run_deploy(announce='7', fail='verify_websocket_authentication')
        self.assertEqual(result.returncode, 23)
        self.assertEqual(commands, ['make:deploy', 'verify_product_analytics', 'verify_websocket_authentication'])

    def test_failed_announcement_fails_deployment(self):
        result, commands = self.run_deploy(announce='7', fail='announce_frontend_deployment')
        self.assertEqual(result.returncode, 23)
        self.assertEqual(commands[-1], 'announce_frontend_deployment')
        self.assertNotIn('make:deploy-cleanup', commands)

    def test_failed_casino_verification_fails_deployment(self):
        result, commands = self.run_deploy(announce='7', fail='verify_casino')
        self.assertEqual(result.returncode, 23)
        self.assertEqual(commands[-1], 'verify_casino')
        self.assertNotIn('announce_frontend_deployment', commands)
        self.assertNotIn('make:deploy-cleanup', commands)

    def test_failed_tribes_verification_fails_deployment(self):
        result, commands = self.run_deploy(announce='7', fail='verify_tribes')
        self.assertEqual(result.returncode, 23)
        self.assertEqual(commands[-1], 'verify_tribes')
        self.assertNotIn('announce_frontend_deployment', commands)
        self.assertNotIn('make:deploy-cleanup', commands)


if __name__ == '__main__':
    unittest.main()
