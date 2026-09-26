# Security policy

Veyro handles API keys and, optionally, real broker orders, so security reports matter a lot to us.

## Reporting a vulnerability

**Please don't open a public issue.** Use GitHub's private reporting instead: **Security → Report a vulnerability** on this repository.

Include what you found, how to reproduce it, and what an attacker could do with it. You'll get a reply within 7 days.

## In scope

- API keys leaking into logs, the database, API responses, the UI or crash reports.
- Any way around the loopback-Host or same-origin checks, for example DNS rebinding or a foreign origin on the WebSocket.
- Any way around the monthly spend cap, including starting paid runs, or side calls that aren't counted.
- An order sent to Alpaca without explicit confirmation, or with execution switched off.
- A path traversal or file write outside Veyro's data folder.

## Out of scope

- The quality of the analysis or of a verdict. Veyro isn't financial advice; please report those as normal issues.
- Vulnerabilities in TradingAgents itself. Please report those upstream: https://github.com/TauricResearch/TradingAgents.

## Supported versions

Fixes land on `main` and in the next release.
