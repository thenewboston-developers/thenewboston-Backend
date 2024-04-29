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

# OpenAI related
OPENAI_API_KEY = None
PROMPTLAYER_API_KEY = None
OPENAI_IMAGE_GENERATION_MODEL = 'dall-e-2'
OPENAI_IMAGE_GENERATION_DEFAULT_SIZE = '1024x1024'
OPENAI_IMAGE_GENERATION_DEFAULT_QUALITY = 'standard'

CREATE_MESSAGE_TEMPLATE_NAME = 'create-message'
GITHUB_PR_ASSESSMENT_TEMPLATE_NAME = 'github-pr-assessment'
PROMPT_TEMPLATE_LABEL = 'prod'

GITHUB_API_ACCESS_TOKEN = None

DEFAULT_CORE_TICKER = 'TNB'
