from pybrainlife.api.utils import validate_branch


def test_valid_branch():
    github_branch = "1.4"
    github = "brainlife/app-hcp-acpc-alignment"

    validate_branch(github, github_branch)
