"""
Settings specific to this application only (no Django or third party settings)
"""

IN_DOCKER = False

ACCOUNT_NUMBER = None
SIGNING_KEY = None

OPENAI_API_KEY = None
PROMPTLAYER_API_KEY = None
GITHUB_API_ACCESS_TOKEN = None

CONTRIBUTION_CORE_DEFAULT_TICKER = 'TNB'

# Settings useful for testing and debugging
GITHUB_PULL_REQUEST_STATE_FILTER = 'open'  # Useful for debugging (when set to 'all')
IS_CASSETTE_RECORDING = False
USE_ON_COMMIT_HOOK = True
KEEP_DEFAULT_STATICFILES_STORAGE = False
