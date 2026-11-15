"""Generate realistic onboarding documents for the fictional company Northwind Labs.

Outputs (in docs/sample_data/):
  pdf/  employee_handbook.pdf, code_of_conduct.pdf, it_security_policy.pdf
  txt/  first_week_faq.txt, how_to_guides.txt
  csv/  onboarding_checklist.csv, team_directory.csv
  xlsx/ benefits_enrollment.xlsx, training_schedule.xlsx

Deterministic: the same seed always produces the same files.
Run: uv run python scripts/generate_sample_data.py
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "sample_data"
SEED = 20261025
TODAY = date(2026, 10, 25)
DOMAIN = "northwindlabs.com"
COHORT_DATES = [date(2026, 10, 5), date(2026, 10, 19), date(2026, 10, 26), date(2026, 11, 2), date(2026, 11, 16)]

BRAND = colors.HexColor("#1F3A5F")
GRID = colors.HexColor("#C9D3E0")
HEADER_BG = colors.HexColor("#E8EEF6")


# --------------------------------------------------------------------------- PDF


def _pdf_styles() -> dict[str, ParagraphStyle]:
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=4)
    return {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=BRAND),
        "subtitle": ParagraphStyle(
            "subtitle", fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#555555"), spaceAfter=6
        ),
        "h": ParagraphStyle(
            "h", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=BRAND, spaceBefore=8, spaceAfter=3
        ),
        "body": body,
        "bullet": ParagraphStyle("bullet", parent=body, leftIndent=12, bulletIndent=3, spaceAfter=2),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=11),
        "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.5, leading=11),
    }


def _esc(text: str) -> str:
    return text.replace(" & ", " &amp; ")


def build_pdf(path: Path, meta: dict[str, str], blocks: list[tuple]) -> None:
    st = _pdf_styles()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title=meta["title"],
        author="Northwind Labs",
        subject=meta["subtitle"],
    )
    width = A4[0] - 36 * mm

    def decorate(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(BRAND)
        canvas.setLineWidth(0.6)
        canvas.line(18 * mm, A4[1] - 13 * mm, A4[0] - 18 * mm, A4[1] - 13 * mm)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(BRAND)
        canvas.drawString(18 * mm, A4[1] - 11 * mm, "NORTHWIND LABS")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 11 * mm, f"{meta['title']}  |  Classification: Internal")
        canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
        canvas.drawString(
            18 * mm, 8 * mm, f"{meta['doc_id']}  |  Version {meta['version']}  |  Effective {meta['effective']}"
        )
        canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f"Page {_doc.page}")
        canvas.restoreState()

    def table(header: list[str], rows: list[list[str]], ratios: list[float]) -> Table:
        data = [[Paragraph(_esc(h), st["cellb"]) for h in header]]
        data += [[Paragraph(_esc(c), st["cell"]) for c in r] for r in rows]
        t = Table(data, colWidths=[width * r for r in ratios], repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                    ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        return t

    story = [Paragraph(meta["title"], st["title"]), Paragraph(meta["subtitle"], st["subtitle"])]
    info = [
        ["Document ID", meta["doc_id"], "Version", meta["version"]],
        ["Owner", meta["owner"], "Effective date", meta["effective"]],
        ["Applies to", meta["applies_to"], "Next review", meta["review"]],
    ]
    it = Table(
        [[Paragraph(_esc(c), st["cellb"] if i % 2 == 0 else st["cell"]) for i, c in enumerate(r)] for r in info],
        colWidths=[width * 0.16, width * 0.42, width * 0.16, width * 0.26],
    )
    it.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, BRAND),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, GRID),
                ("BACKGROUND", (0, 0), (0, -1), HEADER_BG),
                ("BACKGROUND", (2, 0), (2, -1), HEADER_BG),
            ]
        )
    )
    story += [it, Spacer(1, 6)]

    for block in blocks:
        kind = block[0]
        if kind == "h":
            story.append(Paragraph(_esc(block[1]), st["h"]))
        elif kind == "p":
            story.append(Paragraph(_esc(block[1]), st["body"]))
        elif kind == "ul":
            story += [Paragraph(_esc(item), st["bullet"], bulletText="\u2022") for item in block[1]]
        elif kind == "table":
            story += [Spacer(1, 2), table(block[1], block[2], block[3]), Spacer(1, 4)]
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)


def write_handbook(path: Path) -> None:
    meta = {
        "title": "Employee Handbook",
        "subtitle": "How we work at Northwind Labs: policies, pay, leave and your first 90 days",
        "doc_id": "NWL-HR-001",
        "version": "4.1",
        "owner": "People Team (people@northwindlabs.com)",
        "effective": "1 January 2026",
        "review": "31 December 2026",
        "applies_to": "All employees in India and the United States",
    }
    blocks = [
        ("h", "1. Welcome to Northwind Labs"),
        (
            "p",
            "Northwind Labs builds <b>Northwind Insights</b>, a revenue analytics platform used by more than 600 "
            "B2B companies to forecast pipeline, understand churn and plan growth. We are about 180 people across "
            "Austin, Bengaluru, Hyderabad and remote locations in the United States. This handbook summarises the "
            "policies that matter most in your first months. Where local law or your employment contract differs "
            "from this handbook, the law and your contract prevail. Questions are always welcome in "
            "<b>#ask-people</b> on Slack or at people@northwindlabs.com.",
        ),
        ("h", "2. Offices and working model"),
        (
            "table",
            ["Location", "Address", "Working model", "Core hours"],
            [
                ["Austin (HQ)", "1200 Riverside Drive, Suite 400, Austin, TX 78741", "Hybrid: Tue, Wed, Thu in office", "10:00-15:00 CT"],
                ["Bengaluru", "Tower B, 4th Floor, Lakeview Tech Park, Outer Ring Road, Bengaluru 560103", "Hybrid: Tue, Wed, Thu in office", "11:00-16:00 IST"],
                ["Hyderabad", "Level 6, Orion Block, HITEC City, Hyderabad 500081", "Hybrid: Tue, Wed, Thu in office", "11:00-16:00 IST"],
                ["Remote (US)", "As per offer letter", "Fully remote; one on-site week per quarter in Austin", "10:00-15:00 local"],
            ],
            [0.15, 0.40, 0.27, 0.18],
        ),
        (
            "p",
            "Outside core hours you may arrange your day flexibly, provided you work a standard 40-hour week and "
            "keep your calendar up to date. Working from another country for more than 14 days in a calendar year "
            "needs written approval from the People Team and IT, because it can create tax and data-security risks.",
        ),
        ("h", "3. Employment basics"),
        (
            "ul",
            [
                "<b>Probation (India):</b> 6 months. Your manager completes a confirmation review in Workday in month 5 and the People Team issues a confirmation letter.",
                "<b>Introductory period (US):</b> 90 days. Employment in the US is at-will.",
                "<b>Employee ID and badge:</b> issued on Day 1. IDs use the format NWL followed by four digits (for example NWL1042).",
                "<b>Notice period:</b> India: 30 days during probation and 60 days after confirmation. US: two weeks' notice is requested.",
                "<b>Personal details:</b> update address, bank account and emergency contact in Workday within 7 days of any change.",
            ],
        ),
        ("h", "4. Leave and holidays"),
        (
            "table",
            ["Leave type", "India", "United States"],
            [
                ["Annual leave", "18 days of earned leave per year, accrued at 1.5 days per month. Carry forward up to 30 days.", "20 days of PTO per year, accrued each pay period. Carry over up to 5 days into the next year."],
                ["Sick / casual leave", "12 days per year; not carried forward. Medical certificate needed for more than 2 consecutive sick days.", "7 paid sick days per year."],
                ["Public holidays", "10 fixed holidays plus 2 optional holidays from the published list.", "10 company holidays."],
                ["Parental leave", "26 weeks maternity leave; 2 weeks paternity leave.", "16 weeks paid leave for the birthing parent; 8 weeks for the non-birthing parent."],
                ["Bereavement", "5 days.", "5 days."],
            ],
            [0.18, 0.41, 0.41],
        ),
        (
            "p",
            "Request leave in <b>Workday &gt; Time Off</b>. Leave of 3 or more consecutive working days must be "
            "requested at least 10 working days in advance. In India, earned leave accrues from Day 1 and can be "
            "used after 3 months of service; in the US, PTO can be used after 30 days. For unplanned sick leave, "
            "tell your manager before 10:00 local time and record it in Workday when you return. The holiday "
            "calendar for each office is published on Confluence under People &gt; Holidays 2026.",
        ),
        ("h", "5. Pay and payroll"),
        (
            "ul",
            [
                "<b>India:</b> salary is paid monthly on the last working day; payslips appear in Workday by the 1st. Submit your investment declaration (Form 12BB) in Workday within 30 days of joining, otherwise tax is deducted without exemptions until the next declaration window.",
                "<b>United States:</b> paid every other Friday by direct deposit. Complete your W-4 and direct-deposit details in Workday by the end of Day 3. Complete Form I-9 Section 1 on or before Day 1; the People Team verifies your documents within 3 business days.",
                "<b>Payroll cut-off:</b> changes after the 20th of the month (India) or after Monday of a pay week (US) roll into the next cycle.",
                "<b>Questions:</b> payroll@northwindlabs.com.",
            ],
        ),
        ("h", "6. Benefits at a glance"),
        (
            "p",
            "Enroll in benefits within <b>30 calendar days of your start date</b> in Workday &gt; Benefits. If you "
            "miss this window you can only enroll during annual open enrollment (1-15 November) or within 30 days "
            "of a qualifying life event such as marriage or the birth of a child. Plan details and costs are in "
            "the Benefits Enrollment workbook.",
        ),
        (
            "ul",
            [
                "<b>India:</b> group medical floater of INR 5,00,000 for you, your spouse and up to two children at no cost; optional parental cover and super top-up; term life cover of 3x fixed CTC; personal accident cover; optional NPS; wellness allowance of INR 15,000 per year.",
                "<b>United States:</b> choice of PPO or HDHP medical plan (HDHP includes an employer HSA contribution of USD 1,000, or USD 2,000 for family cover), dental, vision, 401(k) with a 100% match on the first 4% of salary from your first paycheck, life and AD&amp;D cover of 2x salary, wellness stipend of USD 600 per year.",
                "<b>Everyone:</b> annual learning budget of USD 1,000 / INR 60,000 and a one-time home-office stipend of USD 500 / INR 25,000, claimable within 60 days of joining.",
            ],
        ),
        ("h", "7. Your first 90 days"),
        (
            "table",
            ["Milestone", "What happens", "Owner"],
            [
                ["Before Day 1", "Accounts created, laptop prepared (shipped to remote US hires), welcome email with your Day 1 agenda.", "IT, People Team"],
                ["Day 1", "New Hire Orientation at 09:30 local time, badge and laptop setup, meet your manager and onboarding buddy.", "People Team, Manager"],
                ["Week 1", "Acknowledge the Code of Conduct (due within 7 days), agree your 30-60-90 day plan, complete IT setup.", "New hire, Manager"],
                ["Day 14", "Security Awareness Essentials training complete.", "New hire"],
                ["Day 30", "Benefits enrollment deadline; remaining mandatory training due; first check-in with your manager.", "New hire, Manager"],
                ["Day 60", "Mid-point check-in, including feedback from your onboarding buddy.", "Manager"],
                ["Day 90", "90-day review. The US introductory period ends.", "Manager, People Team"],
            ],
            [0.16, 0.62, 0.22],
        ),
        (
            "p",
            "Every new hire is paired with an <b>onboarding buddy</b>: an experienced teammate who is not your "
            "manager. Meet your buddy at least once a week for your first 6 weeks. Your buddy is listed in the "
            "team directory and in your welcome email.",
        ),
        ("h", "8. Performance and growth"),
        (
            "p",
            "Performance reviews run twice a year, in April and October. If you join after 1 August you start with "
            "the April cycle; if you join after 1 February you start with the October cycle. Promotions are "
            "considered in the April cycle. Request use of your learning budget in Workday Learning with your "
            "manager's approval.",
        ),
        ("h", "9. Expenses and travel"),
        (
            "ul",
            [
                "Submit expense claims in Workday Expenses within 30 days, with itemised receipts for any item above USD 25 / INR 2,000.",
                "Daily meal limits while travelling: USD 75 in the US and INR 2,500 in India.",
                "Book travel through the Northwind Travel portal. International travel needs VP approval at least 14 days before departure.",
            ],
        ),
        ("h", "10. Conduct, security and leaving Northwind"),
        (
            "p",
            "Everyone must follow the Code of Conduct (NWL-LGL-002) and the IT Security Policy (NWL-SEC-003). When "
            "you leave, return all company equipment on or before your last working day. Final settlement is "
            "processed within 45 days in India and on the next regular payday in the US.",
        ),
        ("h", "11. Who to contact"),
        (
            "table",
            ["Need", "Contact"],
            [
                ["HR policies, leave, letters", "#ask-people on Slack, people@northwindlabs.com"],
                ["Payroll", "payroll@northwindlabs.com"],
                ["Benefits", "benefits@northwindlabs.com"],
                ["IT help", "#it-helpdesk on Slack, it-help@northwindlabs.com, extension 4357"],
                ["Security incident or lost device", "security@northwindlabs.com, +1-512-555-0142 (24x7)"],
                ["Ethics concern (anonymous option)", "ethics.northwindlabs.com or 1-800-555-0199"],
            ],
            [0.35, 0.65],
        ),
    ]
    build_pdf(path, meta, blocks)


def write_code_of_conduct(path: Path) -> None:
    meta = {
        "title": "Code of Conduct",
        "subtitle": "The standards of behaviour we expect from everyone who works at or with Northwind Labs",
        "doc_id": "NWL-LGL-002",
        "version": "2.3",
        "owner": "Legal & Compliance (compliance@northwindlabs.com)",
        "effective": "1 March 2026",
        "review": "28 February 2027",
        "applies_to": "Employees, contractors, interns and board members",
    }
    blocks = [
        ("h", "1. Purpose and scope"),
        (
            "p",
            "This Code explains how we make decisions and treat each other, our customers and our partners. It "
            "applies to everyone who works for or on behalf of Northwind Labs, in every country. New joiners must "
            "read the Code and acknowledge it in <b>Workday &gt; Inbox</b> within <b>7 days of their start date</b>, "
            "and everyone re-acknowledges it every January. No code can cover every situation; when something "
            "feels wrong, ask before you act.",
        ),
        ("h", "2. Our values"),
        (
            "table",
            ["Value", "What it looks like in practice"],
            [
                ["Customers first", "We protect customer data as if it were our own and never overpromise what the product can do."],
                ["Own the outcome", "We follow through on commitments, raise risks early and fix problems instead of assigning blame."],
                ["Be candid and kind", "We give direct, respectful feedback and assume good intent."],
                ["Build trust with data", "We make decisions with evidence and are transparent about how we use data."],
            ],
            [0.25, 0.75],
        ),
        ("h", "3. A respectful workplace"),
        (
            "p",
            "We do not tolerate discrimination, harassment or bullying based on race, colour, religion, caste, "
            "sex, gender identity, sexual orientation, age, disability, national origin, marital status or any "
            "other legally protected characteristic. This applies in the office, online, at offsites and at "
            "company events. In India, complaints of sexual harassment are handled by the Internal Committee under "
            "the POSH Act, 2013 (ic-india@northwindlabs.com). In the US, report concerns to the People Team or the "
            "Ethics Line. Retaliation against anyone who raises a concern in good faith is itself a serious "
            "violation of this Code.",
        ),
        ("h", "4. Conflicts of interest"),
        (
            "p",
            "Disclose any situation that could influence, or appear to influence, your judgment within <b>14 days</b> "
            "using Workday &gt; Disclosures. Common examples:",
        ),
        (
            "ul",
            [
                "Outside employment, consulting or advisory roles, including board seats.",
                "Investments of more than 1% in a competitor, customer or vendor.",
                "A close relative or partner in your reporting line or in a vendor you manage.",
                "Side projects that use company time, equipment or confidential information. Contributions to open-source projects related to your work need manager approval under the Open Source Guidelines.",
            ],
        ),
        ("h", "5. Gifts, hospitality and anti-bribery"),
        (
            "table",
            ["Situation", "Allowed", "Needs Compliance approval", "Never allowed"],
            [
                ["Receiving gifts", "Up to USD 75 / INR 5,000 per source per year", "Anything above the limit; log it in the Gifts Register", "Cash, gift cards or other cash equivalents"],
                ["Customer hospitality", "Reasonable business meals up to USD 150 per person", "Anything above the limit, or any hospitality for a government official", "Anything offered to influence a buying decision"],
                ["Payments to officials", "-", "-", "Facilitation or 'speed' payments of any amount"],
            ],
            [0.20, 0.27, 0.28, 0.25],
        ),
        (
            "p",
            "We comply with the US Foreign Corrupt Practices Act and India's Prevention of Corruption Act. Sales, "
            "Finance and Customer Success employees complete Anti-Bribery and Corruption training (NWL-ABC-201) "
            "within 30 days of joining.",
        ),
        ("h", "6. Confidential information and privacy"),
        (
            "ul",
            [
                "Use customer data only to deliver and support our services, and only in approved systems.",
                "Never download customer data to personal devices or personal cloud storage.",
                "Follow the data classification rules in the IT Security Policy (NWL-SEC-003).",
                "Handle personal data in line with GDPR, CCPA and India's Digital Personal Data Protection Act, 2023.",
                "Your confidentiality obligations continue after you leave Northwind Labs.",
            ],
        ),
        ("h", "7. Company assets and AI tools"),
        (
            "p",
            "Company laptops, accounts and software are provided for business use; limited personal use is fine if "
            "it does not affect your work or security. Use only approved AI tools (Northwind AI Assistant for "
            "everyone; GitHub Copilot Business for Engineering) and never paste Confidential or Restricted "
            "information into public AI services.",
        ),
        ("h", "8. External communication and social media"),
        (
            "p",
            "Only the Marketing and Communications team speaks to the media on behalf of the company; direct press "
            "enquiries to press@northwindlabs.com. Do not name customers publicly unless they appear on our public "
            "customer page. When you post about the industry, make clear that the views are your own.",
        ),
        ("h", "9. Insider information and fair competition"),
        (
            "p",
            "Northwind Labs is privately held, but many customers and partners are public companies. Do not trade "
            "their securities based on material non-public information you learn at work, and do not pass such "
            "information to others. Never discuss pricing, bids or territories with competitors, and never make "
            "false or misleading claims about our product or a competitor's.",
        ),
        ("h", "10. Speaking up"),
        (
            "p",
            "If you see or suspect a violation, raise it through any of these channels: your manager, the People "
            "Team, Legal &amp; Compliance, or the independent <b>Ethics Line</b>, available 24x7 with an anonymous "
            "option at ethics.northwindlabs.com, 1-800-555-0199 (US) or 000-800-100-0199 (India, toll-free). Reports "
            "are acknowledged within 2 business days and most investigations conclude within 30 days.",
        ),
        ("h", "11. Consequences"),
        (
            "p",
            "Violations of this Code may lead to disciplinary action up to and including termination of employment "
            "or contract, and may be reported to authorities where the law requires.",
        ),
        ("h", "12. Acknowledgment"),
        (
            "p",
            "<i>\"I have read the Northwind Labs Code of Conduct, I understand it, and I agree to follow it. I know how "
            "to raise a concern and that I will not face retaliation for doing so in good faith.\"</i> Complete this "
            "acknowledgment in Workday within 7 days of joining.",
        ),
    ]
    build_pdf(path, meta, blocks)


def write_it_security_policy(path: Path) -> None:
    meta = {
        "title": "IT Security Policy",
        "subtitle": "Rules for accounts, devices, data and incident reporting",
        "doc_id": "NWL-SEC-003",
        "version": "5.0",
        "owner": "Information Security (security@northwindlabs.com)",
        "effective": "15 January 2026",
        "review": "14 January 2027",
        "applies_to": "All users of Northwind Labs systems, devices and data",
    }
    blocks = [
        ("h", "1. Purpose and scope"),
        (
            "p",
            "This policy protects our customers' data and our systems. It supports our ISO 27001 certification and "
            "SOC 2 Type II report, and applies to every employee, contractor and intern, on every device used for "
            "Northwind work. Breaking this policy can lead to access removal and disciplinary action.",
        ),
        ("h", "2. Accounts and access"),
        (
            "ul",
            [
                "All applications are accessed through <b>Okta single sign-on</b>. Multi-factor authentication (MFA) is mandatory using Okta Verify push or a FIDO2 security key. SMS codes are not permitted.",
                "Engineering, Finance and IT staff are issued a YubiKey on Day 1 and must register it within 7 days.",
                "Request additional access through the IT Service Portal (it.northwindlabs.com). Requests need approval from your manager and the system owner and follow least privilege.",
                "Shared or generic accounts are not allowed. Access is reviewed every quarter.",
            ],
        ),
        ("h", "3. Passwords"),
        (
            "ul",
            [
                "Minimum 14 characters; a passphrase of four or more random words is recommended.",
                "Store all work passwords in <b>1Password</b> (company account). Never reuse a work password anywhere else.",
                "There is no forced periodic rotation, but change a password immediately if you suspect it has been exposed, and tell Security.",
            ],
        ),
        ("h", "4. Devices"),
        (
            "ul",
            [
                "Use only company-managed laptops for work: MacBook Pro for Engineering and Design; MacBook Air or Dell Latitude 7450 for other roles. Devices are enrolled in Jamf (Mac) or Microsoft Intune (Windows).",
                "Full-disk encryption (FileVault or BitLocker) and CrowdStrike Falcon must stay enabled. Do not attempt to disable or bypass them.",
                "Screens lock automatically after 5 minutes of inactivity. Lock your screen whenever you step away.",
                "Install operating system and browser updates within 7 days of release, and critical updates within 48 hours.",
                "Personal phones may access Gmail and Slack only through apps protected by Intune app protection. Never store customer data on a personal device.",
            ],
        ),
        ("h", "5. Network and remote work"),
        (
            "p",
            "Connect through <b>Zscaler Private Access (ZPA)</b> to reach internal admin tools and any production "
            "system. On public Wi-Fi, keep ZPA switched on at all times. At home, change your router's default "
            "admin password and keep its firmware updated. Never leave a device unattended in a public place.",
        ),
        ("h", "6. Data classification"),
        (
            "table",
            ["Class", "Examples", "How to handle it"],
            [
                ["Public", "Marketing website, published documentation, press releases", "No restrictions."],
                ["Internal", "Policies, org charts, internal wiki, product roadmaps", "Share only inside Northwind Labs."],
                ["Confidential", "Customer contracts, financial reports, source code, pricing", "Need-to-know only. Share with restricted Google Drive links; external sharing needs manager approval."],
                ["Restricted", "Customer production data, personal data, credentials, payroll records", "Approved systems only. Never on local disk, email, Slack, or any AI tool."],
            ],
            [0.15, 0.40, 0.45],
        ),
        ("h", "7. Email, phishing and social engineering"),
        (
            "ul",
            [
                "Report suspicious email with the <b>Report Phish</b> button in Gmail. Do not forward it to colleagues.",
                "Never approve an MFA push you did not start. Report unexpected pushes to Security immediately.",
                "Verify any request for payments, gift cards or bank-detail changes by calling the requester on a known number.",
                "Security runs monthly phishing simulations. Clicking is a learning opportunity; repeated clicks trigger refresher training.",
            ],
        ),
        ("h", "8. Software and AI tools"),
        (
            "p",
            "Install software only from <b>Self Service</b> (Mac) or <b>Company Portal</b> (Windows). New SaaS tools "
            "need a security review requested through the IT Service Portal; reviews take about 5 business days. "
            "Approved AI tools are Northwind AI Assistant (all employees) and GitHub Copilot Business (Engineering). "
            "Never paste Confidential or Restricted data into public AI services.",
        ),
        ("h", "9. Source code and production (Engineering)"),
        (
            "ul",
            [
                "All code lives in GitHub Enterprise. The main branch is protected and every change needs at least one approving review.",
                "Never commit secrets. Store them in HashiCorp Vault.",
                "Production access is just-in-time, approved per session and fully logged.",
            ],
        ),
        ("h", "10. Reporting incidents and lost devices"),
        (
            "p",
            "Report any suspected security incident <b>within 1 hour</b> of noticing it: email security@northwindlabs.com, "
            "post in #security-incidents, or call +1-512-555-0142 (24x7). Report a lost or stolen device to IT and "
            "Security within 1 hour so it can be locked and wiped remotely. Do not investigate on your own or delete "
            "evidence.",
        ),
        ("h", "11. Training, exceptions and offboarding"),
        (
            "ul",
            [
                "Complete <b>Security Awareness Essentials (NWL-SEC-101)</b> within 14 days of your start date, and again every year.",
                "Exceptions to this policy are requested through the IT Service Portal, need CISO approval and last at most 90 days.",
                "Access is removed by 18:00 local time on your last working day; return all devices and security keys before then.",
            ],
        ),
    ]
    build_pdf(path, meta, blocks)


# --------------------------------------------------------------------------- TXT

FIRST_WEEK_FAQ = """NORTHWIND LABS - FIRST WEEK FAQ FOR NEW HIRES
Owner: People Team (people@northwindlabs.com) | Last updated: 1 October 2026

Q: What time should I arrive on Day 1, and where do I go?
A: Arrive by 09:15 local time. New Hire Orientation starts at 09:30. Austin: reception, Suite 400.
   Bengaluru: Tower B, 4th floor. Hyderabad: Level 6, Orion Block. Remote US hires join on Zoom
   using the link in your welcome email.

Q: What should I bring?
A: A government photo ID. US hires also bring their original Form I-9 documents. India hires
   bring PAN, Aadhaar and a cancelled cheque or bank statement for payroll.

Q: When do I get my laptop?
A: Remote US hires receive it by courier before Day 1. Office-based hires collect it from the
   IT desk during orientation. Activate Okta and enroll MFA before installing anything else.

Q: Who is my onboarding buddy?
A: Your buddy is named in your welcome email and in the team directory. Meet at least once a
   week for your first 6 weeks.

Q: Which Slack channels should I join?
A: #announcements, #ask-people, #it-helpdesk, #new-joiners and your team channel.

Q: What must I finish in my first week?
A: Acknowledge the Code of Conduct in Workday (due within 7 days), complete the Code of Conduct
   training (NWL-COC-101), agree your 30-60-90 day plan with your manager, and connect to the
   Zscaler VPN. US hires: W-4 and direct deposit by end of Day 3.

Q: When is the benefits enrollment deadline?
A: 30 calendar days from your start date, in Workday > Benefits. Missing it means waiting
   for open enrollment (1-15 November) unless you have a qualifying life event.

Q: Which trainings are mandatory, and by when?
A: Security Awareness within 14 days. Data Privacy, Responsible Use of AI and Product
   Fundamentals within 30 days. POSH Awareness (India) or Harassment Prevention (US) within
   30 days. Your personal due dates are in Northwind Learn.

Q: Can I work from home in my first week?
A: Plan to be in the office Tuesday to Thursday from your first week. Remote roles follow the
   offer letter.

Q: When do I get paid?
A: India: last working day of each month. US: every other Friday.

Q: I'm locked out of Okta or lost my MFA device. What now?
A: Call the IT helpdesk on extension 4357 or ask a colleague to post in #it-helpdesk.

Q: Who do I contact about anything else?
A: Your buddy first, then your manager, then #ask-people. We would rather you ask than guess.
"""

HOW_TO_GUIDES = """NORTHWIND LABS - HOW-TO GUIDES FOR YOUR FIRST WEEK
Owner: IT and People Team | Last updated: 1 October 2026

1. SET UP OKTA AND MFA (Day 1)
   a) Open the Okta activation link in your welcome email and set a password of at least 14 characters.
   b) Install Okta Verify on your phone, scan the QR code and add a second factor as backup.
   c) Engineering, Finance and IT: register your YubiKey under Settings > Security Methods within 7 days.

2. CONNECT TO THE VPN (Zscaler Private Access)
   a) Install "Zscaler" from Self Service (Mac) or Company Portal (Windows).
   b) Sign in with your Okta account. The icon turns green when you are connected.
   c) Keep it on whenever you use public Wi-Fi or access internal admin tools.

3. REQUEST TIME OFF
   a) Workday > Time Off > Request Time Off. Choose the leave type and dates.
   b) Add a note for your manager and submit. Request 3+ day leave 10 working days ahead.

4. ENROLL IN BENEFITS (deadline: 30 days after your start date)
   a) Workday > Benefits > Benefit Elections > Let's Get Started.
   b) Add dependents first, then choose your plans and coverage level.
   c) Review the summary, submit, and save the confirmation PDF.

5. REQUEST SOFTWARE OR SYSTEM ACCESS
   a) Approved apps: install from Self Service (Mac) or Company Portal (Windows).
   b) Anything else: it.northwindlabs.com > Request Access. Approvals take 1-2 business days;
      new SaaS tools need a security review (about 5 business days).

6. REPORT A PHISHING EMAIL
   a) Do not click links or open attachments.
   b) Click "Report Phish" in Gmail. Security replies within 4 business hours.

7. BOOK A DESK (hybrid offices)
   a) Open the Robin app or robin.northwindlabs.com.
   b) Pick your office and floor, choose a desk in your team zone, and confirm.

8. SUBMIT AN EXPENSE OR HOME-OFFICE STIPEND
   a) Workday > Expenses > Create Expense Report. Attach itemised receipts above USD 25 / INR 2,000.
   b) Home-office stipend: use expense type "Home Office - One Time" within 60 days of joining.

9. LOST DEVICE OR SECURITY INCIDENT
   Report within 1 hour: security@northwindlabs.com, #security-incidents, or +1-512-555-0142.
"""


# --------------------------------------------------------------------------- Directory

IN_FIRST = [
    "Aarav", "Ananya", "Arjun", "Diya", "Ishaan", "Kavya", "Rohan", "Sneha", "Vikram", "Priya", "Aditya", "Meera",
    "Karthik", "Nisha", "Rahul", "Pooja", "Siddharth", "Lakshmi", "Varun", "Divya", "Harsha", "Swathi", "Naveen",
    "Revathi", "Abhishek", "Deepika", "Manoj", "Shruti", "Pranav", "Keerthi", "Suresh", "Anjali", "Rajesh", "Tanvi",
    "Gautam", "Bhavana", "Nikhil", "Ritu", "Sanjay", "Aishwarya",
]
IN_LAST = [
    "Sharma", "Iyer", "Reddy", "Nair", "Patel", "Rao", "Menon", "Gupta", "Kulkarni", "Joshi", "Krishnan", "Bhat",
    "Verma", "Pillai", "Desai", "Chowdary", "Naidu", "Banerjee", "Shetty", "Hegde", "Agarwal", "Subramanian",
    "Mehta", "Kapoor",
]
US_FIRST = [
    "James", "Olivia", "Michael", "Emma", "David", "Sophia", "Daniel", "Ava", "Matthew", "Mia", "Christopher",
    "Isabella", "Andrew", "Emily", "Joshua", "Abigail", "Ryan", "Madison", "Brandon", "Chloe", "Marcus", "Grace",
    "Luis", "Camila", "Kevin", "Hannah", "Jamal", "Aaliyah", "Ethan", "Zoe", "Carlos", "Natalie", "Tyler", "Leah",
]
US_LAST = [
    "Johnson", "Williams", "Brown", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Wilson", "Anderson",
    "Thomas", "Moore", "Jackson", "Lee", "Thompson", "White", "Harris", "Clark", "Lewis", "Walker", "Nguyen",
    "Patel", "Kim", "Lopez", "Hall", "Young", "Allen", "Wright",
]

LOCATIONS = {
    "Austin": ("United States", "Hybrid"),
    "Remote-US": ("United States", "Remote"),
    "Bengaluru": ("India", "Hybrid"),
    "Hyderabad": ("India", "Hybrid"),
}

EXECUTIVES = [
    ("Chief Executive Officer", "Executive", "Leadership", "Austin", None),
    ("Chief Technology Officer", "Engineering", "Leadership", "Bengaluru", 0),
    ("Chief Product Officer", "Product & Design", "Leadership", "Austin", 0),
    ("Chief Revenue Officer", "Sales", "Leadership", "Austin", 0),
    ("Chief People Officer", "People", "Leadership", "Austin", 0),
    ("Chief Financial Officer", "Finance", "Leadership", "Austin", 0),
    ("Chief Information Security Officer", "IT & Security", "Leadership", "Austin", 0),
    ("VP Engineering, India", "Engineering", "Leadership", "Bengaluru", 1),
]
EXEC_FOR_DEPT = {
    "Engineering": 7, "Data Science": 1, "Product & Design": 2, "Sales": 3, "Customer Success": 3,
    "Marketing": 3, "People": 4, "Finance": 5, "Legal": 5, "IT & Security": 6,
}

TEAMS = [
    ("Engineering", "Platform Engineering", ["Bengaluru"], "Engineering Manager, Platform",
     ["Software Engineer I", "Software Engineer II", "Senior Software Engineer", "Staff Software Engineer"], 15),
    ("Engineering", "Data Engineering", ["Hyderabad"], "Engineering Manager, Data",
     ["Data Engineer I", "Data Engineer II", "Senior Data Engineer"], 11),
    ("Engineering", "Web Application", ["Bengaluru", "Hyderabad"], "Engineering Manager, Web",
     ["Frontend Engineer II", "Senior Frontend Engineer", "Software Engineer II"], 12),
    ("Engineering", "Site Reliability", ["Austin", "Remote-US"], "SRE Manager",
     ["Site Reliability Engineer", "Senior Site Reliability Engineer"], 7),
    ("Engineering", "QA Automation", ["Hyderabad"], "QA Manager",
     ["QA Engineer", "Senior QA Engineer", "SDET II"], 8),
    ("Product & Design", "Product Management", ["Austin", "Bengaluru"], "Director of Product",
     ["Associate Product Manager", "Product Manager", "Senior Product Manager"], 7),
    ("Product & Design", "UX Design", ["Bengaluru"], "Design Manager",
     ["Product Designer", "Senior Product Designer", "UX Researcher"], 6),
    ("Data Science", "Machine Learning", ["Bengaluru"], "Machine Learning Manager",
     ["Data Scientist", "Senior Data Scientist", "ML Engineer"], 7),
    ("Sales", "Enterprise Sales", ["Austin", "Remote-US"], "Regional Sales Director, North America",
     ["Account Executive", "Senior Account Executive", "Sales Engineer"], 10),
    ("Sales", "Sales Development", ["Austin"], "Sales Development Manager",
     ["Sales Development Representative", "Senior Sales Development Representative"], 8),
    ("Sales", "APAC Sales", ["Bengaluru"], "Sales Director, APAC",
     ["Account Executive", "Sales Engineer"], 6),
    ("Customer Success", "Customer Success", ["Austin", "Remote-US"], "Customer Success Lead",
     ["Customer Success Manager", "Senior Customer Success Manager"], 8),
    ("Customer Success", "Technical Support", ["Hyderabad"], "Support Manager",
     ["Support Engineer I", "Support Engineer II", "Senior Support Engineer"], 10),
    ("Marketing", "Growth Marketing", ["Remote-US", "Austin"], "Head of Growth Marketing",
     ["Marketing Manager", "Content Marketing Manager", "Marketing Operations Specialist"], 6),
    ("People", "People Operations", ["Bengaluru", "Austin"], "People Operations Manager",
     ["People Partner", "HR Generalist", "People Operations Specialist"], 6),
    ("People", "Talent Acquisition", ["Austin", "Bengaluru"], "Talent Acquisition Manager",
     ["Technical Recruiter", "Recruiting Coordinator"], 5),
    ("Finance", "Finance & Payroll", ["Hyderabad", "Austin"], "Finance Controller",
     ["Payroll Specialist", "Financial Analyst", "Accountant"], 6),
    ("IT & Security", "IT Operations", ["Bengaluru", "Austin"], "IT Manager",
     ["IT Support Engineer", "Systems Administrator"], 5),
    ("IT & Security", "Information Security", ["Austin"], "Security Manager",
     ["Security Engineer", "Senior Security Engineer", "GRC Analyst"], 5),
    ("Legal", "Legal & Compliance", ["Austin"], "Senior Legal Counsel",
     ["Compliance Analyst", "Contracts Manager"], 3),
]

NEW_HIRE_TEAMS = [
    "Platform Engineering", "Platform Engineering", "Data Engineering", "Web Application", "Site Reliability",
    "QA Automation", "Product Management", "UX Design", "Machine Learning", "Enterprise Sales", "Sales Development",
    "Sales Development", "APAC Sales", "Customer Success", "Technical Support", "Technical Support",
    "Growth Marketing", "Talent Acquisition", "Finance & Payroll", "Information Security", "IT Operations",
    "Web Application",
]


def build_directory(rng: random.Random) -> list[dict]:
    used_emails: set[str] = set()
    people: list[dict] = []

    def make_person(country: str) -> tuple[str, str, str]:
        first_pool, last_pool = (IN_FIRST, IN_LAST) if country == "India" else (US_FIRST, US_LAST)
        while True:
            first, last = rng.choice(first_pool), rng.choice(last_pool)
            email = f"{first}.{last}@{DOMAIN}".lower()
            if email not in used_emails:
                used_emails.add(email)
                return first, last, email

    def add(title, dept, team, loc, manager, start, emp_type="Full-time"):
        country, mode = LOCATIONS[loc]
        first, last, email = make_person(country)
        person = {
            "employee_id": f"NWL{1001 + len(people)}",
            "first_name": first,
            "last_name": last,
            "work_email": email,
            "job_title": title,
            "department": dept,
            "team": team,
            "manager_id": manager["employee_id"] if manager else "",
            "manager_name": f"{manager['first_name']} {manager['last_name']}" if manager else "",
            "location": loc,
            "country": country,
            "work_mode": mode,
            "employment_type": emp_type,
            "start_date": start,
            "is_new_hire": "Yes" if start >= date(2026, 10, 1) else "No",
            "onboarding_buddy_id": "",
            "onboarding_buddy_name": "",
            "slack_handle": "@" + email.split("@")[0],
            "desk_extension": "" if mode == "Remote" else str(rng.randint(2100, 6899)),
        }
        people.append(person)
        return person

    def past_date(start_year: int) -> date:
        lo = date(start_year, 1, 1).toordinal()
        hi = date(2026, 9, 21).toordinal()
        return date.fromordinal(rng.randint(lo, hi))

    execs: list[dict] = []
    for title, dept, team, loc, mgr_idx in EXECUTIVES:
        manager = execs[mgr_idx] if mgr_idx is not None else None
        execs.append(add(title, dept, team, loc, manager, past_date(2016 if mgr_idx is None else 2017)))
    execs[0]["start_date"] = date(2016, 3, 1)

    managers: dict[str, dict] = {}
    for dept, team, locs, mgr_title, ic_titles, headcount in TEAMS:
        mgr = add(mgr_title, dept, team, locs[0], execs[EXEC_FOR_DEPT[dept]], past_date(2017))
        managers[team] = mgr
        for _ in range(headcount - 1):
            loc = locs[0] if len(locs) == 1 or rng.random() < 0.7 else rng.choice(locs[1:])
            emp_type = "Contractor" if rng.random() < 0.05 else "Full-time"
            add(rng.choice(ic_titles), dept, team, loc, mgr, past_date(2018), emp_type)

    for i, team in enumerate(NEW_HIRE_TEAMS):
        dept, _, locs, _, ic_titles, _ = next(t for t in TEAMS if t[1] == team)
        start = COHORT_DATES[i % len(COHORT_DATES)]
        loc = locs[0] if rng.random() < 0.75 else rng.choice(locs)
        title = ic_titles[0] if rng.random() < 0.6 else rng.choice(ic_titles)
        hire = add(title, dept, team, loc, managers[team], start)
        candidates = [
            p for p in people
            if p["team"] == team and p["employee_id"] != managers[team]["employee_id"]
            and p["is_new_hire"] == "No" and (TODAY - p["start_date"]).days > 365
        ]
        buddy = rng.choice(candidates)
        hire["onboarding_buddy_id"] = buddy["employee_id"]
        hire["onboarding_buddy_name"] = f"{buddy['first_name']} {buddy['last_name']}"

    interns = [("Platform Engineering", "Software Engineering Intern"), ("Machine Learning", "Data Science Intern"),
               ("UX Design", "Design Intern")]
    for team, title in interns:
        dept, _, locs, *_ = next(t for t in TEAMS if t[1] == team)
        add(title, dept, team, locs[0], managers[team], date(2026, 7, 6), "Intern")

    return people


def write_directory(people: list[dict], path: Path) -> None:
    fields = list(people[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for p in people:
            w.writerow({**p, "start_date": p["start_date"].isoformat()})


# --------------------------------------------------------------------------- Checklist

CHECKLIST = [
    # task_id, offset, phase, task, details, owner, country, department, system, mandatory, reference
    ("OB-001", -14, "Pre-boarding", "Send welcome email with Day 1 agenda", "Include start time, office address or Zoom link, documents to bring and buddy name.", "People Team", "All", "All", "Workday", "Yes", "Employee Handbook s.7"),
    ("OB-002", -14, "Pre-boarding", "Confirm background verification is cleared", "Offer is contingent on clearance; escalate any delay to the hiring manager.", "People Team", "All", "All", "BGV vendor portal", "Yes", "Employee Handbook s.3"),
    ("OB-003", -10, "Pre-boarding", "Create Workday worker record and employee ID", "Employee ID format NWL followed by four digits.", "People Team", "All", "All", "Workday", "Yes", "Employee Handbook s.3"),
    ("OB-004", -7, "Pre-boarding", "Prepare and enroll laptop", "Enroll in Jamf or Intune, enable disk encryption, install CrowdStrike Falcon.", "IT", "All", "All", "Jamf / Intune", "Yes", "IT Security Policy s.4"),
    ("OB-005", -7, "Pre-boarding", "Create Okta, Google Workspace and Slack accounts", "Send Okta activation link to the new hire's personal email.", "IT", "All", "All", "Okta", "Yes", "IT Security Policy s.2"),
    ("OB-006", -7, "Pre-boarding", "Ship laptop to home address", "Use tracked courier; share tracking number with the new hire.", "IT", "United States", "All", "IT Service Portal", "Yes", "First Week FAQ"),
    ("OB-007", -5, "Pre-boarding", "Assign onboarding buddy", "Pick a teammate with 12+ months tenure who is not the manager; notify both.", "Manager", "All", "All", "Workday", "Yes", "Employee Handbook s.7"),
    ("OB-008", -5, "Pre-boarding", "Draft 30-60-90 day plan", "Outline goals, first project and key stakeholders.", "Manager", "All", "All", "Workday Goals", "Yes", "Employee Handbook s.7"),
    ("OB-009", -3, "Pre-boarding", "Book desk for first week", "Reserve a desk in the team zone for Tuesday to Thursday.", "People Team", "All", "All", "Robin", "No", "How-To Guides s.7"),
    ("OB-010", -3, "Pre-boarding", "Add new hire to team channels and meetings", "Team Slack channel, stand-ups, team calendar and distribution lists.", "Manager", "All", "All", "Slack / Google Calendar", "Yes", ""),
    ("OB-011", -2, "Pre-boarding", "Request role-based access", "GitHub, Jira and Confluence for Engineering; Salesforce for Sales and CS.", "Manager", "All", "All", "IT Service Portal", "Yes", "IT Security Policy s.2"),
    ("OB-012", 0, "Day 1", "Attend New Hire Orientation", "Starts 09:30 local time (NWL-ORI-101).", "New Hire", "All", "All", "Northwind Learn", "Yes", "First Week FAQ"),
    ("OB-013", 0, "Day 1", "Collect ID badge and laptop", "Office-based hires collect from the IT desk during orientation.", "New Hire", "All", "All", "", "Yes", "First Week FAQ"),
    ("OB-014", 0, "Day 1", "Activate Okta and enroll MFA", "Okta Verify push plus a backup factor; SMS is not allowed.", "New Hire", "All", "All", "Okta", "Yes", "How-To Guides s.1"),
    ("OB-015", 0, "Day 1", "Set up 1Password", "Store your Okta password in the company 1Password account.", "New Hire", "All", "All", "1Password", "Yes", "IT Security Policy s.3"),
    ("OB-016", 0, "Day 1", "Meet your manager", "Discuss role expectations and walk through the draft 30-60-90 plan.", "Manager", "All", "All", "", "Yes", "Employee Handbook s.7"),
    ("OB-017", 0, "Day 1", "Meet your onboarding buddy", "Schedule a weekly 30-minute check-in for 6 weeks.", "Buddy", "All", "All", "Google Calendar", "Yes", "Employee Handbook s.7"),
    ("OB-018", 0, "Day 1", "Complete Form I-9 Section 1", "Bring original identity and work-authorisation documents.", "New Hire", "United States", "All", "Workday", "Yes", "Employee Handbook s.5"),
    ("OB-019", 0, "Day 1", "Upload KYC and bank details", "PAN, Aadhaar and cancelled cheque or bank statement.", "New Hire", "India", "All", "Workday", "Yes", "Employee Handbook s.5"),
    ("OB-020", 2, "Week 1", "Verify I-9 documents (Section 2)", "Must be completed within 3 business days of start.", "People Team", "United States", "All", "Workday", "Yes", "Employee Handbook s.5"),
    ("OB-021", 2, "Week 1", "Submit W-4 and direct deposit", "Due by end of Day 3 to be paid on the next payday.", "New Hire", "United States", "All", "Workday", "Yes", "Employee Handbook s.5"),
    ("OB-022", 3, "Week 1", "Update emergency contact and personal details", "Address, emergency contact and pronouns.", "New Hire", "All", "All", "Workday", "Yes", "Employee Handbook s.3"),
    ("OB-023", 4, "Week 1", "Install Zscaler and confirm VPN access", "Required for internal admin tools and production.", "New Hire", "All", "All", "Zscaler Private Access", "Yes", "How-To Guides s.2"),
    ("OB-024", 4, "Week 1", "Join core Slack channels", "#announcements, #ask-people, #it-helpdesk, #new-joiners and team channel.", "New Hire", "All", "All", "Slack", "No", "First Week FAQ"),
    ("OB-025", 5, "Week 1", "Read the Employee Handbook and IT Security Policy", "Note any questions for your buddy or manager.", "New Hire", "All", "All", "Confluence", "Yes", "NWL-HR-001, NWL-SEC-003"),
    ("OB-026", 5, "Week 1", "Agree 30-60-90 goals in Workday", "Manager and new hire finalise goals in the first 1:1.", "Manager", "All", "All", "Workday Goals", "Yes", "Employee Handbook s.7"),
    ("OB-027", 5, "Week 1", "Team welcome lunch or virtual coffee", "Expense under team events.", "Manager", "All", "All", "Workday Expenses", "No", ""),
    ("OB-028", 7, "Week 1", "Acknowledge the Code of Conduct", "Due within 7 days of start date.", "New Hire", "All", "All", "Workday", "Yes", "Code of Conduct s.1"),
    ("OB-029", 7, "Week 1", "Complete Code of Conduct and Ethics training", "Course NWL-COC-101.", "New Hire", "All", "All", "Northwind Learn", "Yes", "Code of Conduct s.1"),
    ("OB-030", 7, "Week 1", "Register YubiKey", "Required for Engineering, Finance and IT.", "New Hire", "All", "Engineering; Finance; IT & Security", "Okta", "Yes", "IT Security Policy s.2"),
    ("OB-031", 14, "Weeks 2-4", "Complete Security Awareness Essentials", "Course NWL-SEC-101.", "New Hire", "All", "All", "Northwind Learn", "Yes", "IT Security Policy s.11"),
    ("OB-032", 14, "Weeks 2-4", "Complete Dev Environment and CI/CD onboarding", "Course NWL-ENG-110; set up local environment with your buddy.", "New Hire", "All", "Engineering", "Northwind Learn", "Yes", ""),
    ("OB-033", 21, "Weeks 2-4", "Ship your first change to production", "Pair with your buddy on a small, low-risk change.", "New Hire", "All", "Engineering", "GitHub", "No", ""),
    ("OB-034", 30, "Weeks 2-4", "Enroll in benefits", "Deadline is 30 calendar days from start date.", "New Hire", "All", "All", "Workday Benefits", "Yes", "Benefits Enrollment workbook"),
    ("OB-035", 30, "Weeks 2-4", "Submit investment declaration (Form 12BB)", "Otherwise tax is deducted without exemptions.", "New Hire", "India", "All", "Workday", "Yes", "Employee Handbook s.5"),
    ("OB-036", 30, "Weeks 2-4", "Complete Data Privacy and Protection training", "Course NWL-PRV-101.", "New Hire", "All", "All", "Northwind Learn", "Yes", "Code of Conduct s.6"),
    ("OB-037", 30, "Weeks 2-4", "Complete POSH Awareness training", "Course NWL-POSH-101.", "New Hire", "India", "All", "Northwind Learn", "Yes", "Code of Conduct s.3"),
    ("OB-038", 30, "Weeks 2-4", "Complete Harassment Prevention training", "Course NWL-AHT-101.", "New Hire", "United States", "All", "Northwind Learn", "Yes", "Code of Conduct s.3"),
    ("OB-039", 30, "Weeks 2-4", "Complete Responsible Use of AI Tools training", "Course NWL-AI-101.", "New Hire", "All", "All", "Northwind Learn", "Yes", "Code of Conduct s.7"),
    ("OB-040", 30, "Weeks 2-4", "Complete Anti-Bribery and Corruption training", "Course NWL-ABC-201.", "New Hire", "All", "Sales; Finance; Customer Success", "Northwind Learn", "Yes", "Code of Conduct s.5"),
    ("OB-041", 30, "Weeks 2-4", "Complete Product Fundamentals", "Course NWL-PRD-101.", "New Hire", "All", "All", "Northwind Learn", "Yes", ""),
    ("OB-042", 30, "Weeks 2-4", "Complete Secure Coding Practices", "Course NWL-ENG-120.", "New Hire", "All", "Engineering", "Northwind Learn", "Yes", "IT Security Policy s.9"),
    ("OB-043", 30, "Weeks 2-4", "Complete Sales Playbook and CRM training", "Course NWL-SAL-110; Salesforce access required.", "New Hire", "All", "Sales", "Northwind Learn", "Yes", ""),
    ("OB-044", 30, "Weeks 2-4", "Complete Customer Success Toolkit", "Course NWL-CS-110.", "New Hire", "All", "Customer Success", "Northwind Learn", "Yes", ""),
    ("OB-045", 30, "Weeks 2-4", "30-day check-in", "Review progress against the 30-60-90 plan.", "Manager", "All", "All", "Workday Goals", "Yes", "Employee Handbook s.7"),
    ("OB-046", 30, "Weeks 2-4", "30-day onboarding pulse survey", "Five-question survey sent automatically.", "People Team", "All", "All", "Workday", "No", ""),
    ("OB-047", 45, "Days 31-90", "Shadow the on-call rotation", "Course NWL-ENG-130 due by Day 60.", "New Hire", "All", "Engineering (Site Reliability; Platform Engineering)", "PagerDuty", "Yes", "IT Security Policy s.9"),
    ("OB-048", 60, "Days 31-90", "Claim home-office stipend", "One-time USD 500 / INR 25,000; expense type 'Home Office - One Time'.", "New Hire", "All", "All", "Workday Expenses", "No", "Employee Handbook s.6"),
    ("OB-049", 60, "Days 31-90", "60-day check-in with buddy feedback", "Manager collects feedback from the onboarding buddy.", "Manager", "All", "All", "Workday Goals", "Yes", "Employee Handbook s.7"),
    ("OB-050", 90, "Days 31-90", "90-day review", "Confirm goals for the next quarter.", "Manager", "All", "All", "Workday Goals", "Yes", "Employee Handbook s.7"),
    ("OB-051", 90, "Days 31-90", "Close US introductory period", "People Team records completion in Workday.", "People Team", "United States", "All", "Workday", "Yes", "Employee Handbook s.3"),
    ("OB-052", 90, "Days 31-90", "Complete New Manager Essentials", "Course NWL-MGR-201 for people managers.", "New Hire", "All", "People managers", "Northwind Learn", "Yes", ""),
    ("OB-053", 90, "Days 31-90", "Complete onboarding feedback survey", "Helps us improve onboarding for future joiners.", "New Hire", "All", "All", "Workday", "No", ""),
    ("OB-054", 150, "Probation", "Probation confirmation review", "Manager submits recommendation in month 5.", "Manager", "India", "All", "Workday", "Yes", "Employee Handbook s.3"),
    ("OB-055", 180, "Probation", "Issue confirmation letter", "People Team issues letter after a positive review.", "People Team", "India", "All", "Workday", "Yes", "Employee Handbook s.3"),
]


def _due_label(offset: int) -> str:
    if offset < 0:
        return f"{-offset} days before start"
    if offset == 0:
        return "Day 1"
    return f"Within {offset} days"


def write_checklist(path: Path) -> None:
    header = ["task_id", "phase", "due_day_offset", "due", "task", "details", "owner", "applies_to_country",
              "applies_to_department", "system_or_tool", "mandatory", "reference_document"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for tid, off, phase, task, details, owner, country, dept, system, mandatory, ref in CHECKLIST:
            w.writerow([tid, phase, off, _due_label(off), task, details, owner, country, dept, system, mandatory, ref])


# --------------------------------------------------------------------------- Excel helpers

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def _sheet(wb: Workbook, title: str, header: list[str], rows: list[list], widths: list[int] | None = None, first=False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title
    ws.append(header)
    for r in rows:
        ws.append(r)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = ws.dimensions
    for i, h in enumerate(header, start=1):
        width = widths[i - 1] if widths else max(12, min(45, len(h) + 4))
        ws.column_dimensions[get_column_letter(i)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, date):
                cell.number_format = "yyyy-mm-dd"
    return ws


# --------------------------------------------------------------------------- Benefits

PLANS = [
    # id, country, category, name, provider, coverage, tiers(EE, EE+Sp, EE+Ch, Fam), currency, employer, type, eligibility
    ("IN-MED-01", "India", "Medical", "Group Medical - Family Floater", "Suraksha General Insurance", "INR 5,00,000 floater for employee, spouse and up to 2 children; cashless at 9,000+ hospitals", (0, 0, 0, 0), "INR", "100% of premium", "Automatic", "All full-time employees from Day 1"),
    ("IN-MED-02", "India", "Medical", "Super Top-up Cover", "Suraksha General Insurance", "Additional INR 10,00,000 cover above the base floater", (450, 650, 650, 850), "INR", "None (voluntary)", "Elective", "Full-time employees"),
    ("IN-MED-03", "India", "Medical", "Parental Cover", "Suraksha General Insurance", "INR 3,00,000 floater for up to 2 parents or parents-in-law", (1250, 1250, 1250, 1250), "INR", "50% of premium", "Elective", "Full-time employees"),
    ("IN-LIF-01", "India", "Life", "Group Term Life", "LifeShield Assurance", "3x fixed annual CTC", (0, 0, 0, 0), "INR", "100% of premium", "Automatic", "All full-time employees from Day 1"),
    ("IN-ACC-01", "India", "Accident", "Group Personal Accident", "LifeShield Assurance", "5x fixed annual CTC for accidental death or disability", (0, 0, 0, 0), "INR", "100% of premium", "Automatic", "All full-time employees from Day 1"),
    ("IN-RET-01", "India", "Retirement", "Employees' Provident Fund", "EPFO", "12% of basic salary from employee and 12% from employer", (None, None, None, None), "INR", "12% of basic salary", "Mandatory", "All full-time employees"),
    ("IN-RET-02", "India", "Retirement", "National Pension System (Corporate)", "NPS Trust", "Employer contribution up to 10% of basic via salary restructuring", (None, None, None, None), "INR", "Up to 10% of basic (from CTC)", "Elective", "Full-time employees"),
    ("IN-WEL-01", "India", "Wellness", "Wellness Allowance", "Northwind Labs", "Reimbursement for gym, sports or wellness apps up to INR 15,000 per year", (0, 0, 0, 0), "INR", "INR 15,000 per year", "Automatic", "All full-time employees"),
    ("IN-EAP-01", "India", "Wellbeing", "Employee Assistance Program", "MindHaven", "6 confidential counselling sessions per person per year, 24x7 helpline", (0, 0, 0, 0), "INR", "100%", "Automatic", "Employees and dependents"),
    ("US-MED-01", "United States", "Medical", "Cascade Health PPO 500", "Cascade Health", "USD 500 deductible, 20% coinsurance, USD 3,500 out-of-pocket max (individual)", (85, 310, 260, 455), "USD", "About 85% of premium", "Elective", "Full-time employees, coverage from Day 1"),
    ("US-MED-02", "United States", "Medical", "Cascade Health HDHP 2000 + HSA", "Cascade Health", "USD 2,000 deductible; HSA seed USD 1,000 (individual) or USD 2,000 (family)", (35, 140, 120, 210), "USD", "About 90% of premium plus HSA seed", "Elective", "Full-time employees, coverage from Day 1"),
    ("US-DEN-01", "United States", "Dental", "BrightSmile Dental PPO", "BrightSmile", "Preventive 100%, basic 80%, major 50%; USD 2,000 annual max", (8, 18, 20, 32), "USD", "About 80% of premium", "Elective", "Full-time employees"),
    ("US-VIS-01", "United States", "Vision", "ClearView Vision", "ClearView", "Annual eye exam; USD 200 frame or contact lens allowance", (3, 7, 7, 11), "USD", "About 75% of premium", "Elective", "Full-time employees"),
    ("US-LIF-01", "United States", "Life", "Basic Life and AD&D", "LifeShield Assurance", "2x annual salary up to USD 500,000", (0, 0, 0, 0), "USD", "100% of premium", "Automatic", "All full-time employees"),
    ("US-LIF-02", "United States", "Life", "Supplemental Life", "LifeShield Assurance", "Up to 5x salary; age-rated premium", (None, None, None, None), "USD", "None (voluntary)", "Elective", "Full-time employees"),
    ("US-DIS-01", "United States", "Disability", "Short and Long-Term Disability", "LifeShield Assurance", "STD 60% of salary up to 12 weeks; LTD 60% up to USD 15,000/month", (0, 0, 0, 0), "USD", "100% of premium", "Automatic", "All full-time employees"),
    ("US-RET-01", "United States", "Retirement", "401(k) Plan", "Summit Retirement", "100% match on first 4% of salary; immediate vesting", (None, None, None, None), "USD", "Up to 4% of salary", "Elective", "Full-time employees from first paycheck"),
    ("US-FSA-01", "United States", "Spending account", "Dependent Care FSA", "Summit Benefits", "Pre-tax dependent care up to the IRS annual limit", (None, None, None, None), "USD", "None", "Elective", "Full-time employees"),
    ("US-WEL-01", "United States", "Wellness", "Wellness Stipend", "Northwind Labs", "Reimbursement for gym, fitness or wellness apps up to USD 600 per year", (0, 0, 0, 0), "USD", "USD 600 per year", "Automatic", "All full-time employees"),
    ("US-EAP-01", "United States", "Wellbeing", "Employee Assistance Program", "MindHaven", "6 confidential counselling sessions per person per year, 24x7 helpline", (0, 0, 0, 0), "USD", "100%", "Automatic", "Employees and dependents"),
]

TIERS = ["Employee only", "Employee + Spouse", "Employee + Children", "Family"]
TIER_DEPENDENTS = {"Employee only": 0, "Employee + Spouse": 1, "Employee + Children": 2, "Family": 3}


def write_benefits(people: list[dict], rng: random.Random, path: Path) -> None:
    wb = Workbook()
    plan_rows = []
    for pid, country, cat, name, prov, cov, tiers, cur, employer, etype, elig in PLANS:
        plan_rows.append([pid, country, cat, name, prov, cov, *tiers, cur, employer, etype, elig, date(2026, 1, 1)])
    _sheet(
        wb, "Plan Catalog",
        ["plan_id", "country", "category", "plan_name", "provider", "coverage_summary",
         "monthly_cost_employee_only", "monthly_cost_employee_spouse", "monthly_cost_employee_children",
         "monthly_cost_family", "currency", "employer_contribution", "enrollment_type", "eligibility", "plan_year_start"],
        plan_rows, [11, 14, 15, 32, 24, 55, 14, 14, 14, 14, 9, 28, 14, 34, 14], first=True,
    )

    plans = {p[0]: p for p in PLANS}
    hires = [p for p in people if p["is_new_hire"] == "Yes" and p["employment_type"] == "Full-time"]
    rows = []
    for h in hires:
        start = h["start_date"]
        deadline = start + timedelta(days=30)
        if start > TODAY:
            progress = "Not started"
        elif start <= date(2026, 10, 5):
            progress = "Complete"
        else:
            progress = rng.choice(["In progress", "Not started", "Complete"])
        tier = rng.choices(TIERS, weights=[45, 20, 10, 25])[0]

        if h["country"] == "India":
            elections = [("Medical", "IN-MED-01", "Enrolled"),
                         ("Medical", "IN-MED-02", rng.choice(["Enrolled", "Waived"])),
                         ("Medical", "IN-MED-03", rng.choice(["Enrolled", "Waived", "Waived"])),
                         ("Retirement", "IN-RET-02", rng.choice(["Enrolled", "Waived"]))]
        else:
            med = rng.choices(["US-MED-01", "US-MED-02", "WAIVE"], weights=[50, 40, 10])[0]
            elections = [("Medical", med if med != "WAIVE" else "US-MED-01", "Waived" if med == "WAIVE" else "Enrolled"),
                         ("Dental", "US-DEN-01", rng.choice(["Enrolled", "Enrolled", "Waived"])),
                         ("Vision", "US-VIS-01", rng.choice(["Enrolled", "Waived"])),
                         ("Retirement", "US-RET-01", "Enrolled")]

        submitted = start + timedelta(days=rng.randint(3, 20)) if progress == "Complete" else None
        for cat, pid, election in elections:
            plan = plans[pid]
            tier_cost = None
            level = ""
            if progress == "Not started":
                election = "Pending"
            elif progress == "In progress" and rng.random() < 0.5:
                election = "Pending"
            if election == "Enrolled" and cat != "Retirement":
                level = "Employee only" if pid == "IN-MED-03" else tier
                costs = plan[6]
                tier_cost = costs[TIERS.index(level)] if costs[0] is not None else None
            note = ""
            if pid == "US-RET-01" and election == "Enrolled":
                note = f"Contribution {rng.choice([4, 5, 6, 8, 10])}% of salary"
            if pid == "IN-RET-02" and election == "Enrolled":
                note = f"Employer NPS {rng.choice([5, 8, 10])}% of basic"
            if pid == "IN-MED-03" and election == "Enrolled":
                note = "2 parents covered"
            rows.append([
                h["employee_id"], f"{h['first_name']} {h['last_name']}", h["country"], h["location"], start, deadline,
                cat, pid, plan[3], election, level, TIER_DEPENDENTS.get(level, "") if level else "",
                tier_cost, plan[7], submitted if election != "Pending" else None, progress, note,
            ])
    _sheet(
        wb, "New Hire Enrollment",
        ["employee_id", "employee_name", "country", "location", "start_date", "enrollment_deadline", "benefit_category",
         "plan_id", "plan_name", "election", "coverage_level", "dependents_covered", "employee_monthly_cost",
         "currency", "submitted_on", "overall_status", "notes"],
        rows, [12, 22, 14, 12, 12, 14, 14, 11, 32, 10, 20, 11, 12, 9, 12, 14, 30],
    )

    rules = [
        ["Enrollment window", "30 calendar days from your start date. Coverage is backdated to your start date."],
        ["If you miss the window", "You keep automatic benefits only and can change elections at open enrollment (1-15 November) or after a qualifying life event."],
        ["Qualifying life events", "Marriage, divorce, birth or adoption, loss of other coverage. Report in Workday within 30 days of the event."],
        ["Open enrollment 2026", "1 November 2026 to 15 November 2026, for the plan year starting 1 January 2027."],
        ["Where to enroll", "Workday > Benefits > Benefit Elections."],
        ["Documents needed", "Dependent names, dates of birth and (US) Social Security numbers; (India) parents' dates of birth for parental cover."],
        ["Payroll deduction", "Employee costs are deducted monthly (India) or split across the two paychecks in a month (US)."],
        ["Contact", "benefits@northwindlabs.com or #ask-people on Slack."],
    ]
    ws = _sheet(wb, "Key Dates and Rules", ["topic", "details"], rules, [26, 110])
    for row in ws.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(path)


# --------------------------------------------------------------------------- Training

COURSES = [
    # code, title, category, mandatory, audience, duration_min, due_days, delivery, sessions_per_region(weekday, every_n_weeks, regions)
    ("NWL-ORI-101", "New Hire Orientation", "Onboarding", "Yes", "All new hires", 180, 0, "In-person / Zoom", (0, 1, "both")),
    ("NWL-COC-101", "Code of Conduct and Ethics", "Compliance", "Yes", "All employees", 45, 7, "Live virtual", (2, 1, "both")),
    ("NWL-SEC-101", "Security Awareness Essentials", "Security", "Yes", "All employees", 60, 14, "Live virtual", (3, 1, "both")),
    ("NWL-PRV-101", "Data Privacy and Protection", "Compliance", "Yes", "All employees", 45, 30, "Live virtual", (1, 2, "both")),
    ("NWL-POSH-101", "POSH Awareness", "Compliance", "Yes", "Employees in India", 90, 30, "In-person", (4, 2, "IN")),
    ("NWL-AHT-101", "Harassment Prevention", "Compliance", "Yes", "Employees in the US", 120, 30, "Live virtual", (4, 2, "US")),
    ("NWL-AI-101", "Responsible Use of AI Tools", "Security", "Yes", "All employees", 45, 30, "Live virtual", (2, 2, "both")),
    ("NWL-PRD-101", "Northwind Insights Product Fundamentals", "Product", "Yes", "All employees", 120, 30, "Live virtual", (3, 2, "both")),
    ("NWL-ABC-201", "Anti-Bribery and Corruption", "Compliance", "Yes", "Sales, Finance, Customer Success", 60, 30, "Live virtual", (1, 4, "both")),
    ("NWL-ENG-110", "Dev Environment and CI/CD Onboarding", "Engineering", "Yes", "Engineering", 180, 14, "In-person / Zoom", (1, 1, "both")),
    ("NWL-ENG-120", "Secure Coding Practices", "Engineering", "Yes", "Engineering", 120, 30, "Live virtual", (3, 2, "both")),
    ("NWL-ENG-130", "Production Access and On-call", "Engineering", "Yes", "Site Reliability, Platform Engineering", 120, 60, "Live virtual", (4, 4, "both")),
    ("NWL-DAT-110", "Data Platform and Analytics Stack", "Engineering", "No", "Data Engineering, Machine Learning", 120, 30, "Live virtual", (2, 4, "IN")),
    ("NWL-SAL-110", "Sales Playbook and Salesforce CRM", "Sales", "Yes", "Sales", 180, 30, "In-person / Zoom", (1, 4, "both")),
    ("NWL-CS-110", "Customer Success Toolkit", "Customer Success", "Yes", "Customer Success", 120, 30, "Live virtual", (2, 4, "both")),
    ("NWL-MGR-201", "New Manager Essentials", "Leadership", "Yes", "People managers", 240, 90, "In-person", (3, 4, "both")),
    ("NWL-COM-101", "Communicating in Hybrid Teams", "Professional skills", "No", "All employees", 90, 90, "Live virtual", (4, 4, "both")),
    ("NWL-WEL-101", "Benefits and Wellbeing Walkthrough", "Benefits", "No", "New hires", 60, 30, "Live virtual", (4, 2, "both")),
]

DESCRIPTIONS = {
    "NWL-ORI-101": "Company history, values, how we work, tools tour and Q&A with the People Team.",
    "NWL-COC-101": "Walkthrough of the Code of Conduct with real scenarios; required before acknowledgment.",
    "NWL-SEC-101": "Phishing, MFA, device security, data classification and incident reporting.",
    "NWL-PRV-101": "GDPR, CCPA and India DPDP Act basics; handling customer and employee personal data.",
    "NWL-POSH-101": "Prevention of Sexual Harassment Act 2013, the Internal Committee and how to raise a complaint.",
    "NWL-AHT-101": "US harassment and discrimination prevention, bystander intervention and reporting.",
    "NWL-AI-101": "Approved AI tools, what data you may and may not share, and reviewing AI output.",
    "NWL-PRD-101": "Product demo, core personas, pricing tiers and common customer use cases.",
    "NWL-ABC-201": "FCPA, India Prevention of Corruption Act, gifts register and hospitality limits.",
    "NWL-ENG-110": "Local setup, monorepo layout, CI/CD pipeline, code review and release process.",
    "NWL-ENG-120": "OWASP Top 10, secrets management with Vault, dependency scanning.",
    "NWL-ENG-130": "Just-in-time production access, incident roles, PagerDuty and runbooks.",
    "NWL-DAT-110": "Data warehouse, dbt models, orchestration and data quality checks.",
    "NWL-SAL-110": "Ideal customer profile, discovery framework, Salesforce opportunity stages.",
    "NWL-CS-110": "Health scores, QBR templates, renewal playbook and escalation paths.",
    "NWL-MGR-201": "1:1s, feedback, performance cycles, hiring and inclusive leadership.",
    "NWL-COM-101": "Async writing, effective meetings and collaboration across time zones.",
    "NWL-WEL-101": "Live walkthrough of medical, retirement and wellbeing benefits with Q&A.",
}

COURSE_OWNER_TEAM = {
    "Onboarding": "People Operations", "Compliance": "Legal & Compliance", "Security": "Information Security",
    "Product": "Product Management", "Engineering": "Platform Engineering", "Sales": "Enterprise Sales",
    "Customer Success": "Customer Success", "Leadership": "People Operations", "Professional skills": "People Operations",
    "Benefits": "People Operations",
}

ROOMS = {
    "IN": ["Bengaluru - Training Room Kaveri (4F)", "Hyderabad - Training Room Godavari (L6)"],
    "US": ["Austin - Training Room Colorado (Suite 400)"],
}
HOLIDAYS = {
    "IN": {date(2026, 11, 9), date(2026, 12, 25), date(2027, 1, 1), date(2027, 1, 14), date(2027, 1, 26)},
    "US": {date(2026, 11, 26), date(2026, 11, 27), date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 31), date(2027, 1, 1), date(2027, 1, 18)},
}


def _audience_match(course: tuple, person: dict) -> bool:
    code, audience = course[0], course[4]
    team, dept = person["team"], person["department"]
    if audience in ("All new hires", "All employees", "New hires"):
        return True
    if audience == "Employees in India":
        return person["country"] == "India"
    if audience == "Employees in the US":
        return person["country"] == "United States"
    if code == "NWL-MGR-201":
        return False
    groups = [g.strip() for g in audience.split(",")]
    return dept in groups or team in groups


def write_training(people: list[dict], rng: random.Random, path: Path) -> None:
    wb = Workbook()
    catalog = [[c[0], c[1], c[2], c[3], c[4], c[5], c[6] if c[6] else "Day 1", c[7], DESCRIPTIONS[c[0]]] for c in COURSES]
    ws = _sheet(
        wb, "Course Catalog",
        ["course_code", "course_title", "category", "mandatory", "audience", "duration_minutes",
         "due_within_days_of_start", "delivery_mode", "description"],
        catalog, [14, 38, 18, 10, 36, 10, 14, 17, 80], first=True,
    )
    for row in ws.iter_rows(min_row=2):
        row[8].alignment = Alignment(wrap_text=True, vertical="top")

    trainers_by_team: dict[str, list[str]] = {}
    for p in people:
        if p["is_new_hire"] == "No" and p["employment_type"] == "Full-time":
            trainers_by_team.setdefault(p["team"], []).append(f"{p['first_name']} {p['last_name']}")

    start_monday = date(2026, 10, 26)
    weeks = 14
    sessions = []
    sid = 1
    for code, title, cat, mand, aud, dur, due, delivery, (weekday, every, regions) in COURSES:
        region_list = ["IN", "US"] if regions == "both" else [regions]
        trainers = trainers_by_team[COURSE_OWNER_TEAM[cat]]
        for region in region_list:
            for w in range(0, weeks, every):
                if code == "NWL-ORI-101":
                    d = start_monday + timedelta(weeks=w)
                    if d not in COHORT_DATES and d < date(2026, 11, 30):
                        continue
                else:
                    d = start_monday + timedelta(weeks=w, days=weekday)
                if d in HOLIDAYS[region]:
                    continue
                if region == "IN":
                    start_t, tz = ("09:30" if code == "NWL-ORI-101" else rng.choice(["11:00", "14:30", "16:00"])), "IST"
                else:
                    start_t, tz = ("09:30" if code == "NWL-ORI-101" else rng.choice(["10:00", "13:00", "14:30"])), "CT"
                h, m = map(int, start_t.split(":"))
                end_min = h * 60 + m + dur
                end_t = f"{end_min // 60:02d}:{end_min % 60:02d}"
                in_person = delivery == "In-person" or (delivery == "In-person / Zoom" and rng.random() < 0.6)
                if in_person:
                    venue = rng.choice(ROOMS[region])
                    mode = "In-person"
                    capacity = 20
                else:
                    venue = f"Zoom: https://northwindlabs.zoom.us/j/{rng.randint(81000000000, 89999999999)}"
                    mode = "Virtual"
                    capacity = 40
                days_out = (d - TODAY).days
                fill = max(0.1, 1.0 - days_out / 120) if days_out > 0 else 1.0
                booked = min(capacity, int(capacity * fill * rng.uniform(0.6, 1.1)))
                status = "Full - join waitlist" if booked >= capacity else ("Few seats left" if booked >= capacity * 0.8 else "Open")
                sessions.append([
                    f"TS-{sid:04d}", code, title, mand, aud, mode, d, d.strftime("%A"), start_t, end_t, tz, venue,
                    rng.choice(trainers), capacity, booked, capacity - booked, status,
                ])
                sid += 1
    sessions.sort(key=lambda r: (r[6], r[10], r[8]))
    _sheet(
        wb, "Session Schedule",
        ["session_id", "course_code", "course_title", "mandatory", "audience", "delivery", "date", "day", "start_time",
         "end_time", "time_zone", "location_or_link", "trainer", "capacity", "seats_booked", "seats_available",
         "registration_status"],
        sessions, [10, 13, 36, 10, 30, 10, 12, 11, 9, 9, 9, 46, 22, 9, 10, 10, 18],
    )

    assignments = []
    for p in people:
        if p["is_new_hire"] != "Yes":
            continue
        for course in COURSES:
            if course[3] != "Yes" or not _audience_match(course, p):
                continue
            due = p["start_date"] + timedelta(days=course[6])
            if p["start_date"] > TODAY:
                status, completed = "Not started", None
            else:
                elapsed = (TODAY - p["start_date"]).days
                if elapsed >= course[6] and rng.random() < 0.85:
                    status = "Completed"
                    completed = p["start_date"] + timedelta(days=rng.randint(0, max(course[6], 1)))
                elif due < TODAY:
                    status, completed = "Overdue", None
                else:
                    status = rng.choice(["Registered", "In progress", "Not started"])
                    completed = None
            assignments.append([
                p["employee_id"], f"{p['first_name']} {p['last_name']}", p["team"], p["country"], p["start_date"],
                course[0], course[1], due, status, completed,
            ])
    _sheet(
        wb, "New Hire Assignments",
        ["employee_id", "employee_name", "team", "country", "start_date", "course_code", "course_title", "due_date",
         "status", "completed_on"],
        assignments, [12, 22, 22, 14, 12, 14, 38, 12, 12, 13],
    )
    wb.save(path)


# --------------------------------------------------------------------------- main


def main() -> None:
    rng = random.Random(SEED)
    dirs = {k: OUT / k for k in ("pdf", "txt", "csv", "xlsx")}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    write_handbook(dirs["pdf"] / "employee_handbook.pdf")
    write_code_of_conduct(dirs["pdf"] / "code_of_conduct.pdf")
    write_it_security_policy(dirs["pdf"] / "it_security_policy.pdf")

    (dirs["txt"] / "first_week_faq.txt").write_text(FIRST_WEEK_FAQ, encoding="utf-8", newline="\n")
    (dirs["txt"] / "how_to_guides.txt").write_text(HOW_TO_GUIDES, encoding="utf-8", newline="\n")

    people = build_directory(rng)
    write_directory(people, dirs["csv"] / "team_directory.csv")
    write_checklist(dirs["csv"] / "onboarding_checklist.csv")

    write_benefits(people, rng, dirs["xlsx"] / "benefits_enrollment.xlsx")
    write_training(people, rng, dirs["xlsx"] / "training_schedule.xlsx")

    for f in sorted(OUT.rglob("*.*")):
        if f.suffix in {".pdf", ".txt", ".csv", ".xlsx"}:
            print(f"{f.relative_to(ROOT)}  {f.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
