from types import SimpleNamespace

import pytest

from config.settings import APP_VERSION, ConfigError, Settings


def env(**values):
    return SimpleNamespace(**values)


PROD_ORIGIN = "https://abinayagarment.dentcare-demo.workers.dev"


def test_defaults_apply_when_vars_missing():
    settings = Settings.from_env(env(ALLOWED_ORIGINS=PROD_ORIGIN))
    assert settings.environment == "production"
    assert settings.max_body_bytes == 32_768
    assert settings.max_message_chars == 1_000
    assert settings.max_history_messages == 10
    assert settings.session_ttl_seconds == 900
    assert settings.gemini_model == "gemini-3.5-flash-lite"
    assert settings.search_top_k == 4
    assert settings.version == APP_VERSION


def test_values_are_parsed_from_strings():
    settings = Settings.from_env(
        env(ENVIRONMENT="development", ALLOWED_ORIGINS="http://localhost:5173", SEARCH_TOP_K="6")
    )
    assert settings.environment == "development"
    assert settings.search_top_k == 6
    assert not settings.is_production


def test_origins_are_normalized_and_deduplicated():
    settings = Settings.from_env(
        env(ALLOWED_ORIGINS=f" {PROD_ORIGIN}/ , https://ABC.pages.dev,{PROD_ORIGIN}")
    )
    assert settings.allowed_origins == (PROD_ORIGIN, "https://abc.pages.dev")


@pytest.mark.parametrize(
    "origins",
    ["https://*.example.com", "ftp://example.com", "https://example.com/path", "not-a-url"],
)
def test_invalid_origins_are_rejected(origins):
    with pytest.raises(ConfigError):
        Settings.from_env(env(ENVIRONMENT="development", ALLOWED_ORIGINS=origins))


def test_production_requires_origins():
    with pytest.raises(ConfigError, match="must not be empty"):
        Settings.from_env(env())


def test_production_rejects_http_origins():
    with pytest.raises(ConfigError, match="https"):
        Settings.from_env(env(ALLOWED_ORIGINS="http://localhost:5173"))


def test_development_allows_http_and_empty_origins():
    assert Settings.from_env(env(ENVIRONMENT="development")).allowed_origins == ()
    assert Settings.from_env(
        env(ENVIRONMENT="development", ALLOWED_ORIGINS="http://localhost:5173")
    ).allowed_origins == ("http://localhost:5173",)


def test_unknown_environment_rejected():
    with pytest.raises(ConfigError, match="ENVIRONMENT"):
        Settings.from_env(env(ENVIRONMENT="staging", ALLOWED_ORIGINS=PROD_ORIGIN))


@pytest.mark.parametrize("value", ["abc", "1.5", "-1", "99999999"])
def test_bad_integers_rejected(value):
    with pytest.raises(ConfigError, match="MAX_MESSAGE_CHARS"):
        Settings.from_env(env(ALLOWED_ORIGINS=PROD_ORIGIN, MAX_MESSAGE_CHARS=value))


def test_blank_values_fall_back_to_defaults():
    settings = Settings.from_env(
        env(ALLOWED_ORIGINS=PROD_ORIGIN, GEMINI_MODEL="  ", SEARCH_TOP_K="")
    )
    assert settings.gemini_model == "gemini-3.5-flash-lite"
    assert settings.search_top_k == 4
