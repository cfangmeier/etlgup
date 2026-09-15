"""Configuration and settings persistence for etlgup."""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import List, Optional


CONFIG_FILE_NAME = "config.json"
DOTENV_FILE_NAME = ".env"


def _get_default_config_dir() -> Path:
    """Return platform config directory (~/.config/etlgup or local)."""
    home = Path.home()
    config_dir = home / ".config" / "etlgup"
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir
    except Exception:
        # Fallback to local directory
        return Path.cwd()


@dataclass
class AppConfig:
    location: str = "BU"
    user_created: str = field(default_factory=lambda: os.getenv("USER") or os.getenv("USERNAME") or "operator")
    api_token: str = ""
    prod: bool = False
    custom_domain: Optional[str] = None
    config_path: Optional[Path] = None

    def validate_for_upload(self, module: Optional[str] = None) -> List[str]:
        """Validate whether the configuration is ready for an upload."""
        errors: List[str] = []
        if not self.location or not self.location.strip():
            errors.append("Lab location is required (e.g. 'BU')")
        if not self.user_created or not self.user_created.strip():
            errors.append("Operator username (user_created) is required")
        if not self.api_token or not self.api_token.strip():
            errors.append("ETL API token is required. Please set it in Settings or .env file.")
        if module is not None and (not module or not str(module).strip()):
            errors.append("Module serial number is required")
        return errors

    def sync_to_env(self) -> None:
        """Export current token to os.environ so etlup Session can find it."""
        if self.api_token and self.api_token.strip():
            os.environ["ETL_API_TOKEN"] = self.api_token.strip()
            os.environ["API_TOKEN_ENV"] = self.api_token.strip()


def load_config(dotenv_path: Optional[Path | str] = None, config_path: Optional[Path | str] = None) -> AppConfig:
    """Load configuration from local config JSON and environment/.env."""
    cfg = AppConfig()

    # 1. Try to load from JSON config file
    target_config_file = Path(config_path) if config_path else (_get_default_config_dir() / CONFIG_FILE_NAME)
    cfg.config_path = target_config_file

    if target_config_file.is_file():
        try:
            with open(target_config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "location" in data:
                cfg.location = str(data["location"])
            if "user_created" in data:
                cfg.user_created = str(data["user_created"])
            if "api_token" in data and data["api_token"]:
                cfg.api_token = str(data["api_token"])
            if "prod" in data:
                cfg.prod = bool(data["prod"])
            if "custom_domain" in data:
                cfg.custom_domain = data["custom_domain"]
        except Exception:
            pass

    # 2. Try to load .env if exists
    target_dotenv = Path(dotenv_path) if dotenv_path else Path.cwd() / DOTENV_FILE_NAME
    if target_dotenv.is_file():
        try:
            with open(target_dotenv, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k in ("ETL_API_TOKEN", "API_TOKEN_ENV") and v:
                        # Prefer explicit token from .env if cfg didn't have one or .env is provided
                        cfg.api_token = v
                    elif k == "ETL_LOCATION" and v and not cfg.location:
                        cfg.location = v
                    elif k == "ETL_USER_CREATED" and v and not cfg.user_created:
                        cfg.user_created = v
                    elif k == "ETL_PROD":
                        cfg.prod = v.lower() in ("true", "1", "yes")
        except Exception:
            pass

    # 3. Environment variables override
    env_token = os.getenv("ETL_API_TOKEN") or os.getenv("API_TOKEN_ENV")
    if env_token:
        cfg.api_token = env_token

    if os.getenv("ETL_LOCATION"):
        cfg.location = os.environ["ETL_LOCATION"]

    if os.getenv("ETL_USER_CREATED"):
        cfg.user_created = os.environ["ETL_USER_CREATED"]

    if os.getenv("ETL_PROD"):
        cfg.prod = os.getenv("ETL_PROD", "").lower() in ("true", "1", "yes")

    cfg.sync_to_env()
    return cfg


def save_config(cfg: AppConfig, save_to_dotenv: bool = True, dotenv_path: Optional[Path | str] = None) -> None:
    """Save current configuration to local config file and optionally update .env."""
    if cfg.config_path:
        try:
            cfg.config_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "location": cfg.location,
                "user_created": cfg.user_created,
                "api_token": cfg.api_token,
                "prod": cfg.prod,
                "custom_domain": cfg.custom_domain,
            }
            with open(cfg.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    cfg.sync_to_env()

    if save_to_dotenv and cfg.api_token:
        target_dotenv = Path(dotenv_path) if dotenv_path else Path.cwd() / DOTENV_FILE_NAME
        lines: List[str] = []
        token_written = False
        if target_dotenv.is_file():
            try:
                with open(target_dotenv, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("ETL_API_TOKEN=") or line.startswith("API_TOKEN_ENV="):
                            if not token_written:
                                lines.append(f'ETL_API_TOKEN="{cfg.api_token}"\n')
                                token_written = True
                        else:
                            lines.append(line)
            except Exception:
                pass
        if not token_written:
            lines.append(f'ETL_API_TOKEN="{cfg.api_token}"\n')
        try:
            with open(target_dotenv, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception:
            pass
