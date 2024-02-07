from pybrainlife.api.app import app_run, get_app_by_id
from pybrainlife.cli.utils import set_auth, init_auth

init_auth()


def test_app_run():
    projectID = "65b022f04ce5ac2907f7d4a1"
    # freesurfer Deface
    appID = "59714d376c3b7e0029153f53"
    # login and then run app in one of my project in brainlife
    inputs = {
        "t1: 65b030124ce5ac2907f81c48",
    }

    instanceID = "65ba8fb94028114d986cc6ce"

    app = get_app_by_id(appID)

    # assert 1 == 0

    print(
        app_run(
            app_id=appID,
            project_id=projectID,
            inputs=inputs,
            instance_id=instanceID,
            config={"reorient": True, "crop": True},
        )
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
