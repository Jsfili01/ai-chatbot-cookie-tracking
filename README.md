# AI Chatbot Cookie Tracking Research

Research project investigating cookie tracking, consent behavior, and third-party data collection associated with AI chatbots embedded in websites.

## Research Objectives

- Identify websites using embedded AI chatbot services.
- Analyze cookies created before and after chatbot interaction.
- Compare cookie behavior under different consent conditions.
- Investigate third-party network requests and potential data exposure.
- Compare tracking behavior across chatbot providers and geographic regions.
- Classify websites by industry, chatbot provider, and web infrastructure.

## Technologies

- Python
- Playwright
- Google Chrome
- SQLite
- Pandas

## Project Files

| File | Description |
|---|---|
| `discover.py` | Discovers websites with chatbot-related evidence |
| `capture.py` | Captures cookies and network requests |
| `analyze.py` | Analyzes cookies, consent behavior, and data exposure |
| `canaries.py` | Generates synthetic test identities |
| `diag.py` | Website diagnostic utility |
| `diag2.py` | Additional chatbot diagnostics |
| `prep_chatbase.py` | Prepares chatbot discovery candidates |

## Research Methodology

The crawler examines websites using browser automation and records cookies at four stages:

1. Initial page load
2. Consent interaction
3. Chatbot opening
4. Chatbot message submission

Three consent conditions are evaluated:

- No interaction
- Accept All
- Reject All

Synthetic identities are used to investigate whether chatbot inputs appear in outgoing network requests.

## Current Progress

- Scanned 90 candidate websites.
- Identified 53 websites with preliminary chatbot-related evidence.
- Tested Chatbase and Impel detection.
- Collected initial cookie data from RetroFoam and GTWeed.
- Completed an initial three-condition consent comparison on GTWeed.

## Limitations

Results are preliminary and do not establish legal compliance violations.

Chatbot detection does not independently prove that every identified widget uses AI.

Cookie classifications require validation, and geographic comparisons require verified country-specific network connections.

## Privacy and Research Ethics

Only synthetic personal information is used during chatbot testing.

Raw cookie captures, session identifiers, and potentially sensitive network data are excluded from this repository.

