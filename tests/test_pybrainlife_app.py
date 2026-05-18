from pybrainlife.api.app import app_run, app_fetch
from pybrainlife.cli.utils import init_auth
import pytest

init_auth()


@pytest.mark.skip("Check for integration test environment")
def test_app_run_fail_incorrect_inputs():
    """Test running an app with incorrect inputs (should fail gracefully)."""
    project_id = "6566f998b094062da65337ef"
    app_id = "5f3593e84615e04651bf9364"
    
    # Use incorrect input that should cause an error
    inputs = {
        "t1": "656fc8a1d0ae0de207f3f315",
        "t2": "65c3f736745ef7acd7bcf08b",  # This input might not be valid for the app
    }

    # This should raise an exception due to incorrect inputs
    with pytest.raises(Exception) as exc_info:
        app_run(
            app_id=app_id,
            project_id=project_id,
            inputs=inputs,
            instance_id=None,
            config={"reorient": True, "crop": True},
        )

    # Verify that we get an appropriate error message
    assert exc_info.value is not None


@pytest.mark.skip("Check for integration test environment")
def test_app_run_multiple_different_inputs():
    """Test running an app with multiple different inputs."""
    project_id = "6566f998b094062da65337ef"
    # C-PAC app
    app_id = "5f3593e84615e04651bf9364"
    
    inputs = {
        "t1": "656fc8a1d0ae0de207f3f315",
        "func": "65c3f7a7745ef7acd7bcfa87",
    }

    # Run the app with multiple inputs
    result = app_run(
        app_id=app_id,
        project_id=project_id,
        inputs=inputs,
        instance_id=None,
        config={"reorient": True, "crop": True},
    )
    
    # Verify app run results
    assert result is not None
    assert hasattr(result, 'id')  # Should return a task or similar object


@pytest.mark.skip("Check for integration test environment")
def test_app_run_without_instance():
    """Test running an app without specifying an instance."""
    project_id = "65b022f04ce5ac2907f7d4a1"
    # freesurfer Deface app
    app_id = "59714d376c3b7e0029153f53"
    
    inputs = {
        "t1": "65b030124ce5ac2907f81c48",
    }

    # Fetch app details first
    app = app_fetch(app_id)
    assert app is not None
    assert app.id == app_id

    # Run the app without instance (should auto-create)
    result = app_run(
        app_id=app_id,
        project_id=project_id,
        inputs=inputs,
        instance_id=None,
        config={"reorient": True, "crop": True},
    )
    
    # Verify app run results
    assert result is not None
    assert hasattr(result, 'id')


@pytest.mark.skip("Check for integration test environment")
def test_app_run_valid_instance():
    """Test running an app with a valid instance."""
    project_id = "65b022f04ce5ac2907f7d4a1"
    # freesurfer Deface app
    app_id = "59714d376c3b7e0029153f53"
    
    inputs = {
        "t1": "65b030124ce5ac2907f81c48",
    }

    instance_id = "65c3ec484028114d9819f8b6"

    # Fetch app details first
    app = app_fetch(app_id)
    assert app is not None
    assert app.id == app_id

    # Run the app with valid instance
    result = app_run(
        app_id=app_id,
        project_id=project_id,
        inputs=inputs,
        instance_id=instance_id,
        config={"reorient": True, "crop": True},
    )
    
    # Verify app run results
    assert result is not None
    assert hasattr(result, 'id')


@pytest.mark.skip("Check for integration test environment")
def test_app_run_invalid_instance():
    """Test running an app with an invalid instance (should handle gracefully)."""
    project_id = "65b022f04ce5ac2907f7d4a1"
    # freesurfer Deface app
    app_id = "59714d376c3b7e0029153f53"
    
    inputs = {
        "t1": "65b030124ce5ac2907f81c48",
    }
    
    # Use an invalid instance ID
    invalid_instance_id = "invalid_instance_id_12345"
    
    # This should either raise an exception or handle gracefully
    with pytest.raises(Exception):
        app_run(
            app_id=app_id,
            project_id=project_id,
            inputs=inputs,
            instance_id=invalid_instance_id,
            config={"reorient": True, "crop": True},
        )
