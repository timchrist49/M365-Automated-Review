import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings
from app.constants import UUID_RE


def _validate_tenant_id(tenant_id: str) -> str:
    """Raise ValueError if tenant_id is not a valid UUID (prevents PS injection)."""
    if not UUID_RE.match(tenant_id):
        raise ValueError(f"Invalid tenant_id format: {tenant_id!r}")
    return tenant_id


def _validate_spo_url(spo_url: str) -> str:
    """Raise ValueError if spo_url is not a safe HTTPS SharePoint URL."""
    if not spo_url:
        return ""
    parsed = urlparse(spo_url)
    if parsed.scheme != "https" or not parsed.netloc.lower().endswith(".sharepoint.com"):
        raise ValueError(f"Invalid SharePoint URL: {spo_url!r}")
    # Ensure no embedded quotes or special characters
    safe = f"{parsed.scheme}://{parsed.netloc}"
    return safe

logger = logging.getLogger(__name__)


def _get_sharepoint_url(tenant_id: str) -> str:
    """
    Discover the customer's SharePoint root URL via Graph API.
    Returns e.g. 'https://contoso.sharepoint.com'.
    Falls back to empty string if discovery fails (scan will skip SharePoint).
    """
    try:
        import httpx
        from app.services.graph_admin import _get_token_for_tenant
        _validate_tenant_id(tenant_id)
        token = _get_token_for_tenant(tenant_id)
        resp = httpx.get(
            "https://graph.microsoft.com/v1.0/sites/root?$select=webUrl",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code == 200:
            web_url = resp.json().get("webUrl", "")
            if web_url:
                # Return just the root host, e.g. https://contoso.sharepoint.com
                parsed = urlparse(web_url)
                root_url = f"{parsed.scheme}://{parsed.netloc}"
                logger.info("Discovered SharePoint root URL for tenant %s: %s", tenant_id, root_url)
                return root_url
        logger.warning("Could not discover SharePoint URL for tenant %s: %s %s", tenant_id, resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("SharePoint URL discovery failed for tenant %s: %s", tenant_id, exc)
    return ""


def build_ps_script(
    job_id: str,
    tenant_id: str,
    cert_path: str,
    client_id: str,
    out_dir: str,
    spo_url: str = "",
) -> str:
    """Generate the PowerShell script for this audit job."""
    spo_line = f"    SpoSites        = @('{spo_url}')" if spo_url else ""
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
{spo_line}
}}

Invoke-Monkey365 @param
"""


# Monkey365 OCSF provider/resource names → our internal service keys
_PROVIDER_NAME_MAP = {
    "EntraID": "EntraId",
    "Entra ID": "EntraId",
    "EntraId": "EntraId",
    "ExchangeOnline": "ExchangeOnline",
    "SharePointOnline": "SharePointOnline",
    "MicrosoftTeams": "MicrosoftTeams",
    "Purview": "Purview",
    "AdminPortal": "AdminPortal",
    "Defender": "Defender",
    "Intune": "Intune",
}

# resources.group.name → our internal service keys
# Used as tertiary fallback when unmapped.resource and unmapped.provider are both absent
_GROUP_NAME_MAP = {
    "Entra Identity Governance": "EntraId",
    "Users": "EntraId",
    "Identity Protection": "EntraId",
    "Exchange Online": "ExchangeOnline",
    "SharePoint Online": "SharePointOnline",
    "Microsoft Teams": "MicrosoftTeams",
    "Defender": "Defender",
    "Intune": "Intune",
    "Microsoft 365 Admin": "AdminPortal",
    "Microsoft 365": "AdminPortal",
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
        _unmapped_resources: set = set()
        _unmapped_groups: set = set()

        for finding in data:
            unmapped = finding.get("unmapped") or {}
            # Priority 1: unmapped.resource — per-service discriminator set by most plugins
            raw_key = unmapped.get("resource") or unmapped.get("provider")
            if raw_key:
                if raw_key not in _PROVIDER_NAME_MAP:
                    _unmapped_resources.add(raw_key)
                provider = _PROVIDER_NAME_MAP.get(raw_key, raw_key)
            else:
                # Priority 2: resources.group.name — set by manual/cross-service checks
                # that don't populate unmapped.resource (e.g. Defender, Intune, email auth)
                group_name = ((finding.get("resources") or {}).get("group") or {}).get("name", "")
                if group_name and group_name not in _GROUP_NAME_MAP:
                    _unmapped_groups.add(group_name)
                provider = _GROUP_NAME_MAP.get(group_name, "Unknown")
            grouped.setdefault(provider, []).append(finding)

        # Warn about any new values from a Monkey365 upgrade so they can be mapped explicitly
        if _unmapped_resources:
            logger.warning(
                "Monkey365 output contains unmapped resource values — findings passed through "
                "using raw name. Add to _PROVIDER_NAME_MAP if categorisation is wrong: %s",
                sorted(_unmapped_resources),
            )
        if _unmapped_groups:
            logger.warning(
                "Monkey365 output contains unmapped resources.group.name values — findings "
                "placed in 'Unknown'. Add to _GROUP_NAME_MAP to categorise them: %s",
                sorted(_unmapped_groups),
            )

        return grouped

    # Legacy dict format — return as-is
    return data


def run_monkey365(job_id: str, tenant_id: str) -> str:
    """
    Execute Monkey365 via PowerShell 7 subprocess.
    Returns the path to the output directory.
    """
    _validate_tenant_id(tenant_id)  # Belt-and-suspenders: must be UUID before PS interpolation

    out_dir = f"/tmp/monkey365/{job_id}"
    os.makedirs(out_dir, exist_ok=True)

    raw_spo_url = _get_sharepoint_url(tenant_id)
    spo_url = _validate_spo_url(raw_spo_url)  # Ensure the discovered URL is safe before interpolation

    script_content = build_ps_script(
        job_id=job_id,
        tenant_id=tenant_id,
        cert_path=settings.CERT_PATH,
        client_id=settings.AZURE_CLIENT_ID,
        out_dir=out_dir,
        spo_url=spo_url,
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

        # Always log full output so permission errors / service failures are visible
        if result.stdout:
            for line in result.stdout.splitlines():
                logger.info("MONKEY365 | %s", line)
        if result.stderr:
            for line in result.stderr.splitlines():
                logger.warning("MONKEY365 ERR | %s", line)

        if result.returncode != 0:
            raise RuntimeError(
                f"Monkey365 failed with exit code {result.returncode}: {result.stderr[:500]}"
            )

        logger.info(f"Monkey365 complete for job {job_id}")
        return out_dir

    finally:
        os.unlink(script_path)  # Always clean up script file
