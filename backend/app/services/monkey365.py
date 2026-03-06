import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def build_ps_script(
    job_id: str,
    tenant_id: str,
    cert_path: str,
    client_id: str,
    out_dir: str,
) -> str:
    """Generate the PowerShell script for this audit job."""
    return f"""
Import-Module monkey365 -Force

$certPath = "{cert_path}"
$certPass = ($env:CERT_PASSWORD | ConvertTo-SecureString -AsPlainText -Force)

$param = @{{
    ClientId         = "{client_id}"
    Certificate      = $certPath
    CertFilePassword = $certPass
    TenantID         = "{tenant_id}"
    Instance         = 'Microsoft365'
    Collect          = @('ExchangeOnline', 'MicrosoftTeams', 'Purview', 'SharePointOnline', 'AdminPortal')
    IncludeEntraID   = $true
    ExportTo         = @('JSON')
    OutDir           = "{out_dir}"
}}

Invoke-Monkey365 @param
"""


# Monkey365 OCSF provider names → our internal service keys
_PROVIDER_NAME_MAP = {
    "EntraID": "EntraId",
    "Entra ID": "EntraId",
    "EntraId": "EntraId",
    "ExchangeOnline": "ExchangeOnline",
    "SharePointOnline": "SharePointOnline",
    "MicrosoftTeams": "MicrosoftTeams",
    "Purview": "Purview",
    "AdminPortal": "AdminPortal",
}


def parse_monkey365_output(out_dir: str) -> dict:
    """Find and parse the JSON output file from Monkey365.

    Monkey365 v0.9+ outputs OCSF-format JSON as a flat list of findings
    nested under {out_dir}/{uuid}/json/*.json.  Older versions wrote a
    dict keyed by service area directly in out_dir.  Both formats are
    handled: lists are grouped by unmapped.provider; dicts are returned
    as-is.
    """
    out_path = Path(out_dir)
    # Recursive glob covers both flat (*.json) and nested ({uuid}/json/*.json)
    json_files = list(out_path.glob("**/*.json"))

    if not json_files:
        raise FileNotFoundError(f"No JSON output found in {out_dir}")

    with open(json_files[0], "r", encoding="utf-8") as f:
        data = json.load(f)

    # OCSF list format (Monkey365 v0.9+)
    if isinstance(data, list):
        grouped: dict = {}
        for finding in data:
            raw_provider = finding.get("unmapped", {}).get("provider") or "Unknown"
            provider = _PROVIDER_NAME_MAP.get(raw_provider, raw_provider)
            grouped.setdefault(provider, []).append(finding)
        return grouped

    # Legacy dict format — return as-is
    return data


def run_monkey365(job_id: str, tenant_id: str) -> str:
    """
    Execute Monkey365 via PowerShell 7 subprocess.
    Returns the path to the output directory.
    """
    out_dir = f"/tmp/monkey365/{job_id}"
    os.makedirs(out_dir, exist_ok=True)

    script_content = build_ps_script(
        job_id=job_id,
        tenant_id=tenant_id,
        cert_path=settings.CERT_PATH,
        client_id=settings.AZURE_CLIENT_ID,
        out_dir=out_dir,
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ps1", delete=False, prefix=f"audit_{job_id}_"
    ) as script_file:
        script_file.write(script_content)
        script_path = script_file.name

    try:
        env = os.environ.copy()
        env["CERT_PASSWORD"] = settings.CERT_PASSWORD
        env["TARGET_TENANT_ID"] = tenant_id
        env["JOB_ID"] = job_id

        logger.info(f"Running Monkey365 for job {job_id}, tenant {tenant_id}")

        result = subprocess.run(
            ["pwsh", "-NonInteractive", "-NoProfile", "-File", script_path],
            env=env,
            capture_output=True,
            text=True,
            timeout=2400,  # 40 min
        )

        if result.returncode != 0:
            logger.error(f"Monkey365 stderr: {result.stderr}")
            raise RuntimeError(
                f"Monkey365 failed with exit code {result.returncode}: {result.stderr[:500]}"
            )

        logger.info(f"Monkey365 complete for job {job_id}")
        return out_dir

    finally:
        os.unlink(script_path)  # Always clean up script file
