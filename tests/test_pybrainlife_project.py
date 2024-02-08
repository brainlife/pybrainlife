import pytest

from pybrainlife.cli.utils import set_auth, init_auth
from pybrainlife.api.project import project_create, project_delete, project_query
from pybrainlife.api.api import login, set_host

projectID = None


# TODO decide what to do with this
# set_host("test.brainlife.io")
# jwt = login('', '')
# set_auth(jwt)
# init_auth()


@pytest.mark.skip("Check for integration test environment")
@pytest.mark.dependency()
def test_create_project():
    pass
    # global projectID
    # project = project_create(name="test", description="test")
    # print(project)
    # assert project is not None
    # assert project.id is not None
    # assert project.name == "test"
    # assert project.description == "test"
    # projectID = project.id


@pytest.mark.skip("Check for integration test environment")
@pytest.mark.dependency(depends=["test_create_project"])
def test_retrieve_project():
    pass
    # projects = project_query(id=projectID)
    # assert projects is not None
    # assert len(projects) > 0
    # project = projects[0]
    # assert project.id == projectID
    # assert project.name == "test"
    # assert project.description == "test"


@pytest.mark.skip("Check for integration test environment")
@pytest.mark.dependency(depends=["test_retrieve_project"])
def test_delete_project():
    pass
    # project_delete(projectID)
    # project = project_query(id=projectID)[0]
    # assert project.removed is True
