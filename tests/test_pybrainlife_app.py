from pybrainlife.api.app import app_run, get_app_by_id
from pybrainlife.cli.utils import set_auth, init_auth
import pytest

init_auth()


@pytest.mark.skip("Check for integration test environment")
def test_app_run_fail_incorrect_inputs():
    pass
    # project_id = "6566f998b094062da65337ef"
    # app_id = "5f3593e84615e04651bf9364"
    # inputs = {
    #     "t1": "656fc8a1d0ae0de207f3f315",
    #     "t2": "65c3f736745ef7acd7bcf08b",
    # }

    # with pytest.raises(KeyError) as exc_info:
    #     app_run(
    #         app_id=app_id,
    #         project_id=project_id,
    #         inputs=inputs,
    #         instance_id=None,
    #         config={"reorient": True, "crop": True},
    #     )

    # # Assert the message of KeyError if necessary
    # # This step is optional and depends on whether you want to check the error message.
    # assert "t2" in str(exc_info.value)


@pytest.mark.skip("Check for integration test environment")
def test_app_run_multiple_different_inputs():
    pass
    # project_id = "6566f998b094062da65337ef"
    # # C-PAC
    # app_id = "5f3593e84615e04651bf9364"
    # # login and then run app in one of my project in brainlife
    # inputs = {
    #     "t1": "656fc8a1d0ae0de207f3f315",
    #     "func": "65c3f7a7745ef7acd7bcfa87",
    # }

    # # assert 1 == 0
    # app_run(
    #     app_id=app_id,
    #     project_id=project_id,
    #     inputs=inputs,
    #     instance_id=None,
    #     config={"reorient": True, "crop": True},
    # )


@pytest.mark.skip("Check for integration test environment")
def test_app_run_without_instance():
    pass
    # project_id = "65b022f04ce5ac2907f7d4a1"
    # # freesurfer Deface
    # app_id = "59714d376c3b7e0029153f53"
    # # login and then run app in one of my project in brainlife
    # inputs = {
    #     "t1": "65b030124ce5ac2907f81c48",
    # }

    # instance_id = "65c3ec484028114d9819f8b6"

    # app = get_app_by_id(app_id)

    # # assert 1 == 0
    # app_run(
    #     app_id=app_id,
    #     project_id=project_id,
    #     inputs=inputs,
    #     instance_id=None,
    #     config={"reorient": True, "crop": True},
    # )


@pytest.mark.skip("Check for integration test environment")
def test_app_run_valid_instance():
    pass
    # project_id = "65b022f04ce5ac2907f7d4a1"
    # # freesurfer Deface
    # app_id = "59714d376c3b7e0029153f53"
    # # login and then run app in one of my project in brainlife
    # inputs = {
    #     "t1": "65b030124ce5ac2907f81c48",
    # }

    # instance_id = "65c3ec484028114d9819f8b6"

    # app = get_app_by_id(app_id)

    # # assert 1 == 0
    # app_run(
    #     app_id=app_id,
    #     project_id=project_id,
    #     inputs=inputs,
    #     instance_id=instance_id,
    #     config={"reorient": True, "crop": True},
    # )

    # bl app run
    #     --id 59714d376c3b7e0029153f53
    #     --input t1:65b030124ce5ac2907f81c48
    #     --project 65b022f04ce5ac2907f7d4a1
    #     --resource abcdsdfdsfsdfdsfsdfdsfsdfdsfsdfdsf
    #     --config '{"reorient" : true, "crop" : true}'
    # #     #add you, anibal and om to the project

    # print(app_run(app_id=appID,project_id=projectID,inputs=inputs,instance_id=instanceID))
    # bl app run --id 59714d376c3b7e0029153f53 --input t1:65b030124ce5ac2907f81c48 --project 65b022f04ce5ac2907f7d4a1 --config '{"reorient" : true, "crop" : true}'


@pytest.mark.skip("Check for integration test environment")
def test_app_run_invalid_instance():
    pass
    # project_id = "65b022f04ce5ac2907f7d4a1"
    # # freesurfer Deface
    # app_id = "59714d376c3b7e0029153f53"
    # # login and then run app in one of my project in brainlife
    # inputs = {
    #     "t1": "65b030124ce5ac2907f81c48",
    # }

    # instance_id = "65ba8fb94028114d986cc6ce"

    # app = get_app_by_id(app_id)

    # # assert 1 == 0
    # with pytest.raises(Exception) as exc_info:
    #     app_run(
    #         app_id=app_id,
    #         project_id=project_id,
    #         inputs=inputs,
    #         instance_id=instance_id,
    #         config={"reorient": True, "crop": True},
    #     )

    # expected_error_message = (
    #     f"Instance {instance_id} is being removed and cannot be used"
    # )
    # assert expected_error_message in str(
    #     exc_info.value
    # ), "Expected error message not found in exception."

    # bl app run
    #     --id 59714d376c3b7e0029153f53
    #     --input t1:65b030124ce5ac2907f81c48
    #     --project 65b022f04ce5ac2907f7d4a1
    #     --resource abcdsdfdsfsdfdsfsdfdsfsdfdsfsdfdsf
    #     --config '{"reorient" : true, "crop" : true}'
    # #     #add you, anibal and om to the project

    # print(app_run(app_id=appID,project_id=projectID,inputs=inputs,instance_id=instanceID))
    # bl app run --id 59714d376c3b7e0029153f53 --input t1:65b030124ce5ac2907f81c48 --project 65b022f04ce5ac2907f7d4a1 --config '{"reorient" : true, "crop" : true}'
