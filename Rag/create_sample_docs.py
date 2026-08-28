"""
Generate realistic sample legal PDF documents for the RAG pipeline demo.
These are richer than the placeholder PDFs so that chunking and retrieval
are meaningful.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
import os

DOCS_DIR = os.path.join(os.path.dirname(__file__), "documents")
os.makedirs(DOCS_DIR, exist_ok=True)


def build_pdf(filename: str, title: str, sections: list[tuple[str, str]]):
    """Build a PDF with a title and a list of (heading, body) sections."""
    path = os.path.join(DOCS_DIR, filename)
    doc = SimpleDocTemplate(path, pagesize=A4,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("DocTitle", parent=styles["Title"], fontSize=18,
                                  spaceAfter=20)
    heading_style = ParagraphStyle("SectionHead", parent=styles["Heading2"],
                                    fontSize=13, spaceAfter=8, spaceBefore=14)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10,
                                 leading=14, spaceAfter=10)

    story = [Paragraph(title, title_style), Spacer(1, 0.2*inch)]
    for heading, body in sections:
        story.append(Paragraph(heading, heading_style))
        for para in body.split("\n\n"):
            story.append(Paragraph(para.strip(), body_style))
        story.append(Spacer(1, 0.1*inch))
    doc.build(story)
    print(f"  [OK] {path}")


# ── Employment Contract ──────────────────────────────────────────────
build_pdf("Employment_Contract.pdf", "EMPLOYMENT CONTRACT", [
    ("1. Parties", 
     "This Employment Contract ('Contract') is entered into between Acme Corporation Ltd "
     "('the Company'), registered at 42 Innovation Drive, London, EC2A 4DP, and the "
     "Employee named on the accompanying offer letter.\n\n"
     "This Contract sets out the terms and conditions of employment and supersedes any "
     "prior agreements, representations, or understandings between the parties."),

    ("2. Role and Duties",
     "The Employee is engaged in the role specified in the offer letter. The Employee "
     "shall perform all duties reasonably associated with this role, and any additional "
     "duties the Company may assign from time to time.\n\n"
     "The Employee shall report to their line manager and comply with all reasonable "
     "instructions. The Company reserves the right to change the Employee's duties, "
     "job title, or reporting line, provided such changes are reasonable."),

    ("3. Probation Period",
     "The first 3 months of employment constitute a probationary period. During this "
     "time, either party may terminate the Contract with 1 week's written notice.\n\n"
     "At the end of the probationary period, the Company will confirm the Employee's "
     "appointment in writing, extend the probation by up to 3 additional months, or "
     "terminate employment. Performance reviews will be conducted at 6-week intervals "
     "during probation."),

    ("4. Notice Period",
     "After successful completion of the probationary period, the Employee must provide "
     "30 days' written notice before resignation. The Company must also provide 30 days' "
     "written notice before termination, except in cases of gross misconduct.\n\n"
     "During the notice period, the Company may, at its discretion, place the Employee "
     "on garden leave. The Employee remains bound by all contractual obligations during "
     "garden leave and shall not commence alternative employment.\n\n"
     "In cases of gross misconduct, the Company reserves the right to terminate "
     "employment immediately without notice or payment in lieu of notice."),

    ("5. Working Hours",
     "The standard working week is 40 hours, typically Monday to Friday, 9:00 AM to "
     "5:30 PM with a one-hour unpaid lunch break. The Employee may be required to work "
     "additional hours to meet business needs.\n\n"
     "Overtime is not automatically compensated unless the Employee's role is classified "
     "as overtime-eligible. Overtime-eligible employees receive 1.5× their standard "
     "hourly rate for hours worked beyond 40 per week, and 2× for work on public holidays."),

    ("6. Salary and Benefits",
     "The Employee's salary is stated in the offer letter and is paid monthly on the last "
     "working day of each month via bank transfer. The salary is subject to applicable tax "
     "and national insurance deductions.\n\n"
     "The Employee is enrolled in the Company's pension scheme after successful completion "
     "of probation. The Company contributes 5% and the Employee contributes a minimum of "
     "3% of gross salary. Additional voluntary contributions may be made.\n\n"
     "Private health insurance is provided after 6 months of continuous service. The "
     "Employee may add dependents at their own cost."),

    ("7. Confidentiality",
     "The Employee shall not, during or after employment, disclose any Confidential "
     "Information to any third party without prior written consent from the Company. "
     "'Confidential Information' includes trade secrets, client lists, financial data, "
     "business strategies, and proprietary technology.\n\n"
     "Upon termination, the Employee must return all Company property, documents, and "
     "data. This obligation survives the termination of this Contract indefinitely."),

    ("8. Restrictive Covenants",
     "For a period of 6 months following termination, the Employee shall not: (a) solicit "
     "or deal with any client of the Company with whom they had material contact in the "
     "12 months prior to termination; (b) recruit or entice away any employee of the "
     "Company; (c) engage in any business that competes directly with the Company within "
     "a 25-mile radius of the Company's registered office.\n\n"
     "These covenants are considered reasonable and necessary to protect the Company's "
     "legitimate business interests."),
])

# ── Annual Leave Policy ──────────────────────────────────────────────
build_pdf("Annual_Leave_Policy.pdf", "ANNUAL LEAVE POLICY", [
    ("1. Entitlement",
     "All full-time employees are entitled to 25 days of paid annual leave per calendar "
     "year, in addition to 8 public holidays. Part-time employees receive a pro-rata "
     "entitlement based on their contracted hours.\n\n"
     "New joiners receive a pro-rata entitlement for their first year, calculated from "
     "their start date. After 5 years of continuous service, employees receive an "
     "additional 2 days per year, up to a maximum of 30 days."),

    ("2. Booking Leave",
     "Leave must be requested through the Company's HR portal at least 5 working days in "
     "advance for requests of 1-3 days, and at least 15 working days in advance for "
     "requests of 4 or more consecutive days.\n\n"
     "Managers must respond to leave requests within 3 working days. Leave approval is "
     "subject to business needs and team coverage requirements. No more than 2 consecutive "
     "weeks may be taken at one time without senior management approval.\n\n"
     "During peak business periods (December and end of financial year), leave requests "
     "may be restricted. The Company will communicate blackout periods at least 30 days "
     "in advance."),

    ("3. Carry-Over",
     "Employees may carry forward a maximum of 5 unused leave days into the next calendar "
     "year. Carried-forward days must be used by 31 March of the following year, after "
     "which they are forfeited.\n\n"
     "In exceptional circumstances (e.g., extended sick leave preventing use of annual "
     "leave), the HR Director may approve additional carry-over on a case-by-case basis.\n\n"
     "Employees are encouraged to take their full leave entitlement each year for "
     "wellbeing purposes. Managers must ensure team members take a minimum of 15 days "
     "annually."),

    ("4. Leave During Notice Period",
     "During the notice period, employees may use accrued but untaken leave only with "
     "management approval. The Company reserves the right to require employees to take "
     "outstanding leave during their notice period.\n\n"
     "Any untaken leave at the termination date will be paid out at the Employee's daily "
     "rate. Conversely, if the Employee has taken more leave than accrued, the excess will "
     "be deducted from the final salary payment."),

    ("5. Sick Leave During Annual Leave",
     "If an employee falls ill during a period of annual leave, the leave days may be "
     "recredited as sick leave, provided the employee: (a) notifies their manager on the "
     "first day of illness; (b) obtains a medical certificate from a registered "
     "practitioner; (c) submits the certificate to HR within 5 days of return.\n\n"
     "A minimum of 2 consecutive days of illness is required for annual leave to be "
     "recredited."),

    ("6. Compassionate and Emergency Leave",
     "Up to 5 days of paid compassionate leave is granted for bereavement of an immediate "
     "family member (spouse, parent, child, or sibling). Additional unpaid leave may be "
     "approved at management discretion.\n\n"
     "In cases of household emergencies (e.g., flooding, break-in), up to 2 days of "
     "paid emergency leave may be taken. Evidence may be required."),
])

# ── Employee Handbook ────────────────────────────────────────────────
build_pdf("Employee_Handbook.pdf", "EMPLOYEE HANDBOOK", [
    ("1. Welcome and Company Values",
     "Welcome to Acme Corporation Ltd. This handbook outlines the policies, procedures, "
     "and expectations that apply to all employees. Our core values are: Integrity, "
     "Innovation, Collaboration, and Customer Focus.\n\n"
     "All employees are expected to conduct themselves professionally and to uphold "
     "these values in their daily work. Violation of company policies may result in "
     "disciplinary action, up to and including dismissal."),

    ("2. Remote and Flexible Working",
     "Employees may work remotely up to 2 days per week, subject to manager approval "
     "and role suitability. Remote work arrangements must be agreed in writing and "
     "reviewed every 6 months.\n\n"
     "Core hours are 10:00 AM to 3:00 PM, during which all employees must be available "
     "for meetings and collaboration regardless of their work location. Outside core "
     "hours, employees may flex their start and finish times between 7:00 AM and 7:00 PM.\n\n"
     "Employees working remotely must have a suitable workspace, reliable internet "
     "connection (minimum 20 Mbps), and comply with all data security policies. The "
     "Company will provide a one-time £200 home office allowance for ergonomic equipment."),

    ("3. IT and Security Policies",
     "Company laptops and devices must be used for work purposes only. Personal use "
     "is permitted to a reasonable extent but must not interfere with work duties or "
     "compromise security.\n\n"
     "All devices must have full-disk encryption enabled. Passwords must be at least "
     "12 characters and changed every 90 days. Multi-factor authentication is mandatory "
     "for all company systems.\n\n"
     "Employees must not install unauthorized software, access blocked websites, or "
     "connect to unsecured Wi-Fi networks. Any suspected security breaches must be "
     "reported to the IT Security team immediately via security@acme.com.\n\n"
     "The Company reserves the right to monitor usage of company devices and networks "
     "in accordance with applicable data protection laws."),

    ("4. Disciplinary and Grievance Procedures",
     "The disciplinary process follows four stages: (1) Verbal warning, (2) First "
     "written warning, (3) Final written warning, (4) Dismissal. Each stage includes "
     "a formal meeting with the right to be accompanied by a colleague or union "
     "representative.\n\n"
     "Warnings remain on file for 12 months (verbal and first written) or 18 months "
     "(final written) before being considered spent.\n\n"
     "Employees who wish to raise a grievance should first attempt informal resolution "
     "with their manager. If unresolved, a formal grievance may be submitted in writing "
     "to the HR department. HR will arrange a hearing within 10 working days and provide "
     "a written outcome within 5 working days of the hearing."),

    ("5. Health and Safety",
     "The Company is committed to providing a safe working environment. All employees "
     "must complete mandatory health and safety training within their first week of "
     "employment and attend annual refresher courses.\n\n"
     "Employees must report all accidents, near-misses, and hazards to their manager "
     "and the Health & Safety Officer immediately. First aid kits are located on every "
     "floor, and trained first aiders are identified by green lanyards.\n\n"
     "Display screen equipment (DSE) assessments will be conducted for all office-based "
     "employees upon request. Employees experiencing discomfort should request an "
     "assessment through HR."),

    ("6. Expenses and Travel",
     "Business expenses must be submitted within 30 days of being incurred, using the "
     "Company's expense management system. Original receipts or digital copies are "
     "required for all claims above £10.\n\n"
     "Mileage is reimbursed at 45p per mile for the first 10,000 miles, and 25p per "
     "mile thereafter. Hotel accommodation for business travel is capped at £150 per "
     "night (London) or £100 per night (elsewhere).\n\n"
     "All travel must be booked through the Company's approved booking platform. "
     "Business class flights require VP-level approval for domestic travel and Director-"
     "level approval for international travel."),

    ("7. Equal Opportunities and Diversity",
     "The Company is an equal opportunities employer. We are committed to eliminating "
     "discrimination and promoting diversity across all levels of the organization.\n\n"
     "Discrimination, harassment, or victimization on the grounds of age, disability, "
     "gender, race, religion, sexual orientation, or any other protected characteristic "
     "will not be tolerated and may result in immediate dismissal.\n\n"
     "The Company conducts annual pay gap analyses and publishes the results in "
     "accordance with regulatory requirements."),
])

# ── Redundancy Policy ────────────────────────────────────────────────
build_pdf("Redundancy_Policy.pdf", "REDUNDANCY POLICY", [
    ("1. Overview",
     "This Redundancy Policy applies when the Company needs to reduce headcount due to "
     "business restructuring, economic downturn, technological changes, or closure of a "
     "business unit. The Company is committed to handling redundancies fairly, "
     "transparently, and in compliance with UK employment law.\n\n"
     "Redundancy is always a last resort. Before commencing a redundancy process, the "
     "Company will explore alternatives including redeployment, voluntary redundancy, "
     "reduced working hours, and natural attrition."),

    ("2. Selection Criteria",
     "Where redundancy is unavoidable, selection will be based on objective, measurable "
     "criteria. These may include: skills and qualifications, performance ratings over "
     "the past 2 years, attendance records (excluding disability-related and statutory "
     "leave), length of service, and disciplinary record.\n\n"
     "The selection criteria will be shared with affected employees and their "
     "representatives before the consultation process begins. No selection criterion "
     "will directly or indirectly discriminate against any protected characteristic."),

    ("3. Consultation Process",
     "Individual consultation meetings will be held with each affected employee. "
     "Employees have the right to be accompanied by a colleague or trade union "
     "representative at all consultation meetings.\n\n"
     "For collective redundancies affecting 20 or more employees within a 90-day period, "
     "the Company will begin consultation at least 30 days before the first dismissal. "
     "For 100 or more employees, consultation begins at least 45 days before.\n\n"
     "During consultation, the Company will discuss: the reasons for redundancy, the "
     "number and categories of affected employees, proposed selection criteria, and any "
     "measures to mitigate redundancies."),

    ("4. Redundancy Pay",
     "Employees with at least 2 years of continuous service are entitled to statutory "
     "redundancy pay. The Company offers an enhanced redundancy package as follows:\n\n"
     "For each completed year of service: 2 weeks' gross pay (compared to the statutory "
     "0.5-1.5 weeks). The maximum service counted is 20 years. Redundancy pay is "
     "calculated based on the Employee's actual weekly pay, not the statutory cap.\n\n"
     "In addition, employees made redundant will receive: payment in lieu of notice "
     "(if applicable), payment for any accrued but untaken annual leave, and an ex-gratia "
     "payment of £500 to assist with job search costs."),

    ("5. Career Transition Support",
     "The Company will provide career transition support to all employees affected by "
     "redundancy, including: access to outplacement services for 3 months, up to 5 days "
     "of paid time off for job interviews and training during the notice period, CV "
     "writing and interview coaching workshops, and access to the Company's internal job "
     "board for 6 months after termination.\n\n"
     "Employees may also access the Employee Assistance Programme (EAP) for confidential "
     "counselling and support during and after the redundancy process. The EAP is "
     "available 24/7 on 0800-XXX-XXXX."),

    ("6. Appeals",
     "Employees who believe they have been unfairly selected for redundancy may appeal "
     "in writing to the HR Director within 5 working days of receiving their redundancy "
     "notice.\n\n"
     "An appeal hearing will be conducted by a senior manager not involved in the "
     "original selection process. The outcome will be communicated in writing within "
     "10 working days. The decision of the appeal panel is final."),
])

print("\n[DONE] All sample documents created in the 'documents/' folder.")
