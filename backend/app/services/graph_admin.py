"""
graph_admin.py — Manage our service principal lifecycle in customer tenants.

After a customer consents, we:
  1. Assign Exchange Admin, SharePoint Admin, Teams Admin roles to our SP
  2. Run the Monkey365 audit
  3. Delete our SP from their tenant (removes all permissions and role assignments)
"""
import logging
import time

import httpx
import msal
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12

from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Well-known role definition IDs — identical across all Azure AD tenants
AUDIT_ROLES = {
    "Exchange Administrator": "29232cdf-9323-42fd-ade2-1d097af3e4de",
    "SharePoint Administrator": "f28a1f50-f6e7-4571-818b-6a12f2af6b6c",
    "Teams Administrator": "69091246-20e8-4a56-aa4d-066075b2a7a8",
}
# Reverse map for O(1) role name lookup during cleanup
_AUDIT_ROLES_BY_ID = {v: k for k, v in AUDIT_ROLES.items()}


def _get_token_for_tenant(tenant_id: str) -> str:
    """Acquire an app-only token scoped to the customer's tenant using our certificate."""
    with open(settings.CERT_PATH, "rb") as f:
        pfx_data = f.read()

    passphrase = settings.CERT_PASSWORD.encode() if settings.CERT_PASSWORD else None
    private_key, certificate, _ = pkcs12.load_key_and_certificates(pfx_data, passphrase)

    private_key_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=NoEncryption(),
    ).decode()

    thumbprint = certificate.fingerprint(hashes.SHA1()).hex().upper()  # noqa: S303

    app = msal.ConfidentialClientApplication(
        client_id=settings.AZURE_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential={"thumbprint": thumbprint, "private_key": private_key_pem},
    )

    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Unknown"))
        raise RuntimeError(f"Failed to acquire token for tenant {tenant_id}: {error}")

    return result["access_token"]


def _get_service_principal_id(token: str, retries: int = 8, delay: float = 10.0) -> str:
    """
    Find our app's service principal object ID in the customer's tenant.
    Retries with delay to handle Azure AD replication lag after consent.
    Also retries on 401 — permission grants need a few seconds to propagate
    after a freshly-consented or re-created service principal.
    """
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH_BASE}/servicePrincipals?$filter=appId eq '{settings.AZURE_CLIENT_ID}'&$select=id,appId,displayName"

    for attempt in range(1, retries + 1):
        resp = httpx.get(url, headers=headers, timeout=15)

        # 401 immediately after consent = permission grants not yet propagated
        if resp.status_code == 401:
            logger.warning(
                "401 Unauthorized querying servicePrincipals (attempt %d/%d) — "
                "permission grants still propagating, waiting %.0fs...",
                attempt, retries, delay,
            )
            if attempt < retries:
                time.sleep(delay)
            continue

        resp.raise_for_status()
        value = resp.json().get("value", [])
        if value:
            sp_id = value[0]["id"]
            logger.info("Found service principal %s in customer tenant", sp_id)
            return sp_id
        logger.warning(
            "Service principal not found yet (attempt %d/%d), waiting %.0fs...",
            attempt, retries, delay,
        )
        if attempt < retries:
            time.sleep(delay)

    raise RuntimeError(
        f"Service principal for app {settings.AZURE_CLIENT_ID} not found in customer tenant "
        f"after {retries} attempts. Consent may not have completed."
    )


def assign_audit_roles(tenant_id: str) -> str:
    """
    Assign Exchange Admin, SharePoint Admin, and Teams Admin roles to our
    service principal in the customer's tenant.

    Returns the SP object ID (needed for cleanup).

    After fresh admin consent, Azure AD propagates the permission grants
    asynchronously.  The token MUST be re-acquired on every retry because
    tokens are signed with the scopes that existed at acquisition time —
    reusing a stale token guarantees a 403 even after grants propagate.
    """
    logger.info("Assigning audit roles in tenant %s", tenant_id)
    token = _get_token_for_tenant(tenant_id)
    sp_id = _get_service_principal_id(token)

    role_retries = 12
    role_retry_delay = 20.0  # seconds per attempt; total window ≈ 4 min

    pending_roles = dict(AUDIT_ROLES)  # roles not yet successfully assigned

    for attempt in range(1, role_retries + 1):
        # Re-acquire a fresh token on every attempt so newly-propagated grants are included
        token = _get_token_for_tenant(tenant_id)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        still_pending = {}
        for role_name, role_def_id in pending_roles.items():
            payload = {
                "principalId": sp_id,
                "roleDefinitionId": role_def_id,
                "directoryScopeId": "/",
            }
            resp = httpx.post(
                f"{GRAPH_BASE}/roleManagement/directory/roleAssignments",
                json=payload,
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 201:
                logger.info("Assigned %s role to SP %s in tenant %s", role_name, sp_id, tenant_id)
            elif resp.status_code == 409:
                logger.info("%s role already assigned in tenant %s, skipping", role_name, tenant_id)
            elif resp.status_code == 403:
                # Grant not yet propagated — queue for next attempt with fresh token
                still_pending[role_name] = role_def_id
            else:
                logger.warning(
                    "Failed to assign %s role: %s %s", role_name, resp.status_code, resp.text[:200]
                )

        pending_roles = still_pending  # update before break check

        if not pending_roles:
            break  # all roles assigned

        logger.warning(
            "403 on %s (attempt %d/%d) — permission grants still propagating, "
            "re-acquiring token and waiting %.0fs...",
            list(pending_roles), attempt, role_retries, role_retry_delay,
        )
        if attempt < role_retries:
            time.sleep(role_retry_delay)

    if pending_roles:
        logger.error(
            "Could not assign roles %s to SP %s in tenant %s after %d attempts — "
            "Exchange/SharePoint/Teams findings may be incomplete.",
            list(pending_roles), sp_id, tenant_id, role_retries,
        )

    return sp_id


def _revoke_admin_roles(tenant_id: str, sp_object_id: str, token: str) -> None:
    """
    Fallback cleanup: remove the three elevated admin role assignments from our SP.
    Used when Application.ReadWrite.All is not consented and SP deletion fails with 403.
    Requires only RoleManagement.ReadWrite.Directory which is already granted.
    """
    headers = {"Authorization": f"Bearer {token}"}

    # Fetch all active role assignments for our SP
    resp = httpx.get(
        f"{GRAPH_BASE}/roleManagement/directory/roleAssignments"
        f"?$filter=principalId eq '{sp_object_id}'",
        headers=headers,
        timeout=15,
    )
    if resp.status_code != 200:
        logger.warning("Could not list role assignments for SP %s: %s", sp_object_id, resp.status_code)
        return

    assignments = resp.json().get("value", [])
    audit_role_ids = set(AUDIT_ROLES.values())
    removed = 0
    for assignment in assignments:
        if assignment.get("roleDefinitionId") in audit_role_ids:
            assignment_id = assignment["id"]
            del_resp = httpx.delete(
                f"{GRAPH_BASE}/roleManagement/directory/roleAssignments/{assignment_id}",
                headers=headers,
                timeout=15,
            )
            role_name = _AUDIT_ROLES_BY_ID.get(assignment.get("roleDefinitionId"), "unknown")
            if del_resp.status_code == 204:
                logger.info("Removed %s role assignment from SP %s in tenant %s", role_name, sp_object_id, tenant_id)
                removed += 1
            else:
                logger.warning("Failed to remove %s role: %s", role_name, del_resp.status_code)

    logger.info(
        "Fallback role revocation complete for SP %s in tenant %s: %d/%d roles removed",
        sp_object_id, tenant_id, removed, len(AUDIT_ROLES),
    )


def remove_service_principal(tenant_id: str, sp_object_id: str) -> None:
    """
    Remove our app's access from the customer's tenant after the audit.

    Primary path: DELETE the service principal entirely (requires Application.ReadWrite.All).
    Fallback path: if 403, remove only the elevated admin role assignments using
    RoleManagement.ReadWrite.Directory (always consented for role assignment to work).
    """
    logger.info("Removing service principal %s from tenant %s", sp_object_id, tenant_id)
    token = _get_token_for_tenant(tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    resp = httpx.delete(
        f"{GRAPH_BASE}/servicePrincipals/{sp_object_id}",
        headers=headers,
        timeout=15,
    )

    if resp.status_code == 204:
        logger.info(
            "Service principal %s fully removed from tenant %s — all permissions revoked",
            sp_object_id, tenant_id,
        )
    elif resp.status_code == 404:
        logger.info("Service principal %s already removed from tenant %s", sp_object_id, tenant_id)
    elif resp.status_code == 403:
        # Application.ReadWrite.All not consented — fall back to revoking admin roles only
        logger.warning(
            "SP deletion denied (403) for tenant %s — Application.ReadWrite.All not granted. "
            "Falling back to admin role revocation. Add Application.ReadWrite.All to your "
            "app registration so future customers get full cleanup.",
            tenant_id,
        )
        _revoke_admin_roles(tenant_id, sp_object_id, token)
    else:
        raise RuntimeError(
            f"Failed to delete SP {sp_object_id} from tenant {tenant_id}: "
            f"{resp.status_code} {resp.text[:200]}"
        )
