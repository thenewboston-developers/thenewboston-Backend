"""
Settings specific to this application only (no Django or third party settings)
"""

IN_DOCKER = False

# TODO(dmu) MEDIUM: Do we need both `ACCOUNT_NUMBER` and `SIGNING_KEY`.
#                   Can't we derive `ACCOUNT_NUMBER` from `SIGNING_KEY`?
ACCOUNT_NUMBER = None
SIGNING_KEY = None

ENV_NAME = 'unknown'

SENTRY_EVENT_LEVEL = 'WARNING'
SENTRY_DSN = None

LOGGING_MIDDLEWARE_SKIPPED_REQUEST_MEDIA_TYPES = ('multipart/form-data',)
LOGGING_MIDDLEWARE_SKIPPED_RESPONSE_MEDIA_TYPES = ('text/html', 'text/javascript')

# PromptLayer
PROMPTLAYER_API_KEY = None
PROMPT_DEFAULT_LABEL = 'prod'

# OpenAI
OPENAI_API_KEY = None
OPENAI_IMAGE_GENERATION_MODEL = 'dall-e-2'
OPENAI_IMAGE_GENERATION_DEFAULT_SIZE = '1024x1024'
OPENAI_IMAGE_GENERATION_DEFAULT_QUALITY = 'standard'

# Anthropic
ANTHROPIC_API_KEY = None

# Github
GITHUB_API_ACCESS_TOKEN = None

# Prompts
CREATE_MESSAGE_PROMPT_NAME = 'create-message'
GITHUB_PR_ASSESSMENT_PROMPT_NAME = 'github-pr-assessment'
GITHUB_MANUAL_CONTRIBUTION_ASSESSMENT_PROMPT_NAME = 'manual-assessment'

# Misc
DEFAULT_CORE_TICKER = 'TNB'
IS_DEPLOYED = False
