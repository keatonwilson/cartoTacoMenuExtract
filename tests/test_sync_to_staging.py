from src.sync_to_staging import diff


def test_diff_splits_new_changed_and_staging_only():
    prod = [{"est_id": 1, "name": "a"}, {"est_id": 2, "name": "b2"}, {"est_id": 4, "name": "d"}]
    staging = [{"est_id": 1, "name": "a"}, {"est_id": 2, "name": "b"}, {"est_id": 3, "name": "c"}]
    new, changed, extra = diff(prod, staging, "est_id")
    assert [r["est_id"] for r in new] == [4]
    assert [r["est_id"] for r in changed] == [2]
    assert extra == [3]
