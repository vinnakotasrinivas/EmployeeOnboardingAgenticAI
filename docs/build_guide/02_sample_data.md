# Step 2: Sample data

## Spec

**Goal:** a realistic set of fake company documents for testing every path: good onboarding files, files that are off-topic, and files that are broken or unsupported.

This step reuses the data set built by the earlier cloud agent, so most of it already exists. The step adds the off-topic and broken files, which that data set didn't have.

**Files**
- `scripts/generate_sample_data.py` (already exists): rebuilds the onboarding documents for "Northwind Labs", a made-up company. It always produces the same content (fixed random seed).
- `scripts/make_test_files.py` (new): builds the off-topic and broken files.
- `docs/sample_data/README.md` (already exists): describes every file and lists good test questions.

**Onboarding documents (`docs/sample_data/`, 9 files, all should be indexed)**

| File | Contents |
| --- | --- |
| `pdf/employee_handbook.pdf` | 3 pages: offices, probation, leave (India and US), payroll, benefits summary, first 90 days, expenses, contacts |
| `pdf/code_of_conduct.pdf` | 2 pages: values, respectful workplace, conflicts of interest, gifts, privacy, AI tools, speak-up channels |
| `pdf/it_security_policy.pdf` | 2 pages: Okta MFA, passwords, devices, VPN, data classification, phishing, incident reporting |
| `txt/first_week_faq.txt` | 12 Q&A pairs: Day 1 logistics, what to bring, first-week deadlines, pay dates |
| `txt/how_to_guides.txt` | 9 step-by-step guides: MFA, VPN (Zscaler), time off, benefits, software access, phishing, desks, expenses |
| `csv/onboarding_checklist.csv` | 55 tasks with phase, due offset, owner, country and department scope |
| `csv/team_directory.csv` | 184 employees: team, manager, location, onboarding buddy; 22 new hires |
| `xlsx/benefits_enrollment.xlsx` | Sheets `Plan Catalog`, `New Hire Enrollment`, `Key Dates and Rules` |
| `xlsx/training_schedule.xlsx` | Sheets `Course Catalog`, `Session Schedule` (220 sessions), `New Hire Assignments` |

**Off-topic files (`docs/sample_data/irrelevant/`, valid formats, should be rejected by the relevance gate)**
- `pasta_recipe.txt`
- `quarterly_sales.csv` (sales figures with no onboarding content)
- `football_rules.pdf`

**Broken or unsupported files (`docs/sample_data/invalid/`, should be rejected by the validator)**
- `photo.jpg` (a real small JPEG)
- `archive.zip`
- `empty.txt` (0 bytes)
- `fake_pdf.pdf` (JPEG bytes renamed to `.pdf`)
- `slides.pptx`
- `corrupt.pdf` (the `%PDF` header followed by garbage)
- `macro_book.xlsm`
- `oversize.pdf` (20 MB, only created with `--oversize`, and ignored by git)

**Reference facts for later checkpoints**

| Question | Answer | Source |
| --- | --- | --- |
| How many PTO days do US employees get per year? | 20 days (India: 18 days of earned leave, carry forward up to 30) | `employee_handbook.pdf` |
| Who is Siddharth Patel's manager and onboarding buddy? | Manager Nisha Chowdary, buddy Abhishek Banerjee | `team_directory.csv` |
| How many people work in Platform Engineering? | 18 | `team_directory.csv` |
| When is the next Security Awareness session in IST? | Thursday 29 October 2026, 14:30 IST, on Zoom | `training_schedule.xlsx` |
| How do I connect to the VPN? | Install Zscaler from Self Service or Company Portal and sign in with Okta | `how_to_guides.txt` |
| What is the 401(k) match? | 100% match on the first 4% of salary | `employee_handbook.pdf`, `benefits_enrollment.xlsx` |
| When do I get paid in India? | Last working day of each month | `first_week_faq.txt`, `employee_handbook.pdf` |

## Prompt

Already done in this project. If you're rebuilding from scratch, use this:

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md for context and docs/build_guide/02_sample_data.md for the spec. This is STEP 2 ONLY: sample data. Do not build loaders or validators yet.

scripts/generate_sample_data.py already exists and produces the onboarding documents in docs/sample_data/. Add its libraries as dev dependencies: `uv add --dev reportlab openpyxl pillow`.

Create scripts/make_test_files.py that writes the off-topic files to docs/sample_data/irrelevant/ (pasta_recipe.txt, quarterly_sales.csv, football_rules.pdf) and the broken files to docs/sample_data/invalid/ (photo.jpg as a real JPEG via Pillow, archive.zip containing a txt, empty.txt with 0 bytes, fake_pdf.pdf with JPEG bytes, slides.pptx and macro_book.xlsm with dummy bytes, corrupt.pdf as "%PDF-1.4" then random bytes). Only with --oversize, also create a 20 MB oversize.pdf. Use a fixed random seed. Add docs/sample_data/invalid/oversize.pdf to .gitignore.

Run `uv run python scripts/make_test_files.py --oversize` and show the output.
```

## Checkpoint

```powershell
uv run python scripts/make_test_files.py --oversize
Get-ChildItem -Recurse docs\sample_data -File | Select-Object FullName, Length
```

**Expected output:** 9 onboarding files across `pdf\`, `txt\`, `csv\` and `xlsx\`, 3 files in `irrelevant\`, and 8 in `invalid\`. `empty.txt` is 0 bytes and `oversize.pdf` is 20,971,520 bytes. Open `employee_handbook.pdf` and `training_schedule.xlsx` to see what the data looks like.

## Common problems

- **Running `generate_sample_data.py` shows the PDFs and Excel files as changed in git:** those files embed the time they were created, so every run changes a few bytes even though the content is the same. Only re-run it if you change the script, or discard the changes with `git checkout -- docs/sample_data`.
- **`oversize.pdf` shows up in `git status`:** check that `.gitignore` contains `docs/sample_data/invalid/oversize.pdf`.
- **`make_test_files.py` says to run the generator first:** it copies `first_week_faq.txt` into `archive.zip`, so the onboarding documents must exist.
