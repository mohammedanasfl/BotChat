import pytest

from core.errors import ApiError, ErrorCode, error_result, status_for
from routes import ROUTES, normalize_path, resolve
from routes.health import health


def test_every_error_code_has_a_status():
    for code in ErrorCode:
        assert 400 <= status_for(code) <= 599


def test_error_envelope_shape():
    result = error_result(ApiError(ErrorCode.SESSION_EXPIRED), "r_abc")
    assert result.status == 401
    assert result.body == {
        "error": {"code": "session_expired", "message": "Your session has expired."},
        "request_id": "r_abc",
    }


def test_error_custom_message_and_headers():
    error = ApiError(ErrorCode.RATE_LIMITED, "Slow down", headers={"retry-after": "30"})
    result = error_result(error, "r_x")
    assert result.status == 429
    assert result.body["error"]["message"] == "Slow down"
    assert result.headers == {"retry-after": "30"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("/api/health", "/api/health"), ("/api/health/", "/api/health"), ("", "/"), ("/", "/")],
)
def test_normalize_path(raw, expected):
    assert normalize_path(raw) == expected


def test_resolve_known_route():
    assert resolve("GET", "/api/health") is health
    assert resolve("get", "/api/health/") is health


def test_resolve_unknown_path_is_404():
    with pytest.raises(ApiError) as exc:
        resolve("GET", "/api/nope")
    assert exc.value.code is ErrorCode.NOT_FOUND


def test_resolve_wrong_method_is_405_with_allow_header():
    with pytest.raises(ApiError) as exc:
        resolve("POST", "/api/health")
    assert exc.value.code is ErrorCode.METHOD_NOT_ALLOWED
    assert exc.value.headers == {"allow": "GET"}


def test_all_routes_live_under_api_prefix():
    assert all(path.startswith("/api/") for path in ROUTES)
