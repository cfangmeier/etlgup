"""Upload service wrapping etlup.Session with dry-run and live upload capabilities."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import requests

from etlup.upload import Session
from etlgup.config import AppConfig
from etlgup.models import UploadBatch


class UploadError(Exception):
    """Custom exception raised during upload failures with structured context."""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details

    def __str__(self) -> str:
        if self.status_code:
            return f"[HTTP {self.status_code}] {self.message}"
        return self.message


@dataclass
class UploadResult:
    success: bool
    is_dry_run: bool
    count: int
    message: str
    details: Optional[Dict[str, Any]] = None


class UploadService:
    """Service to coordinate dry-run validation and live data uploads to CERN ETL database."""

    def __init__(self, config: AppConfig):
        self.config = config

    def get_api_domain(self, prod: Optional[bool] = None, domain: Optional[str] = None) -> str:
        """Resolve current target domain."""
        if domain is not None:
            return domain
        if self.config.custom_domain:
            return self.config.custom_domain
        is_prod = self.config.prod if prod is None else prod
        return "https://prod-etl.app.cern.ch/" if is_prod else "https://staging-etl.app.cern.ch/"

    def execute_dry_run(
        self,
        batch: UploadBatch,
        prod: Optional[bool] = None,
        domain: Optional[str] = None,
    ) -> UploadResult:
        """Run dry-run serialization without contacting remote server."""
        models = batch.all_models()
        if not models:
            raise ValueError("No models available in batch for upload.")

        target_prod = self.config.prod if prod is None else prod
        target_domain = domain if domain is not None else self.config.custom_domain

        with Session(prod=target_prod, domain=target_domain) as sesh:
            sesh.add_all(models)
            res = sesh.upload(dry_run=True)

        count = res.get("count", len(models))
        return UploadResult(
            success=True,
            is_dry_run=True,
            count=count,
            message=f"Dry run successful: {count} item(s) validated in payload.",
            details=res,
        )

    def execute_upload(
        self,
        batch: UploadBatch,
        prod: Optional[bool] = None,
        domain: Optional[str] = None,
        timeout: float = 30.0,
        module: Optional[str] = None,
    ) -> UploadResult:
        """Perform live upload of test records to ETL API."""
        models = batch.all_models()
        if not models:
            raise ValueError("No models available in batch for upload.")

        # Validate configuration
        validation_errors = self.config.validate_for_upload(module=module)
        if validation_errors:
            raise UploadError(
                message="Upload prerequisites not met:\n" + "\n".join(f"- {e}" for e in validation_errors),
                status_code=None,
                details={"validation_errors": validation_errors},
            )

        self.config.sync_to_env()
        target_prod = self.config.prod if prod is None else prod
        target_domain = domain if domain is not None else self.config.custom_domain

        try:
            with Session(prod=target_prod, domain=target_domain) as sesh:
                sesh.add_all(models)
                res = sesh.upload(dry_run=False, timeout=timeout)

            count = len(models)
            return UploadResult(
                success=True,
                is_dry_run=False,
                count=count,
                message=f"Successfully uploaded {count} item(s) to ETL database.",
                details=res,
            )

        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            text = exc.response.text if exc.response is not None else str(exc)
            msg = f"ETL Server returned error ({status}): {text}"
            raise UploadError(message=msg, status_code=status, details=text) from exc

        except requests.ConnectionError as exc:
            domain_used = self.get_api_domain(prod=target_prod, domain=target_domain)
            msg = f"Failed to connect to ETL API at {domain_used}. Please verify your network connection."
            raise UploadError(message=msg, status_code=None, details=str(exc)) from exc

        except requests.Timeout as exc:
            msg = f"Request timed out after {timeout} seconds while communicating with ETL API."
            raise UploadError(message=msg, status_code=None, details=str(exc)) from exc

        except Exception as exc:
            msg = f"Upload failed: {exc}"
            raise UploadError(message=msg, status_code=None, details=str(exc)) from exc
