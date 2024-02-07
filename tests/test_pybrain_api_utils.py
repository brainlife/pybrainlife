from pybrainlife.api.utils import validate_branch


def test_valid_branch():
    github_branch = "v1.00"
    github = "brain-life/app-autoalignacpc"

    branch = validate_branch(github, github_branch)

    assert branch == "v1.00"
