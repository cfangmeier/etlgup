from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch
import requests

from etlgup.config import AppConfig, load_config, save_config
from etlgup.models import build_upload_batch
from etlgup.parser import discover_and_parse_directory
from etlgup.uploader import UploadError, UploadResult, UploadService

SAMPLE_DIR = Path("/home/caleb/Downloads/MP40229/2026-09-15-12-03-51_AFTER-BL-100V")


def test_config_save_and_load(tmp_path):
    cfg_file = tmp_path / "test_config.json"
    dotenv_file = tmp_path / "test.env"

    cfg = AppConfig(
        location="BU",
        user_created="testuser",
        api_token="my-token-123",
        prod=False,
        config_path=cfg_file,
    )
    save_config(cfg, save_to_dotenv=True, dotenv_path=dotenv_file)
    assert cfg_file.is_file()
    assert dotenv_file.is_file()

    loaded = load_config(dotenv_path=dotenv_file, config_path=cfg_file)
    assert loaded.location == "BU"
    assert loaded.user_created == "testuser"
    assert loaded.api_token == "my-token-123"
    assert loaded.prod is False


def test_config_validation():
    cfg = AppConfig(location="", user_created="", api_token="")
    errors = cfg.validate_for_upload(module="")
    assert len(errors) == 4

    cfg_valid = AppConfig(location="BU", user_created="user", api_token="tok")
    assert len(cfg_valid.validate_for_upload(module="40229")) == 0


def test_execute_dry_run():
    run_data = discover_and_parse_directory(SAMPLE_DIR)
    cfg = load_config()
    service = UploadService(cfg)
    batch = build_upload_batch(
        run_data=run_data,
        location=cfg.location,
        user_created=cfg.user_created,
    )
    result = service.execute_dry_run(batch)
    assert result.success is True
    assert result.is_dry_run is True
    assert result.count == 5
    assert "test_payload" in result.details
    assert len(result.details["test_payload"]) == 5


def test_execute_upload_validation_error():
    cfg = AppConfig(location="BU", user_created="user", api_token="")
    service = UploadService(cfg)
    run_data = discover_and_parse_directory(SAMPLE_DIR)
    batch = build_upload_batch(run_data, cfg.location, cfg.user_created)
    with pytest.raises(UploadError) as exc_info:
        service.execute_upload(batch, module="")
    assert "prerequisites" in str(exc_info.value)


@patch("etlup.upload.Session.upload")
def test_execute_upload_success(mock_upload):
    mock_upload.return_value = {"test_response": {"status": "ok"}}
    cfg = AppConfig(location="BU", user_created="user", api_token="test_token")
    service = UploadService(cfg)
    run_data = discover_and_parse_directory(SAMPLE_DIR)
    batch = build_upload_batch(run_data, cfg.location, cfg.user_created)
    res = service.execute_upload(batch, module="40229")
    assert res.success is True
    assert res.is_dry_run is False
    assert res.count == 5


@patch("etlup.upload.requests.post")
def test_execute_upload_http_error(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized token"
    mock_resp.raise_for_status.side_effect = requests.HTTPError(response=mock_resp)
    mock_post.return_value = mock_resp

    cfg = AppConfig(location="BU", user_created="user", api_token="bad_token")
    service = UploadService(cfg)
    run_data = discover_and_parse_directory(SAMPLE_DIR)
    batch = build_upload_batch(run_data, cfg.location, cfg.user_created)
    with pytest.raises(UploadError) as exc_info:
        service.execute_upload(batch, module="40229")
    assert exc_info.value.status_code == 401
