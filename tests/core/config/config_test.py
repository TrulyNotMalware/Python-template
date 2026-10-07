from pathlib import Path

import pytest
import uvicorn
from click.testing import CliRunner
from pydantic import ValidationError
from sqlalchemy.engine import make_url

import main
from app.core.config.config import DevConfig, LocalConfig, ProdConfig, get_config
from app.core.exception.configuration_exception import ConfigurationException

pytestmark = pytest.mark.usefixtures("isolated_config")

PASSWORD = "p@ss/w#rd"
ALL_INTERFACES = "0.0.0.0"  # noqa: S104  expected value, nothing binds here
SERVER_DATABASE_FIELDS = {
    "DATABASE_USER",
    "DATABASE_PASSWORD",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
}


def set_database_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_USER", "app")
    monkeypatch.setenv("DATABASE_PASSWORD", PASSWORD)
    monkeypatch.setenv("DATABASE_HOST", "db.internal")
    monkeypatch.setenv("DATABASE_PORT", "3306")
    monkeypatch.setenv("DATABASE_NAME", "service")


def test_without_env_the_local_config_is_used() -> None:
    config = get_config()

    assert isinstance(config, LocalConfig)
    assert config.DATABASE_URL == "sqlite+aiosqlite://"
    assert config.DATABASE_READ_URL is None
    assert config.MONGO_URL is None


def test_get_config_is_cached() -> None:
    assert get_config() is get_config()


def test_prod_assembles_the_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "prod")
    set_database_parts(monkeypatch)

    config = get_config()

    assert isinstance(config, ProdConfig)
    assert config.DEBUG is False
    assert config.WORKERS == 4
    assert config.APP_HOST == ALL_INTERFACES
    url = make_url(config.DATABASE_URL)
    assert url.drivername == "mariadb+aiomysql"
    assert url.username == "app"
    assert url.password == PASSWORD
    assert url.host == "db.internal"
    assert url.port == 3306
    assert url.database == "service"


def test_prod_settings_repr_hides_the_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "prod")
    set_database_parts(monkeypatch)

    config = get_config()

    assert PASSWORD not in repr(config)
    assert "p%40ss" not in repr(config)


@pytest.mark.parametrize("env", ["dev", "prod"])
def test_server_envs_require_database_parts(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("ENV", env)

    with pytest.raises(ValidationError) as excinfo:
        get_config()

    missing = {error["loc"][0] for error in excinfo.value.errors()}
    assert missing == SERVER_DATABASE_FIELDS


def test_blank_values_in_the_env_file_count_as_unset() -> None:
    # isolated_config made the test's tmp_path the working directory.
    Path(".env.local").write_text(
        "DEBUG=\nDATABASE_READ_URL=\nMONGO_URL=\nCORS_ALLOW_ORIGINS=\n",
        encoding="utf-8",
    )

    config = get_config()

    assert isinstance(config, LocalConfig)
    assert config.DEBUG is True
    assert config.DATABASE_READ_URL is None
    assert config.MONGO_URL is None
    assert config.CORS_ALLOW_ORIGINS == []


def test_blank_required_value_is_reported_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "prod")
    set_database_parts(monkeypatch)
    monkeypatch.setenv("DATABASE_PASSWORD", "")

    with pytest.raises(ValidationError) as excinfo:
        get_config()

    assert [error["loc"] for error in excinfo.value.errors()] == [
        ("DATABASE_PASSWORD",)
    ]


def test_env_in_an_env_file_does_not_change_the_environment() -> None:
    # Only the process environment selects the settings class.
    Path(".env.local").write_text("ENV=prod\n", encoding="utf-8")

    config = get_config()

    assert isinstance(config, LocalConfig)
    assert config.ENV == "local"


def test_dev_uses_its_own_settings_class(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    set_database_parts(monkeypatch)

    config = get_config()

    assert isinstance(config, DevConfig)
    assert config.APP_HOST == "127.0.0.1"
    assert config.WORKERS == 1


def test_unknown_env_raises_configuration_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "qa")

    with pytest.raises(ConfigurationException) as excinfo:
        get_config()

    assert excinfo.value.code == 404
    assert excinfo.value.argument_errors[0].field_name == "env"
    assert excinfo.value.argument_errors[0].value == "qa"


@pytest.fixture
def uvicorn_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, dict[str, object]]]:
    """Replace uvicorn.run so main() returns, and record its arguments."""
    runs: list[tuple[str, dict[str, object]]] = []

    def fake_run(app: str, **kwargs: object) -> None:
        runs.append((app, kwargs))

    monkeypatch.setattr(uvicorn, "run", fake_run)
    return runs


def test_main_reads_settings_after_setting_env(
    monkeypatch: pytest.MonkeyPatch,
    uvicorn_runs: list[tuple[str, dict[str, object]]],
) -> None:
    set_database_parts(monkeypatch)

    result = CliRunner().invoke(main.main, ["--env", "prod"])

    assert result.exit_code == 0, result.output
    assert uvicorn_runs == [
        (
            "app.server:init_app",
            {
                "factory": True,
                "host": ALL_INTERFACES,
                "port": 8080,
                "reload": False,
                "workers": 4,
            },
        )
    ]
    config = get_config()
    assert isinstance(config, ProdConfig)
    assert config.DEBUG is False


@pytest.mark.usefixtures("uvicorn_runs")
def test_main_without_debug_flag_keeps_the_config_default() -> None:
    result = CliRunner().invoke(main.main, ["--env", "local"])

    assert result.exit_code == 0, result.output
    config = get_config()
    assert isinstance(config, LocalConfig)
    assert config.DEBUG is True


@pytest.mark.usefixtures("uvicorn_runs")
def test_main_without_debug_flag_keeps_the_env_file_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_database_parts(monkeypatch)
    Path(".env.prod").write_text("DEBUG=true\n", encoding="utf-8")

    result = CliRunner().invoke(main.main, ["--env", "prod"])

    assert result.exit_code == 0, result.output
    config = get_config()
    assert isinstance(config, ProdConfig)
    assert config.DEBUG is True


def test_main_debug_flag_turns_debug_on(
    monkeypatch: pytest.MonkeyPatch,
    uvicorn_runs: list[tuple[str, dict[str, object]]],
) -> None:
    set_database_parts(monkeypatch)

    result = CliRunner().invoke(main.main, ["--env", "prod", "--debug"])

    assert result.exit_code == 0, result.output
    config = get_config()
    assert isinstance(config, ProdConfig)
    assert config.DEBUG is True
