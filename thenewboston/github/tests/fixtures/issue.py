from model_bakery import baker


def create_issue(repo):
    return baker.make(
        'github.Issue',
        repo=repo,
        issue_number=1,
        title='First issue',
    )
