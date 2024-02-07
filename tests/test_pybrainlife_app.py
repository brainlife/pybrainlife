from pybrainlife.api.app import app_run, get_app_by_id
from pybrainlife.cli.utils import set_auth, init_auth
import pytest

init_auth()


def test_app_run_without_instance():
    project_id = "65b022f04ce5ac2907f7d4a1"
    # freesurfer Deface
    app_id = "59714d376c3b7e0029153f53"
    # login and then run app in one of my project in brainlife
    inputs = {
        "t1: 65b030124ce5ac2907f81c48",
    }

    instance_id = "65c3ec484028114d9819f8b6"

    app = get_app_by_id(app_id)

    # assert 1 == 0
    app_run(
        app_id=app_id,
        project_id=project_id,
        inputs=inputs,
        instance_id=None,
        config={"reorient": True, "crop": True},
    )


def test_app_run_valid_instance():
    project_id = "65b022f04ce5ac2907f7d4a1"
    # freesurfer Deface
    app_id = "59714d376c3b7e0029153f53"
    # login and then run app in one of my project in brainlife
    inputs = {
        "t1: 65b030124ce5ac2907f81c48",
    }

    instance_id = "65c3ec484028114d9819f8b6"

    app = get_app_by_id(app_id)

    # assert 1 == 0
    app_run(
        app_id=app_id,
        project_id=project_id,
        inputs=inputs,
        instance_id=instance_id,
        config={"reorient": True, "crop": True},
    )

    # bl app run
    #     --id 59714d376c3b7e0029153f53
    #     --input t1:65b030124ce5ac2907f81c48
    #     --project 65b022f04ce5ac2907f7d4a1
    #     --resource abcdsdfdsfsdfdsfsdfdsfsdfdsfsdfdsf
    #     --config '{"reorient" : true, "crop" : true}'
    # #     #add you, anibal and om to the project

    # print(app_run(app_id=appID,project_id=projectID,inputs=inputs,instance_id=instanceID))
    # bl app run --id 59714d376c3b7e0029153f53 --input t1:65b030124ce5ac2907f81c48 --project 65b022f04ce5ac2907f7d4a1 --config '{"reorient" : true, "crop" : true}'


def test_app_run_invalid_instance():
    project_id = "65b022f04ce5ac2907f7d4a1"
    # freesurfer Deface
    app_id = "59714d376c3b7e0029153f53"
    # login and then run app in one of my project in brainlife
    inputs = {
        "t1: 65b030124ce5ac2907f81c48",
    }

    instance_id = "65ba8fb94028114d986cc6ce"

    app = get_app_by_id(app_id)

    # assert 1 == 0
    with pytest.raises(Exception) as exc_info:
        app_run(
            app_id=app_id,
            project_id=project_id,
            inputs=inputs,
            instance_id=instance_id,
            config={"reorient": True, "crop": True},
        )

    expected_error_message = (
        f"Instance {instance_id} is being removed and cannot be used"
    )
    assert expected_error_message in str(
        exc_info.value
    ), "Expected error message not found in exception."

    # bl app run
    #     --id 59714d376c3b7e0029153f53
    #     --input t1:65b030124ce5ac2907f81c48
    #     --project 65b022f04ce5ac2907f7d4a1
    #     --resource abcdsdfdsfsdfdsfsdfdsfsdfdsfsdfdsf
    #     --config '{"reorient" : true, "crop" : true}'
    # #     #add you, anibal and om to the project

    # print(app_run(app_id=appID,project_id=projectID,inputs=inputs,instance_id=instanceID))
    # bl app run --id 59714d376c3b7e0029153f53 --input t1:65b030124ce5ac2907f81c48 --project 65b022f04ce5ac2907f7d4a1 --config '{"reorient" : true, "crop" : true}'


def run_app_without_instance_id():
    assert 1 == 0

    project_id = "65b022f04ce5ac2907f7d4a1"
    # freesurfer Deface
    app_id = "59714d376c3b7e0029153f53"
    # login and then run app in one of my project in brainlife
    inputs = {
        "t1: 65b030124ce5ac2907f81c48",
    }

    app = get_app_by_id(app_id)

    print(
        app_run(
            app_id=app_id,
            project_id=project_id,
            inputs=inputs,
            config={"reorient": True, "crop": True},
        )
    )
