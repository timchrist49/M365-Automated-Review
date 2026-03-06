import json
import logging
from typing import Any

from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

client = OpenAI(api_key=settings.OPENAI_API_KEY)

KNOWN_SERVICES = [
    "EntraId", "ExchangeOnline", "SharePointOnline",
    "MicrosoftTeams", "Purview", "AdminPortal",
]

SERVICE_DISPLAY_NAMES = {
    "EntraId": "Microsoft Entra ID (Azure AD)",
    "ExchangeOnline": "Exchange Online",
    "SharePointOnline": "SharePoint Online",
    "MicrosoftTeams": "Microsoft Teams",
    "Purview": "Microsoft Purview",
    "AdminPortal": "M365 Admin Portal",
}

CHUNK_SYSTEM_PROMPT = """You are a senior Microsoft 365 security analyst writing a professional security assessment report section.

Analyze ALL the provided findings for this service area and produce a structured markdown report section.

Your output MUST include:

## [Service Name] Security Analysis

### Summary
2-3 sentence overview of the security posture for this service.

### Findings

For EVERY finding (pass AND fail), include it grouped by severity:

#### Critical Findings
- **[Check Name]** — [CIS Benchmark ref if available]
  - **Status:** FAIL
  - **Current State:** [what was found]
  - **Expected State:** [what it should be]
  - **Business Risk:** [clear business impact explanation]
  - **Remediation:** [specific step-by-step fix]

#### High Findings
[same format]

#### Medium Findings
[same format]

#### Low Findings
[same format]

#### Passing Checks
- [Check Name] — PASS: [brief note on what is correctly configured]

### Quick Wins
List 2-3 highest-impact remediations that can be done in under 1 hour.

Be specific, technical, and actionable. Never omit a finding. Use plain language for business risk explanations."""


SYNTHESIS_SYSTEM_PROMPT = """You are a senior Microsoft 365 security analyst writing the executive summary of a security assessment report.

Based on all the per-service analysis sections provided, produce:

## Executive Summary

A 3-5 sentence plain-language summary of the client's overall M365 security posture, written for a non-technical executive audience.

## Overall Risk Score

Score: [Critical / High / Medium / Low]
Justification: [2 sentences explaining the score]

## Risk Dashboard

| Service Area | Risk Level | Critical | High | Medium | Low | Passing |
|---|---|---|---|---|---|---|
| Entra ID | [level] | [count] | [count] | [count] | [count] | [count] |
| Exchange Online | ... |
| SharePoint Online | ... |
| Microsoft Teams | ... |
| Purview | ... |
| Admin Portal | ... |

## Prioritized Remediation Roadmap

### Immediate (Quick Wins — This Week)
[Top 5 highest-impact, lowest-effort fixes across all services]

### 30-Day Plan
[Medium-complexity remediations]

### 60-Day Plan
[Longer-term structural improvements]

### 90-Day Plan
[Strategic/architectural changes]

## CIS Benchmark Compliance Summary
Overall CIS M365 Foundations Benchmark compliance percentage and key gaps."""


def chunk_findings_by_service(raw_data: dict) -> dict:
    """Split Monkey365 JSON output into per-service chunks."""
    chunks = {}
    for service in KNOWN_SERVICES:
        if service in raw_data:
            chunks[service] = raw_data[service]
    # Also include any unexpected top-level keys (future-proofing)
    # Accepts both list (OCSF format) and dict (legacy format)
    for key, value in raw_data.items():
        if key not in chunks and isinstance(value, (dict, list)):
            chunks[key] = value
    return chunks


def build_chunk_prompt(service_name: str, service_data) -> str:
    display_name = SERVICE_DISPLAY_NAMES.get(service_name, service_name)

    # OCSF list format: summarise counts then include full JSON
    if isinstance(service_data, list):
        fail_count = sum(1 for f in service_data if f.get("statusCode") == "fail")
        pass_count = sum(1 for f in service_data if f.get("statusCode") == "pass")
        manual_count = sum(1 for f in service_data if f.get("statusCode") == "manual")
        summary = (
            f"{len(service_data)} findings total: "
            f"{fail_count} fail, {pass_count} pass, {manual_count} manual review."
        )
        data_json = json.dumps(service_data, indent=2)
        return (
            f"Analyze the following {display_name} ({service_name}) security findings. "
            f"Summary: {summary} "
            f"Include ALL findings — Critical, High, Medium, Low, and Passing. "
            f"For each failing check, provide specific remediation steps.\n\n"
            f"Data:\n```json\n{data_json}\n```"
        )

    # Legacy dict format
    data_json = json.dumps(service_data, indent=2)
    return (
        f"Analyze the following {display_name} ({service_name}) security findings. "
        f"Include ALL findings — Critical, High, Medium, Low, and Passing. "
        f"For each failing check, provide specific remediation steps.\n\n"
        f"Data:\n```json\n{data_json}\n```"
    )


def _call_openai(system_prompt: str, user_content: str, max_tokens: int = 16000) -> str:
    response = client.chat.completions.create(
        model="gpt-5-nano",
        reasoning_effort="medium",
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content


def analyze_findings(out_dir: str) -> dict:
    """
    Load Monkey365 JSON, chunk by service, analyze each with OpenAI,
    then synthesize into executive summary.
    Returns dict of {service: analysis_markdown, "synthesis": synthesis_markdown}
    """
    from app.services.monkey365 import parse_monkey365_output
    raw_data = parse_monkey365_output(out_dir)
    chunks = chunk_findings_by_service(raw_data)

    analyses = {}
    for service_name, service_data in chunks.items():
        logger.info(f"Analyzing {service_name} findings...")
        user_prompt = build_chunk_prompt(service_name, service_data)
        analyses[service_name] = _call_openai(CHUNK_SYSTEM_PROMPT, user_prompt, max_tokens=16000)

    # Final synthesis across all services
    logger.info("Running synthesis analysis...")
    all_analyses = "\n\n---\n\n".join(
        f"# {SERVICE_DISPLAY_NAMES.get(svc, svc)}\n\n{text}"
        for svc, text in analyses.items()
    )
    analyses["synthesis"] = _call_openai(
        SYNTHESIS_SYSTEM_PROMPT,
        f"Here are all per-service analysis sections:\n\n{all_analyses}",
        max_tokens=32000,
    )

    return analyses
