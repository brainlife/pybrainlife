from pybrainlife.api.resource import resource_create, resource_query, find_best_resource, resource_delete, resource_update

from pybrainlife.cli.utils import logged_in_user_details

def test_create_resource():
    global resource
    name = "test resource"
    active = True
    gids = [0, 1, 2]
    envs = {"test": 123}
    config = {
        "auth_method": "keytab",
        "username": "username_test",
        "keytab": "keytab_test",
    }

    resource = resource_create(name=name,config=config, active=active, gids=gids, envs=envs, )

    assert resource is not None
    assert resource.name == name
    assert resource.active == active
    # assert resource.gids == gids # this is not working as gids dependes on the user and the group
    assert resource.envs == envs
    assert resource.config == config
    assert resource.active == active

def test_query_resource():
    resources = resource_query(id=resource.id)
    assert resources is not None
    assert len(resources) > 0
    resourceReturned = resources[0]
    assert resourceReturned.id == resource.id
    assert resourceReturned.name == resource.name
    assert resourceReturned.active == resource.active
    # assert resourceReturned.gids == resource.gids # this is not working as gids dependes on the user and the group
    assert resourceReturned.envs == resource.envs
    assert resourceReturned.config == resource.config
    assert resourceReturned.active == resource.active

def test_update_resource():
    resource.name = "test resource updated"
    resource.active = False
    print(resource.id)
    response = resource_update(resource.id, name=resource.name, active=resource.active)
    assert response is not None
    print(response)
    assert response['name'] == resource.name
    assert response['active'] == resource.active

def test_delete_resource():
    resource_delete(resource.id)
    response = resource_delete(resource.id)
    assert response is not None
    assert response['status'] == 'ok'

def test_find_best_resource():
    # service = "soichih/sca-product-raw"
    service = "brainlife/app-fsl-anat"
    get_user = logged_in_user_details()
    groupIDS = [17519] + get_user['gids']
    resources = find_best_resource(service,groupIDS)
    assert resources is not None
    assert len(resources) > 0
    resource = resources['resource']
    assert resource is not None
    assert resource.id is not None
    assert resource.name is not None
    assert resource.active is not None
    assert resource.envs is not None
    assert resource.config is not None
    assert resource.active is not None
    assert resource.gids is not None

