from pybrainlife.api.api import get_host, get_auth, set_auth
from pybrainlife.cli.utils import init_auth
from pybrainlife.api.project import project_create, project_delete,project_query


def test_create_project():
    global projectID
    init_auth()
    project = project_create(name="test", description="test")
    print(project)
    assert project is not None
    assert project.id is not None
    assert project.name == "test"
    assert project.description == "test"
    projectID = project.id

def test_retrieve_project_by_id():
    projects = project_query(id=projectID)
    assert projects is not None
    assert len(projects) > 0
    project = projects[0]
    assert project.id == projectID
    assert project.name == "test"
    assert project.description == "test"


def test_delete_project():
    init_auth()
    project_delete(projectID)
    project = project_query(id=projectID)[0]
    assert project.removed is True
