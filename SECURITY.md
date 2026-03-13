# Security Policy

## Supported Versions

| Package | Version | Supported |
| ------- | ------- | --------- |
| pm-data-tools | 0.2.x | Yes |
| agent-task-planning | 0.2.x | Yes |
| pm-mcp-servers | 0.3.x | Yes |
| Any package | < current minor | No |

Only the latest minor release of each package receives security updates.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Email security issues to: **security@pdataskforce.com**

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Suggested fix (if available)
- Your contact information

### Response Timeline

| Severity | Acknowledgement | Fix target |
| -------- | --------------- | ---------- |
| Critical | 48 hours | 7 days |
| High | 48 hours | 14 days |
| Medium | 48 hours | 30 days |
| Low | 48 hours | Next planned release |

## Security Design

pda-platform is designed with a minimal attack surface:

- **No network calls**: All processing is local
- **No persistent storage**: No data is stored between sessions
- **No telemetry**: No usage data is transmitted
- **File-based input only**: Processes only files you explicitly provide

## Known Limitations

1. Malformed project files could cause crashes (XML/Excel parsing)
2. Very large files may consume significant memory

## Coordinated Disclosure

We follow coordinated disclosure practices:
- We will work with you to understand and resolve the issue
- We will not take legal action against good-faith security researchers
- We request 90 days before public disclosure to allow time for fixes

Security updates are announced via GitHub Security Advisories and release notes.
