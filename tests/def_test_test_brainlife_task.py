from pybrainlife.api.api import get_host, get_auth, set_auth
from pybrainlife.cli.utils import init_auth
from pybrainlife.api.project import project_create
from pybrainlife.api.task import task_run, instance_create, instance_query


def test_create_instace():
    global projectID
    global instance
    init_auth()
    project = project_create(name="test", description="test")
    print(project)
    assert project is not None
    assert project.id is not None
    assert project.name == "test"
    assert project.description == "test"
    projectID = project.id
    instance_name = "test task #1"
    instance = instance_create(name=instance_name, project=project)
    assert instance is not None
    assert instance.name == instance_name
    assert instance.project == projectID

def test_query_instance():
    instances = instance_query(id=instance.id)
    assert instances is not None
    assert len(instances) > 0
    instanceReturned = instances[0]
    assert instanceReturned.id == instance.id
    assert instanceReturned.name == instance.name

# def test_task_run():




# def test_retrieve_project_by_id():
#     projects = project_query(id=projectID)
#     assert projects is not None
#     assert len(projects) > 0
#     project = projects[0]
#     assert project.id == projectID
#     assert project.name == "test"
#     assert project.description == "test"


# def test_delete_project():
#     init_auth()
#     project_delete(projectID)
#     project = project_query(id=projectID)[0]
#     assert project.removed is True
