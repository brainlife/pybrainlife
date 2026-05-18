import pytest
import time

from pybrainlife.api.resource import (
    resource_create,
    resource_query,
    find_best_resource,
    resource_delete,
    resource_update,
)

from pybrainlife.cli.utils import logged_in_user_details

# Global variable to store created resource for cleanup
resource = None


@pytest.mark.skip("Requires integration test environment")
def test_create_resource():
    """Test creating a new resource."""
    global resource
    
    # Create unique resource name to avoid conflicts
    name = f"test_resource_{int(time.time())}"
    active = True
    gids = [0, 1, 2]
    envs = {"test": 123}
    config = {
        "auth_method": "keytab",
        "username": "username_test",
        "keytab": "keytab_test",
    }

    resource = resource_create(
        name=name,
        config=config, 
        active=active, 
        gids=gids, 
        envs=envs
    )

    # Verify resource creation
    assert resource is not None
    assert resource.name == name
    assert resource.active == active
    # Note: gids assertion commented out as it depends on user and group
    assert resource.envs == envs
    assert resource.config == config


@pytest.mark.skip("Requires integration test environment")
@pytest.mark.dependency(depends=["test_create_resource"])
def test_query_resource():
    """Test querying a resource by ID."""
    global resource
    
    resources = resource_query(id=resource.id)
    
    # Verify resource retrieval
    assert resources is not None
    assert len(resources) > 0
    
    resourceReturned = resources[0]
    assert resourceReturned.id == resource.id
    assert resourceReturned.name == resource.name
    assert resourceReturned.active == resource.active
    # Note: gids assertion commented out as it depends on user and group
    assert resourceReturned.envs == resource.envs
    assert resourceReturned.config == resource.config


@pytest.mark.skip("Requires integration test environment")
@pytest.mark.dependency(depends=["test_query_resource"])
def test_update_resource():
    """Test updating a resource."""
    global resource
    
    # Update resource properties
    resource.name = f"test_resource_updated_{int(time.time())}"
    resource.active = False
    
    response = resource_update(resource.id, name=resource.name, active=resource.active)
    
    # Verify resource update
    assert response is not None
    assert response['name'] == resource.name
    assert response['active'] == resource.active


@pytest.mark.skip("Requires integration test environment")
@pytest.mark.dependency(depends=["test_update_resource"])
def test_delete_resource():
    """Test deleting a resource."""
    global resource
    
    response = resource_delete(resource.id)
    
    # Verify resource deletion
    assert response is not None
    assert response['status'] == 'ok'


@pytest.mark.skip("Requires integration test environment")
def test_find_best_resource():
    """Test finding the best resource for a service."""
    # Test with a known service
    service = "brainlife/app-fsl-anat"
    
    # Get user details and group IDs
    get_user = logged_in_user_details()
    groupIDS = [17519] + get_user['gids']
    
    resources = find_best_resource(service, groupIDS)
    
    # Verify resource finding
    assert resources is not None
    assert len(resources) > 0
    
    resource = resources['resource']
    assert resource is not None
    assert resource.id is not None
    assert resource.name is not None
    assert resource.active is not None
    assert resource.envs is not None
    assert resource.config is not None
    assert resource.gids is not None
