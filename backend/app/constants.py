"""
Shared constants used across multiple modules.
Single source of truth — import from here, never redefine locally.
"""

# Human-readable display names for each Monkey365 service key
SERVICE_DISPLAY_NAMES: dict[str, str] = {
    "EntraId": "Microsoft Entra ID",
    "ExchangeOnline": "Exchange Online",
    "SharePointOnline": "SharePoint Online",
    "MicrosoftTeams": "Microsoft Teams",
    "Purview": "Microsoft Purview",
    "Defender": "Microsoft Defender",
    "Intune": "Microsoft Intune",
    "AdminPortal": "M365 Admin Portal",
    "Microsoft365": "Microsoft 365",
    "Unknown": "General Controls",
}

# Minutes a PENDING job is kept before expiring (consent window)
PENDING_JOB_EXPIRY_MINUTES: int = 30
