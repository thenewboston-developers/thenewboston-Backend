# Project setup

**SECTIONS**
1. [Initial Project Setup](#initial-project-setup)
2. [Essential Developer Guidelines](#essential-developer-guidelines) 


# Initial Project Setup

Clone the Repository

```bash
git clone https://github.com/thenewboston-developers/thenewboston-Backend.git
```

Copy the settings templates into a new local directory:

```bash
mkdir -p local
cp thenewboston/project/settings/templates/settings.dev.py ./local/settings.dev.py
cp thenewboston/project/settings/templates/settings.unittests.py ./local/settings.unittests.py
```

Commands for setting up local environment
Make sure Docker is installed in your machine and run the following commands:

```bash
make run-dependencies  # Sets up the necessary Docker containers for Redis and PostgreSQL
make install           # Installs project dependencies
make migrate           # Applies database migrations
```

Fire Up the Server 🚀

```bash
make run-server    # Starts the Django development server
make run-celery    # Starts the Celery worker for background tasks and LLM chatbot
```

Now you're all set! The backend is up and ready for action.


# Essential Developer Guidelines

To contribute effectively, follow these guidelines:

- Branch off (new branch) from `master` for new features or fixes.
- Do your work and run `make lint` to ensure code quality.
- Open a Pull Request (PR) for review.
- Wait for approval before merging to `master`. No direct pushes, please!
