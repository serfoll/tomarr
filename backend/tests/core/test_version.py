from tomarr.core.version import APP_VERSION, USER_AGENT


def test_user_agent_names_tomarr_its_version_and_repository() -> None:
    assert f"Tomarr/{APP_VERSION} (+https://github.com/serfoll/tomarr)" == USER_AGENT
