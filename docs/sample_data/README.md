# Sample onboarding data: Northwind Labs (fictional)

Synthetic, production-style onboarding documents for testing the OnboardIQ RAG assistant. All people, phone numbers, addresses and providers are fictional. "Today" in the data is 25 October 2026.

Regenerate (deterministic) with:

```bash
uv run --with reportlab --with openpyxl python scripts/generate_sample_data.py
```

| File | Format | Size | Contents |
|---|---|---|---|
| `pdf/employee_handbook.pdf` | PDF | 3 pages | Offices, hybrid model, probation, leave (India/US), payroll, benefits summary, first 90 days, expenses, contacts |
| `pdf/code_of_conduct.pdf` | PDF | 2 pages | Values, respectful workplace (POSH), conflicts of interest, gifts limits, privacy, AI tools, speak-up channels |
| `pdf/it_security_policy.pdf` | PDF | 2 pages | Okta MFA, passwords, devices, VPN, data classification, phishing, AI tools, incident reporting |
| `txt/first_week_faq.txt` | TXT | 1 page | Day 1 logistics, documents to bring, first-week deadlines, pay dates |
| `txt/how_to_guides.txt` | TXT | 1 page | Step-by-step: MFA, VPN, time off, benefits, software access, phishing, desk booking, expenses |
| `csv/onboarding_checklist.csv` | CSV | 55 rows | Tasks from pre-boarding to probation with owner, due offset, country and department scope |
| `csv/team_directory.csv` | CSV | 184 rows | Employees, managers, teams, locations, 22 new hires with onboarding buddies |
| `xlsx/benefits_enrollment.xlsx` | Excel | 116 rows, 3 sheets | Plan catalog (India/US), new-hire elections and deadlines, key dates and rules |
| `xlsx/training_schedule.xlsx` | Excel | 424 rows, 3 sheets | Course catalog, 220 sessions (Oct 2026 - Jan 2027, IST/CT), new-hire course assignments |

## Facts that connect across files (good test questions)

- New-hire cohorts start on 5, 19 and 26 October and 2 and 16 November 2026.
- Code of Conduct acknowledgment is due within 7 days, Security Awareness (NWL-SEC-101) within 14 days, and benefits enrollment within 30 days of the start date.
- Each new hire in `team_directory.csv` has a manager and an onboarding buddy; their benefits elections and training due dates appear in the Excel workbooks under the same `employee_id`.

Example questions:

- "Who is Siddharth Patel's onboarding buddy and manager?"
- "What is the benefits enrollment deadline for someone who started on 19 October 2026?"
- "When is the next Security Awareness session in IST?"
- "How many days of earned leave do employees in India get, and how much can be carried forward?"
- "What should I do if I lose my laptop?"
