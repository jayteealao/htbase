import pytest
from pydantic import ValidationError

from main import SaveRequest


def test_save_request_requires_id():
    with pytest.raises(ValidationError):
        SaveRequest.model_validate({"url": "https://example.com"})


def test_save_request_accepts_user_id_alias():
    m = SaveRequest.model_validate({"url": "https://example.com", "user_id": "abc"})
    assert m.id == "abc"


def test_save_request_url_validation():
    with pytest.raises(ValidationError):
        SaveRequest.model_validate({"url": "notaurl", "id": "x"})

