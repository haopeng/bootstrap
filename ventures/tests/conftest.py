import os

import pytest

os.environ["VENTURES_OFFLINE"] = "1"  # tests are deterministic: rules layer only


@pytest.fixture
def store(tmp_path):
    from ventures.core import Store

    return Store(str(tmp_path / "t.db"))
