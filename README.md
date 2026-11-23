# Project setup

**SECTIONS**
1. [Initial Project Setup](#initial-project-setup)
2. [Essential Developer Guidelines](#essential-developer-guidelines)


# Initial Project Setup

1. Install Python version 3.10.13 and make sure it is being used in the following steps and later during development
   (it is recommended to use [pyenv](https://github.com/pyenv/pyenv) for Python versions management)

2. Install Poetry

```bash
export PIP_REQUIRED_VERSION=24.2
pip install pip==${PIP_REQUIRED_VERSION} && \
pip install virtualenvwrapper && \
pip install poetry==2.1.3 && \
poetry config virtualenvs.path ${HOME}/.virtualenvs && \
poetry run pip install pip==${PIP_REQUIRED_VERSION}
```

3. Clone the Repository

```bash
git clone https://github.com/thenewboston-developers/thenewboston-Backend.git
```

4. Copy the settings templates into a new local directory:

```bash
mkdir -p local
cp thenewboston/project/settings/templates/settings.dev.py ./local/settings.dev.py
cp thenewboston/project/settings/templates/settings.unittests.py ./local/settings.unittests.py
```

5. Install / upgrade docker as described at https://docs.docker.com/engine/install/
```bash
# Known working versions described in the comments below

docker --version # Docker version 26.0.1, build d260a54

# (!!!) At least Docker Compose version v2.24.0 is required
docker compose version # Docker Compose version v2.26.1
```

6. Commands for setting up local environment. Run the following commands:

```bash
make run-dependencies  # Sets up the necessary Docker containers for Redis and PostgreSQL
make update            # Installs project dependencies, pre-commit and applies database migrations
```

7. Fire Up the Server 🚀

```bash
make run-server       # Starts the Django development server
```

8. Create a superuser and configure the initial data

```bash
make superuser        # Creates a Django superuser account
```

After creating the superuser, you need to set up some initial data:

1. Go to Django admin at http://localhost:8000/admin/
2. Log in with your superuser credentials
3. Navigate to **Currencies** and manually add a currency with the ticker **TNB**
4. Navigate to **Invitation limits** and manually set an invitation limit for your superuser

Now you're all set! The backend is up and ready for action.


# Essential Developer Guidelines

To contribute effectively, follow these guidelines:

- Branch off (new branch) from `master` for new features or fixes.
- Do your work and run `make lint` to ensure code quality.
- Open a Pull Request (PR) for review.
- Wait for approval before merging to `master`. No direct pushes, please!

# Backgammon

Backgammon supports free computer practice and human challenges, with optional TNB stakes for human matches. Matches are played to 1, 3, or 5 points. Singles, gammons, backgammons, doubling-cube ownership, and the Crawford game determine the point score. The TNB stake is fixed for the entire match: cube decisions never increase the coin commitment. Computer games cannot carry a stake.

The server owns dice rolls, legal turns, match clocks, and settlement. A complete turn must use the maximum number of playable dice, including the larger die when only one can be played. Actions include an `expected_version` so stale requests cannot replay moves or payments. Stake, refund, and payout entries are recorded in the match ledger. Free games do not require a wallet.

The API is under `/api/backgammon/matches`. Creation requires a UUID `request_id` that is reused for retries, and selects `mode`, `opponent_id` for human games, `difficulty`, `stake_amount`, `target_score`, and `time_limit_seconds`. Pending matches are invitations; their actions are `accept`, `decline`, and `cancel`. Active match actions are `roll`, `move`, `double`, `respond-double`, `next-game`, and `resign`. A finished match can create a `rematch`. The detail response includes available complete turns for the player currently moving. Public match state supports spectating; pending invitations are private to their participants.

The computer is a local heuristic opponent, not GNU Backgammon or a tournament-strength engine. Easy chooses legal outcomes randomly, normal evaluates board position, and hard considers sampled replies. Computer turns run through Celery. Run both the worker and Beat scheduler alongside the API; the scheduler also handles abandoned challenges and match clocks. New database tables are installed by the normal deployment migration step.

Run the game tests with `poetry run pytest thenewboston/backgammon/tests`. Tests require the same PostgreSQL and Redis services as the rest of the backend suite.
