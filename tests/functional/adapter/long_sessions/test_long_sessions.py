import pytest
import os
from unittest import mock
from dbt.tests import util
from tests.functional.adapter.long_sessions import fixtures

with mock.patch.dict(os.environ, {"DBT_DATABRICKS_LONG_SESSIONS": "true"}):
    import dbt.adapters.databricks.connections  # noqa


class TestLongSessionsBase:
    args_formatter = ""

    @pytest.fixture(scope="class")
    def seeds(self):
        return {
            "source.csv": fixtures.source,
        }

    @pytest.fixture(scope="class")
    def models(self):
        m = {}
        for i in range(5):
            m[f"target{i}.sql"] = fixtures.target

        return m

    def test_long_sessions(self, project):
        _, log = util.run_dbt_and_capture(["--debug", "seed"])
        open_count = log.count("Sending request: OpenSession") / 2
        assert open_count == 2

        _, log = util.run_dbt_and_capture(["--debug", "run"])
        open_count = log.count("Sending request: OpenSession") / 2
        assert open_count == 2


class TestLongSessionsMultipleThreads(TestLongSessionsBase):
    def test_long_sessions(self, project):
        util.run_dbt_and_capture(["seed"])

        for n_threads in [1, 2, 3]:
            _, log = util.run_dbt_and_capture(["--debug", "run", "--threads", f"{n_threads}"])
            open_count = log.count("Sending request: OpenSession") / 2
            assert open_count == (n_threads + 1)


class TestLongSessionsMultipleCompute:
    args_formatter = ""

    @pytest.fixture(scope="class")
    def seeds(self):
        return {
            "source.csv": fixtures.source,
        }

    @pytest.fixture(scope="class")
    def models(self):
        m = {}
        for i in range(2):
            m[f"target{i}.sql"] = fixtures.target

        m["target_alt.sql"] = fixtures.target2

        return m

    @pytest.fixture(scope="class")
    def profiles_config_update(self, dbt_profile_target):
        outputs = {"default": dbt_profile_target}
        outputs["default"]["compute"] = {
            "alternate_warehouse": {"http_path": dbt_profile_target["http_path"]},
        }
        return {"test": {"outputs": outputs, "target": "default"}}

    def test_long_sessions(self, project):
        util.run_dbt_and_capture(["--debug", "seed"])

        _, log = util.run_dbt_and_capture(["--debug", "run"])
        open_count = log.count("Sending request: OpenSession") / 2
        assert open_count == 3
