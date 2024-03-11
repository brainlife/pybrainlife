from pybrainlife.api.datalad import dl_dataset_query

from pybrainlife.cli.utils import set_auth, init_auth

init_auth()

def test_dl_dataset_query():
    # pass
    # assert 1 == 0
    res = dl_dataset_query()
    assert res is not None
    assert len(res) > 0
    # assert 1 == 0
    # pass