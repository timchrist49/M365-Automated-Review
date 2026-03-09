import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI
from app.config import settings
from app.constants import SERVICE_DISPLAY_NAMES

logger = logging.getLogger(__name__)

client = OpenAI(api_key=settings.OPENAI_API_KEY)

KNOWN_SERVICES = [
    "EntraId", "ExchangeOnline", "SharePointOnline",
    "MicrosoftTeams", "Purview", "Defender", "Intune", "AdminPortal",
]

CHUNK_SYSTEM_PROMPT = """You are a senior Microsoft 365 security analyst writing a section of a professional client security assessment report.

STRICT RULES — follow every one without exception:
1. NEVER include internal technical identifiers, bracket codes like [aad_xxx], reference IDs like entraid_1173, or any raw field names from the data. Use only the human-readable "title" field as the check name.
2. NEVER mention any third-party scanning tool. This assessment is branded as an "AI Automated Microsoft 365 Security Assessment".
3. Write for both a technical reader (IT admin) and an executive audience. Business risk explanations must be in plain English.
4. Do NOT truncate or omit any finding. Include every single check in the data.
5. Do NOT use emoji characters anywhere in your output. Use plain text only.

OUTPUT FORMAT — produce exactly this structure in Markdown:

### Summary
2-3 sentences describing the overall security posture for this service.

### Failed Controls

For each failing check, one block:

#### [Human-readable title of the check]
| Field | Detail |
|---|---|
| **Severity** | Critical / High / Medium / Low |
| **Status** | FAILED |
| **Current State** | What was found in the environment |
| **Expected State** | What it should be |
| **Business Risk** | Plain-English explanation of what could go wrong |
| **Remediation** | Step-by-step fix (numbered list if multiple steps) |

### Manual Review Required

For each manual check:

#### [Human-readable title]
| Field | Detail |
|---|---|
| **Severity** | [level] |
| **Status** | MANUAL REVIEW |
| **Why Manual** | Why this cannot be automatically assessed |
| **What to Check** | Specific steps the administrator should verify |

### Controls Implemented

A clean table of all passing controls:

| Control | Severity | Notes |
|---|---|---|
| [title] | Low/Medium/High | Brief confirmation of what is correctly configured |

### Quick Wins
Top 3 highest-impact, lowest-effort remediations for this service (can be done in under 1 hour)."""


SYNTHESIS_SYSTEM_PROMPT = """You are a senior Microsoft 365 security analyst writing the executive summary of a client security assessment report.

STRICT RULES:
1. NEVER mention any third-party tool. This is an "AI Automated Microsoft 365 Security Assessment".
2. NEVER include internal check codes or bracket identifiers.
3. The executive summary must be readable by a non-technical CEO or Board member.
4. Do NOT use emoji characters anywhere. Use plain text only.

OUTPUT FORMAT — produce exactly this structure in Markdown:

## Executive Summary

3-5 sentences describing the overall M365 security posture in plain English. Mention the most critical risks and the general compliance posture.

## Overall Risk Rating

**Risk Level: [Critical / High / Medium / Low]**

[2 sentences justifying the rating, referencing the most significant findings.]

## Risk Dashboard

Use ONLY the services listed in the ACTUAL SCAN STATS provided in the user message. Do NOT add services that are not in the stats. Fill this table using those exact numbers:

| Service Area | Risk Level | Failed | Manual Review | Passing |
|---|---|---|---|---|
| [one row per scanned service — use stats provided] | Critical/High/Medium/Low | N | N | N |

## Prioritized Remediation Roadmap

### Immediate - This Week (Quick Wins)
Top 5 highest-impact, lowest-effort fixes across all services. One sentence each.

### 30-Day Plan
3-5 medium-complexity remediations that require planned change windows.

### 60-Day Plan
Structural or policy-level improvements.

### 90-Day Plan
Strategic or architectural changes (e.g. Zero Trust, PIM rollout).

## Compliance Posture

Brief paragraph on CIS Microsoft 365 Foundations Benchmark alignment and key gaps."""


def _extract_title(finding: dict) -> str:
    """Extract the human-readable title from a finding, with fallbacks."""
    # Primary: findingInfo.title (Monkey365 OCSF format)
    fi = finding.get("findingInfo") or {}
    title = (fi.get("title") or "").strip()
    if title:
        return title
    # Fallback 1: statusDetail often contains the check description
    detail = (finding.get("statusDetail") or "").strip()
    if detail:
        return detail[:100]
    # Fallback 2: first sentence of findingInfo.description
    desc = (fi.get("description") or "").strip()
    if desc:
        return desc.split(".")[0][:100]
    return "Security Check"


def _clean_findings_for_prompt(findings: list) -> list:
    """Extract human-readable fields from OCSF findings, stripping all internal IDs."""
    cleaned = []
    for f in findings:
        fi = f.get("findingInfo") or {}
        remediation = f.get("remediation") or {}
        cleaned.append({
            "title": _extract_title(f),
            "status": f.get("statusCode", ""),
            "severity": f.get("severity", ""),
            "description": (fi.get("description") or "").strip(),
            "remediation": (remediation.get("description") or "").strip(),
            "references": (remediation.get("references") or [])[:2],
        })
    return cleaned


def _deduplicate_findings(grouped_data: dict) -> dict:
    """Remove duplicate findings (same title + statusCode) within each service."""
    result = {}
    for service, findings in grouped_data.items():
        if not isinstance(findings, list):
            result[service] = findings
            continue
        seen = set()
        deduped = []
        for f in findings:
            key = (_extract_title(f), f.get("statusCode", ""))
            if key not in seen:
                seen.add(key)
                deduped.append(f)
        if len(deduped) < len(findings):
            logger.warning(
                "Deduplicated %s: %d → %d findings (removed %d duplicates)",
                service, len(findings), len(deduped), len(findings) - len(deduped),
            )
        result[service] = deduped
    return result


def chunk_findings_by_service(raw_data: dict) -> dict:
    chunks = {}
    for service in KNOWN_SERVICES:
        if service in raw_data:
            chunks[service] = raw_data[service]
    for key, value in raw_data.items():
        if key not in chunks and isinstance(value, (dict, list)):
            chunks[key] = value
    return chunks


def compute_stats(grouped_data: dict) -> dict:
    """Compute counts and control details per service from raw OCSF data."""
    by_service = {}
    total_fail = total_manual = total_pass = 0
    passing_controls = []
    manual_controls = []

    for service, findings in grouped_data.items():
        if not isinstance(findings, list):
            continue
        display = SERVICE_DISPLAY_NAMES.get(service, service)
        fail = manual = passing = 0
        for f in findings:
            status = f.get("statusCode")
            title = _extract_title(f)
            fi = f.get("findingInfo") or {}
            desc = (fi.get("description") or "").strip()
            severity = f.get("severity", "")
            if status == "fail":
                fail += 1
            elif status == "manual":
                manual += 1
                manual_controls.append({
                    "service": display,
                    "title": title,
                    "description": desc if desc else "Manual verification required.",
                    "severity": severity,
                })
            elif status == "pass":
                passing += 1
                passing_controls.append({
                    "service": display,
                    "title": title,
                    "description": desc[:220] if desc else "Control correctly configured.",
                })
        by_service[service] = {"fail": fail, "manual": manual, "pass": passing}
        total_fail += fail
        total_manual += manual
        total_pass += passing

    return {
        "total": {"fail": total_fail, "manual": total_manual, "pass": total_pass},
        "by_service": by_service,
        "passing_controls": passing_controls,
        "manual_controls": manual_controls,
    }


def build_chunk_prompt(service_name: str, service_data) -> str:
    display_name = SERVICE_DISPLAY_NAMES.get(service_name, service_name)
    if isinstance(service_data, list):
        fail_count = sum(1 for f in service_data if f.get("statusCode") == "fail")
        pass_count = sum(1 for f in service_data if f.get("statusCode") == "pass")
        manual_count = sum(1 for f in service_data if f.get("statusCode") == "manual")
        cleaned = _clean_findings_for_prompt(service_data)
        data_json = json.dumps(cleaned, indent=2)
        return (
            f"Analyze the following {display_name} security findings.\n"
            f"Total: {len(service_data)} checks — {fail_count} failed, "
            f"{pass_count} passing, {manual_count} manual review.\n\n"
            f"Findings data:\n```json\n{data_json}\n```"
        )
    data_json = json.dumps(service_data, indent=2)
    return (
        f"Analyze the following {display_name} security findings.\n\n"
        f"Data:\n```json\n{data_json}\n```"
    )


def _call_openai(system_prompt: str, user_content: str, max_tokens: int = 32000) -> str:
    response = client.chat.completions.create(
        model="gpt-5-nano",
        reasoning_effort="high",
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content


def analyze_findings(out_dir: str) -> dict:
    """
    Parse audit JSON, chunk by service, analyze each with OpenAI,
    synthesize into executive summary, and attach raw stats for chart generation.
    Returns dict: {service: markdown, "synthesis": markdown, "_stats": stats_dict}
    """
    from app.services.monkey365 import parse_monkey365_output
    raw_data = parse_monkey365_output(out_dir)
    raw_data = _deduplicate_findings(raw_data)
    chunks = chunk_findings_by_service(raw_data)
    stats = compute_stats(raw_data)

    # Analyze all service chunks in parallel — reduces wall-clock time from ~6× serial to ~1× parallel
    analyses = {}
    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        future_to_service = {
            executor.submit(
                _call_openai,
                CHUNK_SYSTEM_PROMPT,
                build_chunk_prompt(service_name, service_data),
                32000,
            ): service_name
            for service_name, service_data in chunks.items()
        }
        for future in as_completed(future_to_service):
            service_name = future_to_service[future]
            try:
                analyses[service_name] = future.result()
                logger.info("Analyzed %s findings", service_name)
            except Exception as exc:
                logger.error("OpenAI analysis failed for %s: %s", service_name, exc)
                analyses[service_name] = f"*Analysis unavailable for this service: {exc}*"

    logger.info("Running synthesis analysis...")
    all_analyses = "\n\n---\n\n".join(
        f"# {SERVICE_DISPLAY_NAMES.get(svc, svc)}\n\n{text}"
        for svc, text in analyses.items()
    )
    # Build an actual stats table to ground the Risk Dashboard — prevents hallucination
    stats_rows = "\n".join(
        f"| {SERVICE_DISPLAY_NAMES.get(svc, svc)} | {counts['fail']} | {counts['manual']} | {counts['pass']} |"
        for svc, counts in stats["by_service"].items()
    )
    stats_table = (
        "ACTUAL SCAN STATS (use these exact numbers in the Risk Dashboard — do not invent data for unlisted services):\n\n"
        "| Service Area | Failed | Manual Review | Passing |\n"
        "|---|---|---|---|\n"
        f"{stats_rows}\n"
    )
    analyses["synthesis"] = _call_openai(
        SYNTHESIS_SYSTEM_PROMPT,
        f"{stats_table}\n\nHere are all per-service analysis sections:\n\n{all_analyses}",
        max_tokens=64000,
    )

    analyses["_stats"] = stats
    return analyses
