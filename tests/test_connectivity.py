import connectivity


class FakeSocket:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def make_fake_create_connection(captured=None, error=None):
    def fake_create_connection(address, timeout):
        if captured is not None:
            captured["address"] = address
            captured["timeout"] = timeout

        if error:
            raise error

        return FakeSocket()

    return fake_create_connection


def test_is_online_returns_true_on_successful_connection(monkeypatch):
    monkeypatch.setattr(
        connectivity.socket, "create_connection", make_fake_create_connection()
    )

    assert connectivity.is_online("https://www.centrecom.com.au") is True


def test_is_online_returns_false_on_oserror(monkeypatch):
    monkeypatch.setattr(
        connectivity.socket,
        "create_connection",
        make_fake_create_connection(error=OSError("connection refused")),
    )

    assert connectivity.is_online("https://www.centrecom.com.au") is False


def test_is_online_uses_port_443_for_https(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        connectivity.socket, "create_connection", make_fake_create_connection(captured)
    )

    connectivity.is_online("https://www.centrecom.com.au")

    assert captured["address"] == ("www.centrecom.com.au", 443)


def test_is_online_uses_port_80_for_http(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        connectivity.socket, "create_connection", make_fake_create_connection(captured)
    )

    connectivity.is_online("http://www.centrecom.com.au")

    assert captured["address"] == ("www.centrecom.com.au", 80)


def test_is_online_does_not_mistake_similar_scheme_for_https(monkeypatch):
    # Regression test: a URL that merely starts with the substring "https" but
    # has a different actual scheme must not be treated as https.
    captured = {}
    monkeypatch.setattr(
        connectivity.socket, "create_connection", make_fake_create_connection(captured)
    )

    connectivity.is_online("httpsomething://example.com")

    assert captured["address"] == ("example.com", 80)


def test_is_online_passes_timeout_through(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        connectivity.socket, "create_connection", make_fake_create_connection(captured)
    )

    connectivity.is_online("https://www.centrecom.com.au", timeout=7)

    assert captured["timeout"] == 7


def test_is_online_default_uses_base_url(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        connectivity.socket, "create_connection", make_fake_create_connection(captured)
    )

    connectivity.is_online()

    assert captured["address"] == ("www.centrecom.com.au", 443)
