from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import os
import random

import secrets
from PIL import Image
from functools import wraps
from flask import render_template, url_for, flash,redirect, request, abort,make_response,session,json,send_file,Response
from app import app, db, bcrypt, mail
from app.forms import AddEmployeeForm, ForceResetForm, LoginForm, RegisterForm, UpdateSuperAdminPasswordForm, UpdateSuperAdminProfileForm
from sqlalchemy.orm import joinedload
from flask import current_app, send_from_directory

from itsdangerous import URLSafeTimedSerializer
from flask_mail import Message


# from app.models import Users,Admin, Seller, UserAddress,Product,ProductVariation,ProductImage
from app.models import IPCR, AIInsight, Applicant, COERequest, CalendarEvent, CasualEmployeeHistory, ClearanceForm, CreditTransaction, Department, EmployeeCredit, EmploymentTerminationHistory, EvaluationPeriod, EvaluationSection, Interview, IssueReport, JobLog, JobOrderHistory, LeaveApplication, LoginActivity, MessageAttachment, PermanentEmployeeBenefitEligibility, PermanentSalaryHistory, PermitRequest, PermitRequestHistory, Position, SectionItem, TravelLog, TravelOrder, UserMessage, UserPermission, UserSignature, Users, Employee, PermanentEmployeeDetails, CasualEmployeeDetails, JobOrderDetails,JobPosting
from flask_login import login_user, current_user, logout_user, login_required
from flask import jsonify, request
# from flask_caching import Cache
import base64
from werkzeug.utils import secure_filename
import uuid

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import aliased
from sqlalchemy import and_, or_, text, case, desc, String, literal, func, extract
from datetime import datetime
from fpdf import FPDF
import io


from app.pdf_generator import CasualJobPDF, WidePDF, PerformanceReportPDF, TravelOrderPDF,LeaveApplicationPDF,CertificationPDF, ClearanceFormPDF, JobOrderPDF, TravelLogPDF, UnderReviewPDF, InterviewApplicantPDF, AcceptedApplicantPDF, RejectedApplicantPDF, HeadCasualEmployeePDF, HeadJobOrderEmployeePDF, HeadPermanentEmployeePDF, HeadLeaveApplicationPDF, HeadTravelOrderPDF, HeadClearanceSummaryPDF, HeadCOEPDF, EmployeeCreditPDF, EmployeeCreditHistoryPDF, HeadTerminatedCasualPDF, HeadTerminatedPermanentPDF, HeadTerminatedJobOrderPDF, HeadDepartmentIPCRPDF, HeadEmployeeIPCRPDF, OpenIssueSummaryPDF, InProgressIssueSummaryPDF, ResolvedIssueSummaryPDF, IPCRSummaryPDF, HeadIPCRPeriodSummaryPDF, UserCreditPDF, HeadCreditHistoryPDF, UserCreditHistoryPDF, TravelLogUSERPDF, TravelLogheadPDF, HeadCreditPDF,  HRLeaveApplicationPDF, HRTravelOrderPDF, HRClearanceSummaryPDF, ClearanceSummaryheadPDF, TravelOrderHeadPDF, LeaveApplicationhHeadPDF , MayorLeaveApplicationPDF, MayorTravelOrderPDF,  MayorClearanceSummaryPDF, HeadDeptIPCREmployeePDF




from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


import pdfplumber
import docx
import re
import os
import json
from sqlalchemy import func
from flask import Response
from sqlalchemy import desc
from collections import defaultdict
import google.generativeai as genai


genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

s = URLSafeTimedSerializer(app.config['SECRET_KEY'])




# DB DEBUGGING
# @app.route('/test-db')
# def test_db():
#     try:
#         with db.engine.connect() as connection:
#             connection.execute(text("SELECT 1"))
#         return "✅ MySQL connection successful!"
#     except Exception as e:
#         return f" MySQL connection failed: {e}"



@app.template_filter('to_ph_time')
def to_ph_time(value):
    if value is None:
        return None
    
    # Assume stored datetime is UTC if naive
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("Asia/Manila"))


# ROLE REQUIRED DECORATOR
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))

            # Check if current_user.role is in allowed roles
            role = current_user.role.lower() 
            if role not in roles:
                return redirect(url_for('PageNotFound'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator



# REDIRECT BASED ON ROLE
def redirect_based_on_role(user):
    role = user.role.lower()

    if role == 'hr':
        is_hr_department = (
            user.employee and
            user.employee.department and
            user.employee.department.name.strip().lower() ==
            "office of the municipal human resource management officer"
        )
        return redirect(url_for('adminHome'))  # HR head or employee
    elif role == 'head':
        return redirect(url_for('homeHead'))
    elif role == 'employee':
        return redirect(url_for('EmployeeHome'))
    else:
        return redirect(url_for('home'))


@app.errorhandler(403)
def forbidden(error):
    return render_template('pages-misc-error.html'), 403

def load_user(user_id):
    return Users.query.get(int(user_id))



def update_evaluation_period_status():
    today = date.today()
    reminder_days_before = 3
    sent_reminder = False
    notified_hr = False

    periods = EvaluationPeriod.query.all()

    for period in periods:
        # --- REMINDER SECTION ---
        reminder_date = period.end_date - timedelta(days=reminder_days_before)
        if period.is_active and today == reminder_date:
            job_name = f"ipcr_reminder_period_{period.id}"
            existing_job = JobLog.query.filter_by(job_name=job_name).first()
            if existing_job:
                continue  # ✅ Skip if reminders were already sent

            # Filter only active Permanent and Casual employees (exclude Job Orders)
            all_employees = (
                Employee.query
                .filter(
                    Employee.is_deleted == False,
                    Employee.employment_status == 'active',
                    (
                        Employee.permanent_details.has() |
                        Employee.casual_details.has()
                    ),
                    ~Employee.job_order_details.has()  # ✅ exclude Job Order
                )
                .all()
            )

            for emp in all_employees:
                ipcr = IPCR.query.filter_by(employee_id=emp.id, period_id=period.id).first()
                if not ipcr or not ipcr.submitted:
                    user = emp.user
                    if user:
                        message = UserMessage(
                            sender_id=1,
                            recipient_id=user.id,
                            subject="Reminder: Submit your IPCR",
                            body=f"""
                                Dear {emp.first_name},

                                This is a reminder to submit your IPCR for the evaluation period <b>{period.name}</b> 
                                by <b>{period.end_date.strftime('%B %d, %Y')}</b>.

                                Please ensure your submission is completed on time.

                                <hr>
                                <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
                                <p>– HR System</p>
                            """,
                            message_type="system"
                        )
                        db.session.add(message)
                        sent_reminder = True

            db.session.add(JobLog(job_name=job_name, last_run=datetime.utcnow()))

        # --- HR NOTIFICATION SECTION ---
        if period.is_active and today >= period.end_date:
            all_employees = (
                Employee.query
                .filter(
                    Employee.is_deleted == False,
                    Employee.employment_status == 'active',
                    (
                        Employee.permanent_details.has() |
                        Employee.casual_details.has()
                    ),
                    ~Employee.job_order_details.has()  # ✅ exclude Job Order
                )
                .all()
            )

            total_emps = len(all_employees)
            submitted_count = 0

            for emp in all_employees:
                ipcr = IPCR.query.filter_by(employee_id=emp.id, period_id=period.id).first()
                if ipcr and ipcr.submitted:
                    submitted_count += 1

            if total_emps > 0 and submitted_count == total_emps:
                job_name = f"ipcr_all_submitted_notice_{period.id}"
                if not JobLog.query.filter_by(job_name=job_name).first():
                    # ✅ Notify HR users with "write_performance" permission
                    hr_users = (
                        Users.query
                        .join(UserPermission, UserPermission.user_id == Users.id)
                        .join(Employee, Users.employee_id == Employee.id)
                        .filter(
                            Users.role.ilike('hr'),
                            Employee.employment_status == 'active',
                            UserPermission.permission == 'write_performance',
                            UserPermission.is_allowed == True
                        )
                        .all()
                    )

                    for hr in hr_users:
                        message = UserMessage(
                            sender_id=1,
                            recipient_id=hr.id,
                            subject=f"All IPCRs Submitted for {period.name}",
                            body=f"""
                                Dear {hr.name},

                                All employees have successfully submitted their IPCRs 
                                for the evaluation period <b>{period.name}</b>.

                                You may now proceed to review or finalize the evaluation reports.

                                <hr>
                                <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
                                <p>– HR System</p>
                            """,
                            message_type="system"
                        )
                        db.session.add(message)
                        notified_hr = True

                    db.session.add(JobLog(job_name=job_name, last_run=datetime.utcnow()))

    if sent_reminder or notified_hr:
        db.session.commit()




@app.before_request
def check_and_update_periods():
    if 'last_period_update' not in app.config or app.config['last_period_update'] != date.today():
        update_evaluation_period_status()
        app.config['last_period_update'] = date.today()


@app.route("/admin/interview-events")
@login_required
def get_interview_events():
    interviews = Interview.query.all()
    events = []

    for interview in interviews:
        applicant = interview.applicant
        title = f"{applicant.first_name} {applicant.last_name} Interview"
        start_datetime = datetime.combine(interview.scheduled_date, interview.scheduled_time)

        event = {
            "id": interview.id,
            "title": title,
            "start": start_datetime.isoformat(),
            "allDay": False,
            "className": "fc-primary-solid",  # Use a consistent class for styling
            "extendedProps": {
                "method": interview.method,
                "interviewer": interview.interviewer,
                "status": interview.status,
                "source": "interview"
            }
        }
        events.append(event)

    return jsonify(events)






@app.route('/admin/calendar-events')
@login_required
def calendar_events():
    events = CalendarEvent.query.all()

    def label_to_class(label):
        class_map = {
            'Meeting': 'fc-primary',
            'Training': 'fc-warning',
            'Leave': 'fc-success',
            'Official Travel': 'fc-default',
            'Holiday': 'fc-danger',
            'Public Event': 'fc-info-solid',
            'Administrative': 'fc-warning-solid'
        }
        return class_map.get(label, 'fc-default')

    events_data = []
    for e in events:
        event_dict = {
            'id': e.id,
            'title': e.title,
            'start': e.start_date.isoformat(),
            'end': e.end_date.isoformat() if e.end_date else None,
            'className': label_to_class(e.label),  # ✅ use className here
            'allDay': False,
            'extendedProps': {
                'label': e.label,
                'location': e.location,
                'source': 'calendar'
            }
        }
        events_data.append(event_dict)

    return jsonify(events_data)




@app.route("/404")
def PageNotFound():
    
    return render_template(
        'not_found.html',
        title="404",
    )


@app.route("/HR/home", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def adminHome():
    employee = Employee.query.filter_by(id=current_user.employee_id, is_deleted=False).first()
    if not employee:
        flash('Employee record not found.', 'danger')
        return redirect(url_for('logout'))



    # Evaluation Period
    active_period = EvaluationPeriod.query.filter_by(is_active=True).first()
    ipcr_submission_open = bool(active_period)
    ipcr_submitted = False
    ipcr_graded = False
    ipcr_exists = False
    period_id = None  # ✅ Fix: set initial value to avoid UnboundLocalError

    if active_period:
        ipcr = IPCR.query.filter_by(employee_id=employee.id, period_id=active_period.id).first()
        if ipcr:
            ipcr_exists = True
            ipcr_submitted = ipcr.submitted
            ipcr_graded = ipcr.graded
        period_id = active_period.id

    # Counts
    employee_count = Employee.query.filter_by(is_deleted=False).count()
    applicant_count = Applicant.query.count()

    # Job Postings with applicant count
    job_postings = JobPosting.query.all()
    job_applicants_data = [
        {
            'id': job.id,
            'title': job.title,
            'applicant_count': Applicant.query.filter_by(job_id=job.id).count()
        } for job in job_postings
    ]

    # Employee type breakdown

    # Permanent employees (non-deleted)
    permanent_count = db.session.query(func.count(Employee.id))\
        .join(PermanentEmployeeDetails)\
        .filter(Employee.is_deleted == False)\
        .scalar() or 0

    # Casual employees (non-deleted)
    casual_count = db.session.query(func.count(Employee.id))\
        .join(CasualEmployeeDetails)\
        .filter(Employee.is_deleted == False)\
        .scalar() or 0

    # Job Order employees (non-deleted)
    job_order_count = db.session.query(func.count(Employee.id))\
        .join(JobOrderDetails)\
        .filter(Employee.is_deleted == False)\
        .scalar() or 0


    graded_department_count = 0

    if period_id:
        departments = Department.query.all()
        for dept in departments:
            employees = (
                db.session.query(Employee, Users, Position)
                .join(Users, Users.employee_id == Employee.id)
                .outerjoin(PermanentEmployeeDetails, PermanentEmployeeDetails.employee_id == Employee.id)
                .outerjoin(CasualEmployeeDetails, CasualEmployeeDetails.employee_id == Employee.id)
                .outerjoin(
                    Position,
                    (Position.id == PermanentEmployeeDetails.position_id)
                    | (Position.id == CasualEmployeeDetails.position_id)
                )
                .filter(
                    Employee.is_deleted == False,
                    Employee.employment_status == 'active',
                    ~Employee.job_order_details.has(),
                    Users.role != 'head',
                    ~(
                        (Users.role == 'HR') &
                        (Position.title == 'MUNICIPAL GOVERNMENT DEPARTMENT HEAD I')
                    ),
                    db.or_(
                        db.and_(
                            PermanentEmployeeDetails.employee_id.isnot(None),
                            Employee.department_id == dept.id
                        ),
                        db.and_(
                            CasualEmployeeDetails.employee_id.isnot(None),
                            CasualEmployeeDetails.assigned_department_id == dept.id
                        )
                    )
                )
                .all()
            )

            employee_ids = [emp.id for emp, _, _ in employees]
            if not employee_ids:
                continue

            graded_ipcr_count = (
                IPCR.query.filter(
                    IPCR.employee_id.in_(employee_ids),
                    IPCR.period_id == period_id,
                    IPCR.graded == True
                ).count()
            )

            total_employees = len(employee_ids)
            if graded_ipcr_count == total_employees:
                graded_department_count += 1


    ipcr_total_expected = 0
    graded_count = 0
    submitted_not_graded_count = 0
    remaining_count = 0
    ipcr_total_submitted = 0

    if active_period:
        # --- Filter eligible employees directly ---
        filtered_employees = (
            Employee.query
            .outerjoin(PermanentEmployeeDetails)
            .outerjoin(CasualEmployeeDetails)
            .outerjoin(JobOrderDetails)
            .outerjoin(Position, 
                    (Position.id == PermanentEmployeeDetails.position_id) |
                    (Position.id == CasualEmployeeDetails.position_id))
            .outerjoin(Users, Users.employee_id == Employee.id)
            .filter(
                Employee.is_deleted == False,
                Employee.employment_status == 'active',
                Employee.status != 'Job Order',
                # Exclude department heads
                ~func.lower(Position.type).like('head'),
                # Exclude HR with special position
                ~((Users.role == 'hr') & 
                (Position.title == 'MUNICIPAL GOVERNMENT DEPARTMENT HEAD I'))
            )
            .all()
        )

        employee_ids = [e.id for e in filtered_employees]
        ipcr_total_expected = len(employee_ids)

       
        ipcr_list = IPCR.query.filter(
            IPCR.period_id == active_period.id,
            IPCR.employee_id.in_(employee_ids)
        ).all()

        graded_count = sum(1 for ipcr in ipcr_list if ipcr.graded == 1)
        submitted_not_graded_count = sum(1 for ipcr in ipcr_list if ipcr.submitted == 1 and ipcr.graded == 0)
        ipcr_total_submitted = graded_count + submitted_not_graded_count
        remaining_count = max(ipcr_total_expected - ipcr_total_submitted, 0)

    evaluation_period_name = active_period.name if active_period else "No Active Evaluation Period"
    
    
    # ipcr performance 
    top_employees = []
    if active_period:
        top_employees = (
            db.session.query(
                Users.image_file,
                (Employee.last_name + ', ' + Employee.first_name + ' ' + func.coalesce(Employee.middle_name, '')).label('full_name'),
                Department.name.label('department_name'),
                IPCR.final_average_rating
            )
            .join(Employee, Users.employee_id == Employee.id)
            .join(IPCR, Employee.id == IPCR.employee_id)
            .join(Department, Employee.department_id == Department.id)
            .filter(
                IPCR.graded == True,                      # ✅ Only graded IPCRs
                IPCR.period_id == active_period.id        # ✅ Only for the current active period
            )
            .order_by(IPCR.final_average_rating.desc())   # ✅ Highest-rated first
            .all()
        )

    # --- Pending Permits by Type ---
    permit_queries = {
        'Leave': {
            'status': 'In Progress',
            'options': [joinedload(PermitRequest.employee), joinedload(PermitRequest.leave_detail)]
        },
        'Travel Order': {
            'status': 'In Progress',
            'options': [joinedload(PermitRequest.employee), joinedload(PermitRequest.travel_detail)]
        },
        'Clearance Form': {
            'status': 'In Progress',
            'options': [joinedload(PermitRequest.employee), joinedload(PermitRequest.clearance_detail)]
        },
        'Certification of Employment': {
            'status': 'Pending',
            'options': [joinedload(PermitRequest.employee), joinedload(PermitRequest.coe_detail)]
        }
    }

    # Initialize container
    permit_data = {}

    # Execute all queries in a clean loop
    for permit_type, config in permit_queries.items():
        requests = (
            PermitRequest.query
            .filter_by(permit_type=permit_type, current_stage='HR', status=config['status'])
            .options(*config['options'])
            .all()
        )
        permit_data[permit_type] = requests

    # Assign back to specific variables for your template
    pending_leave_requests = permit_data.get('Leave', [])
    pending_travel_requests = permit_data.get('Travel Order', [])
    pending_clearance_requests = permit_data.get('Clearance Form', [])
    pending_coe_requests = permit_data.get('Certification of Employment', [])


  
    today = date.today()
    # Employees currently on approved leave
    current_leave_employees = (
        db.session.query(PermitRequest)
        .join(LeaveApplication)
        .filter(
            PermitRequest.permit_type == 'Leave',
            PermitRequest.status == 'Completed',
            LeaveApplication.date_from <= today,
            LeaveApplication.date_to >= today
        )
        .all()
    )

    # Employees currently on approved travel
    current_travel_employees = (
        db.session.query(PermitRequest)
        .join(TravelOrder)
        .filter(
            PermitRequest.permit_type == 'Travel Order',
            PermitRequest.status == 'Completed',
            TravelOrder.date_departure == today
        )
        .all()
    )

    search = request.args.get('search', '').strip()
    filter_option = request.args.get('filter', 'all')
    position_filter = request.args.get('position', '').strip()

    # Get distinct positions from JobPostings (only active, not deleted)
    positions = db.session.query(JobPosting.title).filter_by(is_deleted=False).distinct().all()
    positions = [p[0] for p in positions]

    # Base query: join Applicant -> JobPosting for position filter
    applicant_query = Applicant.query.join(JobPosting).filter(JobPosting.is_deleted == False)

    # Apply search filter on first_name, last_name, email
    if search:
        search_pattern = f"%{search}%"
        applicant_query = applicant_query.filter(
            or_(
                Applicant.first_name.ilike(search_pattern),
                Applicant.last_name.ilike(search_pattern),
                Applicant.email.ilike(search_pattern),
            )
        )

    # Apply date/status filters
    today = datetime.utcnow().date()
    if filter_option == 'today':
        applicant_query = applicant_query.filter(func.date(Applicant.applied_at) == today)
    elif filter_option == 'last7days':
        last_7 = today - timedelta(days=7)
        applicant_query = applicant_query.filter(func.date(Applicant.applied_at) >= last_7)
    elif filter_option == 'hired':
        applicant_query = applicant_query.filter(Applicant.status == 'Hired')
    elif filter_option == 'rejected':
        applicant_query = applicant_query.filter(Applicant.status == 'Rejected')

    # Apply position filter if valid
    if position_filter and position_filter in positions:
        applicant_query = applicant_query.filter(JobPosting.title == position_filter)

    # Fetch all filtered applicants ordered by application date desc
    applicants = applicant_query.order_by(Applicant.applied_at.desc()).all()

    # Process applicants: deserialize AI-related fields for each applicant
    qualified_threshold = 60.0
    total_applicants = len(applicants)
    total_qualified = sum(1 for a in applicants if a.application_score and a.application_score >= qualified_threshold)
    valid_scores = [a.application_score for a in applicants if a.application_score is not None]
    average_score = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0.0

    for applicant in applicants:
        # Extract education list
        if applicant.education:
            if applicant.education.strip().startswith("["):
                try:
                    applicant.education_list = json.loads(applicant.education)
                except json.JSONDecodeError:
                    applicant.education_list = []
            else:
                applicant.education_list = [e.strip() for e in applicant.education.split("\n") if e.strip()]
        else:
            applicant.education_list = []

        # Extract skills list
        if applicant.other_skills:
            if applicant.other_skills.strip().startswith("["):
                try:
                    applicant.skills_list = json.loads(applicant.other_skills)
                except json.JSONDecodeError:
                    applicant.skills_list = []
            else:
                applicant.skills_list = [s.strip() for s in applicant.other_skills.split(",") if s.strip()]
        else:
            applicant.skills_list = []

        # Extract experience list
        if applicant.work_experience:
            if applicant.work_experience.strip().startswith("["):
                try:
                    applicant.experience_list = json.loads(applicant.work_experience)
                except json.JSONDecodeError:
                    applicant.experience_list = []
            else:
                applicant.experience_list = [e.strip() for e in applicant.work_experience.split("\n") if e.strip()]
        else:
            applicant.experience_list = []

        # Extract strengths list
        if applicant.strengths:
            if applicant.strengths.strip().startswith("["):
                try:
                    applicant.strengths_list = json.loads(applicant.strengths)
                except json.JSONDecodeError:
                    applicant.strengths_list = []
            else:
                applicant.strengths_list = [s.strip() for s in applicant.strengths.split("\n") if s.strip()]
        else:
            applicant.strengths_list = []

        # Extract weaknesses list
        if applicant.weaknesses:
            if applicant.weaknesses.strip().startswith("["):
                try:
                    applicant.weaknesses_list = json.loads(applicant.weaknesses)
                except json.JSONDecodeError:
                    applicant.weaknesses_list = []
            else:
                applicant.weaknesses_list = [w.strip() for w in applicant.weaknesses.split("\n") if w.strip()]
        else:
            applicant.weaknesses_list = []



  
     # --- 📊 Monthly Permit Graph Data ---
    monthly_permits = (
        db.session.query(
            extract('year', PermitRequest.date_requested).label('year'),
            extract('month', PermitRequest.date_requested).label('month'),
            PermitRequest.permit_type,
            PermitRequest.status,   # <-- use actual status
            func.count(PermitRequest.id).label('count')
        )
        .group_by('year', 'month', 'permit_type', 'status')
        .order_by('year', 'month')
        .all()
    )

    # Build nested dictionary with status breakdown
    permit_chart_dict = {}
    for year, month, permit_type, status, count in monthly_permits:
        # Use year-month to avoid merging months across different years
        month_label = f"{int(year)}-{int(month):02d}"  # e.g., "2025-09"
        
        if month_label not in permit_chart_dict:
            permit_chart_dict[month_label] = {
                "Leave": {"Pending": 0, "Approved": 0, "Rejected": 0, "Cancelled": 0},
                "Travel Order": {"Pending": 0, "Approved": 0, "Rejected": 0, "Cancelled": 0},
                "Clearance Form": {"Pending": 0, "Approved": 0, "Rejected": 0, "Cancelled": 0},
                "Certification of Employment": {"Pending": 0, "Approved": 0, "Rejected": 0, "Cancelled": 0},
            }

        # Normalize status to chart categories
        if status in ["Completed", "Released", "Approved"]:
            chart_status = "Approved"
        elif status == "Rejected":
            chart_status = "Rejected"
        elif status == "Cancelled":
            chart_status = "Cancelled"
        else:
            chart_status = "Pending"

        permit_chart_dict[month_label][permit_type][chart_status] += count



    # Sort months chronologically
    sorted_month_keys = sorted(
        permit_chart_dict.keys(),
        key=lambda x: datetime.strptime(x, "%Y-%m")
    )

    # Convert to month names for display
  
    permit_chart_labels = [datetime.strptime(k, "%Y-%m").strftime("%B %Y") for k in sorted_month_keys]

    # Extract totals per permit type
    leave_counts     = [sum(permit_chart_dict[k]["Leave"].values()) for k in sorted_month_keys]
    travel_counts    = [sum(permit_chart_dict[k]["Travel Order"].values()) for k in sorted_month_keys]
    clearance_counts = [sum(permit_chart_dict[k]["Clearance Form"].values()) for k in sorted_month_keys]
    coe_counts       = [sum(permit_chart_dict[k]["Certification of Employment"].values()) for k in sorted_month_keys]

    # --- Placeholder data for other charts ---
    ratings_data = []   # Can be filled later
    trend_data   = []   # Can be filled later
    dept_data    = []   # Can be filled later



    # Pass to template
    return render_template(
        'superAdmin/SuperAdmin_home.html',
        title="home",
        employee=employee,
        ipcr_submission_open=ipcr_submission_open,
        ipcr_exists=ipcr_exists,
        ipcr_submitted=ipcr_submitted,
        ipcr_graded=ipcr_graded,
        employee_count=employee_count,
        applicant_count=applicant_count,
        job_applicants_data=job_applicants_data,
       
        graded_count=graded_count,
        graded_department_count=graded_department_count,
        permanent_count=permanent_count,
        casual_count=casual_count,
        job_order_count=job_order_count,
        top_employees=top_employees,
        ipcr_total_expected=ipcr_total_expected,
        ipcr_total_submitted=ipcr_total_submitted,
        evaluation_period_name=evaluation_period_name,
        pending_leave_requests=pending_leave_requests,
        pending_travel_requests=pending_travel_requests,
        pending_clearance_requests=pending_clearance_requests,
        pending_coe_requests=pending_coe_requests,
        submitted_not_graded_count=submitted_not_graded_count,

        # ✅ Add these:
        current_leave_employees=current_leave_employees,
        current_travel_employees=current_travel_employees,
        
        applicants=applicants,
        total_applicants=total_applicants,
        total_qualified=total_qualified,
        average_score=average_score,
        qualified_threshold=qualified_threshold,
        positions=positions,
        current_search=search,
        current_filter=filter_option,
        current_position=position_filter,


         # ✅ Permit Chart Data
        permit_chart_labels=permit_chart_labels,
        leave_counts=leave_counts,
        travel_counts=travel_counts,
        clearance_counts=clearance_counts,
        coe_counts=coe_counts,
        permit_details=permit_chart_dict,   # ✅ for tooltips

        ratings_data=ratings_data,
        trend_data=trend_data,
        dept_data=dept_data
    )




# document tracking hr 
@app.route('/HR/department/permit', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def HRdepartmentpermit():
    # Get current head's department
    head_employee = current_user.employee
    department_id = head_employee.department_id  

    # Query all employees in this department
    employee_ids = [emp.id for emp in Employee.query.filter_by(department_id=department_id).all()]

    # ✅ LEAVE PERMITS
    leave_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Leave',
            PermitRequest.employee_id.in_(employee_ids),
            PermitRequest.current_stage.in_(['Head','HR' ,'Mayor', 'Completed','Rejected'])  # Still see after action
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Attach latest rejection history
    for permit in leave_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # ✅ TRAVEL ORDERS
    travel_orders = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Travel Order',
            PermitRequest.employee_id.in_(employee_ids),
            PermitRequest.current_stage.in_(['Head','HR' ,'Mayor', 'Completed','Rejected'])
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    for permit in travel_orders:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # ✅ CLEARANCE FORMS
    clearance_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Clearance Form',
            PermitRequest.employee_id.in_(employee_ids),
            PermitRequest.current_stage.in_(['Head','HR', 'Mayor', 'Completed','Rejected'])
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    for permit in clearance_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # ✅ COE (Skips Head, but still show for reference)
    coe_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Certification of Employment',
            PermitRequest.employee_id.in_(employee_ids)
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    for permit in coe_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

       # ===================== PENDING COUNTS FOR BADGES =====================
    pending_leave_count = sum(1 for p in leave_permits if p.current_stage == 'Head')
    pending_travel_count = sum(1 for p in travel_orders if p.current_stage == 'Head')
    pending_clearance_count = sum(1 for p in clearance_permits if p.current_stage == 'Head')

  
    return render_template(
        'superAdmin/departmentpermit.html',
        title="Department Permits",
        leave_permits=leave_permits,
        travel_orders=travel_orders,
        clearance_permits=clearance_permits,
        coe_permits=coe_permits,
        pending_leave_count=pending_leave_count,
        pending_travel_count=pending_travel_count,
        pending_clearance_count=pending_clearance_count
    )



@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = RegisterForm()
    if form.validate_on_submit():
        hashed_pw = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = Users(
            name=form.name.data,
            email=form.email.data,
            password_hash=hashed_pw,
            role='HR'  
        )
        db.session.add(user)
        db.session.commit()
        flash('Account created! You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('landing/register.html', title='Register', form=form)





# @app.route("/login", methods=['GET', 'POST'])
# def login():
#     logout_user()

#     if current_user.is_authenticated:
#         return redirect(url_for('home'))

#     form = LoginForm()
#     if form.validate_on_submit():
#         user = Users.query.filter(
#             or_(
#                 Users.email == form.login.data,
#                 Users.login_id == form.login.data
#             )
#         ).first()

#         login_success = user and bcrypt.check_password_hash(user.password_hash, form.password.data)

#         if user:
#             # Record login attempt
#             login_activity = LoginActivity(
#                 user_id=user.id if user else None,
#                 timestamp=datetime.utcnow(),
#                 ip_address=request.remote_addr,
#                 success=login_success
#             )
#             db.session.add(login_activity)
#             db.session.commit()

#         if login_success:

#             if user.employee and user.employee.employment_status == 'inactive':
#                 flash('Your account has been terminated', 'warning')
#                 return redirect(url_for('login'))


#             login_user(user, remember=form.remember.data)

#             # Check for 3 yrs
#             run_daily_checks()

#             if user.must_reset_password:
#                 flash('You must reset your password before continuing.', 'warning')
#                 return redirect(url_for('force_reset'))

#             next_page = request.args.get('next')
#             role = user.role.lower()

#             if next_page:
#                 return redirect(next_page)
#             elif role == 'hr':
#                 is_hr_department = (
#                     user.employee and
#                     user.employee.department and
#                     user.employee.department.name.strip().lower() == 
#                     "office of the municipal human resource management officer"
#                 )

#                 if is_hr_department:
#                     position_type = None
#                     if user.employee.permanent_details and user.employee.permanent_details.position:
#                         position_type = user.employee.permanent_details.position.type.lower()
#                     elif user.employee.casual_details and user.employee.casual_details.position:
#                         position_type = user.employee.casual_details.position.type.lower()

#                     return redirect(url_for('adminHome'))  # HR head or employee
#                 else:
#                     return redirect(url_for('adminHome'))  # Non-HR employee
#             elif role == 'head':
#                 return redirect(url_for('homeHead'))
#             elif role == 'employee':
#                 return redirect(url_for('EmployeeHome'))
#             else:
#                 return redirect(url_for('home'))
#         else:
#             flash('Login Unsuccessful. Please check Email/ID and Password.', 'danger')

#     response = make_response(render_template('landing/login.html', title="Login", form=form))
#     response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
#     response.headers['Pragma'] = 'no-cache'
#     return response


@app.route("/login", methods=['GET', 'POST'])
def login():
    # ✅ If already logged in (session or remember_token), redirect to dashboard
    if current_user.is_authenticated:
        return redirect_based_on_role(current_user)

    form = LoginForm()
    if form.validate_on_submit():
        user = Users.query.filter(
            or_(
                Users.email == form.login.data,
                Users.login_id == form.login.data
            )
        ).first()

        login_success = user and bcrypt.check_password_hash(
            user.password_hash, form.password.data
        )

        # Record login attempt
        if user:
            login_activity = LoginActivity(
                user_id=user.id,
                timestamp=datetime.utcnow(),
                ip_address=request.remote_addr,
                success=login_success
            )
            db.session.add(login_activity)
            db.session.commit()

        if login_success:
            # Block inactive accounts
            if user.employee and user.employee.employment_status == 'inactive':
                flash('Your account has been terminated', 'warning')
                return redirect(url_for('login'))

            # ✅ Log the user in (with remember option)
            login_user(user, remember=form.remember.data)

            # Run daily checks
            run_daily_checks()

            if user.must_reset_password:
                flash('You must reset your password before continuing.', 'warning')
                return redirect(url_for('force_reset'))

            # ✅ Redirect based on role (or next page if present)
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)

            return redirect_based_on_role(user)

        else:
            flash('Login Unsuccessful. Please check Email/ID and Password.', 'danger')

    # Render login page with no-cache headers
    response = make_response(
        render_template('landing/login.html', title="Login", form=form)
    )
    response.headers['Cache-Control'] = (
        'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    )
    response.headers['Pragma'] = 'no-cache'
    return response



# 3YRS check
def run_daily_checks():
    notify_if_needed()
    notify_benefit_if_needed()
    accrue_monthly_credits_if_needed()
    deduct_unused_force_leave_if_year_end()



def deduct_unused_force_leave_if_year_end():
    today = date.today()
    year = today.year

    # ✅ Run only during the last week of December or first week of January
    if (today.month == 12 and today.day >= 25) or (today.month == 1 and today.day <= 7):
        # Determine which year to deduct for
        # If we're in January, we deduct for the *previous* year
        target_year = year - 1 if today.month == 1 else year

        # ✅ Check if deduction already processed for that target year
        already_done = CreditTransaction.query.filter(
            CreditTransaction.notes.like(f"%({target_year})%")
        ).first()

        if not already_done:
            deduct_unused_force_leave()



def deduct_unused_force_leave():
    today = date.today()
    current_year = today.year

    # Handle case where script runs in early January (apply to previous year)
    if today.month == 1 and today.day <= 7:
        target_year = current_year - 1
    else:
        target_year = current_year

    required_force_leave_days = 5  # Adjust as needed

    employees = (
        Employee.query
        .outerjoin(PermanentEmployeeDetails)
        .outerjoin(CasualEmployeeDetails)
        .outerjoin(JobOrderDetails, JobOrderDetails.employee_id == Employee.id)
        .filter(
            Employee.employment_status == 'active',
            Employee.is_deleted == False,
            JobOrderDetails.id.is_(None),
            db.or_(
                PermanentEmployeeDetails.id.isnot(None),
                CasualEmployeeDetails.id.isnot(None)
            )
        )
        .all()
    )

    hr_users = (
        Users.query
        .join(Employee)
        .join(PermanentEmployeeDetails)
        .join(Position)
        .join(Department)
        .filter(
            Department.id == 15,  # HR dept
            Position.type == 'Head',
            Employee.is_deleted == False
        )
        .all()
    )

    for emp in employees:
        used_force_leaves = (
            db.session.query(LeaveApplication)
            .join(PermitRequest, LeaveApplication.permit_id == PermitRequest.id)
            .filter(
                PermitRequest.employee_id == emp.id,
                PermitRequest.permit_type == 'Leave',
                LeaveApplication.leave_type == 'Force Leave',
                PermitRequest.status == 'Completed',
                db.extract('year', LeaveApplication.date_from) == target_year
            )
            .count()
        )

        unused_force_days = max(0, required_force_leave_days - used_force_leaves)
        if unused_force_days == 0:
            continue

        credit = emp.credit_balance
        if not credit:
            continue

        available = credit.vacation_remaining

        if available <= 0:
            # ⚠ No credits to deduct, skip deduction
            unpaid = unused_force_days
            deducted = 0
        else:
            deducted = min(available, unused_force_days)
            unpaid = unused_force_days - deducted

            credit.vacation_remaining = max(0, credit.vacation_remaining - deducted)
            credit.vacation_used += deducted

            # Log deduction
            db.session.add(CreditTransaction(
                employee_id=emp.id,
                leave_type='Vacation',
                action='Deducted',
                amount=-deducted,
                notes=f"Deduction for unused Force Leave ({target_year})"
            ))

        # Notify employee
        user = Users.query.filter_by(employee_id=emp.id).first()
        if user:
            subject = "Unused Force Leave Deduction Notice"

            unpaid_section = ""
            if unpaid > 0:
                unpaid_section = f"<p>⚠ You had no remaining vacation credits. {unpaid} day(s) were marked as unpaid.</p>"

            body = f"""
            <div>
                <p>📢 <strong>Year-End Force Leave Deduction</strong></p>
                <p>Dear <strong>{user.name}</strong>,</p>
                <p>You have not used <strong>{unused_force_days}</strong> day(s) of Force Leave for {target_year}.</p>
                <p>These days have been automatically deducted from your Vacation Leave balance.</p>
                {unpaid_section}
                <hr>
                <p><em>⚠ This is an automated notification. Please contact HR for any discrepancies.</em></p>
                <p>– HR System</p>
            </div>
            """
            db.session.add(UserMessage(
                sender_id=1,
                recipient_id=user.id,
                subject=subject,
                body=body,
                message_type='system'
            ))

        # Notify HR
        for hr in hr_users:
            hr_body = f"""
            <div>
                <p>📢 <strong>Employee Force Leave Deduction Notice</strong></p>
                <p>Employee <strong>{user.name}</strong> has <strong>{unused_force_days}</strong> unused Force Leave day(s) for {target_year}.</p>
                <p>Deducted: {deducted} day(s). Unpaid: {unpaid} day(s).</p>
            </div>
            """
            db.session.add(UserMessage(
                sender_id=1,
                recipient_id=hr.id,
                subject=f"{user.name} - Unused Force Leave Deduction ({target_year})",
                body=hr_body,
                message_type='system'
            ))

    db.session.commit()


def notify_if_needed():
    today = date.today()

    # Look for existing log entry
    job = JobLog.query.filter_by(job_name='salary_check').first()

    if not job:
        # First run ever
        notify_salary_increase_candidates()
        job = JobLog(job_name='salary_check', last_run=datetime.utcnow())
    elif job.last_run.date() < today:
        # Not run today yet
        notify_salary_increase_candidates()
        job.last_run = datetime.utcnow()
    else:
        # Already ran today
        return

    db.session.add(job)
    db.session.commit()


def notify_benefit_if_needed():
    today = date.today()

    job = JobLog.query.filter_by(job_name='benefit_check').first()

    if not job:
        notify_benefit_eligibility()
        job = JobLog(job_name='benefit_check', last_run=datetime.utcnow())
    elif job.last_run.date() < today:
        notify_benefit_eligibility()
        job.last_run = datetime.utcnow()
    else:
        return

    db.session.add(job)
    db.session.commit()


def notify_salary_increase_candidates():
    today = date.today()

    # --- HR recipients (Department 15, type Head)
    hr_users = (
        Users.query
        .join(Employee)
        .join(PermanentEmployeeDetails)
        .join(Position)
        .join(Department)
        .filter(
            Department.id == 15,
            Position.type == 'Head',
            Employee.is_deleted == False
        )
        .all()
    )

    # --- Employees with valid permanent records
    eligible_employees = (
        PermanentEmployeeDetails.query
        .join(Employee)
        .filter(
            PermanentEmployeeDetails.date_original_appointment.isnot(None),
            Employee.is_deleted == False
        )
        .all()
    )


    for emp in eligible_employees:
        current_step = emp.step or 1
        if current_step >= 8:
            # Already at max step — skip
            continue

        # --- Compute years since original appointment
        years_since_appointment = (today - emp.date_original_appointment).days // 365
        if years_since_appointment < 3:
            continue  # Not yet eligible for any step increase

        # --- Compute expected step (every 3 years, capped at 8)
        expected_step = min(1 + (years_since_appointment // 3), 8)

        # --- Skip employees already at or above expected step
        if current_step >= expected_step:
            continue

        # --- Determine milestone interval (3, 6, 9...)
        step_interval = (years_since_appointment // 3) * 3
        reason = f"{step_interval}-year step increase"

        # --- Skip if already recorded in salary history
        existing_record = PermanentSalaryHistory.query.filter_by(
            permanent_employee_id=emp.id,
            reason=reason
        ).first()
        if existing_record:
            continue

        # --- Get employee's user account
        user = Users.query.filter_by(employee_id=emp.employee_id).first()
        if not user:
            continue

        # --- Employee message ---
        subject = "You may be eligible for a salary step increase"
        body = f"""
        <div>
            <p>📢 <strong>Salary Step Increase Eligibility Notice</strong></p>

            <p>Dear <strong>{emp.employee.first_name} {emp.employee.middle_name or ''} {emp.employee.last_name}</strong>,</p>

            <p>Our records indicate that your original appointment was on 
               <strong>{emp.date_original_appointment.strftime('%B %d, %Y')}</strong>.</p>

            <p>Based on your {years_since_appointment} years of service, your current step is 
               <strong>{current_step}</strong> but should now be <strong>{expected_step}</strong>.</p>

            <p>You may now be eligible for a <strong>{step_interval}-year salary step increase</strong>.</p>

            <p>Please coordinate with the Human Resources Department to confirm your eligibility 
               and complete the necessary documentation.</p>

            <p>Thank you for your continued dedication and service.</p>
            
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            <p>– HR System</p>
        </div>
        """

        db.session.add(UserMessage(
            sender_id=1,  # System sender
            recipient_id=user.id,
            subject=subject,
            body=body,
            message_type='system'
        ))

        # --- HR Notifications ---
        for hr in hr_users:
            hr_name = f"{hr.employee.first_name} {hr.employee.last_name}" if hr.employee else hr.name

            hr_subject = f"{user.name} may be due for a {step_interval}-year step increase"
            hr_body = f"""
            <div>
                <p>📢 <strong>Employee Step Increase Notification</strong></p>

                <p>Dear <strong>{hr_name}</strong>,</p>

                <p>This is to inform you that <strong>{user.name}</strong>, originally appointed on 
                   <strong>{emp.date_original_appointment.strftime('%B %d, %Y')}</strong>, 
                   is currently recorded as <strong>Step {current_step}</strong> but should be at 
                   <strong>Step {expected_step}</strong> based on {years_since_appointment} years of service.</p>

                <p>Please review the employee's records and process the necessary step increase if applicable.</p>
                
                <hr>
                <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
                <p>– HR System</p>
            </div>
            """

            db.session.add(UserMessage(
                sender_id=1,
                recipient_id=hr.id,
                subject=hr_subject,
                body=hr_body,
                message_type='system'
            ))


    db.session.commit()


def notify_benefit_eligibility():
    today = date.today()
    milestone_years = [10, 15, 20, 25, 30]  # Extend as needed

    hr_users = (
        Users.query
        .join(Employee)
        .join(PermanentEmployeeDetails)
        .join(Position)
        .join(Department)
        .filter(
            Department.id == 15,
            Position.type == 'Head',
            Employee.is_deleted == False
        )
        .all()
    )

    eligible_employees = PermanentEmployeeDetails.query \
        .join(Employee) \
        .filter(Employee.is_deleted == False) \
        .all()

    for emp in eligible_employees:
        user = Users.query.filter_by(employee_id=emp.employee_id).first()
        if not user or not emp.date_original_appointment:
            continue

        years_of_service = (today - emp.date_original_appointment).days // 365

        for milestone in milestone_years:
            if years_of_service < milestone:
                continue

            benefit_name = f"{milestone}-Year Benefit"

            # Skip if already in eligibility table and marked eligible
            existing_elig = PermanentEmployeeBenefitEligibility.query.filter_by(
                permanent_employee_id=emp.id,
                benefit_name=benefit_name
            ).first()

            if existing_elig and existing_elig.is_eligible:
                continue

            # Skip if already notified
            existing_msg_to_emp = UserMessage.query.filter_by(
                recipient_id=user.id,
                subject=f"You may now be eligible for a {milestone}-year benefit"
            ).first()
            if existing_msg_to_emp:
                continue

           # ✅ Define formal subject/body
            emp_subject = f"You may now be eligible for a {milestone}-year benefit"
            emp_body = f"""📢 <strong>Service Benefit Eligibility Notice</strong><br><br>

            <p>Dear <strong>{user.name}</strong>,</p>

            <p>Based on your appointment date (<strong>{emp.date_original_appointment}</strong>), 
            you may now qualify for a <strong>{milestone}-year service benefit</strong>.</p>

            <p>Kindly coordinate with the Human Resources Department to confirm your eligibility and complete the necessary steps.</p>

            <p>Thank you for your continued dedication and service.</p>

            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            <p>– HR System</p>
            """

            db.session.add(UserMessage(
                sender_id=1,
                recipient_id=user.id,
                subject=emp_subject,
                body=emp_body,
                message_type='system'
            ))


            # Notify HR (if not already notified)
            for hr in hr_users:
                existing_msg_to_hr = UserMessage.query.filter_by(
                    recipient_id=hr.id,
                    subject=f"{user.name} may be eligible for a {milestone}-year benefit"
                ).first()
                if existing_msg_to_hr:
                    continue

            hr_body = f"""📢 <strong>Employee Service Benefit Notification</strong><br><br>

                <p>Dear <strong>{hr.name}</strong>,</p>

                <p>This is to inform you that <strong>{user.name} (Employee ID: {emp.employee_id})</strong>, who has been serving since <strong>{emp.date_original_appointment}</strong>, 
                may now qualify for the <strong>{benefit_name}</strong>.</p>

                <p>Please review and verify the employee's records and coordinate accordingly with the concerned department.</p>

                <hr>
                <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
                <p>– HR System</p>
                """
            
            db.session.add(UserMessage(
                    sender_id=1,
                    recipient_id=hr.id,
                    subject=f"{user.name} may be eligible for a {milestone}-year benefit",
                    body=hr_body,
                    message_type='system'
            ))

    db.session.commit()



def accrue_monthly_credits_if_needed():
    today = date.today()
    this_month = today.month
    this_year = today.year

    job = JobLog.query.filter_by(job_name='monthly_credit_accrual').first()

    should_run = False

    if not job:
        # First-time ever
        should_run = True
        job = JobLog(job_name='monthly_credit_accrual')
    elif job.last_run.year != this_year or job.last_run.month != this_month:
        # Not yet run this month
        should_run = True
    else:
        # Check if any active employee does not have a credit transaction for this month
        subquery = db.session.query(CreditTransaction.employee_id).filter(
            CreditTransaction.action == 'Earned',
            db.extract('year', CreditTransaction.timestamp) == this_year,
            db.extract('month', CreditTransaction.timestamp) == this_month
        ).subquery()

        missing = (
            Employee.query
            .outerjoin(JobOrderDetails, JobOrderDetails.employee_id == Employee.id)
            .filter(
                Employee.employment_status == 'active',
                Employee.is_deleted == False,
                JobOrderDetails.id.is_(None),  # ✅ Exclude JOs
                ~Employee.id.in_(subquery)
            )
            .first()
        )

        if missing:
            should_run = True

    if should_run:
        accrue_monthly_credits()
        job.last_run = datetime.utcnow()
        db.session.add(job)
        db.session.commit()




def accrue_monthly_credits():
    today = date.today()
    this_month = today.month
    this_year = today.year

    employees = (
        Employee.query
        .outerjoin(JobOrderDetails, JobOrderDetails.employee_id == Employee.id)
        .filter(
            Employee.employment_status == 'active',
            Employee.is_deleted == False,
            JobOrderDetails.id.is_(None)  # Exclude Job Orders
        )
        .all()
    )

    for emp in employees:
        # Skip if already credited this month
        already_credited = CreditTransaction.query.filter_by(
            employee_id=emp.id,
            action='Earned'
        ).filter(
            db.extract('month', CreditTransaction.timestamp) == this_month,
            db.extract('year', CreditTransaction.timestamp) == this_year
        ).first()

        if already_credited:
            continue  # Skip — already credited this month

        # Get or create employee credit record
        credit = emp.credit_balance
        if credit:
            # Accrue 1.25 vacation + 1.25 sick (example values, adjust as needed)
            credit.update_vacation(earned=1.25)
            credit.update_sick(earned=1.25)
        else:
            credit = EmployeeCredit(
                employee_id=emp.id,
                vacation_earned=1.25,
                vacation_used=0.0,
                vacation_remaining=1.25,
                sick_earned=1.25,
                sick_used=0.0,
                sick_remaining=1.25,
            )
            db.session.add(credit)

        # Log the transactions separately
        vacation_tx = CreditTransaction(
            employee_id=emp.id,
            leave_type="Vacation",
            action="Earned",
            amount=1.25,
            notes="Monthly vacation leave accrual"
        )
        sick_tx = CreditTransaction(
            employee_id=emp.id,
            leave_type="Sick",
            action="Earned",
            amount=1.25,
            notes="Monthly sick leave accrual"
        )

        db.session.add(vacation_tx)
        db.session.add(sick_tx)

    db.session.commit()








@app.route('/force-reset', methods=['GET', 'POST'])
@login_required
def force_reset():
    if not current_user.must_reset_password:
        return redirect(url_for('login'))  # Prevent access if not required

    form = ForceResetForm()
    if form.validate_on_submit():

        existing_user = Users.query.filter_by(email=form.email.data).first()
        if existing_user and existing_user.id != current_user.id:
            form.email.errors.append('Email is already in use by another account.')
        else:
            # Update user email and password
            current_user.email = form.email.data
            current_user.password_hash = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            current_user.must_reset_password = False
            db.session.commit()
            flash('Password and email updated successfully!', 'success')
            return redirect(url_for('login'))

    return render_template('force_reset.html', form=form)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('login'))



@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        
        user = Users.query.filter_by(email=email).first()
        
        if user:
            # Generate secure token
            token = s.dumps(email, salt='password-reset-salt')
            reset_link = url_for('reset_password', token=token, _external=True)
            
            # Send reset email
            msg = Message('Password Reset Request')
            msg.recipients = [email]
            msg.body = f'''
                        Dear {user.name if user.name else 'User'},

                        We received a request to reset your account password. If you made this request, please click the link below to set a new password:

                        {reset_link}

                        This link will expire after a certain period for your security. If you did not request a password reset, you may safely ignore this message your password will remain unchanged.

                        Best regards,  
                        The HRSync
                        '''
            mail.send(msg)
            
            flash('A password reset link has been sent to your email.', 'info')
            return redirect(url_for('login'))
        else:
            flash('Email not found.', 'danger')

    return render_template('landing/forgotpassword.html')



@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        # Decode the email from the token
        email = s.loads(token, salt='password-reset-salt', max_age=3600)
    except Exception:
        flash('The password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match. Please try again.', 'danger')
            return redirect(request.url)

        # Backend validation for password strength
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return redirect(request.url)

        if not re.search(r'[A-Za-z]', password):
            flash('Password must contain at least one letter.', 'danger')
            return redirect(request.url)

        if not re.search(r'\d', password):
            flash('Password must contain at least one number.', 'danger')
            return redirect(request.url)

        # Find the user
        user = Users.query.filter_by(email=email).first()
        if user:
            # Bcrypt hashing
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            user.password_hash = hashed_password
            db.session.commit()

            flash('Your password has been updated successfully!', 'success')
            return redirect(url_for('login'))
        else:
            flash('User not found.', 'danger')
            return redirect(url_for('forgot_password'))

    return render_template('landing/reset_password.html')




def save_picture(form_picture):
    # Generate a random filename
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext

    # Define path to save image
    picture_path = os.path.join(current_app.root_path, 'static/img/avatars', picture_fn)

    # Ensure the folder exists
    os.makedirs(os.path.dirname(picture_path), exist_ok=True)

    # Resize and save image
    output_size = (125, 125)
    image = Image.open(form_picture)  # make sure Pillow is installed
    image.thumbnail(output_size)
    image.save(picture_path)

    return picture_fn


# SUPER ADMIN

@app.route('/job_order_history/<int:employee_id>')
@login_required
def job_order_history(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    current = None

    if employee.job_order_details:
        jod = employee.job_order_details
        current = {
            "position_title": getattr(jod, "position_title", "N/A"),
            "department": getattr(getattr(jod, "assigned_department", None), "name", "N/A"),
            "contract_start": (
                jod.contract_start.strftime('%B %d, %Y')
                if isinstance(jod.contract_start, (date, datetime)) else jod.contract_start or "N/A"
            ),
            "contract_end": (
                jod.contract_end.strftime('%B %d, %Y')
                if isinstance(jod.contract_end, (date, datetime)) else jod.contract_end or "N/A"
            ),
            "date_hired": (
                jod.date_hired.strftime('%Y-%m-%d')
                if isinstance(jod.date_hired, (date, datetime)) else jod.date_hired or "N/A"
            ),
        }

    history_records = (
        JobOrderHistory.query
        .filter_by(employee_id=employee_id)
        .order_by(JobOrderHistory.archived_at.desc())
        .all()
    )

    history = []
    for h in history_records:
        history.append({
            "position_title": getattr(h, "position_title", "N/A"),
            "department": getattr(getattr(h, "assigned_department", None), "name", "N/A"),
            "contract_start": (
                h.contract_start.strftime('%B %d, %Y')
                if isinstance(h.contract_start, (date, datetime)) else h.contract_start or "N/A"
            ),
            "contract_end": (
                h.contract_end.strftime('%B %d, %Y')
                if isinstance(h.contract_end, (date, datetime)) else h.contract_end or "N/A"
            ),
            "return_date": (
                h.return_date.strftime('%B %d, %Y')
                if isinstance(h.return_date, (date, datetime)) else h.return_date or "N/A"
            ),
            "reason": getattr(h, "reason", "N/A"),
        })

    return jsonify({"current": current, "history": history})


@app.route("/Employee", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def EmployeeSection():
    # --- Active and not-deleted employees grouped by employment type ---
    permanent_employees = (
        Employee.query
        .join(PermanentEmployeeDetails)
        .join(Department)
        .filter(Employee.is_deleted == False, Employee.employment_status == 'active')
        .all()
    )

    casual_employees = (
        Employee.query
        .join(CasualEmployeeDetails)
        .outerjoin(Department, CasualEmployeeDetails.assigned_department)
        .filter(Employee.is_deleted == False, Employee.employment_status == 'active')
        .options(joinedload(Employee.casual_details).joinedload(CasualEmployeeDetails.assigned_department))
        .all()
    )

    job_order_employees = (
        Employee.query
        .join(JobOrderDetails)
        .outerjoin(Department, JobOrderDetails.assigned_department)
        .filter(Employee.is_deleted == False, Employee.employment_status == 'active')
        .options(joinedload(Employee.job_order_details).joinedload(JobOrderDetails.assigned_department))
        .order_by(Employee.first_name.asc())
        .all()
    )

    # --- Helper function to group employees by department ---
    def group_by_department(employees):
        grouped = defaultdict(list)
        for emp in employees:
            dept_name = emp.department.name if emp.department else "No Department"
            grouped[dept_name].append(emp)
        return dict(grouped)

    # ✅ Step Eligibility Logic (accurate based on current step vs. expected step)
    for emp in permanent_employees:
        pd = emp.permanent_details
        if not pd or not pd.date_original_appointment:
            emp.is_step_eligible_now = False
            continue

        # Compute years of service
        years_since_appointment = (date.today() - pd.date_original_appointment).days // 365

        # Compute expected step (1 step every 3 years, capped at 8)
        expected_step = min(1 + (years_since_appointment // 3), 8)
        current_step = pd.step or 1

        # Skip if already maxed out
        if current_step >= 8:
            emp.is_step_eligible_now = False
            continue

        # ✅ Check if already recorded in salary history for this interval
        elapsed_interval = (years_since_appointment // 3) * 3
        reason_label = f"{elapsed_interval}-year step increase"

        existing_record = PermanentSalaryHistory.query.filter_by(
            permanent_employee_id=pd.id,
            reason=reason_label
        ).first()

        # ✅ Eligible only if:
        #  - Current step < expected step
        #  - No salary record yet for this milestone
        emp.is_step_eligible_now = (
            current_step < expected_step and existing_record is None
        )

        # Optional: Attach diagnostic info for display
        emp.expected_step = expected_step
        emp.years_since_appointment = years_since_appointment


    # ✅ Benefit eligibility computation (still based on total service)
    milestone_years = [10, 15, 20, 25, 30]
    eligible_for_benefits = {}

    for emp in permanent_employees:
        pd = emp.permanent_details
        if not pd or not pd.date_original_appointment:
            continue

        years_of_service = (date.today() - pd.date_original_appointment).days // 365

        for milestone in milestone_years:
            if years_of_service >= milestone:
                benefit_name = f"{milestone}-Year Benefit"

                existing_benefit = PermanentEmployeeBenefitEligibility.query.filter_by(
                    permanent_employee_id=pd.id,
                    benefit_name=benefit_name,
                    is_eligible=True
                ).first()

                if not existing_benefit:
                    eligible_for_benefits[emp.id] = milestone
                    break  # Only show the first eligible milestone

    # --- Group employees by department ---
    permanent_by_dept = group_by_department(permanent_employees)
    job_order_by_dept = group_by_department(job_order_employees)

    # --- Load departments and positions ---
    departments = Department.query.all()
    positions = Position.query.all()

    # Group positions by department
    positions_by_dept = defaultdict(list)
    for position in positions:
        dept_name = position.department.name if position.department else "No Department"
        positions_by_dept[dept_name].append(position)

    # --- Stats ---
    total_departments = len(departments)
    total_employee = Employee.query.filter_by(is_deleted=False, employment_status='active').count()
    
    return render_template(
        'superAdmin/employee.html',
        title="Employee",
        permanent_by_dept=permanent_by_dept,
        casual_employees=casual_employees,
        job_order_employees=job_order_employees,
        departments=departments,
        positions=positions,
        positions_by_dept=positions_by_dept,
        total_departments=total_departments,
        total_employee=total_employee,
        today=datetime.utcnow().date(),
        eligible_for_benefits=eligible_for_benefits
    )






@app.route('/grant_benefit', methods=['POST'])
@login_required
@role_required('hr')
def grant_benefit():
    emp_id = request.form.get('employee_id')  # This is Employee.id
    milestone = request.form.get('milestone')
    benefit_name = f"{milestone}-Year Benefit"

    # Get the permanent details record (you need the permanent_employee_id, not employee_id)
    emp = Employee.query.filter_by(id=emp_id).first()

    if not emp or not emp.permanent_details:
        flash("Invalid employee or permanent details not found.", "danger")
        return redirect(request.referrer)

    perm_details = emp.permanent_details  # This is a PermanentEmployeeDetails object

    # Check if benefit record already exists
    benefit = PermanentEmployeeBenefitEligibility.query.filter_by(
        permanent_employee_id=perm_details.id,
        benefit_name=benefit_name
    ).first()

    if not benefit:
        benefit = PermanentEmployeeBenefitEligibility(
            permanent_employee_id=perm_details.id,
            benefit_name=benefit_name,
            eligibility_years=int(milestone),
            is_eligible=True,
            eligible_since=date.today(),
            checked_at=datetime.utcnow(),
            checked_by=current_user.name
        )
        db.session.add(benefit)
    else:
        benefit.is_eligible = True
        benefit.eligible_since = date.today()
        benefit.checked_at = datetime.utcnow()
        benefit.checked_by = current_user.name

    db.session.commit()
    flash(f"{milestone}-Year Benefit granted to employee.", "success")
    return redirect(request.referrer)



@app.route("/process_step_increase", methods=["POST"])
@login_required
@role_required('hr')
def process_step_increase():
    emp_id = request.form.get("employee_id")
    previous_salary = request.form.get("previous_salary")
    new_salary = request.form.get("new_salary")
    effective_date = request.form.get("effective_date")

    if not emp_id or not new_salary or not effective_date:
        flash("Missing required fields.", "danger")
        return redirect(url_for("EmployeeSection"))

    employee = Employee.query.get(emp_id)
    if not employee or not employee.permanent_details:
        flash("Permanent employee not found.", "danger")
        return redirect(url_for("EmployeeSection"))

    permanent_info = employee.permanent_details

    if not permanent_info.date_original_appointment:
        flash("Missing date of original appointment for this employee.", "danger")
        return redirect(url_for("EmployeeSection"))

    # Parse salary safely
    def parse_number(value):
        if not value:
            return 0
        value = value.strip()
        valid_format = re.match(r"^\d{1,3}(,\d{3})*(\.\d{1,2})?$", value) or re.match(r"^\d+(\.\d{1,2})?$", value)
        if not valid_format:
            raise ValueError("Invalid number format")
        return float(value.replace(",", ""))

    try:
        prev_salary_num = parse_number(previous_salary)
        new_salary_num = parse_number(new_salary)
    except ValueError:
        flash("Invalid salary format. Please enter a valid number (e.g., 2,000,000.00).", "danger")
        return redirect(url_for("EmployeeSection"))

    if new_salary_num < prev_salary_num:
        flash("New salary cannot be lower than previous salary.", "danger")
        return redirect(url_for("EmployeeSection"))

    prev_salary_value = f"{prev_salary_num:,.2f}"
    new_salary_value = f"{new_salary_num:,.2f}"

    years_since_appointment = (
        datetime.strptime(effective_date, '%Y-%m-%d').date() - permanent_info.date_original_appointment
    ).days // 365

    step_interval = 3
    elapsed_interval = (years_since_appointment // step_interval) * step_interval

    if elapsed_interval < step_interval:
        flash(f"Employee not yet eligible (only {years_since_appointment} years since original appointment).", "warning")
        return redirect(request.referrer or url_for("EmployeeSection"))

    # ✅ Compute what step they should be on
    expected_step = min((years_since_appointment // 3) + 1, 8)
    current_step = permanent_info.step or 1

    if current_step < expected_step:
        new_step = expected_step
    else:
        new_step = min(current_step + 1, 8)

    reason = f"{elapsed_interval}-year step increase"

    # Record salary change
    salary_record = PermanentSalaryHistory(
        permanent_employee_id=permanent_info.id,
        previous_salary=prev_salary_value,
        new_salary=new_salary_value,
        effective_date=effective_date,
        reason=reason,
        updated_by=current_user.name
    )
    db.session.add(salary_record)

    # ✅ Apply updates
    permanent_info.actual_salary = new_salary_value
    permanent_info.step = new_step

    db.session.commit()

    flash(f"Step increase recorded successfully (now Step {new_step}): {reason}", "success-timed")
    return redirect(url_for("EmployeeSection"))







@app.route('/employee/terminate/<int:employee_id>', methods=['POST'])
@login_required
def terminate_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    reason = request.form.get('reason')

    if not reason:
        flash("Termination reason is required.", "danger")
        return redirect(url_for('EmployeeSection'))

    # Determine employment type
    if employee.permanent_details:
        emp_type = "permanent"
    elif employee.casual_details:
        emp_type = "casual"
    elif employee.job_order_details:
        emp_type = "job_order"
    else:
        emp_type = "unknown"

    # Log termination history
    history = EmploymentTerminationHistory(
        employee_id=employee.id,
        employment_type=emp_type,
        reason=reason,
        terminated_by=current_user.id
    )
    db.session.add(history)

    # Soft delete employee
    employee.soft_delete()
    db.session.commit()

    flash(
        f'Employee {employee.last_name}, {employee.first_name} has been terminated.',
        'success-timed'
    )
    return redirect(url_for('EmployeeSection'))





@app.route("/Employee/Archive", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def EmployeeArchiveSection():
    # Only include inactive or deleted employees

    permanent_employees = (
        Employee.query
        .join(PermanentEmployeeDetails)
        .join(Department)
        .options(joinedload(Employee.termination_records))   # <-- preload
        .filter(
            (Employee.is_deleted == True) | (Employee.employment_status != 'active')
        )
        .all()
    )

    casual_employees = (
        Employee.query
        .join(CasualEmployeeDetails)
        .outerjoin(Department, CasualEmployeeDetails.assigned_department_id == Department.id)
        .options(joinedload(Employee.termination_records))   # <-- preload
        .filter(
            (Employee.is_deleted == True) | (Employee.employment_status != 'active')
        )
        .all()
    )

    job_order_employees = (
        Employee.query
        .join(JobOrderDetails)
        .outerjoin(Department, JobOrderDetails.assigned_department_id == Department.id)
        .options(joinedload(Employee.termination_records))   # <-- preload
        .filter(
            (Employee.is_deleted == True) | (Employee.employment_status != 'active')
        )
        .order_by(Employee.first_name.asc())
        .all()
    )

    # Group employees by department
    def group_by_department(employees):
        grouped = defaultdict(list)
        for emp in employees:
            dept_name = emp.department.name if emp.department else "No Department"
            grouped[dept_name].append(emp)
        return dict(grouped)

    permanent_by_dept = group_by_department(permanent_employees)
    casual_by_dept = group_by_department(casual_employees)
    job_order_by_dept = group_by_department(job_order_employees)

    departments = Department.query.all()
    positions = Position.query.all()

    total_departments = len(departments)
    total_employee = Employee.query.filter(
        (Employee.is_deleted == True) | (Employee.employment_status != 'active')
    ).count()

    return render_template(
        'superAdmin/employee_archive.html',  # You'll need to create this template
        title="Archived Employees",
        permanent_by_dept=permanent_by_dept,
        casual_by_dept=casual_by_dept,
        job_order_by_dept=job_order_by_dept,
        departments=departments,
        positions=positions,
        total_departments=total_departments,
        total_employee=total_employee
    )


@app.route('/return_casual_employee', methods=['POST'])
@login_required
@role_required('hr')
def return_casual_employee():
    employee_id = request.form.get("employee_id")
    return_date_str = request.form.get("return_date")
    reason = request.form.get("reason")
    employment_from_str = request.form.get("employment_from")
    employment_to_str = request.form.get("employment_to")
    daily_wage_str = request.form.get("employeeDailyWage")
    assigned_department_id = request.form.get("assigned_department_id")

    # --- Validation 1: Required fields ---
    if not employee_id:
        flash("Employee ID is required.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))
    if not return_date_str:
        flash("Return date is required.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    # --- Validation 2: Parse dates ---
    try:
        return_date = datetime.strptime(return_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid return date format. Use YYYY-MM-DD.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    employment_from = None
    if employment_from_str:
        try:
            employment_from = datetime.strptime(employment_from_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid employment start date format.", "danger")
            return redirect(url_for('EmployeeArchiveSection'))

    employment_to = None
    if employment_to_str:
        try:
            employment_to = datetime.strptime(employment_to_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid employment end date format.", "danger")
            return redirect(url_for('EmployeeArchiveSection'))

    today = datetime.now(ZoneInfo("Asia/Manila")).date()

    # 1. No past dates allowed
    if return_date < today:
        flash("Return date cannot be in the past.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    if employment_from and employment_from < today:
        flash("Employment start date cannot be in the past.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    if employment_to and employment_to < today:
        flash("Employment end date cannot be in the past.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    # --- Validation 3: Date logic ---
    if employment_from and employment_to and employment_from > employment_to:
        flash("Employment start date cannot be after end date.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    if employment_from and return_date < employment_from:
        flash("Return date cannot be before employment start date.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    if employment_to and return_date > employment_to:
        flash("Return date cannot be after employment end date.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    # --- Validation 4: Daily wage numeric ---
    daily_wage = None
    if daily_wage_str:
        try:
            daily_wage = float(daily_wage_str)
            if daily_wage < 0:
                raise ValueError("Daily wage must be positive.")
        except ValueError:
            flash("Invalid daily wage value.", "danger")
            return redirect(url_for('EmployeeArchiveSection'))

    # --- Step 5: Fetch employee ---
    employee = Employee.query.get(employee_id)
    if not employee or not employee.casual_details:
        flash("Employee not found or not a casual employee", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    casual = employee.casual_details

    # --- Step 6: Save snapshot ---
    history = CasualEmployeeHistory(
        employee_id=employee.id,
        position_id=casual.position_id,
        equivalent_salary=casual.equivalent_salary,
        daily_wage=casual.daily_wage,
        contract_start=casual.contract_start,
        contract_end=casual.contract_end,
        return_date=return_date,
        reason=reason
    )
    db.session.add(history)

    # --- Step 7: Update casual details ---
    casual.daily_wage = daily_wage
    casual.contract_start = employment_from
    casual.contract_end = employment_to
    casual.assigned_department_id = assigned_department_id if assigned_department_id else None

    # --- Step 8: Restore employee ---
    employee.employment_status = 'active'
    employee.restore()  # sets is_deleted = False

    db.session.commit()
    flash("Casual employee successfully returned.", "success")
    return redirect(url_for('EmployeeArchiveSection'))




@app.route('/return_jo_employee', methods=['POST'])
@login_required
@role_required('hr')
def return_jo_employee():
    employee_id = request.form.get("employee_id")
    date_returned_str = request.form.get("date_returned")
    contract_start_str = request.form.get("contract_start")
    contract_end_str = request.form.get("contract_end")
    assigned_department_id = request.form.get("assigned_department_id")
    reason = request.form.get("reason")

    print("DEBUG RAW INPUTS:")
    print(f"employee_id={employee_id}")
    print(f"date_returned_str={date_returned_str}")
    print(f"contract_start_str={contract_start_str}")
    print(f"contract_end_str={contract_end_str}")
    print(f"assigned_department_id={assigned_department_id}")
    print(f"reason={reason}")

    # --- Validation 1: Required fields ---
    if not employee_id:
        flash("Employee ID is required.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))
    if not date_returned_str:
        flash("Return date is required.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    # --- Validation 2: Parse dates ---
    try:
        date_returned = datetime.strptime(date_returned_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid return date format. Use YYYY-MM-DD.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    contract_start = None
    if contract_start_str:
        try:
            contract_start = datetime.strptime(contract_start_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid contract start date format.", "danger")
            return redirect(url_for('EmployeeArchiveSection'))

    contract_end = None
    if contract_end_str:
        try:
            contract_end = datetime.strptime(contract_end_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid contract end date format.", "danger")
            return redirect(url_for('EmployeeArchiveSection'))

    today = datetime.now(ZoneInfo("Asia/Manila")).date()

    # --- Validation 3: No past dates allowed ---
    if date_returned < today:
        flash("Return date cannot be in the past.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    if contract_start and contract_start < today:
        flash("Contract start date cannot be in the past.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    if contract_end and contract_end < today:
        flash("Contract end date cannot be in the past.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    # --- Validation 4: Date logic ---
    if contract_start and contract_end and contract_start > contract_end:
        flash("Contract start date cannot be after end date.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    if contract_start and date_returned < contract_start:
        flash("Return date cannot be before contract start date.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    if contract_end and date_returned > contract_end:
        flash("Return date cannot be after contract end date.", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    # --- Step 5: Fetch employee ---
    employee = Employee.query.get(employee_id)
    if not employee or not employee.job_order_details:
        flash("Employee not found or not a JO employee", "danger")
        return redirect(url_for('EmployeeArchiveSection'))

    jo = employee.job_order_details

    # --- Step 6: Save snapshot ---
    history = JobOrderHistory(
        employee_id=employee.id,
        position_title=jo.position_title,
        assigned_department_id=jo.assigned_department_id,
        contract_start=jo.contract_start,
        contract_end=jo.contract_end,
        return_date=date_returned,
        reason=reason if reason else "Rehired/Returned"
    )
    db.session.add(history)

    # --- Step 7: Update JO details ---
    jo.contract_start = contract_start
    jo.contract_end = contract_end
    jo.assigned_department_id = assigned_department_id if assigned_department_id else None

    # --- Step 8: Restore employee ---
    employee.employment_status = 'active'
    employee.restore()  # sets is_deleted = False

    db.session.commit()
    flash("JO employee successfully returned.", "success")
    return redirect(url_for('EmployeeArchiveSection'))


@app.route('/employee/return/<int:employee_id>', methods=['POST'])
@login_required
@role_required('hr')
def return_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)

    # Only check for permanent employees
    if employee.permanent_details:
        position = employee.permanent_details.position
        position_id = employee.permanent_details.position_id

        # Count active permanent employees in the same position
        active_count = Employee.query \
            .join(PermanentEmployeeDetails) \
            .filter(
                PermanentEmployeeDetails.position_id == position_id,
                Employee.employment_status == 'active',
                Employee.is_deleted == False
            ).count()

        if active_count >= position.number_of_positions:
            flash(
                f"Cannot return {employee.first_name} {employee.last_name}. "
                f"The position '{position.title}' is already full "
                f"({active_count}/{position.number_of_positions}).", 'warning'
            )
            return redirect(url_for('EmployeeArchiveSection'))

    # Restore employee
    employee.employment_status = 'active'
    employee.restore()  # restore from soft delete
    db.session.commit()

    flash(f'Employee {employee.last_name}, {employee.first_name} has been returned.', 'success-timed')
    return redirect(url_for('EmployeeSection'))





@app.route('/get_positions/<int:department_id>', methods=['GET'])
@login_required
def get_positions_by_department(department_id):
    positions = Position.query.filter_by(department_id=department_id).all()
    position_list = [{'id': p.id, 'title': p.title} for p in positions]
    return jsonify(position_list)



@app.route("/Employee/Detail", methods=['GET'])
@login_required
@role_required('hr')
def EmployeeDetail():
    employee_id = request.args.get('id')

    if not employee_id:
        flash("Employee not found.", "danger")
        return redirect(url_for('EmployeeSection'))

    # Fetch main employee
    employee = Employee.query.get_or_404(employee_id)

    # Fetch specific employee type details
    permanent_details = PermanentEmployeeDetails.query.filter_by(employee_id=employee.id).first()
    casual_details = CasualEmployeeDetails.query.filter_by(employee_id=employee.id).first()
    job_order_details = JobOrderDetails.query.filter_by(employee_id=employee.id).first()


    # Fetch granted benefits if permanent
    benefits = []
    if permanent_details:
        benefits = PermanentEmployeeBenefitEligibility.query.filter_by(
            permanent_employee_id=permanent_details.id,
            is_eligible=True
        ).order_by(PermanentEmployeeBenefitEligibility.eligibility_years.asc()).all()

    # Fetch latest IPCR
    latest_ipcr = IPCR.query.filter_by(employee_id=employee.id).order_by(desc(IPCR.id)).first()


    eligible_for_bonus = False
    bonus_period_name = None
    if latest_ipcr and latest_ipcr.adjective_rating:
        if latest_ipcr.adjective_rating.strip().lower() == "very satisfactory":
            eligible_for_bonus = True
            bonus_period_name = latest_ipcr.period.name if latest_ipcr.period else "Unknown Period"



    # AI Insight fields
    ai_summary = None
    ai_suggestions = None
    ai_training_recommendations = None

    if latest_ipcr and latest_ipcr.ai_insight:
        ai_insight = latest_ipcr.ai_insight
        ai_summary = ai_insight.ai_summary

        try:
            ai_suggestions = json.loads(ai_insight.ai_suggestion or "[]")
        except Exception:
            ai_suggestions = [ai_insight.ai_suggestion] if ai_insight.ai_suggestion else []

        try:
            ai_training_recommendations = json.loads(ai_insight.ai_training_recommendations or "[]")
        except Exception:
            ai_training_recommendations = [ai_insight.ai_training_recommendations] if ai_insight.ai_training_recommendations else []


    # Second chart: Q/E/T/A per MFO
    chart_data_mfo = {
    "categories": [],
    "series": [
        {"name": "Quality (Q)", "data": []},
        {"name": "Efficiency (E)", "data": []},
        {"name": "Timeliness (T)", "data": []},
        {"name": "Average (A)", "data": []}
    ]
    }

    if latest_ipcr:
        for idx, section in enumerate(latest_ipcr.sections, start=1):
            mfo_label = f"{section.type} - {latest_ipcr.period.name}"
            chart_data_mfo["categories"].append(mfo_label)

            rating_q, rating_e, rating_t, rating_a = [], [], [], []

            for item in section.section_items:
                if item.rating_q is not None:
                    rating_q.append(item.rating_q)
                if item.rating_e is not None:
                    rating_e.append(item.rating_e)
                if item.rating_t is not None:
                    rating_t.append(item.rating_t)
                if item.rating_a is not None:
                    rating_a.append(item.rating_a)

            def avg(ratings):
                return round(sum(ratings) / len(ratings), 2) if ratings else 0

            chart_data_mfo["series"][0]["data"].append(avg(rating_q))
            chart_data_mfo["series"][1]["data"].append(avg(rating_e))
            chart_data_mfo["series"][2]["data"].append(avg(rating_t))
            chart_data_mfo["series"][3]["data"].append(avg(rating_a))



    # Gather IPCRs for chart
    ipcr_list = IPCR.query.options(
        joinedload(IPCR.period),
        joinedload(IPCR.sections).joinedload(EvaluationSection.section_items)
    ).filter_by(employee_id=employee.id) \
     .join(EvaluationPeriod) \
     .order_by(EvaluationPeriod.start_date).all()

    chart_data = []
    for ipcr in ipcr_list:
        rating_a_values = [
            item.rating_a for section in ipcr.sections
            for item in section.section_items if item.rating_a is not None
        ]
        avg_rating_a = round(sum(rating_a_values) / len(rating_a_values), 2) if rating_a_values else 0
        chart_data.append({
            "period": ipcr.period.name if ipcr.period else "N/A",
            "rating_a": avg_rating_a
        })


    casual_history = []
    if casual_details:
        casual_history = CasualEmployeeHistory.query.filter_by(employee_id=employee.id) \
            .order_by(CasualEmployeeHistory.contract_start.desc()).all()    

    termination_history = EmploymentTerminationHistory.query.filter_by(
    employee_id=employee.id
    ).order_by(EmploymentTerminationHistory.terminated_at.desc()).all()

    salary_history = []
    current_salary = None
    current_grade = None

    if permanent_details:
        salary_history = PermanentSalaryHistory.query.filter_by(
            permanent_employee_id=permanent_details.id
        ).order_by(PermanentSalaryHistory.effective_date.desc()).all()

        # Prefer actual_salary if available
        if permanent_details.actual_salary:
            # Clean ₱ and commas
            cleaned_salary = (
                permanent_details.actual_salary
                .replace('₱', '')
                .replace(',', '')
                .strip()
            )
            try:
                current_salary = float(cleaned_salary)
            except ValueError:
                current_salary = 0.0  # fallback if invalid
            current_grade = permanent_details.salary_grade

        elif salary_history:
            current_salary = salary_history[0].new_salary
            current_grade = salary_history[0].new_grade

    else:
        current_salary = getattr(employee, 'salary', None)
        current_grade = getattr(employee, 'salary_grade', None)




    return render_template('superAdmin/EmployeeDetail.html', 
                           title="Employee Details",
                           employee=employee,
                           permanent_details=permanent_details,
                           casual_details=casual_details,
                           job_order_details=job_order_details,
                           latest_ipcr=latest_ipcr,
                           ai_summary=ai_summary,
                           ai_suggestions=ai_suggestions,
                           ai_training_recommendations=ai_training_recommendations,
                           chart_data=chart_data,
                           benefits=benefits,
                           chart_data_mfo=chart_data_mfo,eligible_for_bonus=eligible_for_bonus,
                           bonus_period_name=bonus_period_name,casual_history=casual_history,
                           termination_history=termination_history,
                           salary_history=salary_history,
                            current_salary=current_salary,
                            current_grade=current_grade,)





@app.route('/evaluation-periods/create', methods=['POST'])
def create_evaluation_period():
    name = request.form.get('name')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    if not name or not start_date or not end_date:
        flash('All fields are required.', 'danger')
        return redirect(url_for('EvaluationPeriodHR'))

    try:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format. Please use YYYY-MM-DD.', 'danger')
        return redirect(url_for('EvaluationPeriodHR'))

   
    # today = datetime.now(ZoneInfo("Asia/Manila")).date()
    # if start_date_obj < today:
    #     flash('Start date cannot be in the past.', 'danger')
    #     return redirect(url_for('EvaluationPeriodHR'))

    # Validation: Start must be before end
    if start_date_obj >= end_date_obj:
        flash('End date must be after the start date.', 'danger')
        return redirect(url_for('EvaluationPeriodHR'))

    # Validation: Check for overlapping periods
    overlap = EvaluationPeriod.query.filter(
        and_(
            EvaluationPeriod.is_active == True,
            or_(
                and_(EvaluationPeriod.start_date <= start_date_obj,
                     EvaluationPeriod.end_date >= start_date_obj),
                and_(EvaluationPeriod.start_date <= end_date_obj,
                     EvaluationPeriod.end_date >= end_date_obj),
                and_(EvaluationPeriod.start_date >= start_date_obj,
                     EvaluationPeriod.end_date <= end_date_obj)
            )
        )
    ).first()

    if overlap:
        flash('The new evaluation period overlaps with an existing active period.', 'danger')
        return redirect(url_for('EvaluationPeriodHR'))

    # Validation: Only one active period at a time
    existing_active = EvaluationPeriod.query.filter_by(is_active=True).first()
    if existing_active:
        flash('An active evaluation period already exists. Please deactivate it before creating a new one.', 'warning')
        return redirect(url_for('EvaluationPeriodHR'))

    try:
        new_period = EvaluationPeriod(
            name=name,
            start_date=start_date_obj,
            end_date=end_date_obj,
            is_active=True
        )
        db.session.add(new_period)
        db.session.commit()

        # Send announcement
        employees = Users.query.join(Users.employee).filter(
            Users.role.in_(['employee', 'hr']),
            Employee.employment_status == 'active',
            db.not_(Employee.is_deleted),
            Employee.job_order_details == None
        ).all()

        # Optional: exclude department heads
        employees = [u for u in employees if not u.employee.is_department_head]

        subject = "New Evaluation Period Created"
        body = f"""
        📢 <strong>New Evaluation Period Announcement</strong><br><br>

        Dear Team,<br><br>

        We are pleased to inform you that a <strong>New Evaluation Period</strong> has been officially created and is now <strong>OPEN</strong>.<br><br>

        🔹 <strong>Evaluation Title</strong>: {name}<br>
        📅 <strong>Start Date</strong>: {start_date}<br>
        📅 <strong>End Date</strong>: {end_date}<br><br>

        All employees are encouraged to prepare and submit their required documents and performance reports within the specified period. For any questions or concerns, please coordinate with your respective supervisors or the HR Department.<br><br>

        Thank you for your cooperation and commitment to excellence.<br><br>
        – Human Resources Department
        """

        for user in employees:
            msg = UserMessage(
                sender_id=current_user.id,
                recipient_id=user.id,
                subject=subject,
                body=body,
                message_type='announcement'
            )
            db.session.add(msg)

        db.session.commit()
        flash('Evaluation period created successfully and announcement sent.', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating period: {str(e)}', 'danger')

    return redirect(url_for('EvaluationPeriodHR'))




@app.route("/EvaluationPeriod", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def EvaluationPeriodHR():
    periods = EvaluationPeriod.query.order_by(EvaluationPeriod.start_date.desc()).all()

    period_data = []
    for period in periods:
        # --- Permanent Employees ---
        permanent_employees = (
            Employee.query
            .join(PermanentEmployeeDetails)
            .join(Position)
            .join(Users, Users.employee_id == Employee.id)
            .filter(
                Employee.employment_status == 'active',
                Employee.is_deleted == False,
                ~Position.title.ilike('%head%'),
                Users.role != 'head'
            )
            .all()
        )

        # --- Casual Employees ---
        casual_employees = (
            Employee.query
            .join(CasualEmployeeDetails)
            .join(Position)
            .join(Users, Users.employee_id == Employee.id)
            .filter(
                Employee.employment_status == 'active',
                Employee.is_deleted == False,
                ~Position.title.ilike('%head%'),
                Users.role != 'head'
            )
            .all()
        )

        # Combine both
        employees = permanent_employees + casual_employees
        employee_ids = [emp.id for emp in employees]

        total_ipcr_expected = len(employee_ids)

        # ✅ Choose whether to count submitted or graded IPCRs:
        submitted_ipcr = IPCR.query.filter(
            IPCR.period_id == period.id,
            IPCR.employee_id.in_(employee_ids),
            IPCR.graded == True     # ← use IPCR.submitted == True if you want "submitted" count
        ).count()

        # Append result
        period_data.append({
            'period': period,
            'ipcr_submitted': submitted_ipcr,
            'ipcr_total': total_ipcr_expected,
        })

    return render_template(
        "superAdmin/evaluationPeriod.html",
        title="Submission",
        period_data=period_data
    )


@app.route("/edit-evaluation-period", methods=["POST"])
@login_required
@role_required('hr')
def edit_evaluation_period():
    period_id = request.form.get("period_id")
    period = EvaluationPeriod.query.get_or_404(period_id)

    name = request.form.get("name")
    start_date_str = request.form.get("start_date")
    end_date_str = request.form.get("end_date")

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
        return redirect(request.referrer or url_for("EvaluationPeriodHR"))

    # Use Philippine timezone for "today"
    tz = ZoneInfo("Asia/Manila")
    today = datetime.now(tz).date()

    # Validation checks
    if start_date < today:
        flash("Start date cannot be in the past.", "danger")
        return redirect(request.referrer or url_for("EvaluationPeriodHR"))

    if end_date <= start_date:
        flash("End date must be after the start date.", "danger")
        return redirect(request.referrer or url_for("EvaluationPeriodHR"))

    if not name or not name.strip():
        flash("Evaluation period name is required.", "danger")
        return redirect(request.referrer or url_for("EvaluationPeriodHR"))

    # Update values
    period.name = name.strip()
    period.start_date = start_date
    period.end_date = end_date

    db.session.commit()
    flash("Evaluation period updated successfully!", "success-timed")
    return redirect(url_for("EvaluationPeriodHR"))


@app.route("/close_evaluation_period/<int:period_id>", methods=['POST'])
@login_required
@role_required('hr')
def close_evaluation_period(period_id):
    period = EvaluationPeriod.query.get_or_404(period_id)
    period.is_active = False
    db.session.commit()
    flash(f"Evaluation period {period.name} has been closed.", "success-timed")
    return redirect(url_for('EvaluationPeriodHR'))


@app.route("/activate-evaluation-period", methods=["POST"])
@login_required
@role_required('hr')
def activate_evaluation_period():
    period_id = request.form.get("period_id")
    period = EvaluationPeriod.query.get_or_404(period_id)

    # Check if there is already an active evaluation period
    active_period = EvaluationPeriod.query.filter_by(is_active=True).first()
    if active_period:
        flash(f"Cannot activate '{period.name}'. Period '{active_period.name}' is already active.", "danger")
        return redirect(url_for("EvaluationPeriodHR"))

    # Activate the selected period
    period.is_active = True
    db.session.commit()
    flash(f"Evaluation period '{period.name}' is now active.", "success-timed")
    return redirect(url_for("EvaluationPeriodHR"))



@app.route("/Department/IPCR/View", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def DepartmentOPCR():
    period_id = request.args.get('period_id', type=int)
    all_periods = EvaluationPeriod.query.order_by(EvaluationPeriod.id.desc()).all()

    selected_period = None
    departments_data = []

    if not period_id and all_periods:
        period_id = all_periods[0].id

    if period_id:
        selected_period = EvaluationPeriod.query.get(period_id)
        if selected_period:
            departments = Department.query.all()
            total_all_employees = 0
            for dept in departments:
                # Permanent employees assigned to this department
                permanent_employees = Employee.query.filter(
                    Employee.department_id == dept.id,
                    Employee.is_deleted == False,
                    Employee.employment_status == 'active',
                    Employee.permanent_details.has(),
                    ~Employee.permanent_details.has(PermanentEmployeeDetails.position.has(Position.type.ilike('head')))
                ).all()

                # Casual employees assigned to this department via casual_details.assigned_department_id
                casual_employees = Employee.query.join(CasualEmployeeDetails).filter(
                    CasualEmployeeDetails.assigned_department_id == dept.id,
                    Employee.is_deleted == False,
                    Employee.employment_status == 'active'
                ).all()

                # Combine both
                employees = permanent_employees + casual_employees
                employee_ids = [emp.id for emp in employees]
                ipcr_total = len(employees)

                
              

                ipcrs = IPCR.query.filter(
                    IPCR.employee_id.in_(employee_ids),
                    IPCR.period_id == period_id
                ).all()

                ipcr_submitted_count = sum(1 for ipcr in ipcrs if ipcr.submitted)
                ipcr_not_submitted_count = ipcr_total - ipcr_submitted_count
                ipcr_graded_count = sum(1 for ipcr in ipcrs if ipcr.submitted and ipcr.graded)

                total_all_employees += ipcr_total
                print("===========================================")
                print(f"Department: {dept.name}")
                print(f"Total Employees: {ipcr_total}")

                print("===========================================")
            
                departments_data.append({
                    'division': dept.name,
                    'ipcr_total': ipcr_total,
                    'ipcr_submitted': ipcr_submitted_count,
                    'ipcr_not_submitted': ipcr_not_submitted_count,
                    'ipcr_graded': ipcr_graded_count,
                    'period_id': period_id 
                })

            print("*******************************************")
            print(f"TOTAL EMPLOYEES ACROSS ALL DEPARTMENTS: {total_all_employees}")
            print("*******************************************")


    return render_template(
        'superAdmin/IPCR_DepEmployee.html',
        title="Department IPCR",
        selected_period=selected_period,
        periods=all_periods,
        departments_data=departments_data
    )










@app.route("/Employee/IPCR", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def EmployeeIPCR():
    period_id = request.args.get('period_id', type=int)
    department_name = request.args.get('department')

    hr_employee = Employee.query.get(current_user.employee_id)

    # Default to 'Office of the Municipal Mayor' if no department selected
    if not department_name:
        department_name = hr_employee.department.name if hr_employee and hr_employee.department else "Office of the Municipal Mayor"


    all_periods = EvaluationPeriod.query.order_by(EvaluationPeriod.id.desc()).all()
    all_departments = Department.query.order_by(Department.name).all()

    if not period_id and all_periods:
        period_id = all_periods[0].id  # latest period id

    selected_period = EvaluationPeriod.query.get(period_id) if period_id else None
    
    department = Department.query.filter_by(name=department_name).first() if department_name else None

    employees_query = Employee.query.filter(Employee.is_deleted == False)

    if department:
        employees_query = employees_query.filter(Employee.department_id == department.id)

    employees_query_permanent = Employee.query.filter(
    Employee.is_deleted == False,
    Employee.employment_status == 'active',
    Employee.department_id == department.id if department else True,
    Employee.permanent_details.has(),
    ~Employee.permanent_details.has(PermanentEmployeeDetails.position.has(Position.type.ilike('head')))
    )

    employees_query_casual = Employee.query.join(CasualEmployeeDetails).filter(
        Employee.is_deleted == False,
        Employee.employment_status == 'active',
        CasualEmployeeDetails.assigned_department_id == department.id if department else True,
        ~Employee.casual_details.has(CasualEmployeeDetails.position.has(Position.type.ilike('head')))
    )
    
    # Combine both queries
    employees_query = employees_query_permanent.union(employees_query_casual)

    ipcr_alias = aliased(IPCR)

    if selected_period:
        employees_with_ipcr = (
            employees_query
            .outerjoin(ipcr_alias, and_(
                ipcr_alias.employee_id == Employee.id,
                ipcr_alias.period_id == selected_period.id
            ))
            .add_entity(ipcr_alias)
            .order_by(Employee.last_name, Employee.first_name)
            .all()
        )
    else:
        employees_with_ipcr = (
            employees_query
            .outerjoin(ipcr_alias, ipcr_alias.employee_id == Employee.id)
            .add_entity(ipcr_alias)
            .order_by(Employee.last_name, Employee.first_name)
            .all()
        )


    # Compute overall_grade for each employee's ipcr or None if no IPCR
    result_with_grades = []
    for employee, ipcr in employees_with_ipcr:


        if ipcr:
            sections = EvaluationSection.query.filter_by(ipcr_id=ipcr.id).options(
                joinedload(EvaluationSection.section_items)
            ).all()

            summary_counts = {'Core': 0, 'Support': 0}
            average_ratings = {}
            weights = {'Core': 0.90, 'Support': 0.10}

            for section in sections:
                category = section.type
                if category in summary_counts:
                    for item in section.section_items:
                        if item.rating_a is not None:
                            summary_counts[category] += 1
                            average_ratings.setdefault(category, []).append(float(item.rating_a))

            total_weighted = 0
            category_count = 0

            for category in ['Core', 'Support']:
                ratings = average_ratings.get(category, [])
                if ratings:
                    avg = sum(ratings) / len(ratings)
                    weighted = avg * weights[category]
                    total_weighted += weighted
                    category_count += 1

            overall_grade = round(total_weighted, 2) if category_count > 0 else None
        else:
            overall_grade = None

        result_with_grades.append((employee, ipcr, overall_grade))

    active_period = EvaluationPeriod.query.filter_by(is_active=True).first()


    return render_template(
        'superAdmin/IPCREmployee.html',
        title="IPCR",
        periods=all_periods,
        selected_period=selected_period,
        selected_department=department_name,
        departments=all_departments,
        employees_with_ipcr=result_with_grades,
        hr_employee=hr_employee,
        active_period=active_period
    )




@app.route('/HR/IPCR/<int:ipcr_id>')
@login_required
@role_required('hr')
def HRIpcrView(ipcr_id):
    ipcr = IPCR.query.get_or_404(ipcr_id)
    employee = ipcr.employee

    if employee.casual_details and employee.casual_details.assigned_department:
        department = employee.casual_details.assigned_department
    else:
        department = employee.department

    sections = EvaluationSection.query.filter_by(ipcr_id=ipcr.id).options(
        joinedload(EvaluationSection.section_items)
    ).all()

    # Only Core and Support for IPCR
    summary_counts = {'Core': 0, 'Support': 0}
    average_ratings = {}
    weights = {'Core': 0.90, 'Support': 0.10}

    for section in sections:
        category = section.type
        if category in summary_counts:
            for item in section.section_items:
                if item.rating_a is not None:
                    summary_counts[category] += 1
                    average_ratings.setdefault(category, []).append(float(item.rating_a))

    final_average = {}
    total_weighted = 0
    category_count = 0
    average_values = []

    for category in ['Core', 'Support']:
        ratings = average_ratings.get(category, [])
        count = summary_counts[category]

        if ratings:
            total = sum(ratings)
            avg = round(total / len(ratings), 2)
            weighted = round(avg * weights[category], 2)
            computation = f"{' + '.join(map(str, ratings))} = {total} ÷ {len(ratings)} = {avg} × {weights[category]} = {weighted}"
            total_weighted += weighted
            average_values.append(avg)
            category_count += 1
        else:
            avg = None
            weighted = None
            computation = "-"

        final_average[category] = {
            'count': count,
            'average': avg,
            'weighted': weighted,
            'computation': computation
        }

    final_overall = round(total_weighted, 4) if category_count > 0 else None
    average_rating = round(final_overall, 2) if final_overall is not None else None

    def get_adjective(rating):
        if rating is None:
            return "-"
        elif rating >= 4.5:
            return "Very Satisfactory"
        elif rating >= 3.5:
            return "Satisfactory"
        elif rating >= 2.5:
            return "Fair"
        elif rating >= 1.5:
            return "Poor"
        else:
            return "Very Poor"

    adjective_rating = get_adjective(average_rating)


    ## 🧭 Identify department head depending on employee type
    if employee.permanent_details:
        # Permanent employee → find head in the same department
        dept_head = (
            Employee.query
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(
                Employee.department_id == employee.department_id,
                Position.type == 'Head',
                Employee.is_deleted == False
            )
            .first()
        )

    elif employee.casual_details:
        # Casual employee → find head of their assigned department
        dept_head = (
            Employee.query
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(
                Employee.department_id == employee.casual_details.assigned_department_id,
                Position.type == 'Head',
                Employee.is_deleted == False
            )
            .first()
        )

    else:
        dept_head = None


    # 🧾 HR Staff (non-head)
    hr_staff = (
        Employee.query
        .join(Users, Employee.user)
        .join(UserPermission, Users.permissions)
        .join(PermanentEmployeeDetails)
        .join(Position)
        .filter(
            Employee.department_id == 15,
            Position.type != 'Head',
            UserPermission.permission == 'write_performance',
            UserPermission.is_allowed == True,
            Employee.is_deleted == False
        )
        .all()
    )

    # 🧾 HR Head
    hr_head = (
        Employee.query
        .join(PermanentEmployeeDetails)
        .join(Position)
        .filter(
            Position.id == 98,
            Employee.is_deleted == False
        )
        .first()
    )

    # 🧾 Define the "Assessed By" positions per line
    positions = [
        ["MUNICIPAL PLANNING AND DEVELOPMENT COORDINATOR I"],  # Line 1
        ["MUNICIPAL GOVERNMENT DEPARTMENT HEAD I (LDRRMO)"], 
        ["MUNICIPAL BUDGET OFFICER I"],  # Line 2
        ["MUNICIPAL TREASURER"],  # Line 3
        ["MUNICIPAL ACCOUNTANT"],
        ["MUNICIPAL GOVERNMENT DEPARTMENT HEAD I"],  # Line 4
    ]

    # 🧾 Helper function to get name by position title
    def get_permanent_employee_name_by_position(position_title):
        # ✅ Special override
        if position_title == "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I (LDRRMO)":
            return "Aldwin D. Aloquin"

        # 🔍 Default DB lookup
        emp = (
            db.session.query(Employee)
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(Position.title == position_title)
            .filter(Employee.is_deleted == False)
            .first()
        )
        if emp:
            middle_initial = f"{emp.middle_name[0].upper()}." if emp.middle_name else ""
            return f"{emp.first_name} {middle_initial} {emp.last_name}".strip()
        return "(Not Found)"


    # 🧾 Build "Assessed By" list
    assessed_by = []
    for line in positions:
        line_data = []
        for pos_title in line:
            name = get_permanent_employee_name_by_position(pos_title)
            line_data.append({
                "position": pos_title,
                "name": name
            })
        assessed_by.append(line_data)


    # 🧭 Workflow steps
    workflow = [
        {
            "step": 1,
            "name": f"{employee.first_name} {employee.middle_name or ''} {employee.last_name}",
            "position": employee.permanent_details.position.title if employee.permanent_details and employee.permanent_details.position else "",
            "description": "Submit IPCR form to Department Head."
        },
        {
            "step": 2,
            "name": f"{dept_head.first_name} {dept_head.middle_name or ''} {dept_head.last_name}" if dept_head else "-",
            "position": dept_head.permanent_details.position.title if dept_head and dept_head.permanent_details and dept_head.permanent_details.position else "",
            "description": "Grade IPCR form and provide feedback if needed."
        },
        {
            "step": 3,
            "assessed_by": assessed_by,
            "description": "Assess and review graded IPCR form before final HR validation."
        },
        {
            "step": 4,
            "staff": [
                {
                    "name": f"{staff.first_name} {staff.middle_name or ''} {staff.last_name}",
                    "position": staff.permanent_details.position.title if staff.permanent_details and staff.permanent_details.position else ""
                }
                for staff in hr_staff
            ] if hr_staff else [],
            "description": "Receive submission, check completeness, and forward to HR Head."
        },
        {
            "step": 5,
            "name": f"{hr_head.first_name} {hr_head.middle_name or ''} {hr_head.last_name}" if hr_head else "-",
            "position": hr_head.permanent_details.position.title if hr_head and hr_head.permanent_details and hr_head.permanent_details.position else "",
            "description": "Consolidate graded IPCR forms in the system for compliance and reporting."
        },
    ]


    # 🧾 Render template
    return render_template(
        'superAdmin/IPCR_View.html',
        ipcr=ipcr,
        sections=sections,
        employee=employee,
        department=department,
        final_average=final_average,
        final_overall=final_overall,
        average_rating=average_rating,
        adjective_rating=adjective_rating,
        workflow=workflow  # ✅ pass workflow to template
    )


     # --- NEW: Build workflow ---
    dept_head = (
    Employee.query
    .join(PermanentEmployeeDetails)
    .join(Position)
    .filter(
        Employee.department_id == employee.department_id,  # same department as IPCR owner
        Position.type == 'Head',                          # must be a Department Head
        Employee.is_deleted == False                      # exclude deleted employees
    )
    .first()
    )

    # HR Staff (non-head)
    hr_staff = (
    Employee.query
    .join(Users, Employee.user)                # join employee → user
    .join(UserPermission, Users.permissions)   # join user → permissions
    .join(PermanentEmployeeDetails)
    .join(Position)
    .filter(
        Employee.department_id == 15,
        Position.type != 'Head',                     # not the HR head
        UserPermission.permission == 'write_performance',  # must have this permission
        UserPermission.is_allowed == True,           # and it must be allowed
        Employee.is_deleted == False
    )
    .all()
    )


    # HR Head
    hr_head = (
        Employee.query
        .join(PermanentEmployeeDetails)
        .join(Position)
        .filter(
            Position.id == 98,
            Employee.is_deleted == False
        )
        .first()
    )

    workflow = [
    {
        "step": 1,
        "name": f"{employee.first_name} {employee.middle_name or ''} {employee.last_name}",
        "position": employee.permanent_details.position.title if employee.permanent_details and employee.permanent_details.position else "",
        "description": "Submit IPCR form to Department Head"
    },
    {
        "step": 2,
        "name": f"{dept_head.first_name} {dept_head.middle_name or ''} {dept_head.last_name}" if dept_head else "-",
        "position": dept_head.permanent_details.position.title if dept_head and dept_head.permanent_details and dept_head.permanent_details.position else "",
        "description": "Grade IPCR form and provide feedback if needed."
    },
    {
        "step": 3,
        "staff": [
            {
                "name": f"{staff.first_name} {staff.middle_name or ''} {staff.last_name}",
                "position": staff.permanent_details.position.title if staff.permanent_details and staff.permanent_details.position else ""
            }
            for staff in hr_staff
        ] if hr_staff else [],
        "description": "Receive submission, check completeness, and forward to HR Head."
    },
    {
        "step": 4,
        "name": f"{hr_head.first_name} {hr_head.middle_name or ''} {hr_head.last_name}" if hr_head else "-",
        "position": hr_head.permanent_details.position.title if hr_head and hr_head.permanent_details and hr_head.permanent_details.position else "",
        "description": "Consolidate graded IPCR forms in the system for compliance and reporting."
    },
]




    return render_template(
        'superAdmin/IPCR_View.html',
        ipcr=ipcr,
        sections=sections,
        employee=employee,
        department=employee.department,
        final_average=final_average,
        final_overall=final_overall,
        average_rating=average_rating,
        adjective_rating=adjective_rating,
        workflow=workflow  # pass workflow to template
    )





@app.route('/HR/Performance/Submit', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def EmployeeSubmitIPCRhr():
    # Fetch the active evaluation period from the database
    active_period = EvaluationPeriod.query.filter_by(is_active=True).first()

    # Get the current employee's full name
    if current_user.employee:
        emp = current_user.employee
        full_name = f"{emp.first_name} {emp.middle_name or ''} {emp.last_name}".strip()
    else:
        full_name = "N/A"

    # Fetch the most recent IPCR
    last_ipcr = IPCR.query.filter_by(employee_id=current_user.employee.id) \
                          .order_by(IPCR.id.desc()).first()

    # Prepare prefill data
    prefill_data = []

    if last_ipcr:
        for section in last_ipcr.sections:
            for item in section.section_items:
                prefill_data.append({
                    "type": section.type,
                    "mfo": item.mfo or "",
                    "success_indicator": item.success_indicator or "",
                    "allotted_budget": item.allotted_budget or "",
                    "accomplishment": item.accomplishment or ""
                    })
    
    # Determine if the last IPCR was returned (drafted, not submitted or graded)
    force_prefill = False
    if last_ipcr and not last_ipcr.submitted and not last_ipcr.graded:
        force_prefill = True

    return render_template(
        'superAdmin/submitIPCRHR.html',
        title="Submit IPCR",
        active_period=active_period,
        full_name=full_name,
        prefill_data=prefill_data,
        force_prefill=force_prefill,
    )




@app.route('/submit-ipcrHR', methods=['POST'])
@login_required
@role_required('hr')  # only HR can access
def submit_ipcrHR():
    data = request.get_json()
    employee = current_user.employee  # the employee related to this HR user (or however you get the employee)

    active_period = EvaluationPeriod.query.filter_by(is_active=True).first()
    if not active_period:
        flash("No active evaluation period found.", "danger")
        return redirect(url_for('EmployeeIPCRRecordHR'))

    ipcr = IPCR.query.filter_by(employee_id=employee.id, period_id=active_period.id).first()

    is_late = date.today() > active_period.end_date

    if ipcr:
        if ipcr.graded:
            flash("Cannot edit IPCR after it has been graded.", "warning")
            return redirect(url_for('EmployeeIPCRRecordHR'))

        # Delete old sections and section items
        for section in ipcr.sections:
            SectionItem.query.filter_by(section_id=section.id).delete()
            db.session.delete(section)
    else:
        ipcr = IPCR(employee_id=employee.id, period_id=active_period.id)
        db.session.add(ipcr)
        db.session.flush()

    ipcr.submitted = True
    first_submission = False
    ipcr.late_submission = is_late  # ✅ flag if submitted late

    
    if not ipcr.date_submitted:
        ipcr.date_submitted = datetime.utcnow()
        first_submission = True

    for section_data in data.get('sections', []):
        section = EvaluationSection(type=section_data.get('type'), ipcr_id=ipcr.id)
        db.session.add(section)
        db.session.flush()

        for item in section_data.get('items', []):
            accountable_name = f"{employee.last_name}, {employee.first_name} {employee.middle_name or ''}".strip()
            section_item = SectionItem(
                section_id=section.id,
                mfo=item.get('mfo'),
                success_indicator=item.get('success_indicator'),
                allotted_budget=item.get('allotted_budget'),
                accountable=accountable_name,
                accomplishment=item.get('accomplishment'),
                rating_q=None,
                rating_e=None,
                rating_t=None,
                rating_a=None,
                remarks=None
            )
            db.session.add(section_item)

    # Notify all active HR users only on first submission
    if first_submission:
        hr_users = (
            Users.query
            .join(Employee)
            .join(UserPermission, UserPermission.user_id == Users.id)
            .filter(
                Users.role == 'hr',
                Employee.employment_status == 'active',
                UserPermission.permission == 'write_performance',
                UserPermission.is_allowed == True
            )
            .all()
        )

        for hr_user in hr_users:
            submission_status = "LATE" if ipcr.late_submission else "on time"
            notif = UserMessage(
                sender_id=current_user.id,
                recipient_id=hr_user.id,
                subject="IPCR Submission Notification",
                body=(
                    f"Please be informed that {employee.first_name} {employee.last_name} "
                    f"has submitted their IPCR for the period '{active_period.name}' "
                    f"({submission_status})."
                ),
                message_type='ipcr_submission',
                timestamp=datetime.utcnow()
            )
            db.session.add(notif)

    db.session.commit()

    return jsonify({'redirect': url_for('EmployeeIPCRRecordHR')})





@app.route('/HR/Grade/IPCR/<int:ipcr_id>', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def HeadGradeIpcrHR(ipcr_id):
    ipcr = IPCR.query.get_or_404(ipcr_id)

    if request.method == 'POST':
        data = request.form.to_dict(flat=False)
        action = request.form.get('action')

        item_indexes = set()
        for key in data.keys():
            if key.startswith('items[') and '][' in key:
                idx = key.split('[')[1].split(']')[0]
                item_indexes.add(idx)

        all_ratings_filled = True

        for idx in sorted(item_indexes, key=int):
            item_id = request.form.get(f'items[{idx}][item_id]')
            rating_q = request.form.get(f'items[{idx}][rating_q]')
            rating_e = request.form.get(f'items[{idx}][rating_e]')
            rating_t = request.form.get(f'items[{idx}][rating_t]')
            rating_a = request.form.get(f'items[{idx}][rating_a]')
            remarks = request.form.get(f'items[{idx}][remarks]')

            if not all([rating_q, rating_e, rating_t, rating_a]):
                all_ratings_filled = False

            item = SectionItem.query.get(item_id)
            if item:
                item.rating_q = float(rating_q) if rating_q else None
                item.rating_e = float(rating_e) if rating_e else None
                item.rating_t = float(rating_t) if rating_t else None
                item.rating_a = float(rating_a) if rating_a else None
                item.remarks = remarks

        if action == "submit" and all_ratings_filled:
            weights = {'Core': 0.9, 'Support': 0.1}
            summary_counts = {'Core': 0, 'Support': 0}
            average_ratings = {}

            for section in ipcr.sections:
                category = section.type
                if category in weights:
                    for item in section.section_items:
                        if item.rating_a is not None:
                            summary_counts[category] += 1
                            average_ratings.setdefault(category, []).append(float(item.rating_a))

            total_weighted = 0
            category_count = 0

            for category in ['Core', 'Support']:
                ratings = average_ratings.get(category, [])
                if ratings:
                    avg = sum(ratings) / len(ratings)
                    weighted = avg * weights[category]
                    total_weighted += weighted
                    category_count += 1

            if category_count > 0:
                final_average = round(total_weighted, 4)
                overall_rating = round(final_average, 2)
                ipcr.final_average_rating = final_average
                ipcr.final_overall_rating = overall_rating

                if overall_rating >= 4.5:
                    ipcr.adjective_rating = "Very Satisfactory"
                elif overall_rating >= 3.5:
                    ipcr.adjective_rating = "Satisfactory"
                elif overall_rating >= 2.5:
                    ipcr.adjective_rating = "Fair"
                elif overall_rating >= 1.5:
                    ipcr.adjective_rating = "Poor"
                else:
                    ipcr.adjective_rating = "Very Poor"
            else:
                ipcr.final_average_rating = None
                ipcr.final_overall_rating = None
                ipcr.adjective_rating = None

            ipcr.graded = True

            # Prepare data for AI Insight
            ipcr_data = {
                "employee": f"{ipcr.employee.first_name} {ipcr.employee.last_name}" if ipcr.employee else "Unknown",
                "period": str(ipcr.period.name) if hasattr(ipcr.period, 'name') else str(ipcr.period),
                "sections": []
            }

            for section in ipcr.sections:
                section_data = {
                    "title": section.type,
                    "items": []
                }
                for item in section.section_items:
                    section_data["items"].append({
                        "description": f"{item.mfo} - {item.success_indicator}",
                        "rating_q": item.rating_q,
                        "rating_e": item.rating_e,
                        "rating_t": item.rating_t,
                        "rating_a": item.rating_a,
                        "remarks": item.remarks
                    })
                ipcr_data["sections"].append(section_data)

            try:
                ai_response = generate_ipcr_insight(ipcr_data)
                clean_text = clean_json(ai_response.text)
                structured = json.loads(clean_text)

                summary = structured.get("summary")
                suggestions = structured.get("suggestions")
                training = structured.get("recommended_training")

            except Exception as e:
                summary = "AI insight could not be generated."
                suggestions = [f"Error: {str(e)}"]
                training = []

            insight = AIInsight.query.filter_by(ipcr_id=ipcr.id).first()
            if not insight:
                insight = AIInsight(ipcr_id=ipcr.id)

            insight.ai_summary = summary
            insight.ai_suggestion = json.dumps(suggestions) if isinstance(suggestions, list) else suggestions
            insight.ai_training_recommendations = json.dumps(training) if isinstance(training, list) else training
            insight.last_updated = datetime.utcnow()

            db.session.add(insight)
            db.session.commit()
           
            dept = None
            if ipcr.employee:
                if ipcr.employee.permanent_details:
                    dept = ipcr.employee.department  # Permanent employees use department_id
                elif ipcr.employee.casual_details:
                    dept = ipcr.employee.casual_details.assigned_department  # Casual employees use assigned_department_id

            # ✅ Notify HR only if department is resolved
            if dept:
                notify_hr_if_department_complete(dept, ipcr.period_id, current_user.id)

            flash("IPCR submitted and AI Insight generated!", "success-timed")
            return redirect(url_for('EmployeeIPCR', period_id=ipcr.period_id, department=ipcr.employee.department.name))


        elif action == "draft":
            ipcr.graded = False
            db.session.commit()
            flash("Draft saved successfully.", "info-timed")
            return redirect(url_for('HeadGradeIpcrHR', ipcr_id=ipcr.id))

        elif action == "submit" and not all_ratings_filled:
            flash("All ratings must be filled to submit.", "danger-timed")
            return redirect(url_for('HeadGradeIpcrHR', ipcr_id=ipcr.id))

        elif action == "return":
            ipcr.submitted = False
            db.session.commit()
            flash("IPCR has been returned to the employee for revision.", "success-timed")
            return redirect(url_for('EmployeeIPCR', period_id=ipcr.period_id, department=ipcr.employee.department.name))

    sections = ipcr.sections
    return render_template('superAdmin/GradeIPCRHR.html', title="Grade IPCR", ipcr=ipcr, sections=sections)


@app.route("/HR/Permits", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def EmployeePermits():

    allowed_stages = ['HR', 'Mayor', 'Completed', 'Rejected']

    # Leave Permits
    leave_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Leave',
            PermitRequest.current_stage.in_(allowed_stages)
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Attach latest rejection history + user name to each leave permit
    for permit in leave_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name              # 👈 attach rejector’s name
            permit.rejected_remarks = history.remarks   # 👈 attach remarks if needed
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # Pending counts (your code as-is)
    pending_leave_count = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Leave',
            PermitRequest.status == 'In Progress',
            PermitRequest.current_stage == 'HR'
        )
        .count()
    )

    # Travel Orders
    travel_orders = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Travel Order',
            PermitRequest.current_stage.in_(allowed_stages)
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Attach latest rejection history + user name to each travel order
    for permit in travel_orders:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name          # name of rejector
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None


    pending_travel_count = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Travel Order',
            PermitRequest.status == 'In Progress',
            PermitRequest.current_stage == 'HR'
        )
        .count()
    )

    # Clearance
    clearance_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Clearance Form',
            PermitRequest.current_stage.in_(allowed_stages)
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )


    # Attach latest rejection history + user name to each clearance permit 👇
    for permit in clearance_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None


    pending_clearance_count = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Clearance Form',
            PermitRequest.status == 'In Progress',
            PermitRequest.current_stage == 'HR'
        )
        .count()
    )

    # COE
    coe_permits = (
        PermitRequest.query
        .filter_by(permit_type='Certification of Employment')
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

        # Attach latest rejection history + user name to each COE permit 👇
    for permit in coe_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    pending_coe_count = (
        PermitRequest.query
        .filter_by(permit_type='Certification of Employment', status='Pending')
        .count()
    )

    return render_template(
        'superAdmin/permit.html',
        title="Permits",
        leave_permits=leave_permits,
        travel_orders=travel_orders,
        clearance_permits=clearance_permits,
        coe_permits=coe_permits,
        pending_leave_count=pending_leave_count,
        pending_travel_count=pending_travel_count,
        pending_clearance_count=pending_clearance_count,
        pending_coe_count=pending_coe_count
    )




@app.route('/HR/Personal/Permit', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def HRpersonalpermit():
    employee_id = current_user.employee.id 

    # Leave Permits (for this employee only)
    leave_permits = (
        PermitRequest.query
        .filter_by(permit_type='Leave', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Travel Order Permits
    travel_orders = (
        PermitRequest.query
        .filter_by(permit_type='Travel Order', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Clearance Permits
    clearance_permits = (
        PermitRequest.query
        .filter_by(permit_type='Clearance Form', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # COE Permits
    coe_permits = (
        PermitRequest.query
        .filter_by(permit_type='Certification of Employment', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

        # Attach latest rejection history + user name to each COE permit 👇
    for permit in coe_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    return render_template('superAdmin/personalpermit.html', 
                           title="HR Permit", 
                           leave_permits=leave_permits,
                           travel_orders=travel_orders,
                           clearance_permits=clearance_permits,coe_permits=coe_permits)


@app.template_filter('b64encode')
def b64encode_filter(data):
    if data is None:
        return ''
    return base64.b64encode(data).decode('utf-8')


@app.route("/Accounts", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def ManageAcc():
    # Permanent Employees
    permanent_employees = (
        Employee.query
        .join(PermanentEmployeeDetails)
        .options(
            db.joinedload(Employee.permanent_details).joinedload(PermanentEmployeeDetails.position),
            db.joinedload(Employee.department),
            db.joinedload(Employee.user).joinedload(Users.signature_record)  # ✅ eager load signature
        )
        .all()
    )

    # Casual Employees
    casual_employees = (
        Employee.query
        .join(CasualEmployeeDetails)
        .options(
            db.joinedload(Employee.casual_details).joinedload(CasualEmployeeDetails.position),
            db.joinedload(Employee.casual_details).joinedload(CasualEmployeeDetails.assigned_department),
            db.joinedload(Employee.department),
            db.joinedload(Employee.user).joinedload(Users.signature_record)
        )
        .all()
    )

    # Job Order Employees
    job_order_employees = (
        Employee.query
        .join(JobOrderDetails)
        .options(
            db.joinedload(Employee.job_order_details),
            db.joinedload(Employee.department),
            db.joinedload(Employee.user).joinedload(Users.signature_record)
        )
        .all()
    )

    # ✅ Attach base64 signatures (so Jinja can use them directly)
    def attach_signature(employees):
        for emp in employees:
            if emp.user and emp.user.signature_record:
                emp.user.signature_b64 = "data:image/png;base64," + base64.b64encode(
                    emp.user.signature_record.signature
                ).decode("utf-8")
            else:
                emp.user.signature_b64 = None

    attach_signature(permanent_employees)
    attach_signature(casual_employees)
    attach_signature(job_order_employees)

    departments = Department.query.all()

    return render_template(
        'superAdmin/accounts.html',
        title="Accounts",
        permanent_employees=permanent_employees,
        casual_employees=casual_employees,
        job_order_employees=job_order_employees,
        departments=departments
    )



from io import BytesIO

@app.route('/update_user_account', methods=['POST'])
@login_required
@role_required('hr')
def update_user_account():
    employee_id = request.form['employee_id']
    login_id = request.form['login_id']
    email = request.form['email']
    role = request.form.get('role')

    # 🔍 Find the user based on employee_id
    user = Users.query.join(Employee).filter(Employee.id == employee_id).first()

    if not user:
        flash('User not found. No changes were made.', 'danger')
        return redirect(request.referrer or url_for('ManageAcc'))

    # ✏️ Update basic fields
    user.login_id = login_id
    user.email = email
    if role:
        user.role = role

    # ✅ Handle signature upload
    signature_file = request.files.get('signature_file')
    if signature_file and signature_file.filename.strip() != "":
        try:
            # Convert image and remove white background
            img = make_signature_transparent(signature_file)

            # Save processed image into bytes
            img_bytes = BytesIO()
            img.save(img_bytes, format="PNG")  # Always PNG for transparency
            img_bytes = img_bytes.getvalue()

            # Look for existing signature in DB
            signature = UserSignature.query.filter_by(user_id=user.id).first()
            if signature:
                signature.signature = img_bytes
            else:
                new_sig = UserSignature(user_id=user.id, signature=img_bytes)
                db.session.add(new_sig)

        except Exception as e:
            flash(f"Error processing signature: {str(e)}", "danger")

    try:
        db.session.commit()
        flash('User account updated successfully.', 'success-timed')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating account: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('ManageAcc'))




@app.context_processor
def inject_issue_count():
    total_issue_count = db.session.query(IssueReport).filter(IssueReport.status == 'Open').count()
    return dict(total_issue_count=total_issue_count)


# NOT FINAL / NOT SURE
def save_signature(form_signature):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_signature.filename)
    filename = random_hex + f_ext
    path = os.path.join(current_app.root_path, 'static/signatures', filename)

    # Resize signature (optional, keep aspect ratio)
    img = Image.open(form_signature)
    img.thumbnail((400, 200))
    img.save(path)

    return filename



def make_signature_transparent(input_file):
    img = Image.open(input_file).convert("RGBA")
    datas = img.getdata()

    newData = []
    for item in datas:
        # Detect white-ish pixels and make them transparent
        if item[0] > 240 and item[1] > 240 and item[2] > 240:  
            newData.append((255, 255, 255, 0))  # transparent
        else:
            newData.append(item)
    img.putdata(newData)

    return img

@app.route("/MyProfile", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def update_profile():
    form = UpdateSuperAdminProfileForm()
    employee = current_user.employee

    # Pre-fill profile data on GET request
    if request.method == 'GET':
        if employee:
            form.first_name.data = employee.first_name
            form.middle_name.data = employee.middle_name
            form.last_name.data = employee.last_name

            if employee.permanent_details:
                form.date_of_birth.data = employee.permanent_details.date_of_birth
                form.gender.data = employee.permanent_details.sex
                form.tin.data = employee.permanent_details.tin

        form.email.data = current_user.email

    # Handle profile update on POST request
    if form.submit.data and form.validate_on_submit():
        if employee:
            employee.first_name = form.first_name.data
            employee.middle_name = form.middle_name.data
            employee.last_name = form.last_name.data

            if employee.permanent_details:
                employee.permanent_details.date_of_birth = form.date_of_birth.data
                employee.permanent_details.sex = form.gender.data
                employee.permanent_details.tin = form.tin.data

            # Update display name
            full_name = " ".join(filter(None, [
                form.first_name.data,
                form.middle_name.data,
                form.last_name.data
            ]))
            current_user.name = full_name

        # Update email
        current_user.email = form.email.data

        # Save profile picture
        if form.image_file.data:
            picture_file = save_picture(form.image_file.data)
            current_user.image_file = picture_file

        # ✅ Save digital signature with transparency
        if form.signature_file.data:
            sig_file = form.signature_file.data

            # Process signature → make transparent
            transparent_img = make_signature_transparent(sig_file)

            # Save to memory buffer as PNG
            img_io = io.BytesIO()
            transparent_img.save(img_io, format="PNG")
            sig_bytes = img_io.getvalue()

            # Compute SHA256 hash
            sig_hash = hashlib.sha256(sig_bytes).hexdigest()

            if current_user.signature_record:
                current_user.signature_record.signature = sig_bytes
                current_user.signature_record.signature_hash = sig_hash
            else:
                signature_record = UserSignature(
                    user_id=current_user.id,
                    signature=sig_bytes,
                    signature_hash=sig_hash
                )
                db.session.add(signature_record)

        db.session.commit()
        flash('Your profile has been updated.', 'success-timed')
        return redirect(url_for('update_profile'))

    # Avatar fallback
    image_filename = current_user.image_file if current_user.image_file else 'default.png'
    image_path = url_for('static', filename='img/avatars/' + image_filename)

    # 🔑 Get user signature as base64 (for preview)
    signature_data = None
    if current_user.signature_record:
        sig_bytes = current_user.signature_record.signature
        signature_data = "data:image/png;base64," + base64.b64encode(sig_bytes).decode("utf-8")

    return render_template(
        'superAdmin/personalInfo.html',
        title="Profile",
        form=form,
        image_file=image_path,
        signature_data=signature_data
    )



@app.route("/UpdatePassword", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def update_password():
    form2 = UpdateSuperAdminPasswordForm()

    if request.method == 'POST' and form2.validate_on_submit():
        # Check if the current password matches
        if not bcrypt.check_password_hash(current_user.password_hash, form2.current_password.data):
            flash('Incorrect current password. Please try again.', 'danger')
        else:
            # Hash and update the new password
            new_hashed_password = bcrypt.generate_password_hash(form2.password.data).decode('utf-8')
            current_user.password_hash = new_hashed_password
            current_user.must_reset_password = False
            db.session.commit()
            flash('Your password has been updated.', 'success-timed')
            return redirect(url_for('update_password'))

    # Query only this user's login attempts
    logins = LoginActivity.query.filter_by(user_id=current_user.id).order_by(LoginActivity.timestamp.desc()).all()

    return render_template('superAdmin/update_password.html', form2=form2,logins=logins)




# newtravel
@app.route("/travel", methods=['GET'])
@login_required
@role_required('hr')
def travel_logs():
    search = request.args.get('search', '').strip()

    query = (
        db.session.query(TravelLog)
        .join(TravelOrder)
        .join(PermitRequest)
        .join(Employee)
        .options(
            joinedload(TravelLog.travel_order)
            .joinedload(TravelOrder.permit)
            .joinedload(PermitRequest.employee)
        )
    )

    if search:
        like = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(Employee.first_name).ilike(like),
                func.lower(Employee.last_name).ilike(like),
                func.lower(Employee.middle_name).ilike(like),
                func.lower(TravelOrder.destination).ilike(like),
                func.lower(TravelOrder.purpose).ilike(like),
                func.lower(TravelLog.tracking_id).ilike(like),
                func.lower(TravelLog.status).ilike(like),
                func.lower(func.concat(Employee.last_name, ', ', Employee.first_name)).ilike(like),
                func.lower(func.concat(Employee.first_name, ' ', Employee.last_name)).ilike(like),
            )
        )

    logs = query.order_by(
        case((TravelLog.status == 'Approved', 1), else_=0),
        desc(TravelLog.tracking_id)
    ).all()

    return render_template(
        'superAdmin/travellogs.html',
        title="Travel Logs",
        logs=logs,  # now a list, not a pagination object
        search=search
    )


# TravelLogs
@app.route('/approve_travel_leave', methods=['POST'])
@login_required
def approve_travel_leave():
    permit_id = request.form.get('permit_id')
    
    if not permit_id:
        flash("Permit ID is missing.", "danger")
        return redirect(request.referrer or url_for('travel_logs'))

    # Get the related TravelOrder using the permit
    permit = PermitRequest.query.get(permit_id)
    if not permit:
        flash("Permit not found.", "danger")
        return redirect(request.referrer or url_for('travel_logs'))

    if permit.permit_type != 'Travel Order':
        flash("Invalid permit type.", "danger")
        return redirect(request.referrer or url_for('travel_logs'))

    travel_order = TravelOrder.query.filter_by(permit_id=permit.id).first()
    if not travel_order:
        flash("Related Travel Order not found.", "danger")
        return redirect(request.referrer or url_for('travel_logs'))

    # Update the existing TravelLog status and date
    travel_log = TravelLog.query.filter_by(travel_order_id=travel_order.id).first()
    if not travel_log:
        flash("Travel log not found. It must be created before approval.", "danger")
        return redirect(request.referrer or url_for('travel_logs'))

    travel_log.status = 'Approved'
    travel_log.log_date = datetime.utcnow()

    db.session.commit()
    flash(f'Travel log updated successfully. Tracking ID: {travel_log.tracking_id}', 'success-timed')

    return redirect(request.referrer or url_for('travel_logs'))






@app.route("/Performance/View", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def HRSubmissionView():
    return render_template('superAdmin/submission.html',title="View")


def generate_department_password(department_name, year=2025):
    # List of words to ignore
    ignore_words = ['of', 'the']

    # Split the department name into words
    words = department_name.split()

    # Get the first letter of each word, excluding words in the ignore list
    initials = ''.join([word[0].upper() for word in words if word.lower() not in ignore_words])

    # Append the year at the end
    password = f"{initials}{year}"

    return password


# For adding Permanent Employee
@app.route('/add_employee', methods=['POST'])
@login_required
@role_required('hr')
def add_employee():
    try:
        # Collect form data
        last_name = request.form.get('last_name')
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        department_id = request.form.get('organizational_unit')
        position_id = request.form.get('position_title')
        status = request.form.get('status')
        sex = request.form.get('sex')
        date_of_birth = request.form.get('date_of_birth')
        tin = request.form.get('tin')
        date_original_appointment = request.form.get('date_original_appointment')
        date_last_promotion = request.form.get('date_last_promotion')
        eligibility = request.form.get('eligibility')
        comments = request.form.get('comments')

        item_number = request.form.get('item_number')
        salary_grade = request.form.get('salary_grade')
        authorized_salary = request.form.get('authorized_salary')
        actual_salary = request.form.get('actual_salary')
        step = request.form.get('step')
        area_code = request.form.get('area_code')
        area_type = request.form.get('area_type')
        level = request.form.get('level')
        

        # Ensure department and position exist
        department = Department.query.get(department_id)
        position = Position.query.get(position_id)

        

        if not department or not position:
            flash("Invalid department or position selected.", "danger")
            return redirect(url_for('EmployeeSection'))

        # Check current employees assigned to this position
        assigned_count = db.session.query(PermanentEmployeeDetails) \
        .join(Employee) \
        .filter(PermanentEmployeeDetails.position_id == position_id) \
        .filter(Employee.employment_status == 'active') \
        .filter(Employee.is_deleted == False) \
        .count()

        if assigned_count >= position.number_of_positions:
            flash(f"Cannot assign more employees to {position.title}. Limit of {position.number_of_positions} reached.", "danger")
            return redirect(url_for('EmployeeSection'))

        # Create employee record
        employee = Employee(
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name,
            department_id=department.id,
            status=status
        )
        db.session.add(employee)
        db.session.flush()  # Retrieve employee.id before committing

        # Create permanent employee details
        permanent_details = PermanentEmployeeDetails(
            employee_id=employee.id,
            item_number=item_number,
            position_id=position.id,
            salary_grade=int(salary_grade) if salary_grade else None,
            authorized_salary=authorized_salary,
            actual_salary=actual_salary,
            step=int(step) if step else None,
            area_code=area_code,
            area_type=area_type,
            level=level,
            sex=sex,
            date_of_birth=datetime.strptime(date_of_birth, '%Y-%m-%d') if date_of_birth else None,
            tin=tin,
            umid_no=None,
            date_original_appointment=datetime.strptime(date_original_appointment, '%Y-%m-%d') if date_original_appointment else None,
            date_last_promotion=datetime.strptime(date_last_promotion, '%Y-%m-%d') if date_last_promotion else None,
            eligibility=eligibility,
            comments=comments
        )
        db.session.add(permanent_details)

        department_name = department.name
        department_password = generate_department_password(department_name)

        if department_name == "Office of the Municipal Human Resource Management Officer":
            user_role = "HR"
        else:
            user_role = position.type.lower().strip() if position.type else "employee"

        # Generate base login ID and email
        login_id_base = f"{first_name[0]}{last_name}".lower()
        login_id_base = re.sub(r'\W+', '', login_id_base)  # Remove non-alphanumeric characters

        login_id = login_id_base
        counter = 1

        # Check if email exists, if yes, append numbers until unique
        while Users.query.filter_by(email=f"{login_id}@example.com").first():
            login_id = f"{login_id_base}{counter}"
            counter += 1

        base_email = f"{login_id}@example.com"
        default_password = bcrypt.generate_password_hash(department_password).decode('utf-8')
        full_name = f"{first_name} {middle_name} {last_name}".strip()

        user = Users(
            login_id=login_id,
            name=full_name,
            email=base_email,
            password_hash=default_password,
            role=user_role,
            employee_id=employee.id,
            must_reset_password=True
        )

        db.session.add(user)
        db.session.commit()

        flash(f'Employee {first_name} {last_name} added successfully.', 'success-timed')
        return redirect(url_for('EmployeeSection'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error adding employee: {str(e)}', 'danger')
        return redirect(url_for('EmployeeSection'))





# Adding Casual Employee
@app.route('/add_Casual_employee', methods=['POST'])
@login_required
@role_required('hr')
def add_casual_employee():
    try:
        # Form data
        last_name = request.form.get('last_name')
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        name_extension = request.form.get('name_extension')
        salary_grade = request.form.get('salary_grade')
        daily_wage = request.form.get('daily_wage')
        employment_from = request.form.get('employment_from')
        employment_to = request.form.get('employment_to')

        # ✅ Parse and validate contract dates
        contract_start = datetime.strptime(employment_from, '%Y-%m-%d') if employment_from else None
        contract_end = datetime.strptime(employment_to, '%Y-%m-%d') if employment_to else None

        if contract_start and contract_end and contract_end < contract_start:
            flash("Contract end date cannot be earlier than contract start date.", "danger")
            return redirect(url_for('EmployeeSection'))

        # Fixed position title
        fixed_position_title = "ADM. AIDE. I"

        # Get or create the "Office of the Municipal Mayor" department
        mayor_office = Department.query.filter_by(name="Office of the Municipal Mayor").first()
        if not mayor_office:
            mayor_office = Department(name="Office of the Municipal Mayor")
            db.session.add(mayor_office)
            db.session.flush()

        # Create Employee
        new_employee = Employee(
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name,
            status='Casual',
            department_id=mayor_office.id
        )
        db.session.add(new_employee)
        db.session.flush()

        # Get or create the fixed Position under that department
        existing_position = Position.query.filter_by(
            title=fixed_position_title,
            department_id=mayor_office.id
        ).first()

        if not existing_position:
            existing_position = Position(
                title=fixed_position_title,
                type='employee',
                number_of_positions=1,
                department_id=mayor_office.id
            )
            db.session.add(existing_position)
        else:
            existing_position.number_of_positions += 1

        # Insert into CasualEmployeeDetails
        casual_details = CasualEmployeeDetails(
            employee_id=new_employee.id,
            name_extension=name_extension,
            position_id=existing_position.id,
            equivalent_salary=salary_grade,
            daily_wage=float(daily_wage) if daily_wage else None,
            contract_start=contract_start,
            contract_end=contract_end
        )
        db.session.add(casual_details)

        # Create User Account
        department_password = generate_department_password(mayor_office.name)

        login_id_base = f"{first_name[0]}{last_name}".lower()
        login_id_base = re.sub(r'\W+', '', login_id_base)

        login_id = login_id_base
        counter = 1
        while Users.query.filter_by(email=f"{login_id}@example.com").first():
            login_id = f"{login_id_base}{counter}"
            counter += 1

        base_email = f"{login_id}@example.com"
        default_password = bcrypt.generate_password_hash(department_password).decode('utf-8')
        full_name = f"{first_name} {middle_name} {last_name}".strip()

        user = Users(
            login_id=login_id,
            name=full_name,
            email=base_email,
            password_hash=default_password,
            role='Employee',
            employee_id=new_employee.id,
            must_reset_password=True
        )
        db.session.add(user)
        db.session.commit()

        flash('Casual employee successfully added!', 'success-timed')
        return redirect(url_for('EmployeeSection'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error adding casual employee: {str(e)}', 'danger')
        return redirect(url_for('EmployeeSection'))

    

# Adding JO Employee
@app.route('/add_jo_employee', methods=['POST'])
@login_required
@role_required('hr')
def add_JO_employee():
    last_name = request.form['last_name']
    first_name = request.form['first_name']
    middle_name = request.form['middle_name']
    date_hired_str = request.form.get('date_hired')
    contract_start_str = request.form.get('contract_start')
    contract_end_str = request.form.get('contract_end')

    date_hired = datetime.strptime(date_hired_str, '%Y-%m-%d').date() if date_hired_str else None
    contract_start = datetime.strptime(contract_start_str, '%Y-%m-%d').date() if contract_start_str else None
    contract_end = datetime.strptime(contract_end_str, '%Y-%m-%d').date() if contract_end_str else None

    if contract_start and contract_end and contract_end < contract_start:
        flash("Contract end date cannot be earlier than contract start date.", "danger")
        return redirect(url_for('EmployeeSection'))

    # Get or create the "Office of the Municipal Mayor" department
    mayor_office = Department.query.filter_by(name="Office of the Municipal Mayor").first()
    if not mayor_office:
        mayor_office = Department(name="Office of the Municipal Mayor")
        db.session.add(mayor_office)
        db.session.flush()  # Get the ID without committing yet

    # Create employee assigned to the mayor's office
    new_employee = Employee(
        last_name=last_name,
        first_name=first_name,
        middle_name=middle_name,
        status='Job Order',
        department_id=mayor_office.id
    )
    db.session.add(new_employee)
    db.session.flush()  # To get the employee ID

    # Create job order details linked to this employee
    jo_details = JobOrderDetails(
        employee_id=new_employee.id,
        position_title='N/A',
        date_hired=date_hired,
        contract_start=contract_start,
        contract_end=contract_end
    )
    db.session.add(jo_details)

    # Create User Account
    department_password = generate_department_password(mayor_office.name)

    login_id_base = f"{first_name[0]}{last_name}".lower()
    login_id_base = re.sub(r'\W+', '', login_id_base)

    login_id = login_id_base
    counter = 1
    while Users.query.filter_by(email=f"{login_id}@example.com").first():
        login_id = f"{login_id_base}{counter}"
        counter += 1

    base_email = f"{login_id}@example.com"
    default_password = bcrypt.generate_password_hash(department_password).decode('utf-8')
    full_name = f"{first_name} {middle_name} {last_name}".strip()


    user = Users(
        login_id=login_id,
        name=full_name,
        email=base_email,
        password_hash=default_password,
        role='Employee',
        employee_id=new_employee.id,
        must_reset_password=True
    )
    db.session.add(user)

    db.session.commit()

    flash("JO Employee added successfully!", "success-timed")
    return redirect(url_for('EmployeeSection'))








@app.route('/edit_employee', methods=['POST'])
@login_required
@role_required('hr')
def edit_employee():
    try:
        employee_id = request.form.get('employee_id')
        employee = Employee.query.get(employee_id)

        if not employee:
            flash('Employee not found.', 'danger')
            return redirect(url_for('EmployeeSection'))

        # Update basic employee info
        employee.last_name = request.form.get('last_name')
        employee.first_name = request.form.get('first_name')
        employee.middle_name = request.form.get('middle_name')
        employee.department_id = request.form.get('organizational_unit')  # Updated to store FK
        employee.status = request.form.get('status')

        permanent_types = ['P', 'E', 'T', 'CT', 'PA']

        if employee.status in permanent_types:
            details = employee.permanent_details
            if not details:
                details = PermanentEmployeeDetails(employee_id=employee.id)
                db.session.add(details)

            # Update permanent employee detail fields
            details.item_number = request.form.get('item_number')
            details.position_id = request.form.get('position_title')  # Now stores FK
            details.salary_grade = request.form.get('salary_grade') or None
            details.authorized_salary = request.form.get('authorized_salary')
            details.actual_salary = request.form.get('actual_salary')
            details.step = request.form.get('step') or None
            details.area_code = request.form.get('area_code')
            details.area_type = request.form.get('area_type')
            details.level = request.form.get('level')
            details.sex = request.form.get('sex')

            dob = request.form.get('date_of_birth')
            details.date_of_birth = datetime.strptime(dob, "%Y-%m-%d") if dob else None

            details.tin = request.form.get('tin')

            doa = request.form.get('date_original_appointment')
            details.date_original_appointment = datetime.strptime(doa, "%Y-%m-%d") if doa else None

            dop = request.form.get('date_last_promotion')
            details.date_last_promotion = datetime.strptime(dop, "%Y-%m-%d") if dop else None

            details.eligibility = request.form.get('eligibility')
            details.comments = request.form.get('comments')
            # ✅ Sync din ang Users table name
            if employee.user:
                parts = [employee.first_name, employee.middle_name, employee.last_name]
                employee.user.name = " ".join([p for p in parts if p]
            )  # skip empty parts


        else:
            flash('Unsupported Employment Type.', 'danger')
            return redirect(url_for('EmployeeSection'))

        db.session.commit()
        flash('Employee updated successfully!', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Error updating employee: {str(e)}', 'danger')

    return redirect(url_for('EmployeeSection'))



@app.route('/edit_Casual_employee', methods=['POST'])
@login_required
@role_required('hr')
def edit_casual_employee():
    # Get data from the form
    employee_id = request.form.get('employee_id')
    last_name = request.form.get('last_name')
    first_name = request.form.get('first_name')
    middle_name = request.form.get('middle_name')
    name_extension = request.form.get('name_extension')
    status = request.form.get('employment_status')
    position_title = request.form.get('position_title')
    salary_grade = request.form.get('salary_grade')
    daily_wage = request.form.get('daily_wage')
    date_from = request.form.get('date_from')
    date_to = request.form.get('date_to')
    assigned_department_id = request.form.get('assigned_department_id')

    # Find employee by ID
    employee = Employee.query.get(employee_id)

    if not employee or not employee.casual_details:
        flash('Employee not found', 'danger')
        return redirect(url_for('EmployeeSection'))

    # ✅ Parse contract dates and validate
    contract_start = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
    contract_end = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None

    if contract_start and contract_end and contract_end < contract_start:
        flash("Contract end date cannot be earlier than contract start date.", "danger")
        return redirect(url_for('EmployeeSection'))

    # Update personal info
    employee.last_name = last_name
    employee.first_name = first_name
    employee.middle_name = middle_name

    # Update casual details
    casual_details = employee.casual_details
    casual_details.name_extension = name_extension or ''
    casual_details.status = status
    casual_details.position_title = position_title
    casual_details.equivalent_salary = salary_grade
    casual_details.daily_wage = float(daily_wage) if daily_wage else None
    casual_details.contract_start = contract_start
    casual_details.contract_end = contract_end
    casual_details.assigned_department_id = assigned_department_id  # ✅ update department assignment

    # ✅ Sync din ang Users table name
    if employee.user:
        parts = [employee.first_name, employee.middle_name, employee.last_name]
        employee.user.name = " ".join([p for p in parts if p])

    db.session.commit()

    flash('Casual employee updated successfully', 'success-timed')
    return redirect(url_for('EmployeeSection'))





@app.route('/edit_JO_employee', methods=['POST'])
@login_required
@role_required('hr')
def edit_JO_employee():
    try:
        # Get the form data safely
        employee_id = request.form.get('employee_id')
        organizational_unit = request.form.get('organizational_unit')
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        last_name = request.form.get('last_name')
        assigned_department_id = request.form.get('assigned_department_id')
        date_hired_str = request.form.get('date_hired')
        contract_start_str = request.form.get('contract_start')
        contract_end_str = request.form.get('contract_end')

        # Validate employee_id
        if not employee_id:
            flash('Employee ID is missing. Please try again.', 'danger')
            return redirect(url_for('EmployeeSection'))

        # Find the employee by ID
        employee = Employee.query.get(employee_id)
        if not employee or not employee.job_order_details:
            flash('Employee not found. Please try again.', 'danger')
            return redirect(url_for('EmployeeSection'))

        # Parse dates safely
        date_hired = datetime.strptime(date_hired_str, '%Y-%m-%d').date() if date_hired_str else None
        contract_start = datetime.strptime(contract_start_str, '%Y-%m-%d').date() if contract_start_str else None
        contract_end = datetime.strptime(contract_end_str, '%Y-%m-%d').date() if contract_end_str else None

        # Validate contract dates
        if contract_start and contract_end and contract_end < contract_start:
            flash("Contract end date cannot be earlier than contract start date.", "danger")
            return redirect(url_for('EmployeeSection'))

        # Update employee basic details
        employee.organizational_unit = organizational_unit
        employee.first_name = first_name
        employee.middle_name = middle_name
        employee.last_name = last_name

        # Update Date Hired
        employee.job_order_details.date_hired = date_hired

        # Update Job Order details
        employee.job_order_details.assigned_department_id = assigned_department_id
        employee.job_order_details.contract_start = contract_start
        employee.job_order_details.contract_end = contract_end

        # Sync Users table name if linked
        if employee.user:
            parts = [employee.first_name, employee.middle_name, employee.last_name]
            employee.user.name = " ".join([p for p in parts if p])

        # Commit changes
        db.session.commit()

        flash('Employee details updated successfully.', 'success-timed')
        return redirect(url_for('EmployeeSection'))

    except Exception as e:
        app.logger.error(f"Error updating JO Employee: {e}")
        flash('An error occurred while updating the employee. Please try again.', 'danger')
        return redirect(url_for('EmployeeSection'))


@app.route('/Hiring/Postings')
@login_required
@role_required('hr')
def JobPostingRecord():
    job_postings = JobPosting.query.order_by(JobPosting.created_at.desc()).all()
    departments = Department.query.all()
    job_count = len(job_postings)
    total_applicants = Applicant.query.count()

    return render_template('superAdmin/job_postings.html',title="Job", departments=departments,job_postings=job_postings,job_count=job_count,total_applicants=total_applicants )


@app.route('/Hiring/Applicants/<int:job_id>')
@login_required
@role_required('hr')
def JobApplicants(job_id):
    qualified_threshold = 60.0

    job = JobPosting.query.get_or_404(job_id)

    # Fetch all applicants for this job
    applicants = Applicant.query.filter_by(job_id=job_id).all()
    total_applicants = len(applicants)

    # Sort applicants by application_score (highest first)
    applicants_sorted = sorted(applicants, key=lambda a: a.application_score or 0, reverse=True)

    total_qualified = sum(1 for a in applicants if a.application_score and a.application_score >= qualified_threshold)
    valid_scores = [a.application_score for a in applicants if a.application_score is not None]
    average_score = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0.0

    # Deserialize fields safely for ALL applicants
    for applicant in applicants_sorted:
        # Helper function
        def parse_json_or_list(field_value, sep="\n"):
            if not field_value:
                return []
            try:
                return json.loads(field_value)
            except (json.JSONDecodeError, TypeError):
                return [x.strip() for x in field_value.split(sep) if x.strip()]

        applicant.education_list = parse_json_or_list(applicant.education)
        applicant.experience_list = parse_json_or_list(applicant.work_experience)
        applicant.eligibility_list = parse_json_or_list(applicant.eligibility)
        applicant.trainings_list = parse_json_or_list(applicant.trainings)
        applicant.voluntary_work_list = parse_json_or_list(applicant.voluntary_work)
        applicant.skills_list = parse_json_or_list(applicant.other_skills, sep=",")
        applicant.strengths_list = parse_json_or_list(applicant.strengths)
        applicant.weaknesses_list = parse_json_or_list(applicant.weaknesses)
        applicant.recognitions_list = parse_json_or_list(applicant.recognitions)
        applicant.memberships_list = parse_json_or_list(applicant.memberships)
        
        if applicant.memberships:
            applicant.memberships_list = [m.strip() for m in applicant.memberships.split(",") if m.strip()]
        else:
            applicant.memberships_list = []


    return render_template(
        'superAdmin/applicants.html',
        title="Applicants",
        job=job,
        total_applicants=total_applicants,
        applicants=applicants_sorted,   # pass sorted applicants
        total_qualified=total_qualified,
        average_score=average_score,
        qualified_threshold=qualified_threshold
    )



@app.route('/add_job_post', methods=['POST'])
@login_required
@role_required('hr')
def add_job_post():
    title = request.form.get('title')
    department_id = request.form.get('department_id')
    job_position_type = request.form.get('job_position_type')
    description = request.form.get('description')
    number_of_openings = request.form.get('number_of_openings')

    # Get all qualifications as a list
    qualifications_list = request.form.getlist('qualifications[]')

    # Join list into a single string separated by commas
    qualifications_str = ";;;".join(qualifications_list)

    # Basic validation
    if not title or not department_id or not job_position_type:
        flash('Please fill in all required fields.', 'danger')
        return redirect(url_for('JobPostingRecord'))

    if not qualifications_list:
        flash('Please add at least one qualification.', 'danger')
        return redirect(url_for('JobPostingRecord'))

    # Create a new job post entry
    new_job = JobPosting(
        title=title,
        department_id=department_id,
        job_position_type=job_position_type,
        description=description,
        qualifications=qualifications_str,  # Store as comma-separated string
        number_of_openings=number_of_openings,
        status='Open'
    )

    db.session.add(new_job)
    db.session.commit()
    flash('New job post created successfully!', 'success-timed')
    return redirect(url_for('JobPostingRecord'))



@app.route('/update_job_post', methods=['POST'])
@login_required
@role_required('hr')
def update_job_post():
    job_id = request.form.get('id')
    job = JobPosting.query.get(job_id)

    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('JobPostingRecord'))

    job.title = request.form.get('title')
    job.department_id = request.form.get('department_id')
    job.job_position_type = request.form.get('job_position_type')
    job.description = request.form.get('description')
    job.status = request.form.get('status')
    job.number_of_openings = request.form.get('number_of_openings')

    # Get the list of qualifications from the dynamic inputs
    qualifications_list = request.form.getlist('qualifications[]')

    # Join using a unique separator ';;;' to preserve commas in each qualification
    job.qualifications = ';;;'.join([q.strip() for q in qualifications_list if q.strip()])

    db.session.commit()
    flash('Job post updated successfully!', 'success-timed')
    return redirect(url_for('JobPostingRecord'))





@app.route('/job/close', methods=['POST'])
@login_required
def close_job_posting():
    job_id = request.form.get('job_id')

    try:
        job = JobPosting.query.get_or_404(job_id)

        # 1. Close the job posting
        job.status = 'Closed'

        # 2. Update all related applicants and their interviews
        for applicant in job.applicants:
            applicant.status = 'Rejected'  # or 'Position Closed'

            for interview in applicant.interviews:
                interview.status = 'Cancelled'
                interview.result = 'Rejected'
                interview.rejection_reason = 'Job posting has been closed.'

        db.session.commit()
        flash('Job and all related applicants and interviews have been updated.', 'success-timed')

    except:
        db.session.rollback()
        # Optional: log error
        app.logger.error(f"Error closing job posting ")
        flash('An error occurred while trying to close the job posting.', 'danger')

    return redirect(url_for('JobPostingRecord'))



@app.route('/Manage/Departments')
@login_required
@role_required('hr')
def ManageDepartments():
    departments = Department.query.all()
    return render_template('superAdmin/Departments.html', title="Departments", departments=departments)





@app.route('/Adding/Departments', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def AddingDepartments():
    if request.method == 'POST':
        # 1) Basic Department Info
        department_name = request.form.get('name')
        department_description = request.form.get('description')

        # Check if department name already exists
        existing_department = Department.query.filter_by(name=department_name).first()
        if existing_department:
            flash('Department name already exists. Please choose another name.', 'danger')
            return redirect(url_for('AddingDepartments'))

        # 2) Gather all services from the form
        services_list = request.form.getlist('service[]')  # Editable services
        services_csv = ",".join(services_list)

        # 3) Create and persist the Department
        department = Department(
            name=department_name,
            description=department_description,
            service=services_csv
        )
        db.session.add(department)
        db.session.flush()  # Ensure department.id is available

        # 4) Gather positions using the new field names
        titles = request.form.getlist('new_position_title[]')
        counts = request.form.getlist('new_number_of_positions[]')
        types = request.form.getlist('new_position_type[]')

        for title, count, p_type in zip(titles, counts, types):
            position = Position(
                title=title.strip(),
                number_of_positions=int(count),
                type=p_type,
                department_id=department.id
            )
            db.session.add(position)

        # 5) Commit all changes
        db.session.commit()

        flash('Department added successfully!', 'success-timed')
        return redirect(url_for('ManageDepartments'))

    # GET request → render the form
    return render_template(
        'superAdmin/addingDepartment.html',
        title="Add Department"
    )




@app.route('/edit_department/<int:department_id>', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def edit_department(department_id):
    department = Department.query.get_or_404(department_id)
    existing_positions = Position.query.filter_by(department_id=department_id).all()

    if request.method == 'POST':
        # Update department name and description
        department.name = request.form.get('name')
        department.description = request.form.get('description')

        # Track updated position IDs
        updated_position_ids = set()

        # Update existing positions from form
        for pos in existing_positions:
            title = request.form.get(f'position_title_{pos.id}')
            number = request.form.get(f'number_of_positions_{pos.id}')
            ptype = request.form.get(f'position_type_{pos.id}')
            if title and number and ptype:
                pos.title = title
                pos.number_of_positions = int(number)
                pos.type = ptype
                updated_position_ids.add(pos.id)

        # Get position IDs in use
        used_position_ids = {p.position_id for p in PermanentEmployeeDetails.query.all()}

        # Delete positions not in use and not updated
        for pos in existing_positions:
            if pos.id not in used_position_ids and pos.id not in updated_position_ids:
                db.session.delete(pos)

        # Add new positions
        position_titles = request.form.getlist('new_position_title[]')
        number_of_positions = request.form.getlist('new_number_of_positions[]')
        position_types = request.form.getlist('new_position_type[]')

        for title, number, ptype in zip(position_titles, number_of_positions, position_types):
            if title and number and ptype:
                new_pos = Position(
                    title=title,
                    number_of_positions=int(number),
                    type=ptype,
                    department_id=department.id
                )
                db.session.add(new_pos)

        # Update services (combine all submitted services)
        services = []
        for key in request.form:
            if key.startswith('service_'):
                services.append(request.form[key].strip())
        services += request.form.getlist('service[]')  # add new services
        department.service = ', '.join([s for s in services if s])  # ensure no blank

        try:
            db.session.commit()
            flash('Department updated successfully!', 'success-timed')
            return redirect(url_for('ManageDepartments'))  # Adjust as needed
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating department: {str(e)}', 'danger')

    return render_template(
        'superadmin/edit_department.html',
        department=department,
        positions=existing_positions
    )




# PERMITDAW
@app.route('/generate_pdf')
@login_required
@role_required('hr')
def generate_pdf():
    pdf = WidePDF(orientation='L', unit='mm', format=(215.9, 355.6))
    pdf.add_page()
    pdf.table_header()

    row_height_estimate = 10
    bottom_limit = pdf.h - pdf.b_margin

    departments = Department.query.all()

    for dept in departments:
        dept_positions = Position.query.filter_by(department_id=dept.id).all()

        for pos in dept_positions:
            assigned_emps = (
                Employee.query.join(PermanentEmployeeDetails)
                .filter(PermanentEmployeeDetails.position_id == pos.id)
                .filter(Employee.department_id == dept.id)
                .filter(Employee.employment_status == 'active')  # ✅ Only active
                .all()
            )

            for i in range(pos.number_of_positions):
                if pdf.get_y() + row_height_estimate > bottom_limit:
                    pdf.add_page()
                    pdf.table_header()

                if i < len(assigned_emps):
                    emp = assigned_emps[i]
                    if emp.permanent_details:
                        pdf.table_row(emp)
                else:
                    # Vacant slot mock data
                    class Vacant:
                        department = dept
                        last_name = "VACANT"
                        first_name = ""
                        middle_name = ""

                        class PermanentDetails:
                            item_number = ""
                            position = pos
                            salary_grade = getattr(pos, 'salary_grade', "")
                            authorized_salary = ""
                            actual_salary = ""
                            step = ""
                            area_code = ""
                            area_type = ""
                            level = ""
                            sex = ""
                            date_of_birth = None
                            tin = ""
                            umid_no = ""
                            date_original_appointment = None
                            date_last_promotion = None
                            eligibility = ""
                            comments = ""

                        permanent_details = PermanentDetails()
                        status = ""

                    pdf.table_row(Vacant())

    # ✅ FIXED PDF OUTPUT
    pdf_bytes = pdf.output(dest='S')  # returns bytes already
    pdf_output = io.BytesIO(pdf_bytes)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='employee_report.pdf'
    )


#causal 
@app.route('/generate_casualjob_pdf')
@login_required
@role_required('hr')
def generate_casualjob_pdf():
    pdf = CasualJobPDF(orientation='L', unit='mm', format=(215.9, 355.6))
    pdf.add_page()
    pdf.table_header()

    # ✅ Get only Casual employees with active employment_status
    casual_jobs = Employee.query.filter_by(status='Casual', employment_status='active').all()

    row_counter = 0
    display_index = 1

    for emp in casual_jobs:
        if emp.casual_details:
            if row_counter == 15:
                pdf.add_page()
                pdf.table_header()
                row_counter = 0
                display_index = 1

            pdf.table_row(emp, display_index)
            row_counter += 1
            display_index += 1

    # --- After all employees, add the note row and a blank row ---
    note_text = (
        "The abovenamed personnel are hereby/appointed as casuals at the rate of compensation stated opposite their names "
        "for the period indicated. It is understood that such employment will cease automatically at the end of the period "
        "stated unless renewed. Any or all of them may be laid-off any time before the expriration\nof the employment period "
        "when their services are no longer needed or funds are no longer available or the project has been completed/finished"
        "or their performance are below per."
    )

    pdf.table_note_row(note_text)   # add the note
    pdf.table_blank_row(height=2)   # add a blank row below the note

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)


    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='casualjob_report.pdf'
    )



#jo
@app.route('/generate_jo_pdf')
@login_required
@role_required('hr')
def generate_jo_pdf():

    pdf = JobOrderPDF(orientation='P', unit='mm', format=(215.9, 355.6))  # 8.5 x 14 inches
    pdf.add_page()

    # Fetch department mapping: {id: name}
    departments = Department.query.all()
    departments_dict = {dept.id: dept.name for dept in departments}

    # Only fetch employees with status 'Job Order'
    job_orders = (
        Employee.query
        .filter_by(status='Job Order')
        .options(joinedload(Employee.job_order_details))  # Avoid N+1
        .order_by(Employee.last_name, Employee.first_name, Employee.middle_name)
        .all()
    )

    # Generate the PDF layout using filtered names + department names
    today = datetime.today()
    year = today.year
    month = today.month

    pdf.jo_layout_table(
    year=year,
    month=month,
    days=15,  # ← limit to 15 days
    names=job_orders,
    departments_dict=departments_dict
    )


    # Generate PDF in memory
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='job_order_layout.pdf'
    )

# Travel Order PDF Generator
@app.route('/generate_travel_order_pdf/<int:permit_id>')
@login_required
def generate_travel_order_pdf(permit_id):
    # Fetch the travel order permit
    permit = PermitRequest.query.filter_by(id=permit_id, permit_type='Travel Order').first()
    if not permit:
        abort(404)

    # Fetch the employee who requested the permit
    employee = permit.employee
    if not employee:
        abort(404)

    # Determine the employee's department
    department_id = None
    if employee.permanent_details:
        department_id = employee.department_id
    elif employee.casual_details:
        department_id = employee.casual_details.assigned_department_id
    elif employee.job_order_details:
        department_id = employee.job_order_details.assigned_department_id

    # --- Find the Department Head ---
    head_user = None

    # Special case: employee belongs to HR
    if employee.department and employee.department.name == "Office of the Municipal Human Resource Management Officer":
        head_user = (
            Users.query.join(Employee)
            .outerjoin(PermanentEmployeeDetails, PermanentEmployeeDetails.employee_id == Employee.id)
            .outerjoin(CasualEmployeeDetails, CasualEmployeeDetails.employee_id == Employee.id)
            .outerjoin(JobOrderDetails, JobOrderDetails.employee_id == Employee.id)
            .outerjoin(Position, 
                (Position.id == PermanentEmployeeDetails.position_id) |
                (Position.id == CasualEmployeeDetails.position_id)
            )
            .filter(
                ((Position.title == "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I") |
                 (JobOrderDetails.position_title == "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I"))
            )
            .first()
        )
    else:
        # Regular case: find head of employee's department
        if department_id:
            head_user = (
                Users.query.join(Employee)
                .filter(
                    Employee.department_id == department_id,
                    Users.role == "Head"
                )
                .first()
            )

    # --- Fetch latest head approval ---
    if head_user:
        head_approval = (
            db.session.query(PermitRequestHistory)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action_by == head_user.id,
                PermitRequestHistory.action == "Approved"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )

        if head_approval:
            permit.head_approver = head_user.name

            # Determine head's position
            head_employee = head_user.employee
            if head_employee.permanent_details:
                permit.head_approver_position = head_employee.permanent_details.position.title
            elif head_employee.casual_details:
                permit.head_approver_position = head_employee.casual_details.position.title
            elif head_employee.job_order_details:
                permit.head_approver_position = head_employee.job_order_details.position_title
            else:
                permit.head_approver_position = "Head of Department"

            permit.head_approver_id = head_user.id
        else:
            # Head exists but has not approved yet
            permit.head_approver = "________________________"
            permit.head_approver_position = "Head of Department"
            permit.head_approver_id = None
    else:
        # No head found for this department
        permit.head_approver = "________________________"
        permit.head_approver_position = "Head of Department"
        permit.head_approver_id = None

    # --- Generate the PDF ---
    pdf = TravelOrderPDF()
    pdf.add_page()
    pdf.add_travel_order_form(permit)  # permit already has head info

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"TravelOrder_{employee.last_name}_{employee.first_name}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


#TRAVEL HISTORY 
@app.route('/generate_travel_log_pdf')
@login_required
def generate_travel_log_pdf():
    # ✅ Filter only APPROVED logs
    logs = (
        TravelLog.query
        .filter(TravelLog.status == 'Approved')
        .all()
    )

    if not logs:
        abort(404)

    pdf = TravelLogPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()

    for log in logs:
        pdf.add_log_row({
            'last_name': log.travel_order.permit.employee.last_name,
            'first_name': log.travel_order.permit.employee.first_name,
            'middle_name': log.travel_order.permit.employee.middle_name,
            'destination': log.travel_order.destination,
            'log_date': log.log_date,
            'purpose': log.travel_order.purpose,
            'tracking_id': log.tracking_id,
        })

    

    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output = io.BytesIO(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=True, download_name=filename)


# TravelLog USER
@app.route("/user_travel_logs_pdf")
@login_required
@role_required('employee')
def user_travel_logs_pdf():
    employee = current_user.employee
    employee_id = employee.id
    department_name = employee.department.name if employee.department else None  # assumes Employee → Department relationship

    # Get travel logs
    logs = (
        db.session.query(TravelLog)
        .join(TravelOrder)
        .join(PermitRequest)
        .join(Employee)
        .options(
            joinedload(TravelLog.travel_order)
            .joinedload(TravelOrder.permit)
            .joinedload(PermitRequest.employee)
        )
        .filter(Employee.id == employee_id)
        .order_by(desc(TravelLog.log_date))
        .all()
    )

    if not logs:
        flash("No travel records found.", "warning")
        return redirect(url_for("travel_logs_User"))

    # Build PDF
    pdf = TravelLogUSERPDF(orientation="L", unit="mm", format="A4", department_name=department_name)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    for log in logs:
        pdf.add_log_row(log)

    # Output
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest="S").encode("latin1")
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Logs_{employee.last_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )

# print TRAVELLOGS USER
@app.route("/user_travel_logs_print")
@login_required
@role_required('employee')
def user_travel_logs_print():
        employee = current_user.employee
        employee_id = employee.id
        department_name = employee.department.name if employee.department else None  # assumes Employee → Department relationship

        # Get travel logs
        logs = (
            db.session.query(TravelLog)
            .join(TravelOrder)
            .join(PermitRequest)
            .join(Employee)
            .options(
                joinedload(TravelLog.travel_order)
                .joinedload(TravelOrder.permit)
                .joinedload(PermitRequest.employee)
            )
            .filter(Employee.id == employee_id)
            .order_by(desc(TravelLog.log_date))
            .all()
        )

        if not logs:
            flash("No travel records found.", "warning")
            return redirect(url_for("travel_logs_User"))

        # Build PDF
        pdf = TravelLogUSERPDF(orientation="L", unit="mm", format="A4", department_name=department_name)
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        for log in logs:
            pdf.add_log_row(log)

        # Output
        pdf_output = io.BytesIO()
        pdf_bytes = pdf.output(dest="S").encode("latin1")
        pdf_output.write(pdf_bytes)
        pdf_output.seek(0)

        filename = f"Travel_Logs_{employee.last_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return send_file(
            pdf_output,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )


# PRINT TRAVEL LOGS HEAD (PDF)
@app.route("/head_travel_logs_print")
@login_required
@role_required('head')
def head_travel_logs_print():
    # Get head's department
    head_department_id = current_user.employee.department_id  
    department = Department.query.get(head_department_id)

    # Get logs for that department
    logs = (
        db.session.query(TravelLog)
        .join(TravelOrder)
        .join(PermitRequest)
        .join(Employee)
        .options(
            joinedload(TravelLog.travel_order)
            .joinedload(TravelOrder.permit)
            .joinedload(PermitRequest.employee)
        )
        .filter(Employee.department_id == head_department_id)
        .order_by(desc(TravelLog.log_date))
        .all()
    )

    if not logs:
        flash("No travel records found for your department.", "warning")
        return redirect(url_for("travel_logs_head"))

    # 👉 Pass department.name here
    pdf = TravelLogheadPDF(
        department_name=department.name if department else "No Department",
        orientation="L", unit="mm", format="A4"
    )
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    for log in logs:
        pdf.add_log_row(log)

    # Output
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest="S").encode("latin1")
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Logs_{department.name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype="application/pdf",
        as_attachment=False,
        # download_name=filename
    )


# TRAVEL LOGS HEAD (PDF)
@app.route("/head_travel_logs_pdf")
@login_required
@role_required('head')
def head_travel_logs_pdf():
    # Get head's department
    head_department_id = current_user.employee.department_id  
    department = Department.query.get(head_department_id)

    # Get logs for that department
    logs = (
        db.session.query(TravelLog)
        .join(TravelOrder)
        .join(PermitRequest)
        .join(Employee)
        .options(
            joinedload(TravelLog.travel_order)
            .joinedload(TravelOrder.permit)
            .joinedload(PermitRequest.employee)
        )
        .filter(Employee.department_id == head_department_id)
        .order_by(desc(TravelLog.log_date))
        .all()
    )

    if not logs:
        flash("No travel records found for your department.", "warning")
        return redirect(url_for("travel_logs_head"))

    # 👉 Pass department.name here
    pdf = TravelLogheadPDF(
        department_name=department.name if department else "No Department",
        orientation="L", unit="mm", format="A4"
    )
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    for log in logs:
        pdf.add_log_row(log)

    # Output
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest="S").encode("latin1")
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Logs_{department.name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


# LEAVE PDF Generator
@app.route('/generate_leave_application_pdf/<int:permit_id>')
@login_required
def generate_leave_application_pdf(permit_id):
    # Fetch permit request of type 'Leave'
    permit = PermitRequest.query.filter_by(id=permit_id, permit_type='Leave').first()
    if not permit:
        abort(404)

    leave = permit.leave_detail
    if not leave:
        abort(404)

    employee = permit.employee
    if not employee:
        abort(404)

    # ✅ Department & Position (depende sa employee type)
    if employee.permanent_details:
        department = employee.department.name if employee.department else 'N/A'
        position = employee.permanent_details.position.title if employee.permanent_details.position else 'N/A'
    elif employee.casual_details:
        department = (employee.casual_details.assigned_department.name
                      if employee.casual_details.assigned_department else 'N/A')
        position = (employee.casual_details.position.title
                    if employee.casual_details.position else 'N/A')
    elif employee.job_order_details:
        department = (employee.job_order_details.assigned_department.name
                      if employee.job_order_details.assigned_department else 'N/A')
        position = employee.job_order_details.position_title or 'N/A'
    else:
        department = employee.department.name if employee.department else 'N/A'
        position = 'N/A'

    # ✅ Head approval info
    head_approved = False
    head_approver = None
    head_approver_position = None
    head_approver_id = None

    approval_history = (
        db.session.query(PermitRequestHistory, Users)
        .join(Users, PermitRequestHistory.action_by == Users.id)
        .filter(
            PermitRequestHistory.permit_request_id == permit.id,
            PermitRequestHistory.action == "Approved"
        )
        .order_by(PermitRequestHistory.timestamp.desc())
        .first()
    )

    if approval_history:
        history, user = approval_history
        head_approved = True
        head_approver = user.name
        head_approver_id = user.id

        # ✅ Determine approver's position
        approver_employee = user.employee
        if approver_employee:
            if approver_employee.permanent_details and approver_employee.permanent_details.position:
                head_approver_position = approver_employee.permanent_details.position.title
            elif approver_employee.casual_details and approver_employee.casual_details.position:
                head_approver_position = approver_employee.casual_details.position.title
            elif approver_employee.job_order_details:
                head_approver_position = approver_employee.job_order_details.position_title
    
    # LEAVE PERMITS
    leave_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Leave',
            PermitRequest.current_stage.in_(['Mayor', 'Completed'])
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )


    # ✅ Generate PDF
    pdf = LeaveApplicationPDF()
    pdf.add_page()
    pdf.add_leave_form(
        department=department,
        last_name=employee.last_name,
        first_name=employee.first_name,
        middle_name=employee.middle_name,
        date_from=leave.date_from.strftime("%B %d, %Y"),
        position=position,
        salary=leave.salary or 'N/A',
        selected_leave=leave.leave_type,
        head_approved=head_approved,
        head_approver=head_approver,
        head_approver_position=head_approver_position,
        head_approver_id=head_approver_id,   # ✅ Pass ID for signature
        current_stage=permit.current_stage 
    )
    pdf.add_instructions_page()

    pdf.show_header = False
    pdf.add_page()

    # ✅ Return PDF response
    pdf_output = pdf.output(dest='S').encode('latin1')
    return Response(
        pdf_output,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=leave_application_{permit_id}.pdf'}
    )

@app.route('/generate_clearance/<int:permit_id>')
def generate_clearance(permit_id):
    clearance = ClearanceForm.query.filter_by(permit_id=permit_id).first_or_404()
    permit = clearance.permit
    employee = permit.employee if permit else None

    if not employee:
        return abort(404, "Employee not found")

    # Department & Position
    if employee.permanent_details:
        department = employee.department.name if employee.department else 'N/A'
        position = employee.permanent_details.position.title if employee.permanent_details.position else 'N/A'
        department_id = employee.department_id
    elif employee.casual_details:
        department = employee.casual_details.assigned_department.name if employee.casual_details.assigned_department else 'N/A'
        position = employee.casual_details.position.title if employee.casual_details.position else 'N/A'
        department_id = employee.casual_details.assigned_department_id
    elif employee.job_order_details:
        department = employee.job_order_details.assigned_department.name if employee.job_order_details.assigned_department else 'N/A'
        position = employee.job_order_details.position_title or 'N/A'
        department_id = employee.job_order_details.assigned_department_id
    else:
        department = employee.department.name if employee.department else 'N/A'
        position = 'N/A'
        department_id = employee.department_id if employee.department else None

    # PDF Content
    leave_type = (clearance.clearance_purpose or 'N/A').lower()
    other_text = clearance.other_purpose or ''
    date_from = clearance.date_from.strftime('%B %d, %Y') if clearance.date_from else 'N/A'
    effectivity_period = (f"{clearance.date_from.strftime('%B %d, %Y')} to {clearance.date_to.strftime('%B %d, %Y')}"
                          if clearance.date_from and clearance.date_to else 'N/A')
    name = f"{employee.first_name} {employee.middle_name[0]}. {employee.last_name}" if employee.first_name and employee.last_name else 'N/A'

    # Employee details (SG/Step)
    if employee.permanent_details:
        salary_grade = employee.permanent_details.salary_grade or 'N/A'
        step = employee.permanent_details.step or 'N/A'
    else:
        salary_grade = 'N/A'
        step = 'N/A'

    # --- Find the Department Head (reuse Travel Order logic) ---
    head_user = None
    if employee.department and employee.department.name == "Office of the Municipal Human Resource Management Officer":
        # Special case: HR
        head_user = (
            Users.query.join(Employee)
            .outerjoin(PermanentEmployeeDetails, PermanentEmployeeDetails.employee_id == Employee.id)
            .outerjoin(CasualEmployeeDetails, CasualEmployeeDetails.employee_id == Employee.id)
            .outerjoin(JobOrderDetails, JobOrderDetails.employee_id == Employee.id)
            .outerjoin(Position,
                (Position.id == PermanentEmployeeDetails.position_id) |
                (Position.id == CasualEmployeeDetails.position_id)
            )
            .filter(
                ((Position.title == "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I") |
                 (JobOrderDetails.position_title == "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I"))
            )
            .first()
        )
    else:
        if department_id:
            head_user = (
                Users.query.join(Employee)
                .filter(
                    Employee.department_id == department_id,
                    Users.role == "Head"
                )
                .first()
            )

    # Fetch head name and signature if available
    if head_user:
        head_name = head_user.name
        sig_record = UserSignature.query.filter_by(user_id=head_user.id).first()
        head_signature = sig_record.signature if sig_record else None
    else:
        head_name = "________________________"
        head_signature = None

    # --- Generate PDF ---
    pdf = ClearanceFormPDF()
    pdf.add_page()
    pdf.add_clearance_form(
        leave_type=leave_type,
        other_text=other_text,
        date_from=date_from,
        position=position,
        office_assignment=department,
        name=name,
        effectivity_period=effectivity_period,
        employee=employee,
        salary_grade=salary_grade,
        step=step,
        permit=permit,
        clearance=clearance,
        head_of_office=head_name,
        head_signature=head_signature  # ✅ pass the e-signature bytes
    )

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"clearance_form_{name.replace(' ', '_')}.pdf"
    return send_file(pdf_output, download_name=filename, as_attachment=False)

#ipcr 

@app.route('/generate_ipcr')
@login_required
def generate_ipcr():
    employee_id = request.args.get('employee_id')
    if not employee_id:
        return abort(400, description="Missing employee_id parameter")

    # ✅ Get latest IPCR for this employee (any period)
    ipcr = IPCR.query.filter_by(employee_id=employee_id).order_by(IPCR.id.desc()).first()
    if not ipcr:
        return abort(404, description="No IPCR record found for this employee.")

    # ✅ Extract related info
    employee = ipcr.employee

    # Use assigned_department if casual employee
    if hasattr(employee, "casual_details") and employee.casual_details and employee.casual_details.assigned_department:
        department = employee.casual_details.assigned_department
    else:
        department = employee.department

    period = ipcr.period
    start_date = period.start_date if period else None
    end_date = period.end_date if period else None

    # ✅ Identify department head for this employee’s department
    dept_employees = Employee.query.filter(Employee.department_id == department.id).all()
    head_employee = next((emp for emp in dept_employees if emp.is_department_head), None)

    if head_employee:
        middle_initial = f"{head_employee.middle_name[0]}." if head_employee.middle_name else ""
        head_name = f"{head_employee.first_name} {middle_initial} {head_employee.last_name}"
    else:
        head_name = "(Head of Department)"

    # ✅ Fetch the head of “Office of the Municipal Mayor”
    mayor_department = Department.query.filter(
        Department.name.ilike('%Office of the Municipal Mayor%')
    ).first()

    mayor_head = None
    if mayor_department:
        mayor_head = Employee.query.filter(
            Employee.department_id == mayor_department.id,
            Employee.is_department_head == True
        ).first()

    # Format mayor name (all caps, with "HON." prefix and MD at the end)
    if mayor_head:
        middle_initial = f"{mayor_head.middle_name[0]}." if mayor_head.middle_name else ""
        mayor_name = f"HON. {mayor_head.first_name.upper()} {middle_initial.upper()} {mayor_head.last_name.upper()}, MD"
    else:
        mayor_name = "HON. MAYOR, MD (NOT SET)"

    # ✅ Initialize PDF
    pdf = PerformanceReportPDF(
        orientation='L',
        unit='mm',
        format=(215.9, 355.6),
        start_date=start_date,
        end_date=end_date,
        head_name=head_name,
        mayor_name=mayor_name,  # ✅ pass mayor to header logic
        employee=employee
    )

    pdf.date_submitted = ipcr.date_submitted
    pdf.department_name = department.name if department else "Unknown Department"

    pdf.add_page()
    pdf.table_header()
    pdf.show_header = False

    core_ratings, support_ratings = [], []

    # ✅ Render IPCR Sections
    for section in ipcr.sections:
        if section.type.lower() == 'core':
            pdf.core_function_row(section.type)
        elif section.type.lower() == 'support':
            pdf.support_function_row(section.type)
        else:
            continue

        for item in section.section_items:
            ratings = [item.rating_q, item.rating_e, item.rating_t, item.rating_a]
            valid_ratings = [r for r in ratings if r is not None]
            if len(valid_ratings) == 4:
                avg = sum(valid_ratings) / 4
                if section.type.lower() == 'core':
                    core_ratings.append(f"{avg:.2f}")
                elif section.type.lower() == 'support':
                    support_ratings.append(f"{avg:.2f}")

            accountable_name = f"{ipcr.employee.first_name} {ipcr.employee.last_name}"

            pdf.table_row({
                'mfo': item.mfo or "",
                'success_indicators': item.success_indicator or "",
                'budget': str(item.allotted_budget) if item.allotted_budget else "",
                'actual': str(item.accomplishment) if item.accomplishment else "",
                'rating': {
                    'Q': str(item.rating_q) if item.rating_q is not None else "",
                    'E': str(item.rating_e) if item.rating_e is not None else "",
                    'T': str(item.rating_t) if item.rating_t is not None else "",
                    'A': str(item.rating_a) if item.rating_a is not None else "",
                },
                'remarks': item.remarks or "",
                'accountable': accountable_name
            })

    # ✅ Summary computation
    core_sum = sum([float(r) for r in core_ratings]) if core_ratings else 0
    support_sum = sum([float(r) for r in support_ratings]) if support_ratings else 0
    core_count, support_count = len(core_ratings), len(support_ratings)
    core_avg = core_sum / core_count if core_count else 0
    support_avg = support_sum / support_count if support_count else 0
    total_weighted = (core_avg * 0.9) + (support_avg * 0.1)

    
    # --- Prepare rows for summary table ---
    rows = [
        # Header row → blue
        {"category": "Category", "mfo": "MFO", "rating": "Rating"},
        # Strategic Priority → white
        {"category": "Strategic Priority", "mfo": "", "rating": ""},
        # Core Function → white, MFO = core count, Rating = average
        {"category": "Core Function", "mfo": str(core_count), "rating": f"{core_avg:.2f}"},
        # Support Function → white, MFO = support count, Rating = average
        {"category": "Support Function", "mfo": str(support_count), "rating": f"{support_avg:.2f}"},
        # Total Overall Rating → blue, MFO = "-", Rating = total weighted
        {"category": "Total Overall Rating", "mfo": "", "rating": f"{total_weighted:.2f}"},
        # Final Average Rating → blue, MFO = "-", Rating = final average
        {"category": "Final Average Rating", "mfo": "", "rating": f"{ipcr.final_average_rating:.2f}" if ipcr.final_average_rating else "-"},
        # Adjectival Rating → blue
        {"category": "Adjectival Rating", "mfo": "", "rating": ipcr.adjective_rating or "-"},
    ]

    # Rows 0, 4, 5, 6 should have blue Cells 2-4
    blue_rows = [0, 4, 5, 6]

    # Add the rows to the PDF
    pdf.new_table_rows_custom_color(rows, blue_rows=blue_rows)
# 🧾 Define the positions per line
    positions = [
        ["MUNICIPAL PLANNING AND DEVELOPMENT COORDINATOR I"],  # Line 1
        ["MUNICIPAL GOVERNMENT DEPARTMENT HEAD I (LDRRMO)", "MUNICIPAL BUDGET OFFICER I"],  # Line 2
        ["MUNICIPAL TREASURER"],  # Line 3
        ["MUNICIPAL ACCOUNTANT", "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I"],  # Line 4
    ]

    # 🧾 Helper function
    def get_permanent_employee_name_by_position(position_title):
        # ✅ Special override
        if position_title == "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I (LDRRMO)":
            return "Aldwin D. Aloquin"

        # 🔍 Default DB lookup
        emp = (
            db.session.query(Employee)
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(Position.title == position_title)
            .filter(Employee.is_deleted == False)
            .first()
        )
        if emp:
            middle_initial = f"{emp.middle_name[0].upper()}." if emp.middle_name else ""
            return f"{emp.first_name} {middle_initial} {emp.last_name}".strip()
        return "(Not Found)"


    # 🧾 Build the name list following your layout
    names_list = []
    for group in positions:
        if len(group) == 1:
            names_list.append(get_permanent_employee_name_by_position(group[0]))
        else:
            combined_names = "                                                ".join(
                [get_permanent_employee_name_by_position(p) for p in group]
            )
            names_list.append(combined_names)

    # Get the employee with position "MUNICIPAL MAYOR"
    mayor_employee = (
        Employee.query
        .join(Employee.permanent_details)
        .join(PermanentEmployeeDetails.position)
        .filter(Position.title.ilike("MUNICIPAL MAYOR"))
        .first()
    )

    if mayor_employee:
        middle_initial = f"{mayor_employee.middle_name[0]}." if mayor_employee.middle_name else ""
        mayor_name = f"HON. {mayor_employee.first_name.upper()} {middle_initial.upper()} {mayor_employee.last_name.upper()}, MD"
    else:
        mayor_name = "HON. MAYOR (NOT SET)"

    # Join all lines with line breaks
    all_names = "\n" + "\n".join(names_list)

    # 🧾 Table rows
    rows_data = [
        (all_names, "", mayor_name, "")  # Mayor in line 4, cell 3
    ]


    # 🧾 Generate the layout
    pdf.assessed_by_table(rows_data)


    # ✅ Output PDF
    pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
    pdf_output = io.BytesIO(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'ipcr_report_{employee_id}.pdf'
    )


#COE
@app.route('/generate_coe_pdf/<int:permit_id>')
@login_required
def generate_coe_pdf(permit_id):
    # Query the permit request by ID and ensure it's a COE permit
    permit = PermitRequest.query.filter_by(id=permit_id, permit_type='Certification of Employment').first()
    if not permit:
        abort(404, description="Permit request not found or not a COE request")

    # Create PDF instance
    pdf = CertificationPDF()
    pdf.add_page()
    pdf.add_certification_body(permit)

    # Output PDF to bytes
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')  # output as string and encode
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    # Return PDF as a file download
    filename = f"COE_{permit.employee.last_name}_{permit.employee.first_name}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )



#JOB HIRING APPLICATION SKDHASDAS
@app.route('/generate_under_review_pdf')
@login_required
def generate_under_review_pdf():
    # Get all applicants with status 'Under Review'
    applicants = Applicant.query.filter_by(status='Under Review').all()

    pdf = UnderReviewPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()  # calls header()

    if not applicants:
        # No applicants message
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, "No Under Review applicants found.", ln=True, align='C')
    else:
        # Add each applicant row
        for applicant in applicants:
            pdf.add_applicant_row(applicant)

    # Output PDF to BytesIO
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Under_Review_Applicants_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )



# INTERVIEW 
@app.route('/generate_interview_pdf')
@login_required
def generate_interview_pdf():
    # Query applicants with Scheduled interviews
    applicants = (
        Applicant.query
        .filter(Applicant.interviews.any(Interview.status == 'Scheduled'))
        .options(
            joinedload(Applicant.job_posting).joinedload(JobPosting.department),
            joinedload(Applicant.interviews)
        )
        .all()
    )

    pdf = InterviewApplicantPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()  # automatically calls header()

    if not applicants:
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, "No Scheduled Interview applicants found.", ln=True, align='C')
    else:
        for applicant in applicants:
            # Pass the object directly
            pdf.add_applicant_row(applicant)

    # Output PDF to BytesIO
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Scheduled_Interview_Applicants_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )




#ACCEPTED APPLICANT 
# ACCEPTED APPLICANT PDF
@app.route('/generate_hired_pdf')
@login_required
def generate_hired_pdf():
    # Fetch applicants with status 'Hired'
    applicants = (
        Applicant.query
        .filter_by(status='Hired')
        .options(
            joinedload(Applicant.job_posting).joinedload(JobPosting.department),
            joinedload(Applicant.interviews)
        )
        .all()
    )

    # Create PDF
    pdf = AcceptedApplicantPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()  # calls header() and prints table header

    if not applicants:
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, "No hired applicants found.", ln=True, align='C')
    else:
        for applicant in applicants:
            # Pass the Applicant object directly
            pdf.add_applicant_row(applicant)

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Hired_Applicants_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


# REJECTED APPLICANTS
@app.route('/generate_rejected_pdf')
@login_required
def generate_rejected_pdf():
    # Fetch applicants with status 'Rejected'
    applicants = (
        Applicant.query
        .filter_by(status='Rejected')
        .options(
            joinedload(Applicant.job_posting).joinedload(JobPosting.department),
            joinedload(Applicant.interviews)
        )
        .all()
    )

    # Create PDF
    pdf = RejectedApplicantPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()  # calls header() and prints table header

    if not applicants:
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, "No rejected applicants found.", ln=True, align='C')
    else:
        for applicant in applicants:
            # Pass the object directly; PDF class handles interview extraction
            pdf.add_applicant_row(applicant)

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Rejected_Applicants_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


#ADMIN EMPLOYEE LIST
#CASUAL PER DEPARTMENT 
@app.route('/head/casual_employee_pdf')
@login_required
def head_casual_employee_pdf():
    # Ensure the current user has a department
    if not current_user.employee or not current_user.employee.department:
        abort(403, description="You are not assigned to any department.")

    # Get the department info of the current head
    department_name = current_user.employee.department.name
    department_id = current_user.employee.department_id

    # Use an alias for clarity
    Casual = aliased(CasualEmployeeDetails)

    # Query for active casual employees assigned to the same department
    casual_employees = (
        db.session.query(Employee)
        .join(Casual, Employee.id == Casual.employee_id)
        .filter(
            Casual.assigned_department_id == department_id,
            Employee.status == 'Casual',
            Employee.employment_status == 'active',
            Employee.is_deleted == False
        )
        .all()
    )

    if not casual_employees:
        abort(404, description="No active casual employees found under this department.")

    # Generate the PDF
    pdf = HeadCasualEmployeePDF(department_name)
    pdf.add_page()

    for idx, emp in enumerate(casual_employees, start=1):
        pdf.add_employee_row(idx, emp)

    # Output the PDF to memory
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"CasualEmployees_{department_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=True, download_name=filename)


#JO PER DEPARTMENT 
@app.route('/head/job_order_employee_pdf')
@login_required
def head_job_order_employee_pdf():
    if not current_user.employee or not current_user.employee.department:
        abort(403, description="You are not assigned to any department.")

    department_name = current_user.employee.department.name
    department_id = current_user.employee.department_id

    # Filter job order employees assigned to the same department
    job_order_employees = Employee.query.join(JobOrderDetails).filter(
        JobOrderDetails.assigned_department_id == department_id,
        Employee.status == 'Job Order',
        Employee.employment_status == 'active',
        Employee.is_deleted == False
    ).all()

    if not job_order_employees:
        abort(404, description="No active job order employees found under this department.")

    pdf = HeadJobOrderEmployeePDF(department_name)
    pdf.add_page()

    for idx, emp in enumerate(job_order_employees, start=1):
        pdf.add_employee_row(idx, emp)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"JobOrderEmployees_{department_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=True, download_name=filename)


#PERMANENT  PER DEPARTMENT 
@app.route('/head/permanent_employee_pdf')
@login_required
def head_permanent_employee_pdf():
    # Ensure current user is assigned to a department
    if not current_user.employee or not current_user.employee.department:
        abort(403, description="You are not assigned to any department.")

    department_name = current_user.employee.department.name
    department_id = current_user.employee.department_id

    # Get all ACTIVE PERMANENT employees assigned to the same department
    permanent_employees = Employee.query.join(PermanentEmployeeDetails).filter(
        Employee.department_id == department_id,
        Employee.status.notin_(['Job Order', 'Casual']),  # NOT Job Order, NOT Casual
        Employee.employment_status.ilike('active'),
        Employee.is_deleted == False
    ).all()

    if not permanent_employees:
        abort(404, description="No active permanent employees found under this department.")

    # Generate PDF
    pdf = HeadPermanentEmployeePDF(department_name)
    pdf.add_page()

    for idx, emp in enumerate(permanent_employees, start=1):
        pdf.add_employee_row(idx, emp)

    # Prepare PDF for download
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"PermanentEmployees_{department_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=True, download_name=filename)



# REPORT:  HR EMPLOYEE REQUEST  APPLICATION FOR LEAVE REPORT
@app.route('/generate_head_leave_summary_pdf')
@login_required
def generate_head_leave_summary_pdf():
    department_name = (
        current_user.employee.department.name 
        if current_user.employee and current_user.employee.department 
        else 'All Departments'
    )

    # Query all leave permits (Leave type only)
    all_permits = PermitRequest.query.filter_by(permit_type="Leave").order_by(PermitRequest.date_requested.asc()).all()

    # Define status order for grouping
    status_order = ['Approved', 'Pending', 'In Progress', 'Rejected']  # Include In Progress

    pdf = HeadLeaveApplicationPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Leave Applications', ln=True)
    pdf.draw_table_headers()

    idx = 1  # Global row counter
    for status in status_order:
        # Filter permits explicitly for the current status
        filtered_permits = [
            p for p in all_permits if (
                (p.status in ['Completed', 'Released', 'Approved'] and status == 'Approved') or
                (p.status == 'Pending' and status == 'Pending') or
                (p.status == 'In Progress' and status == 'In Progress') or
                (p.status == 'Rejected' and status == 'Rejected')
            )
        ]

        for permit in filtered_permits:
            emp = permit.employee
            if not emp:
                continue

            if permit.current_stage == "Head":
                continue

            # Determine Position
            pos = "N/A"
            if emp.permanent_details and emp.permanent_details.position:
                pos = emp.permanent_details.position.title
            elif emp.casual_details and emp.casual_details.position:
                pos = emp.casual_details.position.title
            elif emp.job_order_details:
                pos = emp.job_order_details.position_title

            # Map current stage
            stage_map = {
                'HR': 'With HR for review',
                'Head': 'Awaiting Department Head approval',
                'Mayor': 'Awaiting Mayor approval',
                'Completed': 'Leave process completed'
            }

            # Show custom message for Rejected, else map stage
            if permit.status == 'Rejected':
                current_stage = 'Leave was rejected'
            else:
                current_stage = stage_map.get(permit.current_stage, '-')

            # Prepare data for PDF row
            data = {
                'department': emp.department.name if emp.department else 'N/A',
                'position': pos,
                'first_name': emp.first_name or '',
                'middle_name': emp.middle_name or '',
                'last_name': emp.last_name or '',
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'leave_type': (
                    f"{permit.leave_detail.leave_type if permit.leave_detail else 'N/A'}" +
                    (f"\n{permit.leave_detail.date_from.strftime('%b %d, %Y')} - {permit.leave_detail.date_to.strftime('%b %d, %Y')}" if permit.leave_detail else '')
                ),
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',

                # Employee leave credit
                'employee': {
                    'credit_balance': {
                        'vacation_remaining': emp.credit_balance.vacation_remaining if emp.credit_balance else 0,
                        'sick_remaining': emp.credit_balance.sick_remaining if emp.credit_balance else 0,
                    }
                },
                'leave_detail': {
                    'leave_type': permit.leave_detail.leave_type if permit.leave_detail else '',
                    'paid_days': permit.leave_detail.paid_days if permit.leave_detail else None,
                    'working_days': permit.leave_detail.working_days if permit.leave_detail else None,
                    'date_from': permit.leave_detail.date_from if permit.leave_detail else None,
                    'date_to': permit.leave_detail.date_to if permit.leave_detail else None,
                }
            }

            pdf.add_leave_row(idx, data)
            idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Leave_Application_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=True, download_name=filename)

# REPORT: HR EMPLOYEE REQUEST TRAVEL ORDER
@app.route('/generate_travel_summary_pdf')
@login_required
def generate_travel_summary_pdf():
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'All Departments'
    )

    # Query all travel orders
    all_travel_orders = PermitRequest.query.filter_by(permit_type="Travel Order").order_by(PermitRequest.date_requested.asc()).all()

    # Define status order, excluding 'Cancelled'
    status_order = ['Approved', 'Pending', 'In Progress', 'Rejected']

    pdf = HeadTravelOrderPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages() 
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Travel Orders', ln=True)
    pdf.draw_table_headers()

    row_idx = 1
    for status in status_order:
        # Filter orders explicitly for the current status
        filtered_orders = [
            t for t in all_travel_orders if (
                (t.status in ['Completed', 'Released', 'Approved'] and status == 'Approved') or
                (t.status == 'Pending' and status == 'Pending') or
                (t.status == 'In Progress' and status == 'In Progress') or
                (t.status == 'Rejected' and status == 'Rejected')
            )
        ]

        for permit in filtered_orders:
            emp = permit.employee
            if not emp:
                continue
            if permit.current_stage == "Head":
                continue

            # Determine position
            position = "N/A"
            if emp.permanent_details and emp.permanent_details.position:
                position = emp.permanent_details.position.title
            elif emp.casual_details and emp.casual_details.position:
                position = emp.casual_details.position.title
            elif emp.job_order_details:
                position = emp.job_order_details.position_title

            # Map current_stage descriptions for non-rejected
            stage_map = {
                'HR': 'With HR for review',
                'Head': 'Awaiting Department Head approval',
                'Mayor': 'Awaiting Mayor approval',
                'Completed': 'Travel process completed'
            }
            current_stage = stage_map.get(permit.current_stage, '-') if permit.status != 'Rejected' else 'Travel was rejected'

            # Build data dictionary
            data = {
                'department': emp.department.name if emp.department else 'N/A',
                'position': position,
                'first_name': emp.first_name or '',
                'middle_name': emp.middle_name or '',
                'last_name': emp.last_name or '',
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'destination': permit.travel_detail.destination if permit.travel_detail else 'N/A',
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',
            }

            pdf.add_travel_row(row_idx, data)
            row_idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Order_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )



# REPORT: HR EMPLOYEE REQUEST CLEARANCE FORM
@app.route('/generate_clearance_summary_pdf')
@login_required
def generate_clearance_summary_pdf():
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'All Departments'
    )

    # Query all clearance forms
    all_clearance_permits = PermitRequest.query.filter_by(permit_type="Clearance Form").order_by(PermitRequest.date_requested.asc()).all()

    # Define status order (excluding Cancelled)
    status_order = ['Completed', 'Pending', 'In Progress', 'Approved', 'Rejected']

    pdf = HeadClearanceSummaryPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Clearance Form', ln=True)
    pdf.draw_table_headers()

    row_idx = 1  # Start row numbering

    for status in status_order:
        # Filter permits explicitly for the current status
        filtered_permits = [
            p for p in all_clearance_permits if (
                (p.status == 'Completed' and status == 'Completed') or
                (p.status == 'Pending' and status == 'Pending') or
                (p.status not in ['Completed', 'Cancelled', 'Rejected', 'Approved'] and status == 'In Progress') or
                (p.status == 'Approved' and status == 'Approved') or
                (p.status == 'Rejected' and status == 'Rejected')
            )
        ]

        for permit in filtered_permits:
            emp = permit.employee
            if not emp:
                continue
            if permit.current_stage == "Head":
                continue

            # Determine position
            position = "N/A"
            if emp.permanent_details and emp.permanent_details.position:
                position = emp.permanent_details.position.title
            elif emp.casual_details and emp.casual_details.position:
                position = emp.casual_details.position.title
            elif emp.job_order_details:
                position = emp.job_order_details.position_title

            # Full Name
            full_name = f"{emp.last_name}, {emp.first_name} {emp.middle_name or ''}".strip()

            # Purpose
            if permit.clearance_detail:
                if permit.clearance_detail.clearance_purpose == "Other":
                    purpose = f"Other - {permit.clearance_detail.other_purpose or 'N/A'}"
                else:
                    purpose = permit.clearance_detail.clearance_purpose
            else:
                purpose = "N/A"

            # Map current_stage descriptions
            stage_map = {
                'HR': 'With HR for review',
                'Head': 'Awaiting Department Head approval',
                'Mayor': 'Awaiting Mayors approval',
                'Completed': ' Clearance Process completed'
            }
            current_stage = stage_map.get(permit.current_stage, '-') if permit.status != 'Rejected' else 'Clearance was rejected'


            data = {
                'department': emp.department.name if emp.department else 'N/A',
                'position': position,
                'first_name': emp.first_name or '',
                'middle_name': emp.middle_name or '',
                'last_name': emp.last_name or '',
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'purpose': purpose,
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',
            }

            pdf.add_clearance_row(row_idx, data)
            row_idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Clearance_Form_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

# REPORT: HR EMPLOYEE REQUEST COE
@app.route('/generate_coe_summary_pdf')
@login_required
def generate_coe_summary_pdf():

    # Get department of current user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'All Departments'
    )

    # Query all COE permits excluding Cancelled
    all_coe_permits = PermitRequest.query.filter(
        PermitRequest.permit_type == "Certification of Employment",
        PermitRequest.status != "Cancelled"
    ).order_by(PermitRequest.date_requested.asc()).all()

    # Define status order (excluding Cancelled)
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']

    # Initialize PDF
    pdf = HeadCOEPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages() 
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Certificate of Employment', ln=True)
    pdf.draw_table_headers()

    # Current stage mapping
    stage_map = {
        'HR': 'With HR for review',
        'Head': 'Awaiting Department Head approval',
        'Mayor': 'Awaiting Mayors approval',
        'Completed': 'COE Process completed'
    }

    row_idx = 1
    for status in status_order:
        # Filter permits by current status
        filtered_permits = [p for p in all_coe_permits if p.status == status]

        for permit in filtered_permits:
            emp = permit.employee

            # Determine employee details safely
            if emp:
                department = emp.department.name if emp.department else 'N/A'

                if getattr(emp, 'permanent_details', None) and getattr(emp.permanent_details, 'position', None):
                    position = emp.permanent_details.position.title
                elif getattr(emp, 'casual_details', None) and getattr(emp.casual_details, 'position', None):
                    position = emp.casual_details.position.title
                elif getattr(emp, 'job_order_details', None):
                    position = getattr(emp.job_order_details, 'position_title', 'N/A')
                else:
                    position = 'N/A'

                first_name = emp.first_name or ''
                middle_name = emp.middle_name or ''
                last_name = emp.last_name or ''
            else:
                department = 'N/A'
                position = 'N/A'
                first_name = ''
                middle_name = ''
                last_name = ''

            # Full name with middle initial
            middle_initial = f"{middle_name[0]}." if middle_name else ""
            full_name = f"{last_name}, {first_name} {middle_initial}".strip()

            # Map current_stage with custom message for Rejected
            if permit.status == 'Rejected':
                current_stage = 'COE was rejected'
            else:
                current_stage = stage_map.get(permit.current_stage, '-')

            # Build data dict for PDF
            data = {
                'department': department,
                'position': position,
                'first_name': first_name,
                'middle_name': middle_name,
                'last_name': last_name,
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',
            }

            pdf.add_coe_row(data)
            row_idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"COE_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )



# REPORT: HR DEPARTMETN  LEAVE SUMMARY PDF
@app.route('/generate_hr_leave_summary_pdf')
@login_required
def generate_hr_leave_summary_pdf():

  # Get department of current user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query leave permits for the department, excluding Cancelled
    permits = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Leave")
        .filter(Employee.department_id == current_user.employee.department_id)
        .filter(PermitRequest.status != "Cancelled")
        .all()
    )

    # --- Custom Sorting Order ---
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']
    status_priority = {status: idx for idx, status in enumerate(status_order, start=1)}

    def get_status_priority(permit):
        if permit.status in ['HR', 'Head', 'Mayor']:
            return status_priority.get('Pending', 99)  # Treat as in-progress/pending
        return status_priority.get(permit.status, 99)

    permits.sort(key=lambda p: (
        get_status_priority(p),
        p.date_requested or datetime.min
    ))

    # PDF Setup
    pdf = HRLeaveApplicationPDF(department_name=department_name)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.draw_table_headers()

    # Fill rows
    for permit in permits:
        emp = permit.employee
        if not emp:
            continue

        # Position
        pos = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            pos = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            pos = emp.casual_details.position.title
        elif emp.job_order_details:
            pos = emp.job_order_details.position_title

        # Stage mapping
        if permit.status == 'Rejected':
            current_stage = 'Leave was rejected'
        elif permit.current_stage == 'HR':
            current_stage = 'With HR for review'
        elif permit.current_stage == 'Head':
            current_stage = 'Awaiting Department Head approval'
        elif permit.current_stage == 'Mayor':
            current_stage = 'Awaiting Mayor approval'
        elif permit.current_stage == 'Completed':
            current_stage = 'Leave process completed'
        else:
            current_stage = 'In Progress'

        # --- Credits Remaining (same logic as Mayor PDF) ---
        credits_remaining = "N/A"
        if emp and emp.credit_balance and permit.leave_detail:
            cb = emp.credit_balance
            leave_type = permit.leave_detail.leave_type.lower()

            if "vacation" in leave_type:
                credits_remaining = f"Vacation: {cb.vacation_remaining} credit(s)"
            elif "sick" in leave_type:
                credits_remaining = f"Sick: {cb.sick_remaining} credit(s)"

        # --- Paid Days (same logic as Mayor PDF) ---
        paid_days = "N/A"
        if permit.leave_detail:
            leave = permit.leave_detail
            leave_type = leave.leave_type.lower()

            if "vacation" in leave_type or "sick" in leave_type:
                working_days = 0
                paid_days_val = 0
                try:
                    working_days = int(leave.working_days or 0)
                except (ValueError, TypeError):
                    working_days = 0

                try:
                    paid_days_val = int(leave.paid_days or 0) if leave.paid_days is not None else None
                except (ValueError, TypeError):
                    paid_days_val = None

                if paid_days_val is not None:
                    if paid_days_val > 0:
                        unpaid = max(working_days - paid_days_val, 0)
                        paid_days = f"{paid_days_val} day(s) Paid"
                        if unpaid > 0:
                            paid_days += f" / {unpaid} Unpaid"
                    else:
                        paid_days = "Pending Approval"
                else:
                    requested_days = working_days
                    if emp and emp.credit_balance:
                        cb = emp.credit_balance
                        if "vacation" in leave_type:
                            paid = min(requested_days, cb.vacation_remaining)
                        elif "sick" in leave_type:
                            paid = min(requested_days, cb.sick_remaining)
                        else:
                            paid = 0
                        paid_days = f"Est. {paid} day(s)"
                    else:
                        paid_days = "N/A"
            else:
                paid_days = "Not Applicable"

        # Prepare row data
        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': pos,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'leave_type': (
                f"{permit.leave_detail.leave_type if permit.leave_detail else 'N/A'}" +
                (f"\n{permit.leave_detail.date_from.strftime('%b %d, %Y')} -"
                 f"{permit.leave_detail.date_to.strftime('%b %d, %Y')}"
                 if permit.leave_detail and permit.leave_detail.date_from and permit.leave_detail.date_to else '')
            ),
            'credits_remaining': credits_remaining,
            'paid_days': paid_days,
            'status': permit.status or '-',
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
        }

        pdf.add_leave_row(data)

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"HR_Leave_Application_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )




# REPORT: HR DEPARTMETN  TRAVEL ORDER (Department Only)
@app.route('/generate_hr_travel_summary_pdf')
@login_required
def generate_hr_travel_summary_pdf():
    # Department name of current user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query travel orders for this department, excluding Cancelled
    travel_orders = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Travel Order")
        .filter(Employee.department_id == current_user.employee.department_id)
        .filter(PermitRequest.status != "Cancelled")
        .all()
    )

    # Define clean status order
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']
    status_priority = {status: idx for idx, status in enumerate(status_order, start=1)}

    # Function to normalize statuses
    def get_status_priority(permit):
        if permit.status in ['HR', 'Head', 'Mayor']:
            return status_priority.get('Pending', 99)  # treat as pending/in progress
        elif permit.status in ['Completed', 'Released', 'Approved']:
            return status_priority.get('Approved', 99)
        return status_priority.get(permit.status, 99)

    # Sort permits
    travel_orders.sort(key=lambda p: (
        get_status_priority(p),
        p.date_requested or datetime.min
    ))

    # PDF setup
    pdf = HRTravelOrderPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Travel Orders', ln=True)
    pdf.draw_table_headers()

    row_idx = 1
    for permit in travel_orders:
        emp = permit.employee
        if not emp:
            continue

        # Determine position
        position = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title

        # Stage mapping
        if permit.status == 'Rejected':
            current_stage = 'Travel was rejected'
        elif permit.current_stage == 'HR':
            current_stage = 'With HR for review'
        elif permit.current_stage == 'Head':
            current_stage = 'Awaiting Department Head approval'
        elif permit.current_stage == 'Mayor':
            current_stage = 'Awaiting Mayor approval'
        elif permit.current_stage in ['Completed', 'Released', 'Approved']:
            current_stage = 'Travel process completed'
        else:
            current_stage = 'In Progress'

        # Build row data
        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': position,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'destination': permit.travel_detail.destination if permit.travel_detail else 'N/A',
            'status': permit.status or '-',
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
        }

        pdf.add_travel_row(row_idx, data)
        row_idx += 1

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Order_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )

# REPORT: HR DEPARTMETN  CLEARANCE FORM
@app.route('/generate_hr_clearance_summary_pdf')
@login_required
def generate_hr_clearance_summary_pdf():
    # Kunin department ng HR user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query clearance permits para lang sa department na ito
    permits = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Clearance Form")
        .filter(Employee.department_id == current_user.employee.department_id)
        .all()
    )

    # Status order (hindi kasama Cancelled)
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']

    pdf = HRClearanceSummaryPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Clearance Form', ln=True)
    pdf.draw_table_headers()

    row_idx = 1

    for status in status_order:
        # Filter permits explicitly for this status
        filtered_permits = [
            p for p in permits if (
                (p.status == 'Completed' and status == 'Completed') or
                (p.status == 'Pending' and status == 'Pending') or
                (p.status == 'Approved' and status == 'Approved') or
                (p.status == 'Rejected' and status == 'Rejected') or
                # lahat ng iba (HR, Head, Mayor) ay papasok as Pending/In Progress dati
                (p.status not in ['Completed', 'Cancelled', 'Rejected', 'Approved'] and status == 'Pending')
            )
        ]

        for permit in filtered_permits:
            emp = permit.employee
            if not emp:
                continue

            # Position
            position = "N/A"
            if emp.permanent_details and emp.permanent_details.position:
                position = emp.permanent_details.position.title
            elif emp.casual_details and emp.casual_details.position:
                position = emp.casual_details.position.title
            elif emp.job_order_details:
                position = emp.job_order_details.position_title

            # Purpose
            if permit.clearance_detail:
                if permit.clearance_detail.clearance_purpose == "Other":
                    purpose = f"Other - {permit.clearance_detail.other_purpose or 'N/A'}"
                else:
                    purpose = permit.clearance_detail.clearance_purpose
            else:
                purpose = "N/A"

            # Stage mapping
            if permit.status == 'Rejected':
                current_stage = 'Clearance was rejected'
            elif permit.current_stage == 'HR':
                current_stage = 'With HR for review'
            elif permit.current_stage == 'Head':
                current_stage = 'Awaiting Department Head approval'
            elif permit.current_stage == 'Mayor':
                current_stage = 'Awaiting Mayor approval'
            elif permit.current_stage == 'Completed':
                current_stage = 'Process completed'
            else:
                current_stage = '-'

            data = {
                'department': emp.department.name if emp.department else 'N/A',
                'position': position,
                'first_name': emp.first_name or '',
                'middle_name': emp.middle_name or '',
                'last_name': emp.last_name or '',
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'purpose': purpose,
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',
            }

            pdf.add_clearance_row(row_idx, data)
            row_idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Clearance_Form_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )


# REPORT: dept. head HR LEAVE SUMMARY PDF
@app.route('/generate_depthead_leave_summary_pdf')
@login_required
def generate_depthead_leave_summary_pdf():

    # Get department of current user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query leave permits for the department, excluding Cancelled
    permits = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Leave")
        .filter(Employee.department_id == current_user.employee.department_id)
        .filter(PermitRequest.status != "Cancelled")
        .all()
    )

    # --- Custom Sorting Order ---
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']
    status_priority = {status: idx for idx, status in enumerate(status_order, start=1)}

    def get_status_priority(permit):
        if permit.status in ['HR', 'Head', 'Mayor']:
            return status_priority.get('Pending', 99)  # Treat as in-progress/pending
        return status_priority.get(permit.status, 99)

    permits.sort(key=lambda p: (
        get_status_priority(p),
        p.date_requested or datetime.min
    ))

    # PDF Setup
    pdf = LeaveApplicationhHeadPDF(department_name=department_name)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.draw_table_headers()

    # Fill rows
    for permit in permits:
        emp = permit.employee
        if not emp:
            continue

        # Position
        pos = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            pos = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            pos = emp.casual_details.position.title
        elif emp.job_order_details:
            pos = emp.job_order_details.position_title

        # Stage mapping
        if permit.status == 'Rejected':
            current_stage = 'Leave was rejected'
        elif permit.current_stage == 'HR':
            current_stage = 'With HR for review'
        elif permit.current_stage == 'Head':
            current_stage = 'Awaiting Department Head approval'
        elif permit.current_stage == 'Mayor':
            current_stage = 'Awaiting Mayor approval'
        elif permit.current_stage == 'Completed':
            current_stage = 'Leave process completed'
        else:
            current_stage = 'In Progress'

        # --- Credits Remaining (same logic as Mayor PDF) ---
        credits_remaining = "N/A"
        if emp and emp.credit_balance and permit.leave_detail:
            cb = emp.credit_balance
            leave_type = permit.leave_detail.leave_type.lower()

            if "vacation" in leave_type:
                credits_remaining = f"Vacation: {cb.vacation_remaining} credit(s)"
            elif "sick" in leave_type:
                credits_remaining = f"Sick: {cb.sick_remaining} credit(s)"

        # --- Paid Days (same logic as Mayor PDF) ---
        paid_days = "N/A"
        if permit.leave_detail:
            leave = permit.leave_detail
            leave_type = leave.leave_type.lower()

            if "vacation" in leave_type or "sick" in leave_type:
                working_days = 0
                paid_days_val = 0
                try:
                    working_days = int(leave.working_days or 0)
                except (ValueError, TypeError):
                    working_days = 0

                try:
                    paid_days_val = int(leave.paid_days or 0) if leave.paid_days is not None else None
                except (ValueError, TypeError):
                    paid_days_val = None

                if paid_days_val is not None:
                    if paid_days_val > 0:
                        unpaid = max(working_days - paid_days_val, 0)
                        paid_days = f"{paid_days_val} day(s) Paid"
                        if unpaid > 0:
                            paid_days += f" / {unpaid} Unpaid"
                    else:
                        paid_days = "Pending Approval"
                else:
                    requested_days = working_days
                    if emp and emp.credit_balance:
                        cb = emp.credit_balance
                        if "vacation" in leave_type:
                            paid = min(requested_days, cb.vacation_remaining)
                        elif "sick" in leave_type:
                            paid = min(requested_days, cb.sick_remaining)
                        else:
                            paid = 0
                        paid_days = f"Est. {paid} day(s)"
                    else:
                        paid_days = "N/A"
            else:
                paid_days = "Not Applicable"

        # Prepare row data
        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': pos,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'leave_type': (
                f"{permit.leave_detail.leave_type if permit.leave_detail else 'N/A'}" +
                (f"\n{permit.leave_detail.date_from.strftime('%b %d, %Y')} -"
                 f"{permit.leave_detail.date_to.strftime('%b %d, %Y')}"
                 if permit.leave_detail and permit.leave_detail.date_from and permit.leave_detail.date_to else '')
            ),
            'credits_remaining': credits_remaining,
            'paid_days': paid_days,
            'status': permit.status or '-',
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
        }

        pdf.add_leave_row(data)

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"HR_Leave_Application_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )



# REPORT: dept. head TRAVEL ORDER (Department Only)
@app.route('/generate_depthead_travel_summary_pdf')
@login_required
def generate_depthead_travel_summary_pdf():
    # Department name of current user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query travel orders for this department, excluding Cancelled
    travel_orders = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Travel Order")
        .filter(Employee.department_id == current_user.employee.department_id)
        .filter(PermitRequest.status != "Cancelled")
        .all()
    )

    # Define clean status order
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']
    status_priority = {status: idx for idx, status in enumerate(status_order, start=1)}

    # Function to normalize statuses
    def get_status_priority(permit):
        if permit.status in ['HR', 'Head', 'Mayor']:
            return status_priority.get('Pending', 99)  # treat as pending/in progress
        elif permit.status in ['Completed', 'Released', 'Approved']:
            return status_priority.get('Approved', 99)
        return status_priority.get(permit.status, 99)

    # Sort permits
    travel_orders.sort(key=lambda p: (
        get_status_priority(p),
        p.date_requested or datetime.min
    ))

    # PDF setup
    pdf = TravelOrderHeadPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Travel Orders', ln=True)
    pdf.draw_table_headers()

    row_idx = 1
    for permit in travel_orders:
        emp = permit.employee
        if not emp:
            continue

        # Determine position
        position = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title

        # Stage mapping
        if permit.status == 'Rejected':
            current_stage = 'Travel was rejected'
        elif permit.current_stage == 'HR':
            current_stage = 'With HR for review'
        elif permit.current_stage == 'Head':
            current_stage = 'Awaiting Department Head approval'
        elif permit.current_stage == 'Mayor':
            current_stage = 'Awaiting Mayor approval'
        elif permit.current_stage in ['Completed', 'Released', 'Approved']:
            current_stage = 'Travel process completed'
        else:
            current_stage = 'In Progress'

        # Build row data
        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': position,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'destination': permit.travel_detail.destination if permit.travel_detail else 'N/A',
            'status': permit.status or '-',
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
        }

        pdf.add_travel_row(row_idx, data)
        row_idx += 1

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Order_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )

# REPORT: dept. head CLEARANCE FORM
@app.route('/generate_depthead_clearance_summary_pdf')
@login_required
def generate_depthead_clearance_summary_pdf():
    # Kunin department ng HR user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query clearance permits para lang sa department na ito
    permits = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Clearance Form")
        .filter(Employee.department_id == current_user.employee.department_id)
        .all()
    )

    # Status order (hindi kasama Cancelled)
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']

    pdf = ClearanceSummaryheadPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Clearance Form', ln=True)
    pdf.draw_table_headers()

    row_idx = 1

    for status in status_order:
        # Filter permits explicitly for this status
        filtered_permits = [
            p for p in permits if (
                (p.status == 'Completed' and status == 'Completed') or
                (p.status == 'Pending' and status == 'Pending') or
                (p.status == 'Approved' and status == 'Approved') or
                (p.status == 'Rejected' and status == 'Rejected') or
                # lahat ng iba (HR, Head, Mayor) ay papasok as Pending/In Progress dati
                (p.status not in ['Completed', 'Cancelled', 'Rejected', 'Approved'] and status == 'Pending')
            )
        ]

        for permit in filtered_permits:
            emp = permit.employee
            if not emp:
                continue

            # Position
            position = "N/A"
            if emp.permanent_details and emp.permanent_details.position:
                position = emp.permanent_details.position.title
            elif emp.casual_details and emp.casual_details.position:
                position = emp.casual_details.position.title
            elif emp.job_order_details:
                position = emp.job_order_details.position_title

            # Purpose
            if permit.clearance_detail:
                if permit.clearance_detail.clearance_purpose == "Other":
                    purpose = f"Other - {permit.clearance_detail.other_purpose or 'N/A'}"
                else:
                    purpose = permit.clearance_detail.clearance_purpose
            else:
                purpose = "N/A"

            # Stage mapping
            if permit.status == 'Rejected':
                current_stage = 'Clearance was rejected'
            elif permit.current_stage == 'HR':
                current_stage = 'With HR for review'
            elif permit.current_stage == 'Head':
                current_stage = 'Awaiting Department Head approval'
            elif permit.current_stage == 'Mayor':
                current_stage = 'Awaiting Mayor approval'
            elif permit.current_stage == 'Completed':
                current_stage = 'Process completed'
            else:
                current_stage = '-'

            data = {
                'department': emp.department.name if emp.department else 'N/A',
                'position': position,
                'first_name': emp.first_name or '',
                'middle_name': emp.middle_name or '',
                'last_name': emp.last_name or '',
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'purpose': purpose,
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',
            }

            pdf.add_clearance_row(row_idx, data)
            row_idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Clearance_Form_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )


# REPORT: mayor LEAVE APPLICATION
# REPORT: mayor LEAVE APPLICATION
@app.route('/generate_mayor_leave_summary_pdf')
@login_required
def generate_mayor_leave_summary_pdf():
    department_name = "All Departments"

    permits = (
        PermitRequest.query
        .filter(PermitRequest.permit_type == "Leave")
        .filter(PermitRequest.current_stage.in_(["Mayor", "Completed", "Approved"]))
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    pdf = MayorLeaveApplicationPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Leave Applications', ln=True)
    pdf.draw_table_headers()

    for permit in permits:
        emp = permit.employee
        if not emp:
            continue

        # Position
        position = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title

        # Stage mapping
        if permit.current_stage == "Mayor":
            current_stage = "Awaiting Mayor approval"
        elif permit.current_stage in ["Completed", "Approved"]:
            current_stage = "Leave process completed"
        else:
            current_stage = "-"

        # Normalize status for completed
        status = permit.status or '-'
        if permit.current_stage in ["Completed", "Approved"]:
            status = "Completed"

        # --- Credits Remaining ---
        credits_remaining = "N/A"
        if emp and emp.credit_balance and permit.leave_detail:
            cb = emp.credit_balance
            leave_type = permit.leave_detail.leave_type.lower()

            if "vacation" in leave_type:
                credits_remaining = f"Vacation: {cb.vacation_remaining} credit(s)"
            elif "sick" in leave_type:
                credits_remaining = f"Sick: {cb.sick_remaining} credit(s)"

        # --- Paid Days ---
        paid_days = "N/A"
        if permit.leave_detail:
            leave = permit.leave_detail
            leave_type = leave.leave_type.lower()

            if "vacation" in leave_type or "sick" in leave_type:
                # Safe conversion to int
                working_days = 0
                paid_days_val = 0
                try:
                    working_days = int(leave.working_days or 0)
                except (ValueError, TypeError):
                    working_days = 0

                try:
                    paid_days_val = int(leave.paid_days or 0) if leave.paid_days is not None else None
                except (ValueError, TypeError):
                    paid_days_val = None

                if paid_days_val is not None:
                    if paid_days_val > 0:
                        unpaid = max(working_days - paid_days_val, 0)
                        paid_days = f"{paid_days_val} day(s) Paid"
                        if unpaid > 0:
                            paid_days += f" / {unpaid} Unpaid"
                    else:
                        paid_days = "Pending Approval"
                else:
                    # Estimated if not yet approved
                    requested_days = working_days
                    if emp and emp.credit_balance:
                        cb = emp.credit_balance
                        if "vacation" in leave_type:
                            paid = min(requested_days, cb.vacation_remaining)
                        elif "sick" in leave_type:
                            paid = min(requested_days, cb.sick_remaining)
                        else:
                            paid = 0
                        paid_days = f"Est. {paid} day(s)"
                    else:
                        paid_days = "N/A"
            else:
                paid_days = "Not Applicable"

        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': position,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'leave_type': permit.leave_detail.leave_type if permit.leave_detail else 'N/A',
            'credits_remaining': credits_remaining,
            'paid_days': paid_days,
            'status': status,
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
        }

        pdf.add_leave_row(data)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Leave_Application_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=True, download_name=filename)

# REPORT: Mayor Travel Orders (All Departments, grouped by status)
@app.route('/generate_mayor_travel_summary_pdf')
@login_required
def generate_mayor_travel_summary_pdf():
    department_name = "All Departments"

    # Fetch all travel orders that are relevant
    permits = (
        PermitRequest.query
        .filter(PermitRequest.permit_type == "Travel Order")
        .filter(
            (PermitRequest.current_stage.in_(["Mayor", "Completed", "Approved"])) |
            (PermitRequest.status == "Rejected")
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Attach latest rejection info
    for permit in permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # Group permits in the desired order
    completed = []
    in_progress = []
    pending = []
    rejected = []

    for permit in permits:
        if permit.status == "Rejected":
            rejected.append(permit)
        elif permit.current_stage in ["Completed", "Released", "Approved"]:
            completed.append(permit)
        elif permit.current_stage == "Mayor":
            in_progress.append(permit)
        else:
            pending.append(permit)

    # Combine them in order
    permits_ordered = completed + in_progress + pending + rejected

    pdf = MayorTravelOrderPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Travel Orders', ln=True)
    pdf.draw_table_headers()

    # Add rows
    for idx, permit in enumerate(permits_ordered, start=1):
        emp = permit.employee
        if not emp:
            continue

        # Determine position
        position = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title

        # Stage mapping and status
        if permit.status == "Rejected":
            current_stage = "Travel was rejected"
            status = "Rejected"
        elif permit.current_stage == "Mayor":
            current_stage = "Awaiting Mayor approval"
            status = permit.status or "In Progress"
        elif permit.current_stage in ["Completed", "Released", "Approved"]:
            current_stage = "Travel Order process completed"
            status = "Completed"
        else:
            current_stage = "-"
            status = permit.status or "Pending"

        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': position,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'destination': permit.travel_detail.destination if permit.travel_detail else 'N/A',
            'status': status,
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
            'rejected_by': permit.rejected_by or '-',
            'rejected_remarks': permit.rejected_remarks or '-',
        }

        pdf.add_travel_row(idx, data)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Order_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False, download_name=filename)



# REPORT: mayor CLEARANCE FORM
# REPORT: Mayor Clearance Form (All Departments, grouped by status)
@app.route('/generate_mayor_clearance_summary_pdf')
@login_required
def generate_mayor_clearance_summary_pdf():
    department_name = "All Departments"

    # Fetch all Clearance Forms that are relevant (Mayor / Completed / Approved / Rejected)
    permits = (
        PermitRequest.query
        .filter(PermitRequest.permit_type == "Clearance Form")
        .filter(
            (PermitRequest.current_stage.in_(["Mayor", "Completed", "Approved"])) |
            (PermitRequest.status == "Rejected")
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Attach latest rejection info
    for permit in permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # Group permits in desired order: Completed → In Progress → Pending → Rejected
    completed = []
    in_progress = []
    pending = []
    rejected = []

    for permit in permits:
        if permit.status == "Rejected":
            rejected.append(permit)
        elif permit.current_stage in ["Completed", "Released", "Approved"]:
            completed.append(permit)
        elif permit.current_stage == "Mayor":
            in_progress.append(permit)
        else:
            pending.append(permit)

    permits_ordered = completed + in_progress + pending + rejected

    pdf = MayorClearanceSummaryPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Clearance Form Summary', ln=True)
    pdf.draw_table_headers()

    # Add rows
    row_idx = 1
    for permit in permits_ordered:
        emp = permit.employee
        if not emp:
            continue

        # Determine position
        position = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title

        # Purpose
        if permit.clearance_detail:
            if permit.clearance_detail.clearance_purpose == "Other":
                purpose = f"Other - {permit.clearance_detail.other_purpose or 'N/A'}"
            else:
                purpose = permit.clearance_detail.clearance_purpose
        else:
            purpose = "N/A"

        # Stage mapping and status
        if permit.status == "Rejected":
            current_stage = "Clearance was rejected"
            status = "Rejected"
        elif permit.current_stage == "Mayor":
            current_stage = "Awaiting Mayor approval"
            status = "In Progress"
        elif permit.current_stage in ["Completed", "Released", "Approved"]:
            current_stage = "Clearance process completed"
            status = "Completed"
        else:
            current_stage = "-"
            status = permit.status or "Pending"

        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': position,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'purpose': purpose,
            'status': status,
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
            'rejected_by': permit.rejected_by or '-',
            'rejected_remarks': permit.rejected_remarks or '-',
        }

        pdf.add_clearance_row(row_idx, data)
        row_idx += 1

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Clearance_Form_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False, download_name=filename)





#LEAVE CREDIT REPORT 
# LEAVE CREDIT REPORT
@app.route('/generate_credit_summary_pdf')
@login_required
def generate_credit_summary_pdf():
    pdf = EmployeeCreditPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Step 1: Get all departments
    departments = Department.query.order_by(Department.name).all()

    # Step 1a: Force "Office of the Municipal Mayor" to appear first
    departments.sort(key=lambda d: (0 if d.name == "Office of the Municipal Mayor" else 1, d.name))

    # Step 2: Loop through departments and pass employees
    for dept in departments:
        employees = Employee.query.filter_by(department_id=dept.id).all()
        if not employees:
            continue

        # Format employee data
        formatted_employees = []
        for emp in employees:
            credit = emp.credit_balance
            emp_data = {
                'first_name': emp.first_name,
                'last_name': emp.last_name,
                'middle_name': emp.middle_name or '',
                'credit_balance': {
                    'vacation_earned': credit.vacation_earned if credit else 0.0,
                    'vacation_used': credit.vacation_used if credit else 0.0,
                    'vacation_remaining': credit.vacation_remaining if credit else 0.0,
                    'sick_earned': credit.sick_earned if credit else 0.0,
                    'sick_used': credit.sick_used if credit else 0.0,
                    'sick_remaining': credit.sick_remaining if credit else 0.0,
                },
                'permanent_details': emp.permanent_details,
                'casual_details': emp.casual_details,
                'job_order_details': emp.job_order_details,
            }
            formatted_employees.append(emp_data)

        # Add the department section (with new PDF layout)
        pdf.add_department_section(dept.name, formatted_employees)

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Employee_Credit_Summary_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=True, download_name=filename)


# CREDIT HISTORY REPORT
@app.route('/generate_credit_history_pdf')
@login_required
def generate_credit_history_pdf():
    # Step 1: Get all departments
    departments = Department.query.order_by(Department.name).all()
    credit_transactions_by_dept = {}

    # Step 2: Collect transactions grouped by department
    for dept in departments:
        employees = Employee.query.filter_by(department_id=dept.id).all()
        employee_ids = [e.id for e in employees]

        transactions = CreditTransaction.query.filter(
            CreditTransaction.employee_id.in_(employee_ids)
        ).order_by(CreditTransaction.timestamp.asc()).all()

        if transactions:
            credit_transactions_by_dept[dept.name] = transactions

    # Step 3: Initialize PDF
    pdf = EmployeeCreditHistoryPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Step 4: Loop through each department and add their transactions
    for dept_name, transactions in credit_transactions_by_dept.items():
        pdf.add_department_section(dept_name, transactions)

    # Step 5: Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Leave_Credit_Transactions_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=True, download_name=filename)




# USERCREDIT
# LEAVE CREDIT SUMMARY REPORT (Current User Only)
@app.route('/user_credit_summary_pdf')
@login_required
@role_required('employee')
def user_credit_summary_pdf():
    emp = current_user.employee

    if not emp:
        flash("You are not linked to an employee record.", "warning")
        return redirect(url_for("EmployeeHome"))

    # Skip Job Order employees (no credits)
    if emp.job_order_details:
        flash("Job Order employees do not have credits.", "warning")
        return redirect(url_for("EmployeeHome"))

    # If casual employee, ensure assigned department is set
    if emp.casual_details and not emp.casual_details.assigned_department:
        flash("You are not assigned to any department.", "warning")
        return redirect(url_for("EmployeeHome"))

    # Department
    department = emp.department if emp.permanent_details else (
        emp.casual_details.assigned_department if emp.casual_details else None
    )

    # ---- CREDIT CALCULATION ----
    # Separate Vacation and Sick leave credits
    vacation_earned = sum(tx.amount for tx in emp.credit_transactions 
                          if tx.leave_type == "Vacation" and tx.action == "Earned")
    vacation_used = sum(tx.amount for tx in emp.credit_transactions 
                        if tx.leave_type == "Vacation" and tx.action == "Used")
    vacation_remaining = vacation_earned - vacation_used

    sick_earned = sum(tx.amount for tx in emp.credit_transactions 
                      if tx.leave_type == "Sick" and tx.action == "Earned")
    sick_used = sum(tx.amount for tx in emp.credit_transactions 
                    if tx.leave_type == "Sick" and tx.action == "Used")
    sick_remaining = sick_earned - sick_used

    # ---- FORMAT EMPLOYEE DATA ----
    emp_data = {
        'first_name': emp.first_name,
        'last_name': emp.last_name,
        'middle_name': emp.middle_name or '',
        'credit_balance': {
            'vacation_earned': vacation_earned,
            'vacation_used': vacation_used,
            'vacation_remaining': vacation_remaining,
            'sick_earned': sick_earned,
            'sick_used': sick_used,
            'sick_remaining': sick_remaining,
        },
        'permanent_details': emp.permanent_details,
        'casual_details': emp.casual_details,
        'job_order_details': emp.job_order_details,
    }

    # ---- BUILD PDF ----
    pdf = UserCreditPDF()
    pdf.dept_name = department.name if department else "No Department"
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Add single employee row
    pdf.add_employee_row(emp_data)

    # ---- OUTPUT PDF ----
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"User_Credit_Summary_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


# CREDIT HISTORY SUMMARY REPORT (Current User Only)
# CREDIT HISTORY SUMMARY REPORT (Current User Only)
@app.route('/user_credit_history_pdf')
@login_required
@role_required('employee')
def user_credit_history_pdf():
    emp = current_user.employee

    if not emp:
        flash("You are not linked to an employee record.", "warning")
        return redirect(url_for("EmployeeHome"))

    # Skip Job Order employees (no leave credits)
    if emp.job_order_details:
        flash("Job Order employees do not have credits.", "warning")
        return redirect(url_for("EmployeeHome"))

    # If casual employee, ensure assigned department is set
    if emp.casual_details and not emp.casual_details.assigned_department:
        flash("You are not assigned to any department.", "warning")
        return redirect(url_for("EmployeeHome"))

    # Department name
    department = emp.department if emp.permanent_details else (
        emp.casual_details.assigned_department if emp.casual_details else None
    )

    # Transactions (latest first)
    transactions = sorted(emp.credit_transactions, key=lambda tx: tx.timestamp, reverse=True)

    # ---- BUILD PDF ----
    pdf = UserCreditHistoryPDF()
    pdf.dept_name = department.name if department else "No Department"
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Add all transactions for current user
    for tx in transactions:
        pdf.check_page_break()
        pdf.add_transaction_row(tx)

    # ---- OUTPUT PDF ----
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"User_Credit_History_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )



# HEADCREDIT
# CREDIT HISTORY SUMMARY REPORT (Current head)
@app.route('/head_credit_history_pdf')
@login_required
@role_required('head')
def head_credit_history_pdf():
    # ✅ Step 1: Get logged-in user's department
    if not current_user.employee or not current_user.employee.department:
        flash("No department assigned to your account.", "danger")
        return redirect(request.referrer or url_for('home'))

    department = current_user.employee.department

    # ✅ Step 2: Collect transactions for this department only
    employees = Employee.query.filter_by(department_id=department.id).all()
    employee_ids = [e.id for e in employees]

    transactions = CreditTransaction.query.filter(
        CreditTransaction.employee_id.in_(employee_ids)
    ).order_by(CreditTransaction.timestamp.asc()).all()

    if not transactions:
        flash("No credit transactions found for your department.", "warning")
        return redirect(request.referrer or url_for('home'))

    # ✅ Step 3: Initialize PDF
    pdf = HeadCreditHistoryPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ✅ Step 4: Add only the current department's transactions
    pdf.add_department_section(department.name, transactions)

    # ✅ Step 5: Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Head_Credit_History_{department.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=True, download_name=filename)



# LEAVE CREDIT SUMMARY REPORT (Current head)
@app.route('/head_credit_summary_pdf')
@login_required
@role_required('head')
def head_credit_summary_pdf():
    pdf = HeadCreditPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ✅ Step 1: Get logged-in user's department
    if not current_user.employee or not current_user.employee.department:
        flash("No department assigned to your account.", "danger")
        return redirect(request.referrer or url_for('home'))

    department = current_user.employee.department

    # ✅ Step 2: Get employees in this department only
    employees = Employee.query.filter_by(department_id=department.id).all()
    if not employees:
        flash("No employees found in your department.", "warning")
        return redirect(request.referrer or url_for('home'))

    # ✅ Step 3: Format employee data
    formatted_employees = []
    for emp in employees:
        credit = emp.credit_balance
        emp_data = {
            'first_name': emp.first_name,
            'last_name': emp.last_name,
            'middle_name': emp.middle_name or '',
            'credit_balance': {
                'vacation_earned': credit.vacation_earned if credit else 0.0,
                'vacation_used': credit.vacation_used if credit else 0.0,
                'vacation_remaining': credit.vacation_remaining if credit else 0.0,
                'sick_earned': credit.sick_earned if credit else 0.0,
                'sick_used': credit.sick_used if credit else 0.0,
                'sick_remaining': credit.sick_remaining if credit else 0.0,
            },
            'permanent_details': emp.permanent_details,
            'casual_details': emp.casual_details,
            'job_order_details': emp.job_order_details,
        }
        formatted_employees.append(emp_data)

    # ✅ Step 4: Add the department section
    pdf.add_department_section(department.name, formatted_employees)

    # ✅ Step 5: Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Heada_Credit_Summary_{department.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=True, download_name=filename)









#CASUAL TERMINATED 
@app.route('/generate_terminated_casualjob_pdf')
@login_required
@role_required('hr')
def generate_terminated_casualjob_pdf():
    pdf = HeadTerminatedCasualPDF(department_name="All Departments",)
    pdf.add_page()
    pdf.draw_table_headers()

    terminated_employees = Employee.query.filter(
        Employee.status.ilike('Casual'),
        Employee.employment_status.ilike('inactive')
    ).all()

    row_counter = 0
    display_index = 1

    for emp in terminated_employees:
        if emp.casual_details:
            if row_counter == 15:
                pdf.add_page()
                pdf.draw_table_headers()
                row_counter = 0
                display_index = 1

            pdf.add_employee_row(display_index, emp)
            row_counter += 1
            display_index += 1

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='terminated_casual_employees.pdf'
    )



#PERMANENT TERMINATED 
@app.route('/generate_terminated_permanent_pdf')
@login_required
@role_required('hr')
def generate_terminated_permanent_pdf():
    pdf = HeadTerminatedPermanentPDF(department_name="All Departments")
    pdf.add_page()
    pdf.draw_table_headers()

    # ✅ Get employees who are not 'Casual' or 'Job Order' and are 'inactive'
    terminated_employees = Employee.query.filter(
        ~Employee.status.ilike('Casual'),
        ~Employee.status.ilike('Job Order'),
        Employee.employment_status.ilike('inactive')
    ).all()

    row_counter = 0
    display_index = 1

    for emp in terminated_employees:
        if emp.permanent_details:
            if row_counter == 15:
                pdf.add_page()
                pdf.draw_table_headers()
                row_counter = 0
                display_index = 1

            pdf.add_employee_row(display_index, emp)
            row_counter += 1
            display_index += 1

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='terminated_permanent_employees.pdf'
    )

#JOB ORDER TERMINATED 

@app.route('/generate_terminated_joborder_pdf')
@login_required
@role_required('hr')
def generate_terminated_joborder_pdf():
    pdf = HeadTerminatedJobOrderPDF(department_name="All Departments")
    pdf.add_page()
    pdf.draw_table_headers()

    terminated_employees = Employee.query.filter(
        Employee.status.ilike('Job Order'),
        Employee.employment_status.ilike('inactive')
    ).all()

    row_counter = 0
    display_index = 1

    for emp in terminated_employees:
        if emp.job_order_details:
            if row_counter == 15:
                pdf.add_page()
                pdf.draw_table_headers()
                row_counter = 0
                display_index = 1

            pdf.add_employee_row(display_index, emp)
            row_counter += 1
            display_index += 1

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='terminated_joborder_employees.pdf'
    )




#IPCR HR REPORT
@app.route('/generate_ipcr_dept_pdf')
@login_required
@role_required('hr')
def generate_ipcr_dept_pdf():


    period_id = request.args.get('period_id', type=int)
    selected_period = EvaluationPeriod.query.get(period_id)

    if not selected_period:
        abort(404, "Selected evaluation period not found.")

    period_title = selected_period.name
    departments_data = []

    departments = Department.query.all()

    for dept in departments:
        # ✅ Get active permanent employees (excluding heads and electives)
        permanent_employees = Employee.query.filter(
            Employee.department_id == dept.id,
            Employee.employment_status == 'active',
            Employee.is_deleted == False,
            Employee.status.notin_(['Elective', 'E']),
            Employee.permanent_details.has(),
            ~Employee.permanent_details.has(
                PermanentEmployeeDetails.position.has(Position.title.ilike('%head%'))
            )
        ).all()

        # ✅ Get active casual employees assigned to the department (excluding heads and electives)
        casual_employees = Employee.query.join(CasualEmployeeDetails).filter(
            CasualEmployeeDetails.assigned_department_id == dept.id,
            Employee.employment_status == 'active',
            Employee.is_deleted == False,
            Employee.status.notin_(['Elective', 'E']),
            ~Employee.casual_details.has(
                CasualEmployeeDetails.position.has(Position.title.ilike('%head%'))
            )
        ).all()

        # ✅ Combine all employee IDs
        all_employees = permanent_employees + casual_employees
        employee_ids = [emp.id for emp in all_employees]

        ipcr_total = len(employee_ids)

        ipcrs = IPCR.query.filter(
            IPCR.employee_id.in_(employee_ids),
            IPCR.period_id == selected_period.id
        ).all()

        ipcr_submitted_count = sum(1 for ipcr in ipcrs if ipcr.submitted)
        ipcr_graded_count = sum(1 for ipcr in ipcrs if ipcr.submitted and ipcr.graded)

        departments_data.append({
            'division': dept.name,
            'ipcr_total': ipcr_total,
            'ipcr_submitted': ipcr_submitted_count,
            'ipcr_graded': ipcr_graded_count
        })

    # 📝 Generate PDF
    pdf = HeadDepartmentIPCRPDF(period_title=period_title)
    pdf.add_page()
    pdf.draw_table_headers()

    for i, dept_data in enumerate(departments_data, start=1):
        pdf.add_department_row(i, dept_data)

    # 📤 Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'ipcr_department_summary_{period_title}.pdf'
    )


#IPCR EMPLOYEE HR
@app.route('/generate_employee_ipcr_pdf')
@login_required
@role_required('hr')  # or 'head' if needed
def generate_employee_ipcr_pdf():
   

    department_name = request.args.get('department')
    period_id = request.args.get('period_id', type=int)

    # ✅ Fallback default
    if not department_name:
        department_name = "Office of the Municipal Mayor"

    if not period_id:
        abort(400, "Missing evaluation period ID.")

    department = Department.query.filter_by(name=department_name).first()
    selected_period = EvaluationPeriod.query.get(period_id)

    if not department or not selected_period:
        abort(404, "Invalid department or evaluation period.")

    # ✅ Permanent employees
    permanent_employees = Employee.query.filter(
        Employee.department_id == department.id,
        Employee.employment_status == 'active',
        Employee.is_deleted == False,
        Employee.status.notin_(['Elective', 'E']),
        Employee.permanent_details.has(),
        ~Employee.permanent_details.has(
            PermanentEmployeeDetails.position.has(Position.title.ilike('%head%'))
        )
    ).all()

    # ✅ Casual employees
    casual_employees = Employee.query.join(CasualEmployeeDetails).filter(
        CasualEmployeeDetails.assigned_department_id == department.id,
        Employee.employment_status == 'active',
        Employee.is_deleted == False,
        Employee.status.notin_(['Elective', 'E']),
        ~Employee.casual_details.has(
            CasualEmployeeDetails.position.has(Position.title.ilike('%head%'))
        )
    ).all()

    all_employees = permanent_employees + casual_employees

    # ✅ Create PDF
    pdf = HeadEmployeeIPCRPDF(
        department_name=department.name,
        period_title=selected_period.name
    )
    pdf.add_page()
    pdf.draw_table_headers()

    for index, emp in enumerate(all_employees, start=1):
        ipcr = IPCR.query.filter_by(employee_id=emp.id, period_id=selected_period.id).first()

        # ✅ Compute overall grade (like in the table)
        if ipcr:
            sections = EvaluationSection.query.filter_by(ipcr_id=ipcr.id).options(
                joinedload(EvaluationSection.section_items)
            ).all()

            summary_counts = {'Core': 0, 'Support': 0}
            average_ratings = {}
            weights = {'Core': 0.90, 'Support': 0.10}

            for section in sections:
                category = section.type
                if category in summary_counts:
                    for item in section.section_items:
                        if item.rating_a is not None:
                            summary_counts[category] += 1
                            average_ratings.setdefault(category, []).append(float(item.rating_a))

            total_weighted = 0
            category_count = 0

            for category in ['Core', 'Support']:
                ratings = average_ratings.get(category, [])
                if ratings:
                    avg = sum(ratings) / len(ratings)
                    weighted = avg * weights[category]
                    total_weighted += weighted
                    category_count += 1

            grade = round(total_weighted, 2) if category_count > 0 else None
        else:
            grade = None

        pdf.add_employee_row(index, emp, ipcr, grade)

    # ✅ Return PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"ipcr_employee_details_{department.name.replace(' ', '_')}_{selected_period.name.replace(' ', '_')}.pdf"

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


# HR ISSUE SUMMARY REPORT 
#HR OPRN REPORT 
@app.route('/generate_issue_summary_pdf')
@login_required
@role_required('hr')
def generate_open_issue_summary_pdf():

    # ✅ Only get issues with status 'Open'
    issues = IssueReport.query.filter_by(status='Open').all()

    pdf = OpenIssueSummaryPDF()
    pdf.add_page()
    pdf.draw_table_headers()

    for i, issue in enumerate(issues, 1):
        pdf.add_issue_row(i, issue)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        download_name='issue_summary.pdf',
        as_attachment=True
    )


#HR IN PROCESS 
@app.route('/generate_inprogress_issues_pdf')
@login_required
@role_required('hr')
def generate_inprogress_issues_pdf():

    issues = IssueReport.query.filter_by(status='In Progress').order_by(IssueReport.created_at.desc()).all()

    pdf = InProgressIssueSummaryPDF()
    pdf.add_page()
    pdf.draw_table_headers()

    for idx, issue in enumerate(issues, start=1):
        pdf.add_issue_row(idx, issue)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)


    return send_file(
       pdf_output,
        mimetype='application/pdf',
        download_name='inprogress_issues_summary.pdf',
        as_attachment=True  # ✅ force download
    )

#HR ISSUE RESOLVE 
@app.route('/generate_resolved_issues_pdf')
@login_required
@role_required('hr')
def generate_resolved_issues_pdf():
   
    issues = IssueReport.query.filter_by(status='Resolved').order_by(IssueReport.created_at.desc()).all()

    pdf = ResolvedIssueSummaryPDF()
    pdf.add_page()
    pdf.draw_table_headers()

    for idx, issue in enumerate(issues, start=1):
        pdf.add_issue_row(idx, issue)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)


    return send_file(
       pdf_output,
        mimetype='application/pdf',
        download_name='resolved_issues_summary.pdf',
        as_attachment=True  # ✅ force download
    )


##employee ipcr record 
@app.route('/generate_ipcr_user_summary_pdf')
@login_required
def generate_ipcr_user_summary_pdf():
    employee_id = request.args.get('employee_id', type=int)
    if not employee_id:
        return "Bad Request\nMissing employee_id parameter", 400

    ipcrs = IPCR.query.filter_by(employee_id=employee_id).order_by(IPCR.period_id.desc()).all()
    
    if not ipcrs:
        return "No IPCR records found for this employee.", 404

    # Use only this correct instantiation
    pdf = IPCRSummaryPDF(department_name=current_user.employee.department.name)
    pdf.add_page()
    pdf.draw_table_headers()

    for ipcr in ipcrs:
        pdf.add_ipcr_row(ipcr)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        download_name='ipcr_summary.pdf',
        as_attachment=True
    )

@app.route('/generate_head_ipcr_period_summary_pdf')
@login_required
def generate_head_ipcr_period_summary_pdf():


    employees = current_user.employee.department.employees
    employee_ids = [emp.id for emp in employees]
    total_employees = len(employee_ids)

    if total_employees == 0:
        return "No employees found in your department.", 404

    periods = EvaluationPeriod.query.order_by(EvaluationPeriod.start_date.desc()).all()
    if not periods:
        return "No evaluation periods found.", 404

    # ✅ Create PDF with department name
    department_name = current_user.employee.department.name
    pdf = HeadIPCRPeriodSummaryPDF(department_name=department_name)
    pdf.draw_table_headers()

    for period in periods:
        ipcrs = [ipcr for ipcr in period.ipcrs if ipcr.employee_id in employee_ids]
        pdf.add_period_row(period, ipcrs, total_employees)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        download_name='ipcr_period_summary.pdf',
        as_attachment=True
    )


# dept head ipcr emplloyee 
@app.route('/generate_headdept_ipcr_employee_pdf')
@login_required
def generate_headdept_ipcr_employee_pdf():
    # Get department of logged-in user
    department = current_user.employee.department
    if not department:
        return "You are not assigned to any department.", 404

    # Only Permanent and Casual employees, excluding Heads
    employees = [
        emp for emp in department.employees
        if (emp.permanent_details or emp.casual_details) and not emp.is_department_head
    ]
    if not employees:
        return "No Permanent or Casual employees found in your department.", 404

    # Get selected evaluation period from query parameters
    period_id = request.args.get('period_filter', type=int)
    if not period_id:
        return "No evaluation period selected.", 400

    selected_period = EvaluationPeriod.query.get(period_id)
    if not selected_period:
        return "Selected evaluation period not found.", 404

    # Create PDF
    pdf = HeadDeptIPCREmployeePDF(department_name=department.name)
    pdf.draw_table_headers()

    # Loop through employees once, only for selected period
    for emp in employees:
        ipcr = next((i for i in selected_period.ipcrs if i.employee_id == emp.id), None)
        pdf.add_employee_row(emp, ipcr)

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        download_name=f'{department.name}_{selected_period.name}_ipcr_status.pdf',
        as_attachment=True
    )


# end of permit 


# PRINT
# JO TERMINATED
@app.route('/print_joborder')
@login_required
@role_required('hr')
def print_joborder():
    pdf = HeadTerminatedJobOrderPDF(department_name="All Departments")
    pdf.add_page()
    pdf.draw_table_headers()

    terminated_employees = Employee.query.filter(
        Employee.status.ilike('Job Order'),
        Employee.employment_status.ilike('inactive')
    ).all()

    row_counter = 0
    display_index = 1

    for emp in terminated_employees:
        if emp.job_order_details:
            if row_counter == 15:
                pdf.add_page()
                pdf.draw_table_headers()
                row_counter = 0
                display_index = 1

            pdf.add_employee_row(display_index, emp)
            row_counter += 1
            display_index += 1

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name='terminated_joborder_employees.pdf'
    )

# PERMANENTprint
@app.route('/print_employee_report')
@login_required
@role_required('hr')
def print_employee_report():
    pdf = WidePDF(orientation='L', unit='mm', format=(215.9, 355.6))
    pdf.add_page()
    pdf.table_header()

    row_height_estimate = 10
    bottom_limit = pdf.h - pdf.b_margin

    departments = Department.query.all()

    for dept in departments:
        dept_positions = Position.query.filter_by(department_id=dept.id).all()

        for pos in dept_positions:
            assigned_emps = (
                Employee.query.join(PermanentEmployeeDetails)
                .filter(PermanentEmployeeDetails.position_id == pos.id)
                .filter(Employee.department_id == dept.id)
                .filter(Employee.employment_status == 'active')   # ✅ Only active
                .all()
            )

            for i in range(pos.number_of_positions):
                if pdf.get_y() + row_height_estimate > bottom_limit:
                    pdf.add_page()
                    pdf.table_header()

                if i < len(assigned_emps):
                    emp = assigned_emps[i]
                    if emp.permanent_details:
                        pdf.table_row(emp)
                else:
                    # Vacant slot mock data
                    class Vacant:
                        department = dept
                        last_name = "VACANT"
                        first_name = ""
                        middle_name = ""

                        class PermanentDetails:
                            item_number = ""
                            position = pos
                            salary_grade = pos.salary_grade if hasattr(pos, 'salary_grade') else ""
                            authorized_salary = ""
                            actual_salary = ""
                            step = ""
                            area_code = ""
                            area_type = ""
                            level = ""
                            sex = ""
                            date_of_birth = None
                            tin = ""
                            umid_no = ""
                            date_original_appointment = None
                            date_last_promotion = None
                            eligibility = ""
                            comments = ""

                        permanent_details = PermanentDetails()
                        status = ""

                    pdf.table_row(Vacant())

    # Output to PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name='employee_report.pdf'
    )

#causalprint
@app.route('/print_casualjob')
@login_required
@role_required('hr')
def print_casualjob():
    pdf = CasualJobPDF(orientation='L', unit='mm', format=(215.9, 355.6))
    pdf.add_page()
    pdf.table_header()

    # ✅ Get only Casual employees with active employment_status
    casual_jobs = Employee.query.filter_by(status='Casual', employment_status='active').all()

    row_counter = 0
    display_index = 1

    for emp in casual_jobs:
        if emp.casual_details:
            if row_counter == 15:
                pdf.add_page()
                pdf.table_header()
                row_counter = 0
                display_index = 1

            pdf.table_row(emp, display_index)
            row_counter += 1
            display_index += 1

    # --- After all employees, add the note row and a blank row ---
    note_text = (
        "The abovenamed personnel are hereby/appointed as casuals at the rate of compensation stated opposite their names "
        "for the period indicated. It is understood that such employment will cease automatically at the end of the period "
        "stated unless renewed. Any or all of them may be laid-off any time before the expriration\nof the employment period "
        "when their services are no longer needed or funds are no longer available or the project has been completed/finished"
        "or their performance are below per."
    )

    pdf.table_note_row(note_text)   # add the note
    pdf.table_blank_row(height=2)   # add a blank row below the note

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)


    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name='casualjob_report.pdf'
    )


#joprint
@app.route('/print_jo')
@login_required
@role_required('hr')
def print_jo():
   
    pdf = JobOrderPDF(orientation='P', unit='mm', format=(215.9, 355.6))  # 8.5 x 14 inches
    pdf.add_page()

    # Fetch department mapping: {id: name}
    departments = Department.query.all()
    departments_dict = {dept.id: dept.name for dept in departments}

    # Only fetch employees with status 'Job Order'
    job_orders = (
        Employee.query
        .filter_by(status='Job Order')
        .options(joinedload(Employee.job_order_details))  # Avoid N+1
        .order_by(Employee.last_name, Employee.first_name, Employee.middle_name)
        .all()
    )

    # Generate the PDF layout using filtered names + department names
    today = datetime.today()
    year = today.year
    month = today.month

    pdf.jo_layout_table(
    year=year,
    month=month,
    days=15,  # ← limit to 15 days
    names=job_orders,
    departments_dict=departments_dict
    )


    # Generate PDF in memory
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name='job_order_layout.pdf'
    )

#travelprint
@app.route('/print_travel_order/<int:permit_id>')
@login_required
def print_travel_order(permit_id):

    permit = PermitRequest.query.filter_by(id=permit_id, permit_type='Travel Order').first()
    if not permit:
        abort(404)

    # Fetch the employee who requested the permit
    employee = permit.employee
    if not employee:
        abort(404)

    # Determine the employee's department
    department_id = None
    if employee.permanent_details:
        department_id = employee.department_id
    elif employee.casual_details:
        department_id = employee.casual_details.assigned_department_id
    elif employee.job_order_details:
        department_id = employee.job_order_details.assigned_department_id

    # --- Find the Department Head ---
    head_user = None

    # Special case: employee belongs to HR
    if employee.department and employee.department.name == "Office of the Municipal Human Resource Management Officer":
        head_user = (
            Users.query.join(Employee)
            .outerjoin(PermanentEmployeeDetails, PermanentEmployeeDetails.employee_id == Employee.id)
            .outerjoin(CasualEmployeeDetails, CasualEmployeeDetails.employee_id == Employee.id)
            .outerjoin(JobOrderDetails, JobOrderDetails.employee_id == Employee.id)
            .outerjoin(Position, 
                (Position.id == PermanentEmployeeDetails.position_id) |
                (Position.id == CasualEmployeeDetails.position_id)
            )
            .filter(
                ((Position.title == "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I") |
                 (JobOrderDetails.position_title == "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I"))
            )
            .first()
        )
    else:
        # Regular case: find head of employee's department
        if department_id:
            head_user = (
                Users.query.join(Employee)
                .filter(
                    Employee.department_id == department_id,
                    Users.role == "Head"
                )
                .first()
            )

    # --- Fetch latest head approval ---
    if head_user:
        head_approval = (
            db.session.query(PermitRequestHistory)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action_by == head_user.id,
                PermitRequestHistory.action == "Approved"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )

        if head_approval:
            permit.head_approver = head_user.name

            # Determine head's position
            head_employee = head_user.employee
            if head_employee.permanent_details:
                permit.head_approver_position = head_employee.permanent_details.position.title
            elif head_employee.casual_details:
                permit.head_approver_position = head_employee.casual_details.position.title
            elif head_employee.job_order_details:
                permit.head_approver_position = head_employee.job_order_details.position_title
            else:
                permit.head_approver_position = "Head of Department"

            permit.head_approver_id = head_user.id
        else:
            # Head exists but has not approved yet
            permit.head_approver = "________________________"
            permit.head_approver_position = "Head of Department"
            permit.head_approver_id = None
    else:
        # No head found for this department
        permit.head_approver = "________________________"
        permit.head_approver_position = "Head of Department"
        permit.head_approver_id = None

    # --- Generate the PDF ---
    pdf = TravelOrderPDF()
    pdf.add_page()
    pdf.add_travel_order_form(permit)  # permit already has head info

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"TravelOrder_{employee.last_name}_{employee.first_name}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )

#TRAVEL HISTORYprint
@app.route('/print_travel_log')
@login_required
def print_travel_log():
    # ✅ Filter only APPROVED logs
    logs = (
        TravelLog.query
        .filter(TravelLog.status == 'Approved')
        .all()
    )

    if not logs:
        abort(404)

    pdf = TravelLogPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()

    for log in logs:
        pdf.add_log_row({
            'last_name': log.travel_order.permit.employee.last_name,
            'first_name': log.travel_order.permit.employee.first_name,
            'middle_name': log.travel_order.permit.employee.middle_name,
            'destination': log.travel_order.destination,
            'log_date': log.log_date,
            'purpose': log.travel_order.purpose,
            'tracking_id': log.tracking_id,
        })

    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output = io.BytesIO(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False,)

#LEAVEprint
@app.route('/print_leave_application/<int:permit_id>')
@login_required
def print_leave_application(permit_id):
    # Fetch permit request of type 'Leave' by ID
    permit = PermitRequest.query.filter_by(id=permit_id, permit_type='Leave').first()
    if not permit:
        abort(404)

    leave = permit.leave_detail  # Related LeaveApplication object
    if not leave:
        abort(404)

    employee = permit.employee
    if not employee:
        abort(404)

    # Determine department and position based on employee type/details
    if employee.permanent_details:
        department = employee.department.name if employee.department else 'N/A'
        position = employee.permanent_details.position.title if employee.permanent_details.position else 'N/A'
    elif employee.casual_details:
        department = (employee.casual_details.assigned_department.name 
                      if employee.casual_details.assigned_department else 'N/A')
        position = (employee.casual_details.position.title 
                    if employee.casual_details.position else 'N/A')
    elif employee.job_order_details:
        department = (employee.job_order_details.assigned_department.name 
                      if employee.job_order_details.assigned_department else 'N/A')
        position = employee.job_order_details.position_title or 'N/A'
    else:
        department = employee.department.name if employee.department else 'N/A'
        position = 'N/A'

    pdf = LeaveApplicationPDF()
    pdf.add_page()
    pdf.add_leave_form(
        department=department,
        last_name=employee.last_name,
        first_name=employee.first_name,
        middle_name=employee.middle_name,
        date_from=leave.date_from.strftime("%B %d, %Y"),
        position=position,
        salary=leave.salary or 'N/A'
    )
    pdf.add_instructions_page()

    pdf.show_header = False  # Disable header for next page
    pdf.add_page()

    # Output PDF to bytes
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    # Open PDF directly in browser (not download)
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False  # <-- Open in browser
    )

#clearanceprint
@app.route('/print_clearance/<int:permit_id>')
def print_clearance(permit_id):
    # Get clearance by filtering on permit_id (not clearance id)
    clearance = ClearanceForm.query.filter_by(permit_id=permit_id).first_or_404()
    permit = clearance.permit
    employee = permit.employee if permit else None

    if not employee:
        return abort(404, "Employee not found")

    # Get department and position
    if employee.permanent_details:
        department = employee.department.name if employee.department else 'N/A'
        position = employee.permanent_details.position.title if employee.permanent_details.position else 'N/A'
    elif employee.casual_details:
        department = employee.casual_details.assigned_department.name if employee.casual_details.assigned_department else 'N/A'
        position = employee.casual_details.position.title if employee.casual_details.position else 'N/A'
    elif employee.job_order_details:
        department = employee.job_order_details.assigned_department.name if employee.job_order_details.assigned_department else 'N/A'
        position = employee.job_order_details.position_title or 'N/A'
    else:
        department = employee.department.name if employee.department else 'N/A'
        position = 'N/A'

    # PDF Content Details
    purpose = clearance.clearance_purpose or clearance.other_purpose or 'N/A'
    date_from = clearance.date_from.strftime('%B %d, %Y') if clearance.date_from else 'N/A'
    effectivity_period = (f"{clearance.date_from.strftime('%B %d, %Y')} to {clearance.date_to.strftime('%B %d, %Y')}"
                          if clearance.date_from and clearance.date_to else 'N/A')
    name = f"{employee.first_name} {employee.last_name}" if employee.first_name and employee.last_name else 'N/A'

    # Create PDF
    pdf = ClearanceFormPDF()
    pdf.add_page()
    pdf.add_clearance_form(
        leave_type=purpose,
        date_from=date_from,
        position=position,
        office_assignment=department,
        name=name,
        effectivity_period=effectivity_period
    )
    
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)


    filename = f"clearance_form_{name.replace(' ', '_')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False)

#ipcrprint 

@app.route('/print_ipcr')
@login_required
def print_ipcr():
    employee_id = request.args.get('employee_id')
    if not employee_id:
        return abort(400, description="Missing employee_id parameter")

    # ✅ Get latest IPCR for this employee (any period)
    ipcr = IPCR.query.filter_by(employee_id=employee_id).order_by(IPCR.id.desc()).first()
    if not ipcr:
        return abort(404, description="No IPCR record found for this employee.")

    # ✅ Extract related info
    employee = ipcr.employee

    # Use assigned_department if casual employee
    if hasattr(employee, "casual_details") and employee.casual_details and employee.casual_details.assigned_department:
        department = employee.casual_details.assigned_department
    else:
        department = employee.department

    period = ipcr.period
    start_date = period.start_date if period else None
    end_date = period.end_date if period else None

    # ✅ Identify department head for this employee’s department
    dept_employees = Employee.query.filter(Employee.department_id == department.id).all()
    head_employee = next((emp for emp in dept_employees if emp.is_department_head), None)

    if head_employee:
        middle_initial = f"{head_employee.middle_name[0]}." if head_employee.middle_name else ""
        head_name = f"{head_employee.first_name} {middle_initial} {head_employee.last_name}"
    else:
        head_name = "(Head of Department)"

    # ✅ Fetch the head of “Office of the Municipal Mayor”
    mayor_department = Department.query.filter(
        Department.name.ilike('%Office of the Municipal Mayor%')
    ).first()

    mayor_head = None
    if mayor_department:
        mayor_head = Employee.query.filter(
            Employee.department_id == mayor_department.id,
            Employee.is_department_head == True
        ).first()

    # Format mayor name (all caps, with "HON." prefix and MD at the end)
    if mayor_head:
        middle_initial = f"{mayor_head.middle_name[0]}." if mayor_head.middle_name else ""
        mayor_name = f"HON. {mayor_head.first_name.upper()} {middle_initial.upper()} {mayor_head.last_name.upper()}, MD"
    else:
        mayor_name = "HON. MAYOR, MD (NOT SET)"

    # ✅ Initialize PDF
    pdf = PerformanceReportPDF(
        orientation='L',
        unit='mm',
        format=(215.9, 355.6),
        start_date=start_date,
        end_date=end_date,
        head_name=head_name,
        mayor_name=mayor_name,  # ✅ pass mayor to header logic
        employee=employee
    )

    pdf.date_submitted = ipcr.date_submitted
    pdf.department_name = department.name if department else "Unknown Department"

    pdf.add_page()
    pdf.table_header()
    pdf.show_header = False

    core_ratings, support_ratings = [], []

    # ✅ Render IPCR Sections
    for section in ipcr.sections:
        if section.type.lower() == 'core':
            pdf.core_function_row(section.type)
        elif section.type.lower() == 'support':
            pdf.support_function_row(section.type)
        else:
            continue

        for item in section.section_items:
            ratings = [item.rating_q, item.rating_e, item.rating_t, item.rating_a]
            valid_ratings = [r for r in ratings if r is not None]
            if len(valid_ratings) == 4:
                avg = sum(valid_ratings) / 4
                if section.type.lower() == 'core':
                    core_ratings.append(f"{avg:.2f}")
                elif section.type.lower() == 'support':
                    support_ratings.append(f"{avg:.2f}")

            accountable_name = f"{ipcr.employee.first_name} {ipcr.employee.last_name}"

            pdf.table_row({
                'mfo': item.mfo or "",
                'success_indicators': item.success_indicator or "",
                'budget': str(item.allotted_budget) if item.allotted_budget else "",
                'actual': str(item.accomplishment) if item.accomplishment else "",
                'rating': {
                    'Q': str(item.rating_q) if item.rating_q is not None else "",
                    'E': str(item.rating_e) if item.rating_e is not None else "",
                    'T': str(item.rating_t) if item.rating_t is not None else "",
                    'A': str(item.rating_a) if item.rating_a is not None else "",
                },
                'remarks': item.remarks or "",
                'accountable': accountable_name
            })

    # ✅ Summary computation
    core_sum = sum([float(r) for r in core_ratings]) if core_ratings else 0
    support_sum = sum([float(r) for r in support_ratings]) if support_ratings else 0
    core_count, support_count = len(core_ratings), len(support_ratings)
    core_avg = core_sum / core_count if core_count else 0
    support_avg = support_sum / support_count if support_count else 0
    total_weighted = (core_avg * 0.9) + (support_avg * 0.1)

    
    # --- Prepare rows for summary table ---
    rows = [
        # Header row → blue
        {"category": "Category", "mfo": "MFO", "rating": "Rating"},
        # Strategic Priority → white
        {"category": "Strategic Priority", "mfo": "", "rating": ""},
        # Core Function → white, MFO = core count, Rating = average
        {"category": "Core Function", "mfo": str(core_count), "rating": f"{core_avg:.2f}"},
        # Support Function → white, MFO = support count, Rating = average
        {"category": "Support Function", "mfo": str(support_count), "rating": f"{support_avg:.2f}"},
        # Total Overall Rating → blue, MFO = "-", Rating = total weighted
        {"category": "Total Overall Rating", "mfo": "", "rating": f"{total_weighted:.2f}"},
        # Final Average Rating → blue, MFO = "-", Rating = final average
        {"category": "Final Average Rating", "mfo": "", "rating": f"{ipcr.final_average_rating:.2f}" if ipcr.final_average_rating else "-"},
        # Adjectival Rating → blue
        {"category": "Adjectival Rating", "mfo": "", "rating": ipcr.adjective_rating or "-"},
    ]

    # Rows 0, 4, 5, 6 should have blue Cells 2-4
    blue_rows = [0, 4, 5, 6]

    # Add the rows to the PDF
    pdf.new_table_rows_custom_color(rows, blue_rows=blue_rows)
# 🧾 Define the positions per line
    positions = [
        ["MUNICIPAL PLANNING AND DEVELOPMENT COORDINATOR I"],  # Line 1
        ["MUNICIPAL GOVERNMENT DEPARTMENT HEAD I (LDRRMO)", "MUNICIPAL BUDGET OFFICER I"],  # Line 2
        ["MUNICIPAL TREASURER"],  # Line 3
        ["MUNICIPAL ACCOUNTANT", "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I"],  # Line 4
    ]

    # 🧾 Helper function
    def get_permanent_employee_name_by_position(position_title):
        # ✅ Special override
        if position_title == "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I (LDRRMO)":
            return "Aldwin D. Aloquin"

        # 🔍 Default DB lookup
        emp = (
            db.session.query(Employee)
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(Position.title == position_title)
            .filter(Employee.is_deleted == False)
            .first()
        )
        if emp:
            middle_initial = f"{emp.middle_name[0].upper()}." if emp.middle_name else ""
            return f"{emp.first_name} {middle_initial} {emp.last_name}".strip()
        return "(Not Found)"


    # 🧾 Build the name list following your layout
    names_list = []
    for group in positions:
        if len(group) == 1:
            names_list.append(get_permanent_employee_name_by_position(group[0]))
        else:
            combined_names = "                                                ".join(
                [get_permanent_employee_name_by_position(p) for p in group]
            )
            names_list.append(combined_names)

    # Get the employee with position "MUNICIPAL MAYOR"
    mayor_employee = (
        Employee.query
        .join(Employee.permanent_details)
        .join(PermanentEmployeeDetails.position)
        .filter(Position.title.ilike("MUNICIPAL MAYOR"))
        .first()
    )

    if mayor_employee:
        middle_initial = f"{mayor_employee.middle_name[0]}." if mayor_employee.middle_name else ""
        mayor_name = f"HON. {mayor_employee.first_name.upper()} {middle_initial.upper()} {mayor_employee.last_name.upper()}, MD"
    else:
        mayor_name = "HON. MAYOR (NOT SET)"

    # Join all lines with line breaks
    all_names = "\n" + "\n".join(names_list)

    # 🧾 Table rows
    rows_data = [
        (all_names, "", mayor_name, "")  # Mayor in line 4, cell 3
    ]


    # 🧾 Generate the layout
    pdf.assessed_by_table(rows_data)


    # ✅ Output PDF
    pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
    pdf_output = io.BytesIO(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=f'ipcr_report_{employee_id}.pdf'
    )


#COEprint
@app.route('/print_coe/<int:permit_id>')
@login_required
def print_coe(permit_id):
    # Query the permit request by ID and ensure it's a COE permit
    permit = PermitRequest.query.filter_by(id=permit_id, permit_type='Certification of Employment').first()
    if not permit:
        abort(404, description="Permit request not found or not a COE request")

    # Create PDF instance
    pdf = CertificationPDF()
    pdf.add_page()
    pdf.add_certification_body(permit)

    # Output PDF to bytes
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')  # output as string and encode
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    # Return PDF as a file download
    filename = f"COE_{permit.employee.last_name}_{permit.employee.first_name}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False
        
    )


#JOB HIRING APPLICATION SKDHASDASprint
@app.route('/print_under_review')
@login_required
def print_under_review():

    applicants = Applicant.query.filter_by(status='Under Review').all()

    pdf = UnderReviewPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()  # calls header()

    if not applicants:
        # No applicants message
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, "No Under Review applicants found.", ln=True, align='C')
    else:
        # Add each applicant row
        for applicant in applicants:
            pdf.add_applicant_row(applicant)

    # Output PDF to BytesIO
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Under_Review_Applicants_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )



#APPLICANT INTERVIEWprint
@app.route('/print_interview')
@login_required
def print_interview():
    # Query applicants with Scheduled interviews
    applicants = (
        Applicant.query
        .filter(Applicant.interviews.any(Interview.status == 'Scheduled'))
        .options(
            joinedload(Applicant.job_posting).joinedload(JobPosting.department),
            joinedload(Applicant.interviews)
        )
        .all()
    )

    pdf = InterviewApplicantPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()  # automatically calls header()

    if not applicants:
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, "No Scheduled Interview applicants found.", ln=True, align='C')
    else:
        for applicant in applicants:
            # Pass the object directly
            pdf.add_applicant_row(applicant)

    # Output PDF to BytesIO
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Scheduled_Interview_Applicants_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )


#ACCEPTED APPLICANTprint 
@app.route('/print_hired')
@login_required
def print_hired():
       # Fetch applicants with status 'Hired'
    applicants = (
        Applicant.query
        .filter_by(status='Hired')
        .options(
            joinedload(Applicant.job_posting).joinedload(JobPosting.department),
            joinedload(Applicant.interviews)
        )
        .all()
    )

    # Create PDF
    pdf = AcceptedApplicantPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()  # calls header() and prints table header

    if not applicants:
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, "No hired applicants found.", ln=True, align='C')
    else:
        for applicant in applicants:
            # Pass the Applicant object directly
            pdf.add_applicant_row(applicant)

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Hired_Applicants_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )



#REJECTED KAprint
@app.route('/print_rejected')
@login_required
def print_rejected():
     # Fetch applicants with status 'Rejected'
   # Fetch applicants with status 'Rejected'
    applicants = (
        Applicant.query
        .filter_by(status='Rejected')
        .options(
            joinedload(Applicant.job_posting).joinedload(JobPosting.department),
            joinedload(Applicant.interviews)
        )
        .all()
    )

    # Create PDF
    pdf = RejectedApplicantPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()  # calls header() and prints table header

    if not applicants:
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, "No rejected applicants found.", ln=True, align='C')
    else:
        for applicant in applicants:
            # Pass the object directly; PDF class handles interview extraction
            pdf.add_applicant_row(applicant)

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Rejected_Applicants_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )


#ADMINEMPLOYEELISTprint
#CASUAL PER DEPARTMENT 
@app.route('/head/print_casual_employee')
@login_required
def head_print_casual_employee():
    # Ensure the current user has a department
    if not current_user.employee or not current_user.employee.department:
        abort(403, description="You are not assigned to any department.")

    # Get the department info of the current head
    department_name = current_user.employee.department.name
    department_id = current_user.employee.department_id

    # Use an alias for clarity
    Casual = aliased(CasualEmployeeDetails)

    # Query for active casual employees assigned to the same department
    casual_employees = (
        db.session.query(Employee)
        .join(Casual, Employee.id == Casual.employee_id)
        .filter(
            Casual.assigned_department_id == department_id,
            Employee.status == 'Casual',
            Employee.employment_status == 'active',
            Employee.is_deleted == False
        )
        .all()
    )

    if not casual_employees:
        abort(404, description="No active casual employees found under this department.")

    # Generate the PDF
    pdf = HeadCasualEmployeePDF(department_name)
    pdf.add_page()

    for idx, emp in enumerate(casual_employees, start=1):
        pdf.add_employee_row(idx, emp)

    # Output the PDF to memory
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"CasualEmployees_{department_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False)


#JO PER DEPARTMENTprint
@app.route('/head/print_job_order_employee')
@login_required
def head_print_job_order_employee():
    if not current_user.employee or not current_user.employee.department:
        abort(403, description="You are not assigned to any department.")

    department_name = current_user.employee.department.name
    department_id = current_user.employee.department_id

    # Filter job order employees assigned to the same department
    job_order_employees = Employee.query.join(JobOrderDetails).filter(
        JobOrderDetails.assigned_department_id == department_id,
        Employee.status == 'Job Order',
        Employee.employment_status == 'active',
        Employee.is_deleted == False
    ).all()

    if not job_order_employees:
        abort(404, description="No active job order employees found under this department.")

    pdf = HeadJobOrderEmployeePDF(department_name)
    pdf.add_page()

    for idx, emp in enumerate(job_order_employees, start=1):
        pdf.add_employee_row(idx, emp)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"JobOrderEmployees_{department_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False, download_name=filename)

#PERMANENT  PER DEPARTMENTprint
@app.route('/head/print_permanent_employee')
@login_required
def head_print_permanent_employee():
    # Ensure current user is assigned to a department
    if not current_user.employee or not current_user.employee.department:
        abort(403, description="You are not assigned to any department.")

    department_name = current_user.employee.department.name
    department_id = current_user.employee.department_id

    # Get all ACTIVE PERMANENT employees assigned to the same department
    permanent_employees = Employee.query.join(PermanentEmployeeDetails).filter(
        Employee.department_id == department_id,
        Employee.status.notin_(['Job Order', 'Casual']),  # NOT Job Order, NOT Casual
        Employee.employment_status.ilike('active'),
        Employee.is_deleted == False
    ).all()

    if not permanent_employees:
        abort(404, description="No active permanent employees found under this department.")

    # Generate PDF
    pdf = HeadPermanentEmployeePDF(department_name)
    pdf.add_page()

    for idx, emp in enumerate(permanent_employees, start=1):
        pdf.add_employee_row(idx, emp)

    # Prepare PDF for download
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"PermanentEmployees_{department_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False    )



# REPORT: APPLICATION FOR LEAVE REPORTprint
@app.route('/print_head_leave_summary')
@login_required
def print_head_leave_summary():
    department_name = (
        current_user.employee.department.name 
        if current_user.employee and current_user.employee.department 
        else 'All Departments'
    )

    # Query all leave permits (Leave type only)
    all_permits = PermitRequest.query.filter_by(permit_type="Leave").order_by(PermitRequest.date_requested.asc()).all()

    # Define status order for grouping
    status_order = ['Approved', 'Pending', 'In Progress', 'Rejected']  # Include In Progress

    pdf = HeadLeaveApplicationPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Leave Applications', ln=True)
    pdf.draw_table_headers()

    idx = 1  # Global row counter
    for status in status_order:
        # Filter permits explicitly for the current status
        filtered_permits = [
            p for p in all_permits if (
                (p.status in ['Completed', 'Released', 'Approved'] and status == 'Approved') or
                (p.status == 'Pending' and status == 'Pending') or
                (p.status == 'In Progress' and status == 'In Progress') or
                (p.status == 'Rejected' and status == 'Rejected')
            )
        ]

        for permit in filtered_permits:
            emp = permit.employee
            if not emp:
                continue

            if permit.current_stage == "Head":
                continue

            # Determine Position
            pos = "N/A"
            if emp.permanent_details and emp.permanent_details.position:
                pos = emp.permanent_details.position.title
            elif emp.casual_details and emp.casual_details.position:
                pos = emp.casual_details.position.title
            elif emp.job_order_details:
                pos = emp.job_order_details.position_title

            # Map current stage
            stage_map = {
                'HR': 'With HR for review',
                'Head': 'Awaiting Department Head approval',
                'Mayor': 'Awaiting Mayor approval',
                'Completed': 'Leave process completed'
            }

            # Show custom message for Rejected, else map stage
            if permit.status == 'Rejected':
                current_stage = 'Leave was rejected'
            else:
                current_stage = stage_map.get(permit.current_stage, '-')

            # Prepare data for PDF row
            data = {
                'department': emp.department.name if emp.department else 'N/A',
                'position': pos,
                'first_name': emp.first_name or '',
                'middle_name': emp.middle_name or '',
                'last_name': emp.last_name or '',
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'leave_type': (
                    f"{permit.leave_detail.leave_type if permit.leave_detail else 'N/A'}" +
                    (f"\n{permit.leave_detail.date_from.strftime('%b %d, %Y')} - {permit.leave_detail.date_to.strftime('%b %d, %Y')}" if permit.leave_detail else '')
                ),
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',

                # Employee leave credit
                'employee': {
                    'credit_balance': {
                        'vacation_remaining': emp.credit_balance.vacation_remaining if emp.credit_balance else 0,
                        'sick_remaining': emp.credit_balance.sick_remaining if emp.credit_balance else 0,
                    }
                },
                'leave_detail': {
                    'leave_type': permit.leave_detail.leave_type if permit.leave_detail else '',
                    'paid_days': permit.leave_detail.paid_days if permit.leave_detail else None,
                    'working_days': permit.leave_detail.working_days if permit.leave_detail else None,
                    'date_from': permit.leave_detail.date_from if permit.leave_detail else None,
                    'date_to': permit.leave_detail.date_to if permit.leave_detail else None,
                }
            }

            pdf.add_leave_row(idx, data)
            idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Leave_Application_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False, download_name=filename)



# REPORT: TRAVEL ORDERprint
@app.route('/print_travel_summary')
@login_required
def print_travel_summary():
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'All Departments'
    )

    # Query all travel orders
    all_travel_orders = PermitRequest.query.filter_by(permit_type="Travel Order").order_by(PermitRequest.date_requested.asc()).all()

    # Define status order, excluding 'Cancelled'
    status_order = ['Approved', 'Pending', 'In Progress', 'Rejected']

    pdf = HeadTravelOrderPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages() 
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Travel Orders', ln=True)
    pdf.draw_table_headers()

    row_idx = 1
    for status in status_order:
        # Filter orders explicitly for the current status
        filtered_orders = [
            t for t in all_travel_orders if (
                (t.status in ['Completed', 'Released', 'Approved'] and status == 'Approved') or
                (t.status == 'Pending' and status == 'Pending') or
                (t.status == 'In Progress' and status == 'In Progress') or
                (t.status == 'Rejected' and status == 'Rejected')
            )
        ]

        for permit in filtered_orders:
            emp = permit.employee
            if not emp:
                continue
            if permit.current_stage == "Head":
                continue

            # Determine position
            position = "N/A"
            if emp.permanent_details and emp.permanent_details.position:
                position = emp.permanent_details.position.title
            elif emp.casual_details and emp.casual_details.position:
                position = emp.casual_details.position.title
            elif emp.job_order_details:
                position = emp.job_order_details.position_title

            # Map current_stage descriptions for non-rejected
            stage_map = {
                'HR': 'With HR for review',
                'Head': 'Awaiting Department Head approval',
                'Mayor': 'Awaiting Mayor approval',
                'Completed': 'Travel process completed'
            }
            current_stage = stage_map.get(permit.current_stage, '-') if permit.status != 'Rejected' else 'Travel was rejected'

            # Build data dictionary
            data = {
                'department': emp.department.name if emp.department else 'N/A',
                'position': position,
                'first_name': emp.first_name or '',
                'middle_name': emp.middle_name or '',
                'last_name': emp.last_name or '',
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'destination': permit.travel_detail.destination if permit.travel_detail else 'N/A',
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',
            }

            pdf.add_travel_row(row_idx, data)
            row_idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Order_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )



# REPORT: CLEARANCE FORMprint 

@app.route('/print_clearance_summary')
@login_required
def print_clearance_summary():
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'All Departments'
    )

    # Query all clearance forms
    all_clearance_permits = PermitRequest.query.filter_by(permit_type="Clearance Form").order_by(PermitRequest.date_requested.asc()).all()

    # Define status order (excluding Cancelled)
    status_order = ['Completed', 'Pending', 'In Progress', 'Approved', 'Rejected']

    pdf = HeadClearanceSummaryPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Clearance Form', ln=True)
    pdf.draw_table_headers()

    row_idx = 1  # Start row numbering

    for status in status_order:
        # Filter permits explicitly for the current status
        filtered_permits = [
            p for p in all_clearance_permits if (
                (p.status == 'Completed' and status == 'Completed') or
                (p.status == 'Pending' and status == 'Pending') or
                (p.status not in ['Completed', 'Cancelled', 'Rejected', 'Approved'] and status == 'In Progress') or
                (p.status == 'Approved' and status == 'Approved') or
                (p.status == 'Rejected' and status == 'Rejected')
            )
        ]

        for permit in filtered_permits:
            emp = permit.employee
            if not emp:
                continue
            if permit.current_stage == "Head":
                continue

            # Determine position
            position = "N/A"
            if emp.permanent_details and emp.permanent_details.position:
                position = emp.permanent_details.position.title
            elif emp.casual_details and emp.casual_details.position:
                position = emp.casual_details.position.title
            elif emp.job_order_details:
                position = emp.job_order_details.position_title

            # Full Name
            full_name = f"{emp.last_name}, {emp.first_name} {emp.middle_name or ''}".strip()

            # Purpose
            if permit.clearance_detail:
                if permit.clearance_detail.clearance_purpose == "Other":
                    purpose = f"Other - {permit.clearance_detail.other_purpose or 'N/A'}"
                else:
                    purpose = permit.clearance_detail.clearance_purpose
            else:
                purpose = "N/A"

            # Map current_stage descriptions
            stage_map = {
                'HR': 'With HR for review',
                'Head': 'Awaiting Department Head approval',
                'Mayor': 'Awaiting Mayors approval',
                'Completed': ' Clearance Process completed'
            }
            current_stage = stage_map.get(permit.current_stage, '-') if permit.status != 'Rejected' else 'Clearance was rejected'


            data = {
                'department': emp.department.name if emp.department else 'N/A',
                'position': position,
                'first_name': emp.first_name or '',
                'middle_name': emp.middle_name or '',
                'last_name': emp.last_name or '',
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'purpose': purpose,
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',
            }

            pdf.add_clearance_row(row_idx, data)
            row_idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Clearance_Form_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )

# REPORT: COEprint
@app.route('/print_coe_summary')
@login_required
def print_coe_summary():
    # Get department of current user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'All Departments'
    )

    # Query all COE permits excluding Cancelled
    all_coe_permits = PermitRequest.query.filter(
        PermitRequest.permit_type == "Certification of Employment",
        PermitRequest.status != "Cancelled"
    ).order_by(PermitRequest.date_requested.asc()).all()

    # Define status order (excluding Cancelled)
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']

    # Initialize PDF
    pdf = HeadCOEPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages() 
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Certificate of Employment', ln=True)
    pdf.draw_table_headers()

    # Current stage mapping
    stage_map = {
        'HR': 'With HR for review',
        'Head': 'Awaiting Department Head approval',
        'Mayor': 'Awaiting Mayors approval',
        'Completed': 'COE Process completed'
    }

    row_idx = 1
    for status in status_order:
        # Filter permits by current status
        filtered_permits = [p for p in all_coe_permits if p.status == status]

        for permit in filtered_permits:
            emp = permit.employee

            # Determine employee details safely
            if emp:
                department = emp.department.name if emp.department else 'N/A'

                if getattr(emp, 'permanent_details', None) and getattr(emp.permanent_details, 'position', None):
                    position = emp.permanent_details.position.title
                elif getattr(emp, 'casual_details', None) and getattr(emp.casual_details, 'position', None):
                    position = emp.casual_details.position.title
                elif getattr(emp, 'job_order_details', None):
                    position = getattr(emp.job_order_details, 'position_title', 'N/A')
                else:
                    position = 'N/A'

                first_name = emp.first_name or ''
                middle_name = emp.middle_name or ''
                last_name = emp.last_name or ''
            else:
                department = 'N/A'
                position = 'N/A'
                first_name = ''
                middle_name = ''
                last_name = ''

            # Full name with middle initial
            middle_initial = f"{middle_name[0]}." if middle_name else ""
            full_name = f"{last_name}, {first_name} {middle_initial}".strip()

            # Map current_stage with custom message for Rejected
            if permit.status == 'Rejected':
                current_stage = 'COE was rejected'
            else:
                current_stage = stage_map.get(permit.current_stage, '-')

            # Build data dict for PDF
            data = {
                'department': department,
                'position': position,
                'first_name': first_name,
                'middle_name': middle_name,
                'last_name': last_name,
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',
            }

            pdf.add_coe_row(data)
            row_idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"COE_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )


# REPORT: HR DEPARTMETN  LEAVE SUMMARY PDF
@app.route('/print_hR_leave_summary')
@login_required
def print_hR_leave_summary():

  # Get department of current user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query leave permits for the department, excluding Cancelled
    permits = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Leave")
        .filter(Employee.department_id == current_user.employee.department_id)
        .filter(PermitRequest.status != "Cancelled")
        .all()
    )

    # --- Custom Sorting Order ---
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']
    status_priority = {status: idx for idx, status in enumerate(status_order, start=1)}

    def get_status_priority(permit):
        if permit.status in ['HR', 'Head', 'Mayor']:
            return status_priority.get('Pending', 99)  # Treat as in-progress/pending
        return status_priority.get(permit.status, 99)

    permits.sort(key=lambda p: (
        get_status_priority(p),
        p.date_requested or datetime.min
    ))

    # PDF Setup
    pdf = HRLeaveApplicationPDF(department_name=department_name)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.draw_table_headers()

    # Fill rows
    for permit in permits:
        emp = permit.employee
        if not emp:
            continue

        # Position
        pos = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            pos = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            pos = emp.casual_details.position.title
        elif emp.job_order_details:
            pos = emp.job_order_details.position_title

        # Stage mapping
        if permit.status == 'Rejected':
            current_stage = 'Leave was rejected'
        elif permit.current_stage == 'HR':
            current_stage = 'With HR for review'
        elif permit.current_stage == 'Head':
            current_stage = 'Awaiting Department Head approval'
        elif permit.current_stage == 'Mayor':
            current_stage = 'Awaiting Mayor approval'
        elif permit.current_stage == 'Completed':
            current_stage = 'Leave process completed'
        else:
            current_stage = 'In Progress'

        # --- Credits Remaining (same logic as Mayor PDF) ---
        credits_remaining = "N/A"
        if emp and emp.credit_balance and permit.leave_detail:
            cb = emp.credit_balance
            leave_type = permit.leave_detail.leave_type.lower()

            if "vacation" in leave_type:
                credits_remaining = f"Vacation: {cb.vacation_remaining} credit(s)"
            elif "sick" in leave_type:
                credits_remaining = f"Sick: {cb.sick_remaining} credit(s)"

        # --- Paid Days (same logic as Mayor PDF) ---
        paid_days = "N/A"
        if permit.leave_detail:
            leave = permit.leave_detail
            leave_type = leave.leave_type.lower()

            if "vacation" in leave_type or "sick" in leave_type:
                working_days = 0
                paid_days_val = 0
                try:
                    working_days = int(leave.working_days or 0)
                except (ValueError, TypeError):
                    working_days = 0

                try:
                    paid_days_val = int(leave.paid_days or 0) if leave.paid_days is not None else None
                except (ValueError, TypeError):
                    paid_days_val = None

                if paid_days_val is not None:
                    if paid_days_val > 0:
                        unpaid = max(working_days - paid_days_val, 0)
                        paid_days = f"{paid_days_val} day(s) Paid"
                        if unpaid > 0:
                            paid_days += f" / {unpaid} Unpaid"
                    else:
                        paid_days = "Pending Approval"
                else:
                    requested_days = working_days
                    if emp and emp.credit_balance:
                        cb = emp.credit_balance
                        if "vacation" in leave_type:
                            paid = min(requested_days, cb.vacation_remaining)
                        elif "sick" in leave_type:
                            paid = min(requested_days, cb.sick_remaining)
                        else:
                            paid = 0
                        paid_days = f"Est. {paid} day(s)"
                    else:
                        paid_days = "N/A"
            else:
                paid_days = "Not Applicable"

        # Prepare row data
        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': pos,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'leave_type': (
                f"{permit.leave_detail.leave_type if permit.leave_detail else 'N/A'}" +
                (f"\n{permit.leave_detail.date_from.strftime('%b %d, %Y')} -"
                 f"{permit.leave_detail.date_to.strftime('%b %d, %Y')}"
                 if permit.leave_detail and permit.leave_detail.date_from and permit.leave_detail.date_to else '')
            ),
            'credits_remaining': credits_remaining,
            'paid_days': paid_days,
            'status': permit.status or '-',
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
        }

        pdf.add_leave_row(data)

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"HR_Leave_Application_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )




# REPORT: HR DEPARTMETN  TRAVEL ORDER (Department Only)
@app.route('/print_head_travel_summary')
@login_required
def print_head_travel_summary():
    # Department name of current user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query travel orders for this department, excluding Cancelled
    travel_orders = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Travel Order")
        .filter(Employee.department_id == current_user.employee.department_id)
        .filter(PermitRequest.status != "Cancelled")
        .all()
    )

    # Define clean status order
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']
    status_priority = {status: idx for idx, status in enumerate(status_order, start=1)}

    # Function to normalize statuses
    def get_status_priority(permit):
        if permit.status in ['HR', 'Head', 'Mayor']:
            return status_priority.get('Pending', 99)  # treat as pending/in progress
        elif permit.status in ['Completed', 'Released', 'Approved']:
            return status_priority.get('Approved', 99)
        return status_priority.get(permit.status, 99)

    # Sort permits
    travel_orders.sort(key=lambda p: (
        get_status_priority(p),
        p.date_requested or datetime.min
    ))

    # PDF setup
    pdf = HRTravelOrderPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Travel Orders', ln=True)
    pdf.draw_table_headers()

    row_idx = 1
    for permit in travel_orders:
        emp = permit.employee
        if not emp:
            continue

        # Determine position
        position = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title

        # Stage mapping
        if permit.status == 'Rejected':
            current_stage = 'Travel was rejected'
        elif permit.current_stage == 'HR':
            current_stage = 'With HR for review'
        elif permit.current_stage == 'Head':
            current_stage = 'Awaiting Department Head approval'
        elif permit.current_stage == 'Mayor':
            current_stage = 'Awaiting Mayor approval'
        elif permit.current_stage in ['Completed', 'Released', 'Approved']:
            current_stage = 'Travel process completed'
        else:
            current_stage = 'In Progress'

        # Build row data
        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': position,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'destination': permit.travel_detail.destination if permit.travel_detail else 'N/A',
            'status': permit.status or '-',
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
        }

        pdf.add_travel_row(row_idx, data)
        row_idx += 1

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Order_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )

# REPORT: HR DEPARTMETN  CLEARANCE FORM
@app.route('/print_head_clearance_summary')
@login_required
def print_head_clearance_summary():
    # Kunin department ng HR user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query clearance permits para lang sa department na ito
    permits = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Clearance Form")
        .filter(Employee.department_id == current_user.employee.department_id)
        .all()
    )

    # Status order (hindi kasama Cancelled)
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']

    pdf = HRClearanceSummaryPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Clearance Form', ln=True)
    pdf.draw_table_headers()

    row_idx = 1

    for status in status_order:
        # Filter permits explicitly for this status
        filtered_permits = [
            p for p in permits if (
                (p.status == 'Completed' and status == 'Completed') or
                (p.status == 'Pending' and status == 'Pending') or
                (p.status == 'Approved' and status == 'Approved') or
                (p.status == 'Rejected' and status == 'Rejected') or
                # lahat ng iba (HR, Head, Mayor) ay papasok as Pending/In Progress dati
                (p.status not in ['Completed', 'Cancelled', 'Rejected', 'Approved'] and status == 'Pending')
            )
        ]

        for permit in filtered_permits:
            emp = permit.employee
            if not emp:
                continue

            # Position
            position = "N/A"
            if emp.permanent_details and emp.permanent_details.position:
                position = emp.permanent_details.position.title
            elif emp.casual_details and emp.casual_details.position:
                position = emp.casual_details.position.title
            elif emp.job_order_details:
                position = emp.job_order_details.position_title

            # Purpose
            if permit.clearance_detail:
                if permit.clearance_detail.clearance_purpose == "Other":
                    purpose = f"Other - {permit.clearance_detail.other_purpose or 'N/A'}"
                else:
                    purpose = permit.clearance_detail.clearance_purpose
            else:
                purpose = "N/A"

            # Stage mapping
            if permit.status == 'Rejected':
                current_stage = 'Clearance was rejected'
            elif permit.current_stage == 'HR':
                current_stage = 'With HR for review'
            elif permit.current_stage == 'Head':
                current_stage = 'Awaiting Department Head approval'
            elif permit.current_stage == 'Mayor':
                current_stage = 'Awaiting Mayor approval'
            elif permit.current_stage == 'Completed':
                current_stage = 'Process completed'
            else:
                current_stage = '-'

            data = {
                'department': emp.department.name if emp.department else 'N/A',
                'position': position,
                'first_name': emp.first_name or '',
                'middle_name': emp.middle_name or '',
                'last_name': emp.last_name or '',
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'purpose': purpose,
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',
            }

            pdf.add_clearance_row(row_idx, data)
            row_idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Clearance_Form_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )


# REPORT: dept. head HR LEAVE SUMMARY PDF
@app.route('/print_deptHR_leave_summary')
@login_required
def print_deptHR_leave_summary():

    # Get department of current user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query leave permits for the department, excluding Cancelled
    permits = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Leave")
        .filter(Employee.department_id == current_user.employee.department_id)
        .filter(PermitRequest.status != "Cancelled")
        .all()
    )

    # --- Custom Sorting Order ---
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']
    status_priority = {status: idx for idx, status in enumerate(status_order, start=1)}

    def get_status_priority(permit):
        if permit.status in ['HR', 'Head', 'Mayor']:
            return status_priority.get('Pending', 99)  # Treat as in-progress/pending
        return status_priority.get(permit.status, 99)

    permits.sort(key=lambda p: (
        get_status_priority(p),
        p.date_requested or datetime.min
    ))

    # PDF Setup
    pdf = LeaveApplicationhHeadPDF(department_name=department_name)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.draw_table_headers()

    # Fill rows
    for permit in permits:
        emp = permit.employee
        if not emp:
            continue

        # Position
        pos = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            pos = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            pos = emp.casual_details.position.title
        elif emp.job_order_details:
            pos = emp.job_order_details.position_title

        # Stage mapping
        if permit.status == 'Rejected':
            current_stage = 'Leave was rejected'
        elif permit.current_stage == 'HR':
            current_stage = 'With HR for review'
        elif permit.current_stage == 'Head':
            current_stage = 'Awaiting Department Head approval'
        elif permit.current_stage == 'Mayor':
            current_stage = 'Awaiting Mayor approval'
        elif permit.current_stage == 'Completed':
            current_stage = 'Leave process completed'
        else:
            current_stage = 'In Progress'

        # --- Credits Remaining (same logic as Mayor PDF) ---
        credits_remaining = "N/A"
        if emp and emp.credit_balance and permit.leave_detail:
            cb = emp.credit_balance
            leave_type = permit.leave_detail.leave_type.lower()

            if "vacation" in leave_type:
                credits_remaining = f"Vacation: {cb.vacation_remaining} credit(s)"
            elif "sick" in leave_type:
                credits_remaining = f"Sick: {cb.sick_remaining} credit(s)"

        # --- Paid Days (same logic as Mayor PDF) ---
        paid_days = "N/A"
        if permit.leave_detail:
            leave = permit.leave_detail
            leave_type = leave.leave_type.lower()

            if "vacation" in leave_type or "sick" in leave_type:
                working_days = 0
                paid_days_val = 0
                try:
                    working_days = int(leave.working_days or 0)
                except (ValueError, TypeError):
                    working_days = 0

                try:
                    paid_days_val = int(leave.paid_days or 0) if leave.paid_days is not None else None
                except (ValueError, TypeError):
                    paid_days_val = None

                if paid_days_val is not None:
                    if paid_days_val > 0:
                        unpaid = max(working_days - paid_days_val, 0)
                        paid_days = f"{paid_days_val} day(s) Paid"
                        if unpaid > 0:
                            paid_days += f" / {unpaid} Unpaid"
                    else:
                        paid_days = "Pending Approval"
                else:
                    requested_days = working_days
                    if emp and emp.credit_balance:
                        cb = emp.credit_balance
                        if "vacation" in leave_type:
                            paid = min(requested_days, cb.vacation_remaining)
                        elif "sick" in leave_type:
                            paid = min(requested_days, cb.sick_remaining)
                        else:
                            paid = 0
                        paid_days = f"Est. {paid} day(s)"
                    else:
                        paid_days = "N/A"
            else:
                paid_days = "Not Applicable"

        # Prepare row data
        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': pos,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'leave_type': (
                f"{permit.leave_detail.leave_type if permit.leave_detail else 'N/A'}" +
                (f"\n{permit.leave_detail.date_from.strftime('%b %d, %Y')} -"
                 f"{permit.leave_detail.date_to.strftime('%b %d, %Y')}"
                 if permit.leave_detail and permit.leave_detail.date_from and permit.leave_detail.date_to else '')
            ),
            'credits_remaining': credits_remaining,
            'paid_days': paid_days,
            'status': permit.status or '-',
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
        }

        pdf.add_leave_row(data)

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"HR_Leave_Application_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )



# REPORT: dept. head TRAVEL ORDER (Department Only)
@app.route('/print_deptHEAD_travel_summary')
@login_required
def print_deptHEAD_travel_summary():
    # Department name of current user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query travel orders for this department, excluding Cancelled
    travel_orders = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Travel Order")
        .filter(Employee.department_id == current_user.employee.department_id)
        .filter(PermitRequest.status != "Cancelled")
        .all()
    )

    # Define clean status order
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']
    status_priority = {status: idx for idx, status in enumerate(status_order, start=1)}

    # Function to normalize statuses
    def get_status_priority(permit):
        if permit.status in ['HR', 'Head', 'Mayor']:
            return status_priority.get('Pending', 99)  # treat as pending/in progress
        elif permit.status in ['Completed', 'Released', 'Approved']:
            return status_priority.get('Approved', 99)
        return status_priority.get(permit.status, 99)

    # Sort permits
    travel_orders.sort(key=lambda p: (
        get_status_priority(p),
        p.date_requested or datetime.min
    ))

    # PDF setup
    pdf = TravelOrderHeadPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Travel Orders', ln=True)
    pdf.draw_table_headers()

    row_idx = 1
    for permit in travel_orders:
        emp = permit.employee
        if not emp:
            continue

        # Determine position
        position = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title

        # Stage mapping
        if permit.status == 'Rejected':
            current_stage = 'Travel was rejected'
        elif permit.current_stage == 'HR':
            current_stage = 'With HR for review'
        elif permit.current_stage == 'Head':
            current_stage = 'Awaiting Department Head approval'
        elif permit.current_stage == 'Mayor':
            current_stage = 'Awaiting Mayor approval'
        elif permit.current_stage in ['Completed', 'Released', 'Approved']:
            current_stage = 'Travel process completed'
        else:
            current_stage = 'In Progress'

        # Build row data
        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': position,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'destination': permit.travel_detail.destination if permit.travel_detail else 'N/A',
            'status': permit.status or '-',
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
        }

        pdf.add_travel_row(row_idx, data)
        row_idx += 1

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Order_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )

# REPORT: dept. head CLEARANCE FORM
@app.route('/print_depthead_clearance_summary')
@login_required
def print_deptheas_clearance_summary():
    # Kunin department ng HR user
    department_name = (
        current_user.employee.department.name
        if current_user.employee and current_user.employee.department
        else 'No Department'
    )

    # Query clearance permits para lang sa department na ito
    permits = (
        PermitRequest.query
        .join(Employee)
        .filter(PermitRequest.permit_type == "Clearance Form")
        .filter(Employee.department_id == current_user.employee.department_id)
        .all()
    )

    # Status order (hindi kasama Cancelled)
    status_order = ['Completed', 'Pending', 'In Progress', 'Rejected']

    pdf = ClearanceSummaryheadPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Clearance Form', ln=True)
    pdf.draw_table_headers()

    row_idx = 1

    for status in status_order:
        # Filter permits explicitly for this status
        filtered_permits = [
            p for p in permits if (
                (p.status == 'Completed' and status == 'Completed') or
                (p.status == 'Pending' and status == 'Pending') or
                (p.status == 'Approved' and status == 'Approved') or
                (p.status == 'Rejected' and status == 'Rejected') or
                # lahat ng iba (HR, Head, Mayor) ay papasok as Pending/In Progress dati
                (p.status not in ['Completed', 'Cancelled', 'Rejected', 'Approved'] and status == 'Pending')
            )
        ]

        for permit in filtered_permits:
            emp = permit.employee
            if not emp:
                continue

            # Position
            position = "N/A"
            if emp.permanent_details and emp.permanent_details.position:
                position = emp.permanent_details.position.title
            elif emp.casual_details and emp.casual_details.position:
                position = emp.casual_details.position.title
            elif emp.job_order_details:
                position = emp.job_order_details.position_title

            # Purpose
            if permit.clearance_detail:
                if permit.clearance_detail.clearance_purpose == "Other":
                    purpose = f"Other - {permit.clearance_detail.other_purpose or 'N/A'}"
                else:
                    purpose = permit.clearance_detail.clearance_purpose
            else:
                purpose = "N/A"

            # Stage mapping
            if permit.status == 'Rejected':
                current_stage = 'Clearance was rejected'
            elif permit.current_stage == 'HR':
                current_stage = 'With HR for review'
            elif permit.current_stage == 'Head':
                current_stage = 'Awaiting Department Head approval'
            elif permit.current_stage == 'Mayor':
                current_stage = 'Awaiting Mayor approval'
            elif permit.current_stage == 'Completed':
                current_stage = 'Process completed'
            else:
                current_stage = '-'

            data = {
                'department': emp.department.name if emp.department else 'N/A',
                'position': position,
                'first_name': emp.first_name or '',
                'middle_name': emp.middle_name or '',
                'last_name': emp.last_name or '',
                'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
                'purpose': purpose,
                'status': permit.status or '-',
                'current_stage': current_stage,
                'remarks': permit.hr_remarks or '-',
            }

            pdf.add_clearance_row(row_idx, data)
            row_idx += 1

    # --- Output PDF ---
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Clearance_Form_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )


# REPORT: mayor LEAVE APPLICATION
# REPORT: mayor LEAVE APPLICATION
@app.route('/print_mayor_leave_summary')
@login_required
def print_mayor_leave_summary():
    department_name = "All Departments"

    permits = (
        PermitRequest.query
        .filter(PermitRequest.permit_type == "Leave")
        .filter(PermitRequest.current_stage.in_(["Mayor", "Completed", "Approved"]))
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    pdf = MayorLeaveApplicationPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Leave Applications', ln=True)
    pdf.draw_table_headers()

    for permit in permits:
        emp = permit.employee
        if not emp:
            continue

        # Position
        position = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title

        # Stage mapping
        if permit.current_stage == "Mayor":
            current_stage = "Awaiting Mayor approval"
        elif permit.current_stage in ["Completed", "Approved"]:
            current_stage = "Leave process completed"
        else:
            current_stage = "-"

        # Normalize status for completed
        status = permit.status or '-'
        if permit.current_stage in ["Completed", "Approved"]:
            status = "Completed"

        # --- Credits Remaining ---
        credits_remaining = "N/A"
        if emp and emp.credit_balance and permit.leave_detail:
            cb = emp.credit_balance
            leave_type = permit.leave_detail.leave_type.lower()

            if "vacation" in leave_type:
                credits_remaining = f"Vacation: {cb.vacation_remaining} credit(s)"
            elif "sick" in leave_type:
                credits_remaining = f"Sick: {cb.sick_remaining} credit(s)"

        # --- Paid Days ---
        paid_days = "N/A"
        if permit.leave_detail:
            leave = permit.leave_detail
            leave_type = leave.leave_type.lower()

            if "vacation" in leave_type or "sick" in leave_type:
                # Safe conversion to int
                working_days = 0
                paid_days_val = 0
                try:
                    working_days = int(leave.working_days or 0)
                except (ValueError, TypeError):
                    working_days = 0

                try:
                    paid_days_val = int(leave.paid_days or 0) if leave.paid_days is not None else None
                except (ValueError, TypeError):
                    paid_days_val = None

                if paid_days_val is not None:
                    if paid_days_val > 0:
                        unpaid = max(working_days - paid_days_val, 0)
                        paid_days = f"{paid_days_val} day(s) Paid"
                        if unpaid > 0:
                            paid_days += f" / {unpaid} Unpaid"
                    else:
                        paid_days = "Pending Approval"
                else:
                    # Estimated if not yet approved
                    requested_days = working_days
                    if emp and emp.credit_balance:
                        cb = emp.credit_balance
                        if "vacation" in leave_type:
                            paid = min(requested_days, cb.vacation_remaining)
                        elif "sick" in leave_type:
                            paid = min(requested_days, cb.sick_remaining)
                        else:
                            paid = 0
                        paid_days = f"Est. {paid} day(s)"
                    else:
                        paid_days = "N/A"
            else:
                paid_days = "Not Applicable"

        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': position,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'leave_type': permit.leave_detail.leave_type if permit.leave_detail else 'N/A',
            'credits_remaining': credits_remaining,
            'paid_days': paid_days,
            'status': status,
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
        }

        pdf.add_leave_row(data)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Leave_Application_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False, download_name=filename)

# REPORT: Mayor Travel Orders (All Departments, grouped by status)
@app.route('/print_mayor_travel_summary')
@login_required
def print_mayor_travel_summary():
    department_name = "All Departments"

    # Fetch all travel orders that are relevant
    permits = (
        PermitRequest.query
        .filter(PermitRequest.permit_type == "Travel Order")
        .filter(
            (PermitRequest.current_stage.in_(["Mayor", "Completed", "Approved"])) |
            (PermitRequest.status == "Rejected")
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Attach latest rejection info
    for permit in permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # Group permits in the desired order
    completed = []
    in_progress = []
    pending = []
    rejected = []

    for permit in permits:
        if permit.status == "Rejected":
            rejected.append(permit)
        elif permit.current_stage in ["Completed", "Released", "Approved"]:
            completed.append(permit)
        elif permit.current_stage == "Mayor":
            in_progress.append(permit)
        else:
            pending.append(permit)

    # Combine them in order
    permits_ordered = completed + in_progress + pending + rejected

    pdf = MayorTravelOrderPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Travel Orders', ln=True)
    pdf.draw_table_headers()

    # Add rows
    for idx, permit in enumerate(permits_ordered, start=1):
        emp = permit.employee
        if not emp:
            continue

        # Determine position
        position = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title

        # Stage mapping and status
        if permit.status == "Rejected":
            current_stage = "Travel was rejected"
            status = "Rejected"
        elif permit.current_stage == "Mayor":
            current_stage = "Awaiting Mayor approval"
            status = permit.status or "In Progress"
        elif permit.current_stage in ["Completed", "Released", "Approved"]:
            current_stage = "Travel Order process completed"
            status = "Completed"
        else:
            current_stage = "-"
            status = permit.status or "Pending"

        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': position,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'destination': permit.travel_detail.destination if permit.travel_detail else 'N/A',
            'status': status,
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
            'rejected_by': permit.rejected_by or '-',
            'rejected_remarks': permit.rejected_remarks or '-',
        }

        pdf.add_travel_row(idx, data)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Travel_Order_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False, download_name=filename)



# REPORT: mayor CLEARANCE FORM
# REPORT: Mayor Clearance Form (All Departments, grouped by status)
@app.route('/print_mayor_clerance_summary')
@login_required
def print_mayor_clerance_summary():
    department_name = "All Departments"

    # Fetch all Clearance Forms that are relevant (Mayor / Completed / Approved / Rejected)
    permits = (
        PermitRequest.query
        .filter(PermitRequest.permit_type == "Clearance Form")
        .filter(
            (PermitRequest.current_stage.in_(["Mayor", "Completed", "Approved"])) |
            (PermitRequest.status == "Rejected")
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Attach latest rejection info
    for permit in permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # Group permits in desired order: Completed → In Progress → Pending → Rejected
    completed = []
    in_progress = []
    pending = []
    rejected = []

    for permit in permits:
        if permit.status == "Rejected":
            rejected.append(permit)
        elif permit.current_stage in ["Completed", "Released", "Approved"]:
            completed.append(permit)
        elif permit.current_stage == "Mayor":
            in_progress.append(permit)
        else:
            pending.append(permit)

    permits_ordered = completed + in_progress + pending + rejected

    pdf = MayorClearanceSummaryPDF(department_name=department_name)
    pdf.add_page()
    pdf.alias_nb_pages()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, 'Clearance Form Summary', ln=True)
    pdf.draw_table_headers()

    # Add rows
    row_idx = 1
    for permit in permits_ordered:
        emp = permit.employee
        if not emp:
            continue

        # Determine position
        position = "N/A"
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title

        # Purpose
        if permit.clearance_detail:
            if permit.clearance_detail.clearance_purpose == "Other":
                purpose = f"Other - {permit.clearance_detail.other_purpose or 'N/A'}"
            else:
                purpose = permit.clearance_detail.clearance_purpose
        else:
            purpose = "N/A"

        # Stage mapping and status
        if permit.status == "Rejected":
            current_stage = "Clearance was rejected"
            status = "Rejected"
        elif permit.current_stage == "Mayor":
            current_stage = "Awaiting Mayor approval"
            status = "In Progress"
        elif permit.current_stage in ["Completed", "Released", "Approved"]:
            current_stage = "Clearance process completed"
            status = "Completed"
        else:
            current_stage = "-"
            status = permit.status or "Pending"

        data = {
            'department': emp.department.name if emp.department else 'N/A',
            'position': position,
            'first_name': emp.first_name or '',
            'middle_name': emp.middle_name or '',
            'last_name': emp.last_name or '',
            'date_requested': permit.date_requested.strftime('%b %d, %Y') if permit.date_requested else 'N/A',
            'purpose': purpose,
            'status': status,
            'current_stage': current_stage,
            'remarks': permit.hr_remarks or '-',
            'rejected_by': permit.rejected_by or '-',
            'rejected_remarks': permit.rejected_remarks or '-',
        }

        pdf.add_clearance_row(row_idx, data)
        row_idx += 1

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Clearance_Form_Summary_{department_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False, download_name=filename)





#LEAVE CREDIT REPORTprint
@app.route('/print_credit_summary')
@login_required
def print_credit_summary():
    pdf = EmployeeCreditPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Step 1: Get all departments
    departments = Department.query.order_by(Department.name).all()

    # Step 1a: Force "Office of the Municipal Mayor" to appear first
    departments.sort(key=lambda d: (0 if d.name == "Office of the Municipal Mayor" else 1, d.name))

    # Step 2: Loop through departments and pass employees
    for dept in departments:
        employees = Employee.query.filter_by(department_id=dept.id).all()
        if not employees:
            continue

        # Format employee data
        formatted_employees = []
        for emp in employees:
            credit = emp.credit_balance
            emp_data = {
                'first_name': emp.first_name,
                'last_name': emp.last_name,
                'middle_name': emp.middle_name or '',
                'credit_balance': {
                    'vacation_earned': credit.vacation_earned if credit else 0.0,
                    'vacation_used': credit.vacation_used if credit else 0.0,
                    'vacation_remaining': credit.vacation_remaining if credit else 0.0,
                    'sick_earned': credit.sick_earned if credit else 0.0,
                    'sick_used': credit.sick_used if credit else 0.0,
                    'sick_remaining': credit.sick_remaining if credit else 0.0,
                },
                'permanent_details': emp.permanent_details,
                'casual_details': emp.casual_details,
                'job_order_details': emp.job_order_details,
            }
            formatted_employees.append(emp_data)

        # Add the department section (with new PDF layout)
        pdf.add_department_section(dept.name, formatted_employees)

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Employee_Credit_Summary_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False, download_name=filename)





#CREDIT HISTORY REPORTprint 
@app.route('/print_credit_history')
@login_required
def print_credit_history():
    departments = Department.query.order_by(Department.name).all()
    credit_transactions_by_dept = {}

    # Step 2: Collect transactions grouped by department
    for dept in departments:
        employees = Employee.query.filter_by(department_id=dept.id).all()
        employee_ids = [e.id for e in employees]

        transactions = CreditTransaction.query.filter(
            CreditTransaction.employee_id.in_(employee_ids)
        ).order_by(CreditTransaction.timestamp.asc()).all()

        if transactions:
            credit_transactions_by_dept[dept.name] = transactions

    # Step 3: Initialize PDF
    pdf = EmployeeCreditHistoryPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Step 4: Loop through each department and add their transactions
    for dept_name, transactions in credit_transactions_by_dept.items():
        pdf.add_department_section(dept_name, transactions)

    # Step 5: Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Leave_Credit_Transactions_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False, download_name=filename)


# UserCredit
# PRINT LEAVE CREDIT SUMMARY REPORT (Current User Only)

@app.route('/user_credit_summary_print')
@login_required
@role_required('employee')
def user_credit_summary_print():
    emp = current_user.employee

    if not emp:
        flash("You are not linked to an employee record.", "warning")
        return redirect(url_for("EmployeeHome"))

    # Skip Job Order employees (no credits)
    if emp.job_order_details:
        flash("Job Order employees do not have credits.", "warning")
        return redirect(url_for("EmployeeHome"))

    # If casual employee, ensure assigned department is set
    if emp.casual_details and not emp.casual_details.assigned_department:
        flash("You are not assigned to any department.", "warning")
        return redirect(url_for("EmployeeHome"))

    # Department
    department = emp.department if emp.permanent_details else (
        emp.casual_details.assigned_department if emp.casual_details else None
    )

    # ---- CREDIT CALCULATION ----
    # Separate Vacation and Sick leave credits
    vacation_earned = sum(tx.amount for tx in emp.credit_transactions 
                          if tx.leave_type == "Vacation" and tx.action == "Earned")
    vacation_used = sum(tx.amount for tx in emp.credit_transactions 
                        if tx.leave_type == "Vacation" and tx.action == "Used")
    vacation_remaining = vacation_earned - vacation_used

    sick_earned = sum(tx.amount for tx in emp.credit_transactions 
                      if tx.leave_type == "Sick" and tx.action == "Earned")
    sick_used = sum(tx.amount for tx in emp.credit_transactions 
                    if tx.leave_type == "Sick" and tx.action == "Used")
    sick_remaining = sick_earned - sick_used

    # ---- FORMAT EMPLOYEE DATA ----
    emp_data = {
        'first_name': emp.first_name,
        'last_name': emp.last_name,
        'middle_name': emp.middle_name or '',
        'credit_balance': {
            'vacation_earned': vacation_earned,
            'vacation_used': vacation_used,
            'vacation_remaining': vacation_remaining,
            'sick_earned': sick_earned,
            'sick_used': sick_used,
            'sick_remaining': sick_remaining,
        },
        'permanent_details': emp.permanent_details,
        'casual_details': emp.casual_details,
        'job_order_details': emp.job_order_details,
    }

    # ---- BUILD PDF ----
    pdf = UserCreditPDF()
    pdf.dept_name = department.name if department else "No Department"
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Add single employee row
    pdf.add_employee_row(emp_data)

    # ---- OUTPUT PDF ----
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"User_Credit_Summary_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )

# PRINT CREDIT HISTORY SUMMARY REPORT (Current User Only)

@app.route('/user_credit_history_print')
@login_required
@role_required('employee')
def user_credit_history_print():
    emp = current_user.employee

    if not emp:
        flash("You are not linked to an employee record.", "warning")
        return redirect(url_for("EmployeeHome"))

    # Skip Job Order employees (no leave credits)
    if emp.job_order_details:
        flash("Job Order employees do not have credits.", "warning")
        return redirect(url_for("EmployeeHome"))

    # If casual employee, ensure assigned department is set
    if emp.casual_details and not emp.casual_details.assigned_department:
        flash("You are not assigned to any department.", "warning")
        return redirect(url_for("EmployeeHome"))

    # Department name
    department = emp.department if emp.permanent_details else (
        emp.casual_details.assigned_department if emp.casual_details else None
    )

    # Transactions (latest first)
    transactions = sorted(emp.credit_transactions, key=lambda tx: tx.timestamp, reverse=True)

    # ---- BUILD PDF ----
    pdf = UserCreditHistoryPDF()
    pdf.dept_name = department.name if department else "No Department"
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Add all transactions for current user
    for tx in transactions:
        pdf.check_page_break()
        pdf.add_transaction_row(tx)

    # ---- OUTPUT PDF ----
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"User_Credit_History_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename
    )


# HeadCredit
# PRINT CREDIT HISTORY SUMMARY REPORT (Current head)

@app.route('/head_credit_history_print')
@login_required
@role_required('head')
def head_credit_history_print():
    # ✅ Step 1: Get logged-in user's department
    if not current_user.employee or not current_user.employee.department:
        flash("No department assigned to your account.", "danger")
        return redirect(request.referrer or url_for('home'))

    department = current_user.employee.department

    # ✅ Step 2: Collect transactions for this department only
    employees = Employee.query.filter_by(department_id=department.id).all()
    employee_ids = [e.id for e in employees]

    transactions = CreditTransaction.query.filter(
        CreditTransaction.employee_id.in_(employee_ids)
    ).order_by(CreditTransaction.timestamp.asc()).all()

    if not transactions:
        flash("No credit transactions found for your department.", "warning")
        return redirect(request.referrer or url_for('home'))

    # ✅ Step 3: Initialize PDF
    pdf = HeadCreditHistoryPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ✅ Step 4: Add only the current department's transactions
    pdf.add_department_section(department.name, transactions)

    # ✅ Step 5: Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Head_Credit_History_{department.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False, download_name=filename)



# PRINT LEAVE CREDIT SUMMARY REPORT (Current head)
@app.route('/head_credit_summary_print')
@login_required
@role_required('head')
def head_credit_summary_print():
    pdf = HeadCreditPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ✅ Step 1: Get logged-in user's department
    if not current_user.employee or not current_user.employee.department:
        flash("No department assigned to your account.", "danger")
        return redirect(request.referrer or url_for('home'))

    department = current_user.employee.department

    # ✅ Step 2: Get employees in this department only
    employees = Employee.query.filter_by(department_id=department.id).all()
    if not employees:
        flash("No employees found in your department.", "warning")
        return redirect(request.referrer or url_for('home'))

    # ✅ Step 3: Format employee data
    formatted_employees = []
    for emp in employees:
        credit = emp.credit_balance
        emp_data = {
            'first_name': emp.first_name,
            'last_name': emp.last_name,
            'middle_name': emp.middle_name or '',
            'credit_balance': {
                'vacation_earned': credit.vacation_earned if credit else 0.0,
                'vacation_used': credit.vacation_used if credit else 0.0,
                'vacation_remaining': credit.vacation_remaining if credit else 0.0,
                'sick_earned': credit.sick_earned if credit else 0.0,
                'sick_used': credit.sick_used if credit else 0.0,
                'sick_remaining': credit.sick_remaining if credit else 0.0,
            },
            'permanent_details': emp.permanent_details,
            'casual_details': emp.casual_details,
            'job_order_details': emp.job_order_details,
        }
        formatted_employees.append(emp_data)

    # ✅ Step 4: Add the department section
    pdf.add_department_section(department.name, formatted_employees)

    # ✅ Step 5: Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"Heada_Credit_Summary_{department.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_output, mimetype='application/pdf', as_attachment=False, download_name=filename)





#CASUAL TERMINATEDprint
@app.route('/print_terminated_casualjob')
@login_required
@role_required('hr')
def print_terminated_casualjob():
    pdf = HeadTerminatedCasualPDF(department_name="All Departments",)
    pdf.add_page()
    pdf.draw_table_headers()

    terminated_employees = Employee.query.filter(
        Employee.status.ilike('Casual'),
        Employee.employment_status.ilike('inactive')
    ).all()

    row_counter = 0
    display_index = 1

    for emp in terminated_employees:
        if emp.casual_details:
            if row_counter == 15:
                pdf.add_page()
                pdf.draw_table_headers()
                row_counter = 0
                display_index = 1

            pdf.add_employee_row(display_index, emp)
            row_counter += 1
            display_index += 1

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='terminated_casual_employees.pdf'
    )





#PERMANENT TERMINATEDprint 
@app.route('/print_terminated_permanent')
@login_required
@role_required('hr')
def print_terminated_permanent():
    pdf = HeadTerminatedPermanentPDF(department_name="All Departments")
    pdf.add_page()
    pdf.draw_table_headers()

    # ✅ Get employees who are not 'Casual' or 'Job Order' and are 'inactive'
    terminated_employees = Employee.query.filter(
        ~Employee.status.ilike('Casual'),
        ~Employee.status.ilike('Job Order'),
        Employee.employment_status.ilike('inactive')
    ).all()

    row_counter = 0
    display_index = 1

    for emp in terminated_employees:
        if emp.permanent_details:
            if row_counter == 15:
                pdf.add_page()
                pdf.draw_table_headers()
                row_counter = 0
                display_index = 1

            pdf.add_employee_row(display_index, emp)
            row_counter += 1
            display_index += 1

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name='terminated_permanent_employees.pdf'
    )

#JOB ORDER TERMINATEDprint 

@app.route('/print_terminated_joborder')
@login_required
@role_required('hr')
def print_terminated_joborder():
    pdf = HeadTerminatedJobOrderPDF(department_name="All Departments")
    pdf.add_page()
    pdf.draw_table_headers()

    terminated_employees = Employee.query.filter(
        Employee.status.ilike('Job Order'),
        Employee.employment_status.ilike('inactive')
    ).all()

    row_counter = 0
    display_index = 1

    for emp in terminated_employees:
        if emp.job_order_details:
            if row_counter == 15:
                pdf.add_page()
                pdf.draw_table_headers()
                row_counter = 0
                display_index = 1

            pdf.add_employee_row(display_index, emp)
            row_counter += 1
            display_index += 1

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False,
        download_name='terminated_joborder_employees.pdf'
    )




#IPCR HR REPORTprint
@app.route('/print_ipcr_dept')
@login_required
@role_required('hr')
def print_ipcr_dept():


    period_id = request.args.get('period_id', type=int)
    selected_period = EvaluationPeriod.query.get(period_id)

    if not selected_period:
        abort(404, "Selected evaluation period not found.")

    period_title = selected_period.name
    departments_data = []

    departments = Department.query.all()

    for dept in departments:
        # ✅ Get active permanent employees (excluding heads and electives)
        permanent_employees = Employee.query.filter(
            Employee.department_id == dept.id,
            Employee.employment_status == 'active',
            Employee.is_deleted == False,
            Employee.status.notin_(['Elective', 'E']),
            Employee.permanent_details.has(),
            ~Employee.permanent_details.has(
                PermanentEmployeeDetails.position.has(Position.title.ilike('%head%'))
            )
        ).all()

        # ✅ Get active casual employees assigned to the department (excluding heads and electives)
        casual_employees = Employee.query.join(CasualEmployeeDetails).filter(
            CasualEmployeeDetails.assigned_department_id == dept.id,
            Employee.employment_status == 'active',
            Employee.is_deleted == False,
            Employee.status.notin_(['Elective', 'E']),
            ~Employee.casual_details.has(
                CasualEmployeeDetails.position.has(Position.title.ilike('%head%'))
            )
        ).all()

        # ✅ Combine all employee IDs
        all_employees = permanent_employees + casual_employees
        employee_ids = [emp.id for emp in all_employees]

        ipcr_total = len(employee_ids)

        ipcrs = IPCR.query.filter(
            IPCR.employee_id.in_(employee_ids),
            IPCR.period_id == selected_period.id
        ).all()

        ipcr_submitted_count = sum(1 for ipcr in ipcrs if ipcr.submitted)
        ipcr_graded_count = sum(1 for ipcr in ipcrs if ipcr.submitted and ipcr.graded)

        departments_data.append({
            'division': dept.name,
            'ipcr_total': ipcr_total,
            'ipcr_submitted': ipcr_submitted_count,
            'ipcr_graded': ipcr_graded_count
        })

    # 📝 Generate PDF
    pdf = HeadDepartmentIPCRPDF(period_title=period_title)
    pdf.add_page()
    pdf.draw_table_headers()

    for i, dept_data in enumerate(departments_data, start=1):
        pdf.add_department_row(i, dept_data)

    # 📤 Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False
    )


#IPCR EMPLOYEE HRprint
@app.route('/print_employee_ipcr')
@login_required
@role_required('hr')  # or 'head' if needed
def print_employee_ipcr():
   

    department_name = request.args.get('department')
    period_id = request.args.get('period_id', type=int)

    # ✅ Fallback default
    if not department_name:
        department_name = "Office of the Municipal Mayor"

    if not period_id:
        abort(400, "Missing evaluation period ID.")

    department = Department.query.filter_by(name=department_name).first()
    selected_period = EvaluationPeriod.query.get(period_id)

    if not department or not selected_period:
        abort(404, "Invalid department or evaluation period.")

    # ✅ Permanent employees
    permanent_employees = Employee.query.filter(
        Employee.department_id == department.id,
        Employee.employment_status == 'active',
        Employee.is_deleted == False,
        Employee.status.notin_(['Elective', 'E']),
        Employee.permanent_details.has(),
        ~Employee.permanent_details.has(
            PermanentEmployeeDetails.position.has(Position.title.ilike('%head%'))
        )
    ).all()

    # ✅ Casual employees
    casual_employees = Employee.query.join(CasualEmployeeDetails).filter(
        CasualEmployeeDetails.assigned_department_id == department.id,
        Employee.employment_status == 'active',
        Employee.is_deleted == False,
        Employee.status.notin_(['Elective', 'E']),
        ~Employee.casual_details.has(
            CasualEmployeeDetails.position.has(Position.title.ilike('%head%'))
        )
    ).all()

    all_employees = permanent_employees + casual_employees

    # ✅ Create PDF
    pdf = HeadEmployeeIPCRPDF(
        department_name=department.name,
        period_title=selected_period.name
    )
    pdf.add_page()
    pdf.draw_table_headers()

    for index, emp in enumerate(all_employees, start=1):
        ipcr = IPCR.query.filter_by(employee_id=emp.id, period_id=selected_period.id).first()

        # ✅ Compute overall grade (like in the table)
        if ipcr:
            sections = EvaluationSection.query.filter_by(ipcr_id=ipcr.id).options(
                joinedload(EvaluationSection.section_items)
            ).all()

            summary_counts = {'Core': 0, 'Support': 0}
            average_ratings = {}
            weights = {'Core': 0.90, 'Support': 0.10}

            for section in sections:
                category = section.type
                if category in summary_counts:
                    for item in section.section_items:
                        if item.rating_a is not None:
                            summary_counts[category] += 1
                            average_ratings.setdefault(category, []).append(float(item.rating_a))

            total_weighted = 0
            category_count = 0

            for category in ['Core', 'Support']:
                ratings = average_ratings.get(category, [])
                if ratings:
                    avg = sum(ratings) / len(ratings)
                    weighted = avg * weights[category]
                    total_weighted += weighted
                    category_count += 1

            grade = round(total_weighted, 2) if category_count > 0 else None
        else:
            grade = None

        pdf.add_employee_row(index, emp, ipcr, grade)

    # ✅ Return PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    filename = f"ipcr_employee_details_{department.name.replace(' ', '_')}_{selected_period.name.replace(' ', '_')}.pdf"

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False
    )


# HR ISSUE SUMMARY REPORT print
#HR OPRN REPORT print
@app.route('/print_open_issue_summary')
@login_required
@role_required('hr')
def print_open_issue_summary():

    # ✅ Only get issues with status 'Open'
    issues = IssueReport.query.filter_by(status='Open').all()

    pdf = OpenIssueSummaryPDF()
    pdf.add_page()
    pdf.draw_table_headers()

    for i, issue in enumerate(issues, 1):
        pdf.add_issue_row(i, issue)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False
    )


#HR IN PROCESSprint 
@app.route('/print_inprogress_issues')
@login_required
@role_required('hr')
def print_inprogress_issues():

    issues = IssueReport.query.filter_by(status='In Progress').order_by(IssueReport.created_at.desc()).all()

    pdf = InProgressIssueSummaryPDF()
    pdf.add_page()
    pdf.draw_table_headers()

    for idx, issue in enumerate(issues, start=1):
        pdf.add_issue_row(idx, issue)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)


    return send_file(
       pdf_output,
        mimetype='application/pdf',
        as_attachment=False # ✅ force download
    )

#HR ISSUE RESOLVE print
@app.route('/print_resolved_issues')
@login_required
@role_required('hr')
def print_resolved_issues():
   
    issues = IssueReport.query.filter_by(status='Resolved').order_by(IssueReport.created_at.desc()).all()

    pdf = ResolvedIssueSummaryPDF()
    pdf.add_page()
    pdf.draw_table_headers()

    for idx, issue in enumerate(issues, start=1):
        pdf.add_issue_row(idx, issue)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)


    return send_file(
       pdf_output,
        mimetype='application/pdf',
        as_attachment=False # ✅ force download
    )


##employee ipcr record print
@app.route('/print_ipcr_user_summary')
@login_required
def print_ipcr_user_summary():
    employee_id = request.args.get('employee_id', type=int)
    if not employee_id:
        return "Bad Request\nMissing employee_id parameter", 400

    ipcrs = IPCR.query.filter_by(employee_id=employee_id).order_by(IPCR.period_id.desc()).all()
    
    if not ipcrs:
        return "No IPCR records found for this employee.", 404

    # Use only this correct instantiation
    pdf = IPCRSummaryPDF(department_name=current_user.employee.department.name)
    pdf.add_page()
    pdf.draw_table_headers()

    for ipcr in ipcrs:
        pdf.add_ipcr_row(ipcr)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False
    )

@app.route('/print_head_ipcr_period_summary')
@login_required
def print_head_ipcr_period_summary():
    from flask import send_file
    import io

    employees = current_user.employee.department.employees
    employee_ids = [emp.id for emp in employees]
    total_employees = len(employee_ids)

    if total_employees == 0:
        return "No employees found in your department.", 404

    periods = EvaluationPeriod.query.order_by(EvaluationPeriod.start_date.desc()).all()
    if not periods:
        return "No evaluation periods found.", 404

    # ✅ Create PDF with department name
    department_name = current_user.employee.department.name
    pdf = HeadIPCRPeriodSummaryPDF(department_name=department_name)
    pdf.draw_table_headers()

    for period in periods:
        ipcrs = [ipcr for ipcr in period.ipcrs if ipcr.employee_id in employee_ids]
        pdf.add_period_row(period, ipcrs, total_employees)

    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=False
    )


# dept head ipcr emplloyee 
@app.route('/print_headdept_ipcr_employee')
@login_required
def print_headdept_ipcr_employee():
    # Get department of logged-in user
    department = current_user.employee.department
    if not department:
        return "You are not assigned to any department.", 404

    # Only active Permanent and Casual employees, excluding Heads and deleted ones
    employees = [
        emp for emp in department.employees
        if (
            (emp.permanent_details or emp.casual_details)
            and not emp.is_department_head
            and emp.employment_status == 'active'
            and not emp.is_deleted
        )
    ]
    if not employees:
        return "No active Permanent or Casual employees found in your department.", 404

    # Get selected evaluation period from query parameters
    period_id = request.args.get('period_filter', type=int)
    if not period_id:
        return "No evaluation period selected.", 400

    selected_period = EvaluationPeriod.query.get(period_id)
    if not selected_period:
        return "Selected evaluation period not found.", 404

    # Create PDF
    pdf = HeadDeptIPCREmployeePDF(department_name=department.name)
    pdf.draw_table_headers()

    # Loop through employees once, only for selected period
    for emp in employees:
        ipcr = next((i for i in selected_period.ipcrs if i.employee_id == emp.id), None)
        pdf.add_employee_row(emp, ipcr)

    # Output PDF
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        download_name=f'{department.name}_{selected_period.name}_ipcr_status.pdf',
        as_attachment=False
    )



# end permit print

 
@app.route('/hr/Performance/Record', methods=['GET', 'POST'])
@login_required
@role_required('hr')
def EmployeeIPCRRecordHR():
    ipcrs = IPCR.query.filter_by(employee_id=current_user.employee.id).order_by(IPCR.id.desc()).all()

    return render_template('superAdmin/IPCRRecordHR.html', title="IPCR Record", ipcrs=ipcrs)

# newhrissue
@app.route("/HR/Issue", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def HRIssue():
    # Queries without pagination
    open_issues = IssueReport.query.filter_by(status='Open') \
                    .order_by(IssueReport.created_at.desc()) \
                    .all()

    in_progress_issues = IssueReport.query.filter_by(status='In Progress') \
                        .order_by(IssueReport.created_at.desc()) \
                        .all()

    resolved_issues = IssueReport.query.filter_by(status='Resolved') \
                      .order_by(IssueReport.created_at.desc()) \
                      .all()

    # Totals
    total_open = len(open_issues)
    total_in_progress = len(in_progress_issues)
    total_resolved = len(resolved_issues)

    departments = Department.query.order_by(Department.name).all()

    return render_template(
        'superAdmin/Issues.html',
        title="Manage Issues",
        open_issues=open_issues,
        in_progress_issues=in_progress_issues,
        resolved_issues=resolved_issues,
        total_open=total_open,
        total_in_progress=total_in_progress,
        total_resolved=total_resolved,
        departments=departments
    )



@app.route("/HR/Report/Issue")
@login_required
@role_required('hr')
def HrIssueReport():
    page = request.args.get('page', 1, type=int)
    per_page = 13
    search = request.args.get('search', '').strip()

    # Start base query: only reports created by current user
    query = IssueReport.query.filter_by(reporter_user_id=current_user.id)

    if search:
        like_pattern = f"%{search}%"

        # Safe joins
        query = query.join(Users, IssueReport.reported_user_id == Users.id)\
                     .outerjoin(Employee, Users.employee_id == Employee.id)

        # Add filter
        query = query.filter(
            or_(
                IssueReport.title.ilike(like_pattern),
                IssueReport.description.ilike(like_pattern),
                IssueReport.status.ilike(like_pattern),
                Users.name.ilike(like_pattern),
                Employee.first_name.ilike(like_pattern),
                Employee.last_name.ilike(like_pattern),
                func.concat(Employee.first_name, ' ', Employee.last_name).ilike(like_pattern)
            )
        )

    pagination = query.order_by(IssueReport.created_at.desc()).paginate(page=page, per_page=per_page)

    return render_template(
        'superAdmin/issuesPersonal.html',
        title="Issue",
        issues=pagination.items,
        pagination=pagination,
        search=search
    )



@app.route('/HR/Report/Submit', methods=['POST'])
@login_required
@role_required('hr')
def HRreport_issue():
    employee_id = request.form.get('employee')  # Employee.id from the form
    title = request.form.get('title')
    description = request.form.get('description')

    if not employee_id or not title or not description:
        flash('All fields are required.', 'danger')
        return redirect(request.referrer or url_for('HrIssueReport'))

    # Get the Employee record (make sure not deleted)
    employee = Employee.query.filter_by(id=employee_id, is_deleted=False).first()
    if not employee:
        flash('Employee not found.', 'danger')
        return redirect(request.referrer or url_for('HrIssueReport'))

    # Get the User linked to the Employee
    user = Users.query.filter_by(employee_id=employee.id).first()
    if not user:
        flash('User account for this employee not found.', 'danger')
        return redirect(request.referrer or url_for('HrIssueReport'))

    reported_user_id = user.id  # The actual Users.id foreign key

    # Prevent self-reporting
    if reported_user_id == current_user.id:
        flash("You cannot report yourself.", "danger")
        return redirect(request.referrer or url_for('HrIssueReport'))

    # Create and save the issue report
    issue = IssueReport(
        reporter_user_id=current_user.id,
        reported_user_id=reported_user_id,
        title=title,
        description=description
    )

    db.session.add(issue)
    db.session.commit()

    flash('Issue report submitted successfully!', 'success-timed')
    return redirect(url_for('HrIssueReport'))



@app.route('/HR/Issue/Update', methods=['POST'])
@login_required
@role_required('hr')
def UpdateIssueModal():
    issue_id = request.form.get('issue_id')
    new_status = request.form.get('status')

    issue = IssueReport.query.get_or_404(issue_id)
    if new_status in ['Open', 'In Progress', 'Resolved', 'Closed']:
        issue.status = new_status
        db.session.commit()

        reporter = Users.query.get(issue.reporter_user_id)
        if reporter:
            subject = f"Issue Report Update: {issue.title}"
            body = f"""📢 <strong>Issue Report Status Update</strong><br><br>

            <p>Dear <strong>{reporter.name}</strong>,</p>

            <p>The issue you reported titled <strong>{issue.title}</strong> is now being reviewed by HR.</p>

            <p><strong>Current Status:</strong> {new_status}</p>
            <p><strong>Description:</strong><br>{issue.description}</p>

            <hr>
            <p><em>⚠ This is an automated message. Please do not reply.</em></p>
            <p>– HR System</p>
            """

            db.session.add(UserMessage(
                sender_id=current_user.id,   # HR staff updating
                recipient_id=reporter.id,
                subject=subject,
                body=body,
                message_type='system'
            ))
            db.session.commit()


        flash('Issue status updated successfully.', 'success-timed')

    return redirect(url_for('HRIssue'))




@app.route('/HR/Issue/Remarks', methods=['POST'])
@login_required
@role_required('hr')
def UpdateIssueRemarks():
    issue_id = request.form.get('issue_id')
    remarks = request.form.get('remarks')

    issue = IssueReport.query.get_or_404(issue_id)
    issue.remarks = remarks
    issue.status = 'Resolved' 
    db.session.commit()

    # --- Notify reporter ---
    reporter = Users.query.get(issue.reporter_user_id)
    if reporter:
        subject = f"Issue Report Resolved: {issue.title}"
        body = f"""📢 <strong>Issue Report Resolution</strong><br><br>

        <p>Dear <strong>{reporter.name}</strong>,</p>

        <p>The issue you reported titled <strong>{issue.title}</strong> has been 
        <strong>resolved</strong> by HR.</p>

        <p><strong>HR Remarks:</strong><br>{remarks}</p>

        <p><strong>Original Issue Description:</strong><br>{issue.description}</p>

        <hr>
        <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
        <p>– HR System</p>
        """

        db.session.add(UserMessage(
            sender_id=current_user.id,   # HR staff who resolved it
            recipient_id=reporter.id,
            subject=subject,
            body=body,
            message_type='system'
        ))
        db.session.commit()

    flash('Remarks added and issue marked as Resolved.', 'success-timed')
    return redirect(url_for('HRIssue'))



@app.route('/Accounts/Reponsibilities')
@login_required
@role_required('hr')
def ManageUserCase():

    permanent_employees = (
    Employee.query
    .join(PermanentEmployeeDetails)
    .join(Department)
    .filter(
        Department.name == "Office of the Municipal Human Resource Management Officer",
        Employee.is_deleted == False   # ✅ exclude inactive/deleted employees
    )
    .options(
        db.joinedload(Employee.permanent_details).joinedload(PermanentEmployeeDetails.position),
        db.joinedload(Employee.department),
        db.joinedload(Employee.user)
    )
    .all()
    )


    return render_template('superAdmin/UserCase.html', title="HR Reponsibilities",permanent_employees=permanent_employees)


# newlogin
# @app.route('/LoginAttempt')
# @login_required
# @role_required('hr')
# def HRLoginAttempt():
#     # Fetch all login attempts ordered by latest first
#     logins = LoginActivity.query.order_by(LoginActivity.timestamp.desc()).all()

#     return render_template(
#         'superAdmin/LoginAttemptHR.html',
#         title="Users Attempt Record",
#         logins=logins
#     )

# newlogin
@app.route('/LoginAttempt')
@login_required
@role_required('hr')
def HRLoginAttempt():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search = request.args.get('search', '').strip()

    # Start base query
    query = LoginActivity.query.join(Users).join(Employee)

    # Filtering logic
    if search:
        like_pattern = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(Users.name).ilike(like_pattern),
                func.lower(Users.email).ilike(like_pattern),
                func.lower(Employee.first_name).ilike(like_pattern),
                func.lower(Employee.last_name).ilike(like_pattern),
                func.lower(Employee.middle_name).ilike(like_pattern),
                Employee.department.has(func.lower(Department.name).ilike(like_pattern)),
                Employee.permanent_details.has(
                    PermanentEmployeeDetails.position.has(func.lower(Position.title).ilike(like_pattern))
                ),
                func.lower(LoginActivity.ip_address).ilike(like_pattern),

                # Full name (first + last)
                func.lower(
                    func.concat(
                        func.coalesce(Employee.first_name, ''),
                        literal(' '),
                        func.coalesce(Employee.last_name, '')
                    )
                ).ilike(like_pattern),

                # Full display format: Last, First M.
                func.lower(
                    func.concat(
                        func.coalesce(Employee.last_name, ''),
                        literal(', '),
                        func.coalesce(Employee.first_name, ''),
                        literal(' '),
                        func.substr(func.coalesce(Employee.middle_name, ''), 1, 1),
                        literal('.')
                    )
                ).ilike(like_pattern)
            )
        )



    # Pagination and ordering
    logins = query.order_by(LoginActivity.timestamp.desc()).paginate(page=page, per_page=per_page)

    return render_template(
        'superAdmin/LoginAttemptHR.html',
        title="Users Attempt Record",
        logins=logins,
        search=search
    )




@app.template_filter('ph_time_exact')
def ph_time_exact(utc_dt):
    if not utc_dt:
        return "—"
    ph_dt = utc_dt + timedelta(hours=8)
    return ph_dt.strftime('%B %d, %Y - %I:%M %p')

@app.template_filter('ph_time')
def convert_to_ph_time(utc_dt):
    if not utc_dt:
        return ""
    
    # Convert UTC datetime to Philippine time (UTC+8)
    ph_dt = utc_dt + timedelta(hours=8)
    
    # Current PH time
    now_ph = datetime.utcnow() + timedelta(hours=8)
    diff = now_ph - ph_dt
    seconds = diff.total_seconds()
    
    # Relative time formatting
    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes} min ago" if minutes == 1 else f"{minutes} mins ago"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} hr ago" if hours == 1 else f"{hours} hrs ago"
    elif seconds < 604800:
        days = int(seconds // 86400)
        return f"{days} day ago" if days == 1 else f"{days} days ago"
    else:
        # Older dates: full Philippine datetime
        return ph_dt.strftime('%B %d,')
    
@app.route('/HR/Inbox')
@login_required
@role_required('hr')
def HRInbox():
    # For the Modal
    all_users = Users.query.all()

    grouped_users = defaultdict(list)
    for user in all_users:
        if user.id == current_user.id:
            continue
        if user.employee and user.employee.department:
            dept_name = user.employee.department.name
        else:
            dept_name = "No Department"
        grouped_users[dept_name].append(user)

    inbox_messages = UserMessage.query.filter_by(
        recipient_id=current_user.id,
        is_deleted=False,
        is_sent_copy=False
    ).order_by(UserMessage.timestamp.desc()).all()


     # Generate correct ipcr_link per message
    for msg in inbox_messages:
        msg.ipcr_link = None  # default

        if msg.message_type == "ipcr_submission":
            # Extract the period from the body text
            match = re.search(r"period '([^']+)'", msg.body)

            if match and msg.sender and msg.sender.employee:
                period_name = match.group(1)
                employee_id = msg.sender.employee.id

                ipcr = (
                    IPCR.query
                    .join(IPCR.period)
                    .filter(
                        IPCR.submitted == True,
                        IPCR.graded == False,
                        EvaluationPeriod.name == period_name,
                        IPCR.employee_id == employee_id  # <-- important!
                    )
                    .first()
                )

                if ipcr:
                    msg.ipcr_link = url_for("HeadGradeIpcrHR", ipcr_id=ipcr.id)


    sent_messages = UserMessage.query.filter_by(
        sender_id=current_user.id,
        is_sent_copy=True,
        is_deleted=False
    ).order_by(UserMessage.timestamp.desc()).all()

    trash_messages = UserMessage.query.filter(
        UserMessage.is_deleted == True,
        or_(
            and_(
                UserMessage.recipient_id == current_user.id,
                UserMessage.is_sent_copy == False
            ),
            and_(
                UserMessage.sender_id == current_user.id,
                UserMessage.is_sent_copy == True
            )
        )
    ).order_by(UserMessage.timestamp.desc()).all()

    unread_messages = UserMessage.query.options(
        joinedload(UserMessage.sender)
    ).filter_by(
        recipient_id=current_user.id,
        is_read=False,
        is_deleted=False,
        is_sent_copy=False
    ).order_by(UserMessage.timestamp.desc()).limit(5).all()

    unread_count = UserMessage.query.filter_by(
        recipient_id=current_user.id,
        is_read=False,
        is_deleted=False,
        is_sent_copy=False
    ).count()

    # Get the current user's position title
    position_title = ''
    if current_user.employee:
        if current_user.employee.permanent_details:
            position_title = current_user.employee.permanent_details.position.title
        elif current_user.employee.casual_details:
            position_title = current_user.employee.casual_details.position.title
        elif current_user.employee.job_order_details:
            position_title = current_user.employee.job_order_details.position.title

   

    return render_template(
        'superAdmin/InboxHr.html',
        title="Inbox",
        grouped_users=grouped_users,
        inbox=inbox_messages,
        sent=sent_messages,
        trash=trash_messages,
        unread_messages=unread_messages,
        unread_count=unread_count,
        position_title=position_title,
    )


@app.route('/uploads/messages/<filename>')
def uploaded_file(filename):
    return send_from_directory('uploads/messages', filename)


@app.route('/HR/Credits')
@login_required
@role_required('hr')
def ManageCreditHr():
    # --- Departments & Employees ---
    departments = Department.query.all()
    employees = (
    Employee.query
    .filter(
        Employee.employment_status == 'active',
        Employee.is_deleted == False,
        Employee.job_order_details == None  # Exclude Job Order
    )
    .all()
    )


    employees_by_dept = defaultdict(list)
    credit_transactions_by_dept = defaultdict(list)

    # Totals (separate for vacation & sick)
    total_vacation_earned = 0
    total_vacation_used = 0
    total_vacation_remaining = 0

    total_sick_earned = 0
    total_sick_used = 0
    total_sick_remaining = 0

    for emp in employees:
        # Determine department
        if emp.permanent_details and emp.department:
            dept_name = emp.department.name
        elif emp.casual_details and emp.casual_details.assigned_department:
            dept_name = emp.casual_details.assigned_department.name
        elif emp.job_order_details and emp.job_order_details.assigned_department:
            dept_name = emp.job_order_details.assigned_department.name
        else:
            dept_name = "No Department"

        employees_by_dept[dept_name].append(emp)

        # Credit transactions per department
        for tx in emp.credit_transactions:
            credit_transactions_by_dept[dept_name].append(tx)

        # --- Totals per employee ---
        if emp.credit_balance:
            # Vacation
            total_vacation_earned += emp.credit_balance.vacation_earned or 0
            total_vacation_used += emp.credit_balance.vacation_used or 0
            total_vacation_remaining += emp.credit_balance.vacation_remaining or 0

            # Sick
            total_sick_earned += emp.credit_balance.sick_earned or 0
            total_sick_used += emp.credit_balance.sick_used or 0
            total_sick_remaining += emp.credit_balance.sick_remaining or 0

    total_employees = len(employees)

    # --- Donut chart data (Vacation vs Sick Remaining) ---
    donut_data = [
        round(total_vacation_remaining, 1),
        round(total_sick_remaining, 1)
    ]

    # --- Line chart data (Earned vs Used over last 6 months) ---
    today = datetime.today()
    six_months_ago = today - timedelta(days=180)

    accruals = (
        db.session.query(
            func.extract('year', CreditTransaction.timestamp).label('year'),
            func.extract('month', CreditTransaction.timestamp).label('month'),
            CreditTransaction.leave_type.label('leave_type'),
            CreditTransaction.action.label('action'),
            func.sum(CreditTransaction.amount).label('total')
        )
        .filter(
            CreditTransaction.action.in_(['Earned', 'Used']),
            CreditTransaction.timestamp >= six_months_ago
        )
        .group_by('year', 'month', 'leave_type', 'action')
        .order_by('year', 'month')
        .all()
    )

    # Map months to totals (separate Vacation & Sick)
    line_dict = {}
    for year, month, leave_type, action, total in accruals:
        month_label = datetime(int(year), int(month), 1).strftime("%B")
        if month_label not in line_dict:
            line_dict[month_label] = {
                'Vacation_Earned': 0, 'Vacation_Used': 0,
                'Sick_Earned': 0, 'Sick_Used': 0
            }
        line_dict[month_label][f"{leave_type}_{action}"] = float(total)

    # Sort months chronologically
    sorted_months = sorted(line_dict.keys(), key=lambda x: datetime.strptime(x, "%B"))

    # Prepare datasets
    line_labels = sorted_months
    vacation_earned_data = [round(line_dict[m]['Vacation_Earned'], 1) for m in sorted_months]
    vacation_used_data   = [round(line_dict[m]['Vacation_Used'], 1) for m in sorted_months]
    sick_earned_data     = [round(line_dict[m]['Sick_Earned'], 1) for m in sorted_months]
    sick_used_data       = [round(line_dict[m]['Sick_Used'], 1) for m in sorted_months]

    return render_template(
        'superAdmin/EmployeeCredit.html',
        title="Employee Credit",
        departments=departments,
        employees_by_dept=employees_by_dept,
        credit_transactions_by_dept=credit_transactions_by_dept,
        total_vacation_earned=round(total_vacation_earned, 1),
        total_vacation_used=round(total_vacation_used, 1),
        total_vacation_remaining=round(total_vacation_remaining, 1),
        total_sick_earned=round(total_sick_earned, 1),
        total_sick_used=round(total_sick_used, 1),
        total_sick_remaining=round(total_sick_remaining, 1),
        total_employees=total_employees,
        donut_data=donut_data,
        line_labels=line_labels,
        vacation_earned_data=vacation_earned_data,
        vacation_used_data=vacation_used_data,
        sick_earned_data=sick_earned_data,
        sick_used_data=sick_used_data
    )




@app.route("/update_credit", methods=["POST"])
@login_required
@role_required('hr')
def update_credit():
    emp_id = request.form.get("employee_id")
    employee = Employee.query.get_or_404(emp_id)

    # Get or create EmployeeCredit record
    credit = employee.credit_balance
    if not credit:
        credit = EmployeeCredit(employee_id=employee.id)
        db.session.add(credit)

    # ✅ Safely handle None values
    old_vac_earned = credit.vacation_earned or 0.0
    old_vac_used = credit.vacation_used or 0.0
    old_sick_earned = credit.sick_earned or 0.0
    old_sick_used = credit.sick_used or 0.0
    old_vac_remaining = credit.vacation_remaining or 0.0
    old_sick_remaining = credit.sick_remaining or 0.0

    # New values from form
    credit.vacation_earned = float(request.form.get("vacation_earned", 0))
    credit.vacation_used = float(request.form.get("vacation_used", 0))
    credit.vacation_remaining = float(request.form.get("vacation_remaining", 0))
    credit.sick_earned = float(request.form.get("sick_earned", 0))
    credit.sick_used = float(request.form.get("sick_used", 0))
    credit.sick_remaining = float(request.form.get("sick_remaining", 0))
    credit.last_updated = datetime.utcnow()

    # --- Transaction logging with "Edited" action ---
    changes = []
    if credit.vacation_earned != old_vac_earned:
        changes.append(CreditTransaction(
            employee_id=employee.id,
            leave_type="Vacation",
            action="Edited",
            amount=credit.vacation_earned - old_vac_earned,
            notes=f"Vacation Earned changed from {old_vac_earned} → {credit.vacation_earned} by HR"
        ))
    if credit.vacation_used != old_vac_used:
        changes.append(CreditTransaction(
            employee_id=employee.id,
            leave_type="Vacation",
            action="Edited",
            amount=credit.vacation_used - old_vac_used,
            notes=f"Vacation Used changed from {old_vac_used} → {credit.vacation_used} by HR"
        ))
    if credit.sick_earned != old_sick_earned:
        changes.append(CreditTransaction(
            employee_id=employee.id,
            leave_type="Sick",
            action="Edited",
            amount=credit.sick_earned - old_sick_earned,
            notes=f"Sick Earned changed from {old_sick_earned} → {credit.sick_earned} by HR"
        ))
    if credit.sick_used != old_sick_used:
        changes.append(CreditTransaction(
            employee_id=employee.id,
            leave_type="Sick",
            action="Edited",
            amount=credit.sick_used - old_sick_used,
            notes=f"Sick Used changed from {old_sick_used} → {credit.sick_used} by HR"
        ))

    if credit.vacation_remaining != old_vac_remaining:
        changes.append(CreditTransaction(
            employee_id=employee.id,
            leave_type="Vacation",
            action="Edited",
            amount=credit.vacation_remaining - old_vac_remaining,
            notes=f"Vacation Remaining changed from {old_vac_remaining} → {credit.vacation_remaining} by HR"
        ))

    if credit.sick_remaining != old_sick_remaining:
        changes.append(CreditTransaction(
            employee_id=employee.id,
            leave_type="Sick",
            action="Edited",
            amount=credit.sick_remaining - old_sick_remaining,
            notes=f"Sick Remaining changed from {old_sick_remaining} → {credit.sick_remaining} by HR"
        ))


    if changes:
        db.session.add_all(changes)

    db.session.commit()
    flash("Employee credits updated successfully!", "success-timed")
    return redirect(url_for("ManageCreditHr"))





ATTACHMENT_UPLOAD_FOLDER = 'static/uploads/attachments'
ATTACHMENT_ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx', 'txt', 'zip'}

app.config['ATTACHMENT_UPLOAD_FOLDER'] = ATTACHMENT_UPLOAD_FOLDER

def allowed_attachment_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ATTACHMENT_ALLOWED_EXTENSIONS


def save_attachment(file):
    random_hex = secrets.token_hex(8)
    original_name = secure_filename(file.filename)
    stored_filename = f"{random_hex}_{original_name}"

    save_path = os.path.join(app.root_path, app.config['ATTACHMENT_UPLOAD_FOLDER'], stored_filename)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)

    return stored_filename

@app.route('/send', methods=['POST'])
@login_required
def send_message():
    recipient_emails = request.form.get('recipient_emails', '')
    subject = request.form.get('subject', '')
    content = request.form.get('content', '')
    message_type = request.form.get('message_type', 'personal')
    files = request.files.getlist('attachments')

    if not recipient_emails.strip():
        flash('Recipient is required.', 'danger')
        return redirect(request.referrer)

    if not subject.strip() or not content.strip():
        flash('Subject and content are required.', 'danger')
        return redirect(request.referrer)

    email_list = [email.strip() for email in recipient_emails.split(',') if email.strip()]
    if not email_list:
        flash('No valid recipients provided.', 'danger')
        return redirect(request.referrer)

    # ✅ Save all attachments ONCE
    all_saved_filenames = []
    for file in files:
        if file and file.filename and allowed_attachment_file(file.filename):
            try:
                stored_filename = save_attachment(file)
                all_saved_filenames.append(stored_filename)
            except Exception as e:
                flash(f'❌ Error saving file {file.filename}', 'danger')

    # ✅ Now loop recipients and link the saved filenames
    for email in email_list:
        recipient = Users.query.filter_by(email=email).first()
        if not recipient:
            continue

        # Recipient copy
        message = UserMessage(
            sender_id=current_user.id,
            recipient_id=recipient.id,
            subject=subject,
            body=content,
            is_sent_copy=False,
            message_type=message_type
        )
        db.session.add(message)
        db.session.flush()

        for filename in all_saved_filenames:
            db.session.add(MessageAttachment(
                message_id=message.id,
                filename=filename
            ))

        # Sender copy
        sent_copy = UserMessage(
            sender_id=current_user.id,
            recipient_id=recipient.id,
            subject=subject,
            body=content,
            is_sent_copy=True,
            message_type=message_type
        )
        db.session.add(sent_copy)
        db.session.flush()

        for filename in all_saved_filenames:
            db.session.add(MessageAttachment(
                message_id=sent_copy.id,
                filename=filename
            ))

    db.session.commit()
    flash('Message(s) sent successfully.', 'success-timed')
    return redirect(request.referrer)


@app.route('/messages/mark_read/<int:message_id>', methods=['POST'])
@login_required
def mark_message_read(message_id):
    message = UserMessage.query.get_or_404(message_id)
    if message.recipient_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    if not message.is_read:
        message.is_read = True
        db.session.commit()

    return jsonify({'success': True})




@app.route('/messages/mark_read_bulk', methods=['POST'])
@login_required
def mark_read_bulk():
    raw_ids = request.form.getlist('ids')
    
    # Safely convert to integers, skip invalid ones
    try:
        ids = [int(i) for i in raw_ids if i.isdigit()]
    except ValueError:
        ids = []

    if not ids:
        flash("No valid messages selected.", 'warning')
        return redirect(request.referrer or url_for('HRInbox'))

    # Filter only unread messages
    messages_to_update = UserMessage.query.filter(
        UserMessage.id.in_(ids),
        UserMessage.recipient_id == current_user.id,
        UserMessage.is_read == False
    ).all()

    if not messages_to_update:
        flash("Selected messages are already marked as read.", 'warning')
    else:
        for msg in messages_to_update:
            msg.is_read = True
        db.session.commit()
        flash(f"{len(messages_to_update)} message(s) marked as read.", 'success-timed')

    return redirect(request.referrer or url_for('HRInbox'))



@app.route('/messages/delete_bulk', methods=['POST'])
@login_required
def delete_bulk():
    raw_ids = request.form.getlist('ids')

    try:
        ids = [int(i) for i in raw_ids if i.isdigit()]
    except ValueError:
        ids = []

    if not ids:
        flash("No valid messages selected.", 'warning')
        return redirect(request.referrer or url_for('HRInbox'))

    # Fetch messages that match either inbox or sent criteria
    messages_to_delete = UserMessage.query.filter(
        UserMessage.id.in_(ids),
        UserMessage.is_deleted == False,
        db.or_(
            db.and_(
                UserMessage.recipient_id == current_user.id,
                UserMessage.is_sent_copy == False
            ),
            db.and_(
                UserMessage.sender_id == current_user.id,
                UserMessage.is_sent_copy == True
            )
        )
    ).all()

    if not messages_to_delete:
        flash("Selected messages are already in trash or do not belong to you.", 'warning')
    else:
        for msg in messages_to_delete:
            msg.is_deleted = True
        db.session.commit()
        flash(f"{len(messages_to_delete)} message(s) moved to trash.", 'success-timed')

    return redirect(request.referrer or url_for('HRInbox'))


@app.route('/messages/reply/<int:message_id>', methods=['POST'])
@login_required
def reply_message(message_id):
    content = request.form.get('reply_content', '').strip()
    files = request.files.getlist('attachments')

    if not content:
        flash("Reply cannot be empty.", "warning")
        return redirect(request.referrer or url_for('HRInbox'))

    original_msg = UserMessage.query.get_or_404(message_id)

    # ✅ Avoid multiple "Reply:" prefixes
    subject = original_msg.subject
    if not subject.lower().startswith("reply:"):
        subject = f"Reply: {subject}"

    # ✅ Receiver's copy (Inbox)
    inbox_copy = UserMessage(
        sender_id=current_user.id,
        recipient_id=original_msg.sender_id,
        subject=subject,
        body=content,
        is_read=False,
        is_sent_copy=False
    )
    db.session.add(inbox_copy)
    db.session.flush()

    # ✅ Sender's copy (Sent)
    sent_copy = UserMessage(
        sender_id=current_user.id,
        recipient_id=original_msg.sender_id,
        subject=subject,
        body=content,
        is_read=True,
        is_sent_copy=True
    )
    db.session.add(sent_copy)
    db.session.flush()

    # ✅ Save attachments ONCE
    saved_files = []
    for file in files:
        if file and file.filename and allowed_attachment_file(file.filename):
            stored_filename = save_attachment(file)
            saved_files.append(stored_filename)

    # ✅ Link saved files to both copies
    for filename in saved_files:
        db.session.add(MessageAttachment(message_id=inbox_copy.id, filename=filename))
        db.session.add(MessageAttachment(message_id=sent_copy.id, filename=filename))

    db.session.commit()
    flash("Reply sent successfully.", "success")
    return redirect(request.referrer)


@app.route('/messages/mark_all_read')
@login_required
def mark_all_messages_read():
    UserMessage.query.filter_by(
        recipient_id=current_user.id,
        is_read=False,
        is_deleted=False,
        is_sent_copy=False
    ).update({UserMessage.is_read: True})
    db.session.commit()
    flash("All messages marked as read.", "info")
    return redirect(request.referrer or url_for('HRInbox'))


@app.route('/messages/view/<int:message_id>')
@login_required
def view_message(message_id):
    msg = UserMessage.query.options(joinedload(UserMessage.sender)).get_or_404(message_id)

    if msg.recipient_id != current_user.id:
        abort(403)

    msg.is_read = True
    db.session.commit()
    return render_template('view_message.html', message=msg)

@app.route('/messages/json/<int:message_id>')
@login_required
def view_message_json(message_id):
    msg = UserMessage.query.options(joinedload(UserMessage.sender)).get_or_404(message_id)

    if msg.recipient_id != current_user.id:
        abort(403)

    msg.is_read = True
    db.session.commit()

    return jsonify({
        "id": msg.id,
        "subject": msg.subject,
        "body": msg.body,  # Make sure this is safe HTML
        "tab": "inbox",  # or use logic to decide this
        "message_type": msg.message_type,
        "sender": {
            "name": msg.sender.name,
            "image_file": msg.sender.image_file or "default.jpg"
        }
    })


@app.context_processor
def inject_notifications():
    if current_user.is_authenticated:
        # ✅ Totoong bilang ng lahat ng unread messages
        total_unread_count = UserMessage.query.filter_by(
            recipient_id=current_user.id,
            is_read=False,
            is_deleted=False,
            is_sent_copy=False
        ).count()

        # ✅ Ipakita lang top 5 sa dropdown with sender data loaded
        unread_messages = UserMessage.query.options(
            joinedload(UserMessage.sender)  # ✅ this loads sender.profile_pic
        ).filter_by(
            recipient_id=current_user.id,
            is_read=False,
            is_deleted=False,
            is_sent_copy=False
        ).order_by(UserMessage.timestamp.desc()).limit(5).all()

        return {
            'unread_messages': unread_messages,
            'unread_count': total_unread_count
        }

    return {'unread_messages': [], 'unread_count': 0}



@app.route("/HR/Analytics", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def hranalytics():
    active_period = EvaluationPeriod.query.filter_by(is_active=True).order_by(EvaluationPeriod.start_date.desc()).first()
   
    if not active_period:
    # Fallback to most recent period
         active_period = EvaluationPeriod.query.order_by(EvaluationPeriod.start_date.desc()).first()

    # If still none, return empty analytics page (to prevent 500 error)
    if not active_period:
        flash("No evaluation periods available.", "warning")
        return render_template(
            'superAdmin/anayltics.html',
            title="Analytics",
            rating_distribution={},
            department_averages={},
            rating_trend={"quarters": [], "average_ratings": []},
            rating_counts_by_dept={},
            department_improvement={},
            dept_trend_data={"quarters": [], "departments": {}},
            top_performers={},
            qeta_breakdown={},
            department_acronyms={},
            rating_distribution_by_period={},
            periods=[],
            active_period_id=None,
            department_chart_data_by_period={},
            rating_counts_by_dept_by_period={},
            top_performers_by_period={},
            period_ids=[],
        )
    
    ipcrs = IPCR.query.filter_by(period_id=active_period.id, submitted=True, graded=True).all()

    rating_distribution = defaultdict(int)
    dept_qeta = defaultdict(lambda: {'q': [], 'e': [], 't': [], 'a': []})
    department_averages = defaultdict(list)
    top_performers = {}
    rating_counts_by_dept = defaultdict(lambda: defaultdict(int))

    for ipcr in ipcrs:
        emp = ipcr.employee
        if not emp or not emp.department:
            continue
        dept = emp.department.name

        if ipcr.adjective_rating:
            rating_distribution[ipcr.adjective_rating] += 1
            rating_counts_by_dept[dept][ipcr.adjective_rating] += 1

        if ipcr.final_average_rating:
            department_averages[dept].append(ipcr.final_average_rating)
            if dept not in top_performers or ipcr.final_average_rating > top_performers[dept]['rating']:
                top_performers[dept] = {
                    "name": f"{emp.first_name} {emp.last_name}",
                    "rating": ipcr.final_average_rating
                }

        for section in ipcr.sections:
            for item in section.section_items:
                if item.rating_q is not None: dept_qeta[dept]['q'].append(item.rating_q)
                if item.rating_e is not None: dept_qeta[dept]['e'].append(item.rating_e)
                if item.rating_t is not None: dept_qeta[dept]['t'].append(item.rating_t)
                if item.rating_a is not None: dept_qeta[dept]['a'].append(item.rating_a)

    department_averages = {
        dept: round(sum(ratings) / len(ratings), 2)
        for dept, ratings in department_averages.items() if ratings
    }

    all_departments = Department.query.order_by(Department.name).all()
    department_averages_complete = {
        dept.name: department_averages.get(dept.name, 0)
        for dept in all_departments
    }

    def generate_acronym(name):
        ignore_words = {"of", "the", "and", "for"}
        words = name.strip().split()
        return "".join(word[0].upper() for word in words if word.lower() not in ignore_words)

    department_acronyms = {
        dept.name: generate_acronym(dept.name)
        for dept in all_departments
    }

    qeta_breakdown = {
        dept: {
            'q': round(sum(values['q']) / len(values['q']), 2) if values['q'] else 0,
            'e': round(sum(values['e']) / len(values['e']), 2) if values['e'] else 0,
            't': round(sum(values['t']) / len(values['t']), 2) if values['t'] else 0,
            'a': round(sum(values['a']) / len(values['a']), 2) if values['a'] else 0
        }
        for dept, values in dept_qeta.items()
    }

    sorted_top_performers = dict(sorted(top_performers.items(), key=lambda item: item[1]['rating'], reverse=True))

    rating_trend = {"quarters": [], "average_ratings": []}
    periods = EvaluationPeriod.query.order_by(EvaluationPeriod.start_date).all()
    period_ids = [period.id for period in periods]

    for period in periods:
        ipcrs_in_period = IPCR.query.filter_by(period_id=period.id, submitted=True, graded=True).all()
        ratings = [ipcr.final_average_rating for ipcr in ipcrs_in_period if ipcr.final_average_rating is not None]
        label = period.name or f"Q{((period.start_date.month - 1) // 3 + 1)} {period.start_date.year}"
        rating_trend["quarters"].append(label)
        rating_trend["average_ratings"].append(round(sum(ratings) / len(ratings), 2) if ratings else 0)

    dept_trend_data = {"quarters": [], "departments": {}}
    for period in periods:
        label = period.name or f"Q{((period.start_date.month - 1) // 3 + 1)} {period.start_date.year}"
        dept_trend_data["quarters"].append(label)
        ipcrs_in_period = IPCR.query.filter_by(period_id=period.id, submitted=True, graded=True).all()
        dept_scores = defaultdict(list)

        for ipcr in ipcrs_in_period:
            emp = ipcr.employee
            if emp and emp.department and ipcr.final_average_rating:
                dept_scores[emp.department.name].append(ipcr.final_average_rating)

        for dept_name, scores in dept_scores.items():
            acronym = department_acronyms.get(dept_name, dept_name)
            avg = round(sum(scores) / len(scores), 2) if scores else 0
            if acronym not in dept_trend_data["departments"]:
                dept_trend_data["departments"][acronym] = []
            dept_trend_data["departments"][acronym].append(avg)

    department_improvement = {
        dept: round(department_averages_complete.get(dept, 0) - trend[-2], 2)
        if dept in department_averages_complete and len(trend) >= 2 else 0
        for dept, trend in dept_trend_data["departments"].items()
    }

    # Ensure all rating labels are present
    standard_labels = ["Very Satisfactory", "Satisfactory", "Fair", "Poor", "Very Poor"]
    for label in standard_labels:
        rating_distribution[label] += 0

    rating_distribution_by_period = {}
    for period in periods:
        dist = defaultdict(int)
        ipcrs_in_period = IPCR.query.filter_by(period_id=period.id, submitted=True, graded=True).all()
        for ipcr in ipcrs_in_period:
            if ipcr.adjective_rating:
                dist[ipcr.adjective_rating] += 1
        rating_distribution_by_period[period.id] = {
            "name": period.name or f"Period {period.id}",
            "ratings": {label: dist.get(label, 0) for label in standard_labels}
        }

    rating_counts_by_dept_by_period = {}
    for period in periods:
        counts = defaultdict(lambda: defaultdict(int))
        ipcrs_in_period = IPCR.query.filter_by(period_id=period.id, submitted=True, graded=True).all()
        for ipcr in ipcrs_in_period:
            emp = ipcr.employee
            if emp and emp.department and ipcr.adjective_rating:
                counts[emp.department.name][ipcr.adjective_rating] += 1
        rating_counts_by_dept_by_period[period.id] = {
            dept: dict(ratings) for dept, ratings in counts.items()
        }

    department_chart_data_by_period = {}
    for period in periods:
        averages = defaultdict(list)
        ipcrs_in_period = IPCR.query.filter_by(period_id=period.id, submitted=True, graded=True).all()
        for ipcr in ipcrs_in_period:
            emp = ipcr.employee
            if emp and emp.department and ipcr.final_average_rating:
                averages[emp.department.name].append(ipcr.final_average_rating)

        averages_final = {
            dept.name: round(sum(averages[dept.name]) / len(averages[dept.name]), 2) if averages[dept.name] else 0
            for dept in all_departments
        }

        department_chart_data_by_period[period.id] = {
            "labels": list(averages_final.keys()),
            "ratings": list(averages_final.values()),
            "acronyms": department_acronyms
        }

    # Convert all defaultdicts to dicts to avoid serialization errors
    rating_distribution = dict(rating_distribution)
    rating_counts_by_dept = {k: dict(v) for k, v in rating_counts_by_dept.items()}
    dept_trend_data["departments"] = dict(dept_trend_data["departments"])
    department_improvement = dict(department_improvement)

    top_performers_by_period = {}

    for period in periods:
        ipcrs_in_period = IPCR.query.filter_by(period_id=period.id, submitted=True, graded=True).all()
        performers = {}
        for ipcr in ipcrs_in_period:
            emp = ipcr.employee
            if emp and emp.department and ipcr.final_average_rating:
                dept = emp.department.name
                if dept not in performers or ipcr.final_average_rating > performers[dept]['rating']:
                    performers[dept] = {
                        "name": f"{emp.first_name} {emp.last_name}",
                        "rating": ipcr.final_average_rating
                    }
        top_performers_by_period[period.id] = performers


    return render_template(
        'superAdmin/anayltics.html',
        title="Analytics",
        rating_distribution=rating_distribution,
        department_averages=department_averages_complete,
        rating_trend=rating_trend,
        rating_counts_by_dept=rating_counts_by_dept,
        department_improvement=department_improvement,
        dept_trend_data=dept_trend_data,
        top_performers=sorted_top_performers,
        qeta_breakdown=qeta_breakdown,
        department_acronyms=department_acronyms,
        rating_distribution_by_period=rating_distribution_by_period,
        periods=periods,
        active_period_id=active_period.id if active_period else None,
        department_chart_data_by_period=department_chart_data_by_period,
        rating_counts_by_dept_by_period=rating_counts_by_dept_by_period,
        top_performers_by_period=top_performers_by_period,
        period_ids=period_ids,

    )


@app.route("/HR/Calendar", methods=['GET', 'POST'])
@login_required
@role_required('hr')
def hrCalendar():
    now = datetime.now(ZoneInfo("Asia/Manila"))
    current_day = now.strftime('%A')
    current_date = now.strftime('%d %b, %Y')

    # Query only events that are ongoing or in the future
    active_events = CalendarEvent.query.filter(
        (CalendarEvent.end_date == None) | (CalendarEvent.end_date >= now)
    ).all()

    # Count how many events exist per label
    event_counts = defaultdict(int)
    for event in active_events:
        event_counts[event.label] += 1

    return render_template(
        'superAdmin/calendarHR.html',
        title="Calendar",
        current_day=current_day,
        current_date=current_date,
        event_counts=event_counts
    )


# ADMIN
@app.route("/head/performance/analytics", methods=['GET', 'POST'])
@login_required
@role_required('head')
def headPerformanceAnalytics():
    active_period = EvaluationPeriod.query.filter_by(is_active=True).order_by(EvaluationPeriod.start_date.desc()).first()
    if not active_period:
        active_period = EvaluationPeriod.query.order_by(EvaluationPeriod.start_date.desc()).first()

    if not active_period:
        # 🚨 No periods at all → fallback return
        flash("No evaluation periods available.", "warning")
        return render_template(
            "admin/adminreport.html",
            title="Analytics",
            rating_trend={"quarters": [], "average_ratings": []},
            rating_distribution_by_period={},
            periods=[],
            active_period_id=None,
            period_ids=[],
            employee_trend_data={"quarters": [], "employees": {}},
            employee_chart_data_by_period={},
            rating_by_position={},
            employee_improvement_data={},
            period_names=[]
        )
    
    # Only include IPCRs from active period and department
    department_id = current_user.employee.department_id
    ipcrs = IPCR.query.filter_by(period_id=active_period.id, submitted=True, graded=True).all()

 
    # 🔵 Per-Period Pie Chart
    rating_distribution_by_period = {}

    # 🟣 Department Average Line Chart
    rating_trend = {"quarters": [], "average_ratings": []}

    # 🟦 Employee Trend Line Chart
    employee_trend_data = {"quarters": [], "employees": defaultdict(list)}

    # 🟨 Top Performing Employees
    top_performers_by_period = {}

    standard_labels = ["Very Satisfactory", "Satisfactory", "Fair", "Poor", "Very Poor"]

    periods = EvaluationPeriod.query.order_by(EvaluationPeriod.start_date).all()
    period_ids = [period.id for period in periods]

    # 🔵 Global Pie Chart (Filter by department)
   
    # 🔁 Loop each period
    for period in periods:
        label = period.name or f"Q{((period.start_date.month - 1) // 3 + 1)} {period.start_date.year}"
        rating_trend["quarters"].append(label)
        employee_trend_data["quarters"].append(label)

        ipcrs_in_period = IPCR.query.filter_by(period_id=period.id, submitted=True, graded=True).all()

        dist = defaultdict(int)  # For Pie Chart
        ratings = []             # For Department Line Chart
        performers = {}          # For Top Performers
        employee_scores = defaultdict(list)  # For Employee Trend Line

        for ipcr in ipcrs_in_period:
            emp = ipcr.employee
            if not emp:
                continue

            # 🔵 Pie Chart (Only if employee belongs to department)
            if ipcr.adjective_rating and emp.department_id == department_id:
                dist[ipcr.adjective_rating] += 1

            # 👇 Only process if employee is in same department
            if emp.department_id == department_id:
                if ipcr.final_average_rating:
                    middle_initial = f"{emp.middle_name[0]}." if emp.middle_name else ""
                    full_name = f"{emp.last_name}, {emp.first_name} {middle_initial}".strip()

                    employee_scores[full_name].append(ipcr.final_average_rating)

                    if full_name not in performers or ipcr.final_average_rating > performers[full_name]['rating']:
                        performers[full_name] = {"rating": ipcr.final_average_rating}

                # For line average
                if ipcr.final_average_rating:
                    ratings.append(ipcr.final_average_rating)

        # 🟣 Department Average Rating
        rating_trend["average_ratings"].append(round(sum(ratings) / len(ratings), 2) if ratings else 0)

        # 🟦 Employee Trend
        for emp_name, scores in employee_scores.items():
            avg = round(sum(scores) / len(scores), 2) if scores else 0
            employee_trend_data["employees"][emp_name].append(avg)

        # 🟨 Top Performers Bar Chart
        sorted_performers = dict(sorted(performers.items(), key=lambda x: x[1]['rating'], reverse=True))
        labels = list(sorted_performers.keys())
        ratings = [entry["rating"] for entry in sorted_performers.values()]
        acronyms = {
            label: "".join([part[0] for part in label.replace(",", "").split() if part])
            for label in labels
        }

        top_performers_by_period[period.id] = {
            "labels": labels,
            "ratings": ratings,
            "acronyms": acronyms
        }

        # 🔵 Per-Period Pie Chart (Only department employees)
        rating_distribution_by_period[period.id] = {
            "name": period.name or f"Period {period.id}",
            "ratings": {label: dist.get(label, 0) for label in standard_labels}
        }

    rating_by_position = defaultdict(int)

    for ipcr in ipcrs:
        emp = ipcr.employee

        if not emp:
            continue

        # Check permanent employee details
        if emp.permanent_details and emp.permanent_details.position:
            position_title = emp.permanent_details.position.title
            rating_by_position[position_title] += 1

        # Check casual employee details
        elif emp.casual_details and emp.casual_details.position:
            position_title = emp.casual_details.position.title
            rating_by_position[position_title] += 1

        # Check job order employee details
        elif emp.job_order_details and emp.job_order_details.position_title:
            position_title = emp.job_order_details.position_title
            rating_by_position[position_title] += 1
   


        # 🆕 Prepare Rating Improvement Data (Employee-wise)


    improvement_by_employee = defaultdict(list)
    period_names = [p.name for p in periods]
    all_employee_names = set()

    # First pass: collect all employee names who have at least one graded IPCR
    for period in periods:
        ipcrs = IPCR.query.filter_by(period_id=period.id, submitted=True, graded=True).all()
        for ipcr in ipcrs:
            emp = ipcr.employee
            if not emp or emp.department_id != department_id:
                continue
            middle_initial = f"{emp.middle_name[0]}." if emp.middle_name else ""
            full_name = f"{emp.last_name}, {emp.first_name} {middle_initial}".strip()
            all_employee_names.add(full_name)

    # Second pass: fill improvement_by_employee with average ratings (or None)
    for period in periods:
        ipcrs = IPCR.query.filter_by(period_id=period.id, submitted=True, graded=True).all()
        emp_ratings = defaultdict(list)

        for ipcr in ipcrs:
            emp = ipcr.employee
            if not emp or emp.department_id != department_id or not ipcr.final_average_rating:
                continue
            middle_initial = f"{emp.middle_name[0]}." if emp.middle_name else ""
            full_name = f"{emp.last_name}, {emp.first_name} {middle_initial}".strip()
            emp_ratings[full_name].append(ipcr.final_average_rating)

        for emp_name in all_employee_names:
            if emp_name in emp_ratings:
                avg = round(sum(emp_ratings[emp_name]) / len(emp_ratings[emp_name]), 2)
            else:
                avg = None  # or 0 if you want to default to zero
            improvement_by_employee[emp_name].append(avg)


    return render_template(
        'admin/adminreport.html',
        title="Analytics",
        rating_trend=rating_trend,                # 🟣 Department Average Line
        rating_distribution_by_period=rating_distribution_by_period,  # 🔵 Pie Chart per Period
        periods=periods,
        active_period_id=active_period.id if active_period else None,
        period_ids=period_ids,
        employee_trend_data=employee_trend_data,  # 🟦 Employee Trend
        employee_chart_data_by_period=top_performers_by_period,  # 🟨 Bar Chart
        rating_by_position=rating_by_position, 
        employee_improvement_data = improvement_by_employee,
        period_names=period_names  # 👈 Add this line


    )


@app.route("/head/home", methods=['GET', 'POST'])
@login_required
@role_required('head')
def homeHead():
    # --- Get current head employee ---
    employee = Employee.query.filter_by(id=current_user.employee_id, is_deleted=False).first()
    if not employee or not employee.department_id:
        flash('No department associated with this account.', 'danger')
        return redirect(url_for('homeHead'))

    department_id = employee.department_id

    # --- Evaluation Period ---
    all_periods = EvaluationPeriod.query.order_by(EvaluationPeriod.id.desc()).all()
    latest_period = all_periods[0] if all_periods else None
    active_period = EvaluationPeriod.query.filter_by(is_active=True).first()

    selected_period_id = request.args.get("period", type=int)
    if not selected_period_id:
        selected_period_id = active_period.id if active_period else (latest_period.id if latest_period else None)

    selected_period = EvaluationPeriod.query.get(selected_period_id) if selected_period_id else None
    evaluation_period_name = selected_period.name if selected_period else "No Period Selected"

    # --- Department employee IDs ---
    permanent_ids = db.session.query(Employee.id).join(PermanentEmployeeDetails).filter(
        Employee.department_id == department_id,
        Employee.is_deleted == False
    )

    casual_ids = db.session.query(Employee.id).join(CasualEmployeeDetails).filter(
        CasualEmployeeDetails.assigned_department_id == department_id,
        Employee.is_deleted == False
    )

    jo_ids = db.session.query(Employee.id).join(JobOrderDetails).filter(
        JobOrderDetails.assigned_department_id == department_id,
        Employee.is_deleted == False
    )

    # Total counts (include all types, exclude head later)
    permanent_count = permanent_ids.count()
    casual_count = casual_ids.count()
    job_order_count = jo_ids.count()

    # --- IPCR employee IDs (Permanent + Casual only, exclude JO and head) ---
    ipcr_employee_ids_subquery = permanent_ids.union_all(casual_ids).subquery()
    ipcr_employee_ids = [id for (id,) in db.session.query(ipcr_employee_ids_subquery).all() if id != employee.id]

    # Total employees for IPCR chart
    total_ipcr_employees = len(ipcr_employee_ids)

    # --- IPCR counts ---
    submitted_ipcr = submitted_only_ipcr = approved_ipcr = 0
    if selected_period:
        # Submitted AND graded
        submitted_ipcr = db.session.query(IPCR).filter(
            IPCR.employee_id.in_(ipcr_employee_ids),
            IPCR.period_id == selected_period.id,
            IPCR.submitted == True,
            IPCR.graded == True
        ).count()

        # Submitted BUT not graded
        submitted_only_ipcr = db.session.query(IPCR).filter(
            IPCR.employee_id.in_(ipcr_employee_ids),
            IPCR.period_id == selected_period.id,
            IPCR.submitted == True,
            IPCR.graded == False
        ).count()

        # Approved = same as graded
        approved_ipcr = submitted_ipcr

    # Total submitted (graded + not graded) for table/chart
    total_submitted_ipcr = submitted_ipcr + submitted_only_ipcr

    # --- IPCR data for table (include submitted but not graded) ---
    ipcr_records = db.session.query(IPCR, Employee).join(Employee, Employee.id == IPCR.employee_id).filter(
        IPCR.employee_id.in_(ipcr_employee_ids),
        IPCR.submitted == True,
        IPCR.period_id == selected_period_id
    ).all()

    ipcr_data = [{
        'employee_name': f"{emp.first_name} {emp.last_name}",
        'performance_score': round(ipcr.final_average_rating, 2) if ipcr.final_average_rating else 0,
        'status': ipcr.adjective_rating or ('Submitted, Not Graded' if not ipcr.graded else 'Not Rated')
    } for ipcr, emp in ipcr_records]

    # --- Permit requests for head ---
    permit_requests = PermitRequest.query.filter_by(
        employee_id=employee.id
    ).order_by(PermitRequest.date_requested.desc()).all()

    today = date.today()

    # --- Leave/travel employees today ---
    dept_employee_ids_for_leaves = db.session.query(Employee.id).filter(Employee.department_id == department_id)

    current_leave_employees = db.session.query(PermitRequest).join(LeaveApplication).filter(
        PermitRequest.status == 'Approved',
        PermitRequest.permit_type == 'Leave',
        LeaveApplication.date_from <= today,
        LeaveApplication.date_to >= today,
        PermitRequest.employee_id.in_(dept_employee_ids_for_leaves)
    ).all()

    current_travel_employees = db.session.query(PermitRequest).join(TravelOrder).filter(
        PermitRequest.status == 'Approved',
        PermitRequest.permit_type == 'Travel Order',
        TravelOrder.date_departure == today,
        PermitRequest.employee_id.in_(dept_employee_ids_for_leaves)
    ).all()

    # --- Total employees for cards (include JO, exclude head) ---
    total_employees = permanent_count + casual_count + job_order_count
    if employee.id in [id for (id,) in db.session.query(permanent_ids.union_all(casual_ids).union_all(jo_ids).subquery()).all()]:
        total_employees -= 1

    # --- Render template ---
    return render_template('admin/adminHome.html',
        title="Home",
        total_employees=total_employees,
        submitted_ipcr=total_submitted_ipcr,  # submitted = graded + not graded
        approved_ipcr=approved_ipcr,          # only graded
        submitted_only_ipcr=submitted_only_ipcr,  # optional, can still use separately
        permanent_count=permanent_count,
        casual_count=casual_count,
        job_order_count=job_order_count,
        ipcr_data=ipcr_data,
        permit_requests=permit_requests,
        all_periods=all_periods,
        ipcr_total_expected=total_ipcr_employees,  # for donut/progress chart
        ipcr_total_submitted=submitted_ipcr,      # donut chart = only graded
        selected_period_id=selected_period_id,
        evaluation_period_name=evaluation_period_name,
        current_leave_employees=current_leave_employees,
        current_travel_employees=current_travel_employees
    )




@app.route("/Head/Employees", methods=['GET', 'POST'])
@login_required
@role_required('head')
def HeadEmployee():
    if current_user.employee and current_user.employee.department_id:
        department_id = current_user.employee.department_id

        permanent_employees = Employee.query.\
            filter_by(department_id=department_id, is_deleted=False).\
            join(Employee.permanent_details).\
            filter(Employee.permanent_details != None).\
            all()
        
        casual_employees = Employee.query.\
        join(CasualEmployeeDetails).\
        filter(
            Employee.is_deleted == False,
            Employee.employment_status == 'active',
            CasualEmployeeDetails.assigned_department_id == department_id
        ).all()

        job_order_employees = Employee.query.\
        join(JobOrderDetails).\
        filter(
            Employee.is_deleted == False,
            Employee.employment_status == 'active',
            JobOrderDetails.assigned_department_id == department_id
        ).all()


        

        permanent_count = len(permanent_employees)
        casual_count = len(casual_employees)
        job_order_count = len(job_order_employees)
        
        departments = Department.query.all()
        positions = Position.query.all()
    

    return render_template('admin/DepEmployee.html', 
                           title="Department Employees",
                           permanent_employees=permanent_employees,
                           casual_employees=casual_employees,
                           job_order_employees=job_order_employees,
                           permanent_count=permanent_count,
                            casual_count=casual_count,
                            job_order_count=job_order_count,departments=departments, positions=positions)



@app.route("/Head/Employee/IPCR", methods=['GET', 'POST'])
@login_required
@role_required('head')
def HeadPerformance():
    department_id = current_user.employee.department_id
    period_id = request.args.get('period_id', type=int)

    # Fetch all available evaluation periods
    periods = EvaluationPeriod.query.order_by(EvaluationPeriod.id.desc()).all()

    # Default to latest period if not provided
    if not period_id and periods:
        period_id = periods[0].id

    selected_period = EvaluationPeriod.query.get(period_id) if period_id else None

    # --- Filter permanent employees ---
    permanent_employees = Employee.query.filter(
        Employee.department_id == department_id,
        Employee.is_deleted == False,
        Employee.employment_status == 'active',
        Employee.permanent_details.has(),
        ~Employee.permanent_details.has(
            PermanentEmployeeDetails.position.has(Position.type.ilike('head'))
        )
    )

    # --- Filter casual employees assigned to this department ---
    casual_employees = Employee.query.join(CasualEmployeeDetails).filter(
        Employee.is_deleted == False,
        Employee.employment_status == 'active',
        CasualEmployeeDetails.assigned_department_id == department_id,
        ~Employee.casual_details.has(
            CasualEmployeeDetails.position.has(Position.type.ilike('head'))
        )
    )

    # Combine both
    employees = permanent_employees.union(casual_employees).all()
    employee_ids = [e.id for e in employees]

    # Fetch IPCRs for those employees for selected period
    ipcr_query = IPCR.query.filter(IPCR.employee_id.in_(employee_ids))
    if selected_period:
        ipcr_query = ipcr_query.filter_by(period_id=selected_period.id)
    ipcrs = ipcr_query.all()
    ipcr_dict = {ipcr.employee_id: ipcr for ipcr in ipcrs}

    # Combine employees with their IPCR data
    employee_ipcr_status = [{
        'employee': emp,
        'ipcr': ipcr_dict.get(emp.id)
    } for emp in employees]

    active_period = EvaluationPeriod.query.filter_by(is_active=True).first()
    

    return render_template(
        'admin/Adminperformance.html',
        title="Performance",
        employee_ipcr_status=employee_ipcr_status,
        periods=periods,
        selected_period=selected_period,
        active_period=active_period 
    )


@app.context_processor
def inject_permit_counts():
    permit_count = 0

    if not current_user.is_authenticated:
        return dict(permit_count=0)

    role = (current_user.role or "").lower()

    # 🔹 FOR DEPARTMENT HEADS
    if role == 'head':
        head_employee = current_user.employee
        if not head_employee:
            return dict(permit_count=0)

        dept_id = head_employee.department_id

        permanent_ids = [
            e.id for e in db.session.query(Employee.id)
            .join(PermanentEmployeeDetails, PermanentEmployeeDetails.employee_id == Employee.id)
            .filter(Employee.department_id == dept_id).all()
        ]
        casual_ids = [
            e.id for e in db.session.query(Employee.id)
            .join(CasualEmployeeDetails, CasualEmployeeDetails.employee_id == Employee.id)
            .filter(CasualEmployeeDetails.assigned_department_id == dept_id).all()
        ]
        jo_ids = [
            e.id for e in db.session.query(Employee.id)
            .join(JobOrderDetails, JobOrderDetails.employee_id == Employee.id)
            .filter(JobOrderDetails.assigned_department_id == dept_id).all()
        ]

        all_emp_ids = permanent_ids + casual_ids + jo_ids

        if all_emp_ids:
            permit_count = (
                PermitRequest.query
                .filter(
                    PermitRequest.employee_id.in_(all_emp_ids),
                    PermitRequest.current_stage == 'Head'
                )
                .count()
            )
    # 🔹 FOR MAYOR
    if (
        current_user.employee
        and current_user.employee.permanent_details
        and current_user.employee.permanent_details.position.title.upper() == "MUNICIPAL MAYOR"
    ):
        mayor_count = (
            PermitRequest.query
            .filter(PermitRequest.current_stage == 'Mayor')
            .count()
        )
        permit_count += mayor_count

    return dict(permit_count=int(permit_count or 0))


@app.route('/admin/permit', methods=['GET', 'POST'])
@login_required
@role_required('head')
def adminpermit():
    employee_id = current_user.employee.id 

    # Leave Permits (for this employee only)
    leave_permits = (
        PermitRequest.query
        .filter_by(permit_type='Leave', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Travel Order Permits
    travel_orders = (
        PermitRequest.query
        .filter_by(permit_type='Travel Order', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Clearance Permits
    clearance_permits = (
        PermitRequest.query
        .filter_by(permit_type='Clearance Form', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # COE Permits
    coe_permits = (
        PermitRequest.query
        .filter_by(permit_type='Certification of Employment', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

        # Attach latest rejection history + user name to each COE permit 👇
    for permit in coe_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    return render_template('admin/adminpermit.html', 
                           title="Admin Permit", 
                           leave_permits=leave_permits,
                           travel_orders=travel_orders,
                           clearance_permits=clearance_permits,coe_permits=coe_permits)


@app.route('/admin/department/permit', methods=['GET', 'POST'])
@login_required
@role_required('head')
def admindepartmentpermit():
    # ✅ Get current head's department
    head_employee = current_user.employee
    department_id = head_employee.department_id  

    # ✅ Get Permanent employees in this department
    permanent_employees = (
        db.session.query(Employee.id)
        .join(PermanentEmployeeDetails, PermanentEmployeeDetails.employee_id == Employee.id)
        .filter(Employee.department_id == department_id)
        .all()
    )

    # ✅ Get Casual employees assigned to this department
    casual_employees = (
        db.session.query(Employee.id)
        .join(CasualEmployeeDetails, CasualEmployeeDetails.employee_id == Employee.id)
        .filter(CasualEmployeeDetails.assigned_department_id == department_id)
        .all()
    )

    # ✅ Get Job Order employees assigned to this department
    jo_employees = (
        db.session.query(Employee.id)
        .join(JobOrderDetails, JobOrderDetails.employee_id == Employee.id)
        .filter(JobOrderDetails.assigned_department_id == department_id)
        .all()
    )

    # ✅ Flatten employee IDs list
    employee_ids = (
        [emp.id for emp in permanent_employees] +
        [emp.id for emp in casual_employees] +
        [emp.id for emp in jo_employees]
    )

    # ================= LEAVE PERMITS =================
    leave_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Leave',
            PermitRequest.employee_id.in_(employee_ids),
            PermitRequest.current_stage.in_(['Head', 'Mayor', 'HR', 'Completed','Rejected'])
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    for permit in leave_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # ================= TRAVEL ORDERS =================
    travel_orders = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Travel Order',
            PermitRequest.employee_id.in_(employee_ids),
            PermitRequest.current_stage.in_(['Head', 'Mayor', 'HR', 'Completed','Rejected'])
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    for permit in travel_orders:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # ================= CLEARANCE FORMS =================
    clearance_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Clearance Form',
            PermitRequest.employee_id.in_(employee_ids),
            PermitRequest.current_stage.in_(['Head', 'Mayor', 'HR', 'Completed','Rejected'])
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    for permit in clearance_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # ================= CERTIFICATION OF EMPLOYMENT =================
    coe_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Certification of Employment',
            PermitRequest.employee_id.in_(employee_ids)
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    for permit in coe_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

         # ===================== PENDING COUNTS FOR BADGES =====================
    pending_leave_count = sum(1 for p in leave_permits if p.current_stage == 'Head')
    pending_travel_count = sum(1 for p in travel_orders if p.current_stage == 'Head')
    pending_clearance_count = sum(1 for p in clearance_permits if p.current_stage == 'Head')


    return render_template(
        'admin/departmentpermit.html',
        title="Department Permits",
        leave_permits=leave_permits,
        travel_orders=travel_orders,
        clearance_permits=clearance_permits,
        coe_permits=coe_permits,
        pending_leave_count=pending_leave_count,
        pending_travel_count=pending_travel_count,
        pending_clearance_count=pending_clearance_count
    )





@app.route('/admin/Mayors/permit', methods=['GET', 'POST'])
@login_required
def admindepartmentMayorspermit():
    # ✅ Mayor sees ALL permits (not limited to department)
    
    # LEAVE PERMITS
    leave_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Leave',
            PermitRequest.current_stage.in_(['Mayor', 'Completed', 'Rejected'])
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

     # Attach latest rejection history + user name to each leave permit
    for permit in leave_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name              # 👈 attach rejector’s name
            permit.rejected_remarks = history.remarks   # 👈 attach remarks if needed
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # TRAVEL ORDERS
    travel_orders = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Travel Order',
            PermitRequest.current_stage.in_(['Mayor', 'Completed', 'Rejected'])
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

        # Attach latest rejection history + user name to each travel order
    for permit in travel_orders:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name          # name of rejector
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # CLEARANCE FORMS
    clearance_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Clearance Form',
            PermitRequest.current_stage.in_(['Mayor', 'Completed', 'Rejected'])
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

         # Attach latest rejection history + user name to each clearance permit 👇
    for permit in clearance_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # COE (no Head approval, but still show if it reaches Mayor or completed)
    coe_permits = (
        PermitRequest.query
        .filter(
            PermitRequest.permit_type == 'Certification of Employment',
            PermitRequest.current_stage.in_(['Mayor', 'Completed'])
        )
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Count pending items for Mayor badges
    pending_leave_count = sum(1 for p in leave_permits if p.current_stage == 'Mayor')
    pending_travel_count = sum(1 for p in travel_orders if p.current_stage == 'Mayor')
    pending_clearance_count = sum(1 for p in clearance_permits if p.current_stage == 'Mayor')


    return render_template(
        'admin/mayorRequest.html',
        title="Mayor Permits",
        leave_permits=leave_permits,
        travel_orders=travel_orders,
        clearance_permits=clearance_permits,
        coe_permits=coe_permits,
        pending_leave_count=pending_leave_count,
        pending_travel_count=pending_travel_count,
        pending_clearance_count=pending_clearance_count
    )


@app.route('/admin/inbox', methods=['GET', 'POST'])
@login_required
@role_required('head')
def admininbox():
    all_users = Users.query.all()

    grouped_users = defaultdict(list)
    for user in all_users:
        if user.id == current_user.id:
            continue
        if user.employee and user.employee.department:
            dept_name = user.employee.department.name
        else:
            dept_name = "No Department"
        grouped_users[dept_name].append(user)

    inbox_messages = UserMessage.query.filter_by(
        recipient_id=current_user.id,
        is_deleted=False,
        is_sent_copy=False
    ).order_by(UserMessage.timestamp.desc()).all()

    # Generate correct ipcr_link per message
    for msg in inbox_messages:
        msg.ipcr_link = None  # default
        if msg.message_type == "ipcr_submission":
            match = re.search(r"period '([^']+)'", msg.body)
            if match and msg.sender and msg.sender.employee:
                period_name = match.group(1)
                employee_id = msg.sender.employee.id

                ipcr = (
                    IPCR.query
                    .join(IPCR.period)
                    .filter(
                        IPCR.submitted == True,
                        IPCR.graded == False,
                        EvaluationPeriod.name == period_name,
                        IPCR.employee_id == employee_id
                    )
                    .first()
                )

                if ipcr:
                    msg.ipcr_link = url_for("HeadGradeIpcr", ipcr_id=ipcr.id)


    sent_messages = UserMessage.query.filter_by(
        sender_id=current_user.id,
        is_sent_copy=True,
        is_deleted=False
    ).order_by(UserMessage.timestamp.desc()).all()

    trash_messages = UserMessage.query.filter(
        UserMessage.is_deleted == True,
        or_(
            and_(
                UserMessage.recipient_id == current_user.id,
                UserMessage.is_sent_copy == False
            ),
            and_(
                UserMessage.sender_id == current_user.id,
                UserMessage.is_sent_copy == True
            )
        )
    ).order_by(UserMessage.timestamp.desc()).all()

    unread_messages = UserMessage.query.options(
        joinedload(UserMessage.sender)
    ).filter_by(
        recipient_id=current_user.id,
        is_read=False,
        is_deleted=False,
        is_sent_copy=False
    ).order_by(UserMessage.timestamp.desc()).limit(5).all()

    unread_count = UserMessage.query.filter_by(
        recipient_id=current_user.id,
        is_read=False,
        is_deleted=False,
        is_sent_copy=False
    ).count()

    # Get the current user's position title
    position_title = ''
    if current_user.employee:
        if current_user.employee.permanent_details:
            position_title = current_user.employee.permanent_details.position.title
        elif current_user.employee.casual_details:
            position_title = current_user.employee.casual_details.position.title
        elif current_user.employee.job_order_details:
            position_title = current_user.employee.job_order_details.position.title

    return render_template(
        'admin/admininbox.html',
        title="Inbox",
        grouped_users=grouped_users,
        inbox=inbox_messages,
        sent=sent_messages,
        trash=trash_messages,
        unread_messages=unread_messages,
        unread_count=unread_count,
        position_title=position_title
    )



@app.route('/admin/report', methods=['GET', 'POST'])
@login_required
@role_required('head')
def adminreport():
    return render_template('admin/adminreport.html', title="report")


@app.route('/admin/myprofile', methods=['GET', 'POST'])
@login_required
@role_required('head')
def adminaccount():
    form = UpdateSuperAdminProfileForm()
    employee = current_user.employee

    # Pre-fill form on GET
    if request.method == 'GET':
        if employee:
            form.first_name.data = employee.first_name
            form.middle_name.data = employee.middle_name
            form.last_name.data = employee.last_name

            # Pre-fill permanent details if they exist
            if employee.permanent_details:
                form.date_of_birth.data = employee.permanent_details.date_of_birth
                form.gender.data = employee.permanent_details.sex
                form.tin.data = employee.permanent_details.tin

        form.email.data = current_user.email

    # Handle form submission
    if form.submit.data and form.validate_on_submit():
        if employee:
            # Update employee details
            employee.first_name = form.first_name.data
            employee.middle_name = form.middle_name.data
            employee.last_name = form.last_name.data

            # Update permanent details
            if employee.permanent_details:
                employee.permanent_details.date_of_birth = form.date_of_birth.data
                employee.permanent_details.sex = form.gender.data
                employee.permanent_details.tin = form.tin.data

            # Combine first, middle, and last name (skip empty values)
            full_name = " ".join(filter(None, [
                form.first_name.data,
                form.middle_name.data,
                form.last_name.data
            ]))
            current_user.name = full_name

        # Update email
        current_user.email = form.email.data

        # Update profile picture if uploaded
        if form.image_file.data:
            picture_file = save_picture(form.image_file.data)
            current_user.image_file = picture_file

        # ✅ Save digital signature with transparency
        if form.signature_file.data:
            sig_file = form.signature_file.data

            # Process signature → make transparent
            transparent_img = make_signature_transparent(sig_file)

            # Save to memory buffer as PNG
            img_io = io.BytesIO()
            transparent_img.save(img_io, format="PNG")
            sig_bytes = img_io.getvalue()

            # Compute SHA256 hash
            sig_hash = hashlib.sha256(sig_bytes).hexdigest()

            if current_user.signature_record:
                current_user.signature_record.signature = sig_bytes
                current_user.signature_record.signature_hash = sig_hash
            else:
                signature_record = UserSignature(
                    user_id=current_user.id,
                    signature=sig_bytes,
                    signature_hash=sig_hash
                )
                db.session.add(signature_record)

        db.session.commit()
        flash('Your profile has been updated.', 'success-timed')
        return redirect(url_for('adminaccount'))

    # Fallback to current image or default
    image_filename = current_user.image_file if current_user.image_file else 'default.png'
    image_path = url_for('static', filename=f'img/avatars/{image_filename}')

    # 🔑 Get user signature as base64 (for preview)
    signature_data = None
    if current_user.signature_record:
        sig_bytes = current_user.signature_record.signature
        signature_data = "data:image/png;base64," + base64.b64encode(sig_bytes).decode("utf-8")

    return render_template(
        'admin/adminaccount.html',
        title="Profile",
        form=form,
        image_file=image_path,
        signature_data=signature_data
    )



@app.route('/admin/Update/Password', methods=['GET', 'POST'])
@login_required
@role_required('head')
def adminUpdatePasst():
    form2 = UpdateSuperAdminPasswordForm()

    if request.method == 'POST' and form2.validate_on_submit():
        # Check current password
        if not bcrypt.check_password_hash(current_user.password_hash, form2.current_password.data):
            flash('Incorrect current password. Please try again.', 'danger')
        else:
            # Update password
            new_hashed_password = bcrypt.generate_password_hash(form2.password.data).decode('utf-8')
            current_user.password_hash = new_hashed_password
            current_user.must_reset_password = False
            db.session.commit()
            flash('Your password has been updated.', 'success-timed')
            return redirect(url_for('adminUpdatePasst'))

    # Query login attempts for the current user
    logins = LoginActivity.query.filter_by(user_id=current_user.id).order_by(LoginActivity.timestamp.desc()).all()

    return render_template('admin/resetpass.html', title="Update Password", form2=form2, logins=logins)


@app.route('/Head/IPCR/Periods', methods=['GET', 'POST'])
@login_required
@role_required('head')
def adminIPCRPeriod():
    # Get the logged-in user's department
    department = current_user.employee.department

    # Employees in this department (same filtering as DepartmentOPCR)
    permanent_employees = Employee.query.filter(
        Employee.department_id == department.id,
        Employee.is_deleted == False,
        Employee.employment_status == 'active',
        Employee.permanent_details.has(),
        ~Employee.permanent_details.has(PermanentEmployeeDetails.position.has(Position.type.ilike('head')))
    ).all()

    casual_employees = Employee.query.join(CasualEmployeeDetails).filter(
        CasualEmployeeDetails.assigned_department_id == department.id,
        Employee.is_deleted == False,
        Employee.employment_status == 'active'
    ).all()

    employees = permanent_employees + casual_employees
    employee_ids = [emp.id for emp in employees]


    # Fetch evaluation periods where these employees have IPCRs
    ipcr_periods = (
    EvaluationPeriod.query
    .order_by(EvaluationPeriod.start_date.desc())
    .all()
    )


    # Build results like DepartmentOPCR
    periods_data = []
    for period in ipcr_periods:
        ipcrs = IPCR.query.filter(
            IPCR.employee_id.in_(employee_ids),
            IPCR.period_id == period.id
        ).all()

        ipcr_total = len(employees)
        ipcr_submitted_count = sum(1 for ipcr in ipcrs if ipcr.submitted)
        ipcr_not_submitted_count = ipcr_total - ipcr_submitted_count
        ipcr_graded_count = sum(1 for ipcr in ipcrs if ipcr.submitted and ipcr.graded)

        status = "completed" if ipcr_total > 0 and ipcr_graded_count == ipcr_total else "incomplete"

        print(f"\n[DEBUG] Period: {period.name} ({period.start_date} - {period.end_date})")
        print(f"  Total={ipcr_total}, Submitted={ipcr_submitted_count}, "
              f"Not Submitted={ipcr_not_submitted_count}, Graded={ipcr_graded_count}, Status={status}")

        periods_data.append({
            'period': period,
            'ipcr_total': ipcr_total,
            'ipcr_submitted': ipcr_submitted_count,
            'ipcr_not_submitted': ipcr_not_submitted_count,
            'ipcr_graded': ipcr_graded_count,
            'status': status
        })

    return render_template(
        'admin/IPCR_Period_Record.html',
        title="IPCR Period Record",
        periods_data=periods_data
    )



@app.route("/Head/travel", methods=['GET'])
@login_required
@role_required('head')
def travel_logs_head():
    search = request.args.get('search', '').strip()
    head_department_id = current_user.employee.department_id  

    # Base query: logs for employees in head's department
    query = (
        db.session.query(TravelLog)
        .join(TravelOrder)
        .join(PermitRequest)
        .join(Employee)
        .options(
            joinedload(TravelLog.travel_order)
            .joinedload(TravelOrder.permit)
            .joinedload(PermitRequest.employee)
        )
        .filter(Employee.department_id == head_department_id)
    )

    if search:
        like = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(Employee.first_name).ilike(like),
                func.lower(Employee.last_name).ilike(like),
                func.lower(Employee.middle_name).ilike(like),
                func.lower(TravelOrder.destination).ilike(like),
                func.lower(TravelOrder.purpose).ilike(like),
                func.lower(TravelLog.tracking_id).ilike(like),
                func.lower(TravelLog.status).ilike(like),
                func.lower(func.concat(Employee.last_name, ', ', Employee.first_name)).ilike(like),
                func.lower(func.concat(Employee.first_name, ' ', Employee.last_name)).ilike(like),
            )
        )

    # Remove pagination: fetch all results
    logs = query.order_by(
        case((TravelLog.status == 'Approved', 1), else_=0),
        desc(TravelLog.tracking_id)
    ).all()

    return render_template(
        'admin/travellogs.html',
        title="Travel Logs",
        logs=logs,
        search=search
    )



def generate_ipcr_insight(ipcr_data):
    model = genai.GenerativeModel(model_name="gemini-2.0-flash")

    prompt = f"""
You are an expert evaluator tasked with reviewing an Individual Performance Commitment and Review (IPCR) report.

Based on the IPCR data below, analyze the individual's performance objectively. Your goal is to:
1. Summarize key accomplishments.
2. Highlight strong and weak areas.
3. Provide clear, actionable suggestions to improve future performance.
4. Recommend specific training programs, workshops, or certifications that align with areas of improvement.

IPCR Data:
{json.dumps(ipcr_data, indent=2)}

Respond ONLY in valid JSON with the following structure:

{{
  "summary": "A concise summary of the individual's performance (max 2-3 sentences).",
  "suggestions": [
    "Use specific, actionable items to improve performance.",
    "Avoid vague advice. Each suggestion should target a real issue in the data.",
    "Refer to measurable indicators if possible."
  ],
  "recommended_training": [
    "List relevant training programs or certifications (if any) that would help address performance gaps.",
    "These should align with the individual’s weak areas or job function.",
    "Can be technical skills, soft skills, or job-related qualifications."
  ]
}}

Ensure:
- The JSON is properly formatted.
- The suggestions are specific and constructive.
- The training recommendations are relevant and tailored.
"""
    return model.generate_content(prompt)




@app.route('/Head/Grade/IPCR/<int:ipcr_id>', methods=['GET', 'POST'])
@login_required
@role_required('head')
def HeadGradeIpcr(ipcr_id):
    ipcr = IPCR.query.get_or_404(ipcr_id)

    if request.method == 'POST':
        data = request.form.to_dict(flat=False)
        action = request.form.get('action')

        item_indexes = set()
        for key in data.keys():
            if key.startswith('items[') and '][' in key:
                idx = key.split('[')[1].split(']')[0]
                item_indexes.add(idx)

        all_ratings_filled = True

        for idx in sorted(item_indexes, key=int):
            item_id = request.form.get(f'items[{idx}][item_id]')
            rating_q = request.form.get(f'items[{idx}][rating_q]')
            rating_e = request.form.get(f'items[{idx}][rating_e]')
            rating_t = request.form.get(f'items[{idx}][rating_t]')
            rating_a = request.form.get(f'items[{idx}][rating_a]')
            remarks = request.form.get(f'items[{idx}][remarks]')

            if not all([rating_q, rating_e, rating_t, rating_a]):
                all_ratings_filled = False

            item = SectionItem.query.get(item_id)
            if item:
                item.rating_q = float(rating_q) if rating_q else None
                item.rating_e = float(rating_e) if rating_e else None
                item.rating_t = float(rating_t) if rating_t else None
                item.rating_a = float(rating_a) if rating_a else None
                item.remarks = remarks

        if action == "submit" and all_ratings_filled:
            weights = {'Core': 0.9, 'Support': 0.1}
            summary_counts = {'Core': 0, 'Support': 0}
            average_ratings = {}

            for section in ipcr.sections:
                category = section.type
                if category in weights:
                    for item in section.section_items:
                        if item.rating_a is not None:
                            summary_counts[category] += 1
                            average_ratings.setdefault(category, []).append(float(item.rating_a))

            total_weighted = 0
            category_count = 0

            for category in ['Core', 'Support']:
                ratings = average_ratings.get(category, [])
                if ratings:
                    avg = sum(ratings) / len(ratings)
                    weighted = avg * weights[category]
                    total_weighted += weighted
                    category_count += 1

            if category_count > 0:
                final_average = round(total_weighted, 4)
                overall_rating = round(final_average, 2)
                ipcr.final_average_rating = final_average
                ipcr.final_overall_rating = overall_rating

                if overall_rating >= 4.5:
                    ipcr.adjective_rating = "Very Satisfactory"
                elif overall_rating >= 3.5:
                    ipcr.adjective_rating = "Satisfactory"
                elif overall_rating >= 2.5:
                    ipcr.adjective_rating = "Fair"
                elif overall_rating >= 1.5:
                    ipcr.adjective_rating = "Poor"
                else:
                    ipcr.adjective_rating = "Very Poor"
            else:
                ipcr.final_average_rating = None
                ipcr.final_overall_rating = None
                ipcr.adjective_rating = None

            ipcr.graded = True

            # Prepare data for AI Insight
            ipcr_data = {
                "employee": f"{ipcr.employee.first_name} {ipcr.employee.last_name}" if ipcr.employee else "Unknown",
                "period": str(ipcr.period.name) if hasattr(ipcr.period, 'name') else str(ipcr.period),
                "sections": []
            }

            for section in ipcr.sections:
                section_data = {
                    "title": section.type,
                    "items": []
                }
                for item in section.section_items:
                    section_data["items"].append({
                        "description": f"{item.mfo} - {item.success_indicator}",
                        "rating_q": item.rating_q,
                        "rating_e": item.rating_e,
                        "rating_t": item.rating_t,
                        "rating_a": item.rating_a,
                        "remarks": item.remarks
                    })
                ipcr_data["sections"].append(section_data)

            try:
                ai_response = generate_ipcr_insight(ipcr_data)
                clean_text = clean_json(ai_response.text)
                structured = json.loads(clean_text)

                summary = structured.get("summary")
                suggestions = structured.get("suggestions")
                training = structured.get("recommended_training")

            except Exception as e:
                summary = "AI insight could not be generated."
                suggestions = [f"Error: {str(e)}"]
                training = []

            insight = AIInsight.query.filter_by(ipcr_id=ipcr.id).first()
            if not insight:
                insight = AIInsight(ipcr_id=ipcr.id)

            insight.ai_summary = summary
            insight.ai_suggestion = json.dumps(suggestions) if isinstance(suggestions, list) else suggestions
            insight.ai_training_recommendations = json.dumps(training) if isinstance(training, list) else training
            insight.last_updated = datetime.utcnow()

            db.session.add(insight)
            db.session.commit()

            dept = None
            if ipcr.employee:
                if ipcr.employee.permanent_details:
                    dept = ipcr.employee.department  # Permanent employees use department_id
                elif ipcr.employee.casual_details:
                    dept = ipcr.employee.casual_details.assigned_department  # Casual employees use assigned_department_id

            # ✅ Notify HR only if department is resolved
            if dept:
                notify_hr_if_department_complete(dept, ipcr.period_id, current_user.id)

            flash("IPCR submitted and AI Insight generated!", "success-timed")
            return redirect(url_for('HeadPerformance'))

                    
        elif action == "draft":
            ipcr.graded = False
            db.session.commit()
            flash("Draft saved successfully.", "info-timed")
            return redirect(url_for('HeadGradeIpcr', ipcr_id=ipcr.id))

        elif action == "submit" and not all_ratings_filled:
            flash("All ratings must be filled to submit.", "danger-timed")
            return redirect(url_for('HeadGradeIpcr', ipcr_id=ipcr.id))
        
        elif action == "return":
            ipcr.submitted = False
            db.session.commit()
            flash("IPCR has been returned to the employee for revision.", "success-timed")
            return redirect(url_for('HeadPerformance'))  # or any page you want to go back to

    sections = ipcr.sections
    return render_template('admin/GradeIPCR.html', title="Grade IPCR", ipcr=ipcr, sections=sections)



def notify_hr_if_department_complete(dept, period_id, sender_id):

                # ✅ Permanent employees
                permanent_employees = Employee.query.filter(
                    Employee.department_id == dept.id,
                    Employee.is_deleted == False,
                    Employee.employment_status == 'active',
                    Employee.permanent_details.has(),
                    ~Employee.permanent_details.has(
                        PermanentEmployeeDetails.position.has(Position.type.ilike('head'))
                    )
                ).all()

                # ✅ Casual employees
                casual_employees = Employee.query.join(CasualEmployeeDetails).filter(
                    CasualEmployeeDetails.assigned_department_id == dept.id,
                    Employee.is_deleted == False,
                    Employee.employment_status == 'active'
                ).all()

                employees = permanent_employees + casual_employees
                employee_ids = [emp.id for emp in employees]
                ipcr_total = len(employees)

                # ✅ Fetch IPCRs for this dept and period
                ipcrs = IPCR.query.filter(
                    IPCR.employee_id.in_(employee_ids),
                    IPCR.period_id == period_id
                ).all()

                ipcr_submitted_count = sum(1 for ipcr in ipcrs if ipcr.submitted)
                ipcr_not_submitted_count = ipcr_total - ipcr_submitted_count
                ipcr_graded_count = sum(1 for ipcr in ipcrs if ipcr.submitted and ipcr.graded)



                # ✅ Determine status
                status = "completed" if ipcr_total > 0 and ipcr_graded_count == ipcr_total else "incomplete"

                # ✅ Only send message if completed
                if status == "completed":
                    period = EvaluationPeriod.query.get(period_id)
                    period_name = period.name if period else f"Period {period_id}"

                    # Prevent duplicates
                    existing_msg = UserMessage.query.filter_by(
                        subject=f"Department {dept.name} - IPCR Completed"
                    ).first()
                    if existing_msg:
                        return

                    # Notify HR
                    hr_users = Users.query.filter(Users.role == "HR").all()
                    hr_users = [hr for hr in hr_users if hr.has_permission("write_performance")]

                    for hr in hr_users:
                        subject = f"Department {dept.name} - IPCR Completed"
                        body = f"""
                        📢 <strong>IPCR Completion Notice</strong><br><br>
                        <p>Dear <strong>{hr.name}</strong>,</p>
                        <p>The <strong>{dept.name}</strong> division has completed all IPCR submissions 
                        and grading for the evaluation period <strong>{period_name}</strong>.</p>
                        <p><strong>Total Employees:</strong> {ipcr_total}</p>
                        <p><strong>Graded:</strong> {ipcr_graded_count}</p>
                        <p>You may now review this department’s IPCR records in the system.</p>
                        <hr>
                        <p><em>⚠ This is an automated message. Please do not reply.</em></p>
                        <p>– HR System</p>
                        """

                        db.session.add(UserMessage(
                            sender_id=sender_id,
                            recipient_id=hr.id,
                            subject=subject,
                            body=body,
                            message_type="system"
                        ))
                        print(f"✅ Notification prepared for HR: {hr.name}")

                    db.session.commit()


@app.route('/Head/View/IPCR/<int:ipcr_id>', methods=['GET', 'POST'])
@login_required
@role_required('head')
def HeadViewIpcr(ipcr_id):
    # Get the IPCR record
    ipcr = IPCR.query.get_or_404(ipcr_id)
    sections = ipcr.sections
    employee = ipcr.employee
    
    if employee.casual_details and employee.casual_details.assigned_department:
        department = employee.casual_details.assigned_department
    else:
        department = employee.department

    # --- Selected period for template ---
    # Assuming your IPCR model has a relationship to EvaluationPeriod
    selected_period = getattr(ipcr, 'evaluation_period', None)

    # --- Summary and averages ---
    summary_counts = {'Core': 0, 'Support': 0}
    average_ratings = {}
    weights = {'Core': 0.9, 'Support': 0.1}  # adjust if needed

    for section in sections:
        category = section.type
        if category in summary_counts:
            for item in section.section_items:
                if item.rating_a is not None:
                    summary_counts[category] += 1
                    average_ratings.setdefault(category, []).append(float(item.rating_a))

    final_average = {}
    total_weighted = 0
    category_count = 0
    average_values = []

    for category in ['Core', 'Support']:
        ratings = average_ratings.get(category, [])
        count = summary_counts[category]

        if ratings:
            total = sum(ratings)
            avg = round(total / len(ratings), 2)
            weighted = round(avg * weights[category], 4)
            computation = f"{' + '.join(map(str, ratings))} = {total} ÷ {len(ratings)} = {avg} × {weights[category]} = {weighted}"
            total_weighted += weighted
            average_values.append(avg)
            category_count += 1
        else:
            avg = None
            weighted = None
            computation = "-"

        final_average[category] = {
            'count': count,
            'average': avg,
            'weighted': weighted,
            'computation': computation
        }

    final_overall = round(total_weighted, 4) if category_count > 0 else None
    average_rating = round(final_overall, 2) if final_overall is not None else None

    # --- Convert numeric average to adjective ---
    def get_adjective(rating):
        if rating is None:
            return "-"
        elif rating >= 4.5:
            return "Very Satisfactory"
        elif rating >= 3.5:
            return "Satisfactory"
        elif rating >= 2.5:
            return "Fair"
        elif rating >= 1.5:
            return "Poor"
        else:
            return "Very Poor"

    adjective_rating = get_adjective(average_rating)
    

     # --- NEW: Build workflow ---
    dept_head = (
        Employee.query
        .join(PermanentEmployeeDetails)
        .join(Position)
        .filter(
            Employee.department_id == employee.department_id,  # same department as IPCR owner
            Position.type == 'Head',                          # must be a Department Head
            Employee.is_deleted == False                      # exclude deleted employees
        )
        .first()
    )

        # HR Staff (non-head)
    hr_staff = (
        Employee.query
        .join(Users, Employee.user)                # join employee → user
        .join(UserPermission, Users.permissions)   # join user → permissions
        .join(PermanentEmployeeDetails)
        .join(Position)
        .filter(
            Employee.department_id == 15,
            Position.type != 'Head',                     # not the HR head
            UserPermission.permission == 'write_performance',  # must have this permission
            UserPermission.is_allowed == True,           # and it must be allowed
            Employee.is_deleted == False
        )
        .all()
    )


        # HR Head
    hr_head = (
            Employee.query
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(
                Position.id == 98,
                Employee.is_deleted == False
            )
            .first()
    )

  # 🧾 Define the "Assessed By" positions per line
    positions = [
        ["MUNICIPAL PLANNING AND DEVELOPMENT COORDINATOR I"],  # Line 1
        ["MUNICIPAL GOVERNMENT DEPARTMENT HEAD I (LDRRMO)"], 
        ["MUNICIPAL BUDGET OFFICER I"],  # Line 2
        ["MUNICIPAL TREASURER"],  # Line 3
        ["MUNICIPAL ACCOUNTANT"],
        ["MUNICIPAL GOVERNMENT DEPARTMENT HEAD I"],  # Line 4
    ]

    # 🧾 Helper function to get name by position title
    def get_permanent_employee_name_by_position(position_title):
        # ✅ Special override
        if position_title == "MUNICIPAL GOVERNMENT DEPARTMENT HEAD I (LDRRMO)":
            return "Aldwin D. Aloquin"

        # 🔍 Default DB lookup
        emp = (
            db.session.query(Employee)
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(Position.title == position_title)
            .filter(Employee.is_deleted == False)
            .first()
        )
        if emp:
            middle_initial = f"{emp.middle_name[0].upper()}." if emp.middle_name else ""
            return f"{emp.first_name} {middle_initial} {emp.last_name}".strip()
        return "(Not Found)"


    # 🧾 Build "Assessed By" list
    assessed_by = []
    for line in positions:
        line_data = []
        for pos_title in line:
            name = get_permanent_employee_name_by_position(pos_title)
            line_data.append({
                "position": pos_title,
                "name": name
            })
        assessed_by.append(line_data)


    # 🧭 Workflow steps
    workflow = [
        {
            "step": 1,
            "name": f"{employee.first_name} {employee.middle_name or ''} {employee.last_name}",
            "position": employee.permanent_details.position.title if employee.permanent_details and employee.permanent_details.position else "",
            "description": "Submit IPCR form to Department Head."
        },
        {
            "step": 2,
            "name": f"{dept_head.first_name} {dept_head.middle_name or ''} {dept_head.last_name}" if dept_head else "-",
            "position": dept_head.permanent_details.position.title if dept_head and dept_head.permanent_details and dept_head.permanent_details.position else "",
            "description": "Grade IPCR form and provide feedback if needed."
        },
        {
            "step": 3,
            "assessed_by": assessed_by,
            "description": "Assess and review graded IPCR form before final HR validation."
        },
        {
            "step": 4,
            "staff": [
                {
                    "name": f"{staff.first_name} {staff.middle_name or ''} {staff.last_name}",
                    "position": staff.permanent_details.position.title if staff.permanent_details and staff.permanent_details.position else ""
                }
                for staff in hr_staff
            ] if hr_staff else [],
            "description": "Receive submission, check completeness, and forward to HR Head."
        },
        {
            "step": 5,
            "name": f"{hr_head.first_name} {hr_head.middle_name or ''} {hr_head.last_name}" if hr_head else "-",
            "position": hr_head.permanent_details.position.title if hr_head and hr_head.permanent_details and hr_head.permanent_details.position else "",
            "description": "Consolidate graded IPCR forms in the system for compliance and reporting."
        },
    ]
    

    # --- Render template with all required variables ---
    return render_template(
        'admin/IPCREmpView.html',
        title="View IPCR",
        ipcr=ipcr,
        sections=sections,
        employee=employee,
        department=department,
        final_average=final_average,
        final_overall=final_overall,
        average_rating=average_rating,
        adjective_rating=adjective_rating,
        selected_period=selected_period, #prevents the UndefinedError
        workflow=workflow  # pass workflow to template
    )




# newheadreport
@app.route("/head/Report/Issue")
@login_required
@role_required('head')
def HeadIssue():
    search = request.args.get('search', '').strip()

    # Base query: only reports created by current user
    query = IssueReport.query.filter_by(reporter_user_id=current_user.id)

    if search:
        like_pattern = f"%{search}%"

        # Safe joins
        query = query.join(Users, IssueReport.reported_user_id == Users.id)\
                     .outerjoin(Employee, Users.employee_id == Employee.id)

        # Add filter
        query = query.filter(
            or_(
                IssueReport.title.ilike(like_pattern),
                IssueReport.description.ilike(like_pattern),
                IssueReport.status.ilike(like_pattern),
                Users.name.ilike(like_pattern),
                Employee.first_name.ilike(like_pattern),
                Employee.last_name.ilike(like_pattern),
                func.concat(Employee.first_name, ' ', Employee.last_name).ilike(like_pattern)
            )
        )

    # Get all results without pagination
    issues = query.order_by(IssueReport.created_at.desc()).all()

    return render_template(
        'admin/issueReport.html',
        title="Issue",
        issues=issues,
        search=search
    )






@app.route('/head/report-issue', methods=['POST'])
@login_required
@role_required('head')
def Headreport_issue():
    employee_id = request.form.get('employee')  # Employee.id from the form
    title = request.form.get('title')
    description = request.form.get('description')


    if not employee_id or not title or not description:
        flash('All fields are required.', 'danger')
        return redirect(request.referrer or url_for('HeadIssue'))

    # Get the Employee record (make sure not deleted)
    employee = Employee.query.filter_by(id=employee_id, is_deleted=False).first()
    if not employee:
        flash('Employee not found.', 'danger')
        return redirect(request.referrer or url_for('HeadIssue'))

    # Get the User linked to the Employee
    user = Users.query.filter_by(employee_id=employee.id).first()
    if not user:
        flash('User account for this employee not found.', 'danger')
        return redirect(request.referrer or url_for('HeadIssue'))

    reported_user_id = user.id  # The actual Users.id foreign key

    # Prevent self-reporting
    if reported_user_id == current_user.id:
        flash("You cannot report yourself.", "danger")
        return redirect(request.referrer or url_for('HeadIssue'))

    # Create and save the issue report
    issue = IssueReport(
        reporter_user_id=current_user.id,
        reported_user_id=reported_user_id,
        title=title,
        description=description
    )

    db.session.add(issue)
    db.session.commit()


     # --- Notify HR ---
    hr_users = Users.query.filter_by(role='hr').all()
    for hr in hr_users:
        hr_subject = f"Issue Report: {title}"
        
        # Avoid duplicate notifications for the same subject
        existing_msg_to_hr = UserMessage.query.filter_by(
            recipient_id=hr.id,
            subject=hr_subject
        ).first()
        if existing_msg_to_hr:
            continue

        hr_body = f"""📢 <strong>New Issue Report</strong><br><br>

        <p>Dear <strong>{hr.name}</strong>,</p>

        <p><strong>{current_user.name}</strong> has reported an issue against 
        <strong>{employee.first_name} {employee.last_name}</strong>.</p>

        <p><strong>Title:</strong> {title}</p>
        <p><strong>Description:</strong>{description}</p>

        <p>Please review this issue in the HR system.</p>

        <hr>
        <p><em>⚠ This is an automated message. Please do not reply.</em></p>
        <p>– HR System</p>
        """

        db.session.add(UserMessage(
            sender_id=current_user.id,   # or system user_id (e.g., 1)
            recipient_id=hr.id,
            subject=hr_subject,
            body=hr_body,
            message_type='system'
        ))

    db.session.commit()

    flash('Issue report submitted successfully!', 'success-timed')
    return redirect(url_for('HeadIssue'))








@app.route("/Head/Employee/Detail", methods=['GET'])
@login_required
@role_required('head')
def HeadEmployeeDetail():
    employee_id = request.args.get('id')

    if not employee_id:
        flash("Employee not found.", "danger")
        return redirect(url_for('EmployeeSection'))

    # Fetch main employee
    employee = Employee.query.get_or_404(employee_id)

    # Try fetching specific details
    permanent_details = PermanentEmployeeDetails.query.filter_by(employee_id=employee.id).first()
    casual_details = CasualEmployeeDetails.query.filter_by(employee_id=employee.id).first()
    job_order_details = JobOrderDetails.query.filter_by(employee_id=employee.id).first()


    # Fetch granted benefits if permanent
    benefits = []
    if permanent_details:
        benefits = PermanentEmployeeBenefitEligibility.query.filter_by(
            permanent_employee_id=permanent_details.id,
            is_eligible=True
        ).order_by(PermanentEmployeeBenefitEligibility.eligibility_years.asc()).all()


    # Fetch latest IPCR for this employee
    latest_ipcr = IPCR.query.filter_by(employee_id=employee.id).order_by(desc(IPCR.id)).first()

    eligible_for_bonus = False
    bonus_period_name = None
    if latest_ipcr and latest_ipcr.adjective_rating:
        if latest_ipcr.adjective_rating.strip().lower() == "very satisfactory":
            eligible_for_bonus = True
            bonus_period_name = latest_ipcr.period.name if latest_ipcr.period else "Unknown Period"


    # Initialize defaults
    ai_summary = None
    ai_suggestions = None
    ai_training_recommendations = None

    # If there is an IPCR, check for AI insights
    if latest_ipcr and latest_ipcr.ai_insight:
        ai_summary = latest_ipcr.ai_insight.ai_summary
        try:
            ai_suggestions = json.loads(latest_ipcr.ai_insight.ai_suggestion or "[]")
        except Exception:
            ai_suggestions = [latest_ipcr.ai_insight.ai_suggestion] if latest_ipcr.ai_insight.ai_suggestion else []

        try:
            ai_training_recommendations = json.loads(latest_ipcr.ai_insight.ai_training_recommendations or "[]")
        except Exception:
            ai_training_recommendations = [latest_ipcr.ai_insight.ai_training_recommendations] if latest_ipcr.ai_insight.ai_training_recommendations else []


    # Second chart: Q/E/T/A per MFO
    chart_data_mfo = {
        "categories": [],
        "series": [
            {"name": "Quality (Q)", "data": []},
            {"name": "Efficiency (E)", "data": []},
            {"name": "Timeliness (T)", "data": []},
            {"name": "Average (A)", "data": []}
        ]
    }

    if latest_ipcr:
        for section in latest_ipcr.sections:
            mfo_label = f"{section.type} - {latest_ipcr.period.name}"
            chart_data_mfo["categories"].append(mfo_label)

            rating_q, rating_e, rating_t, rating_a = [], [], [], []
            for item in section.section_items:
                if item.rating_q is not None:
                    rating_q.append(item.rating_q)
                if item.rating_e is not None:
                    rating_e.append(item.rating_e)
                if item.rating_t is not None:
                    rating_t.append(item.rating_t)
                if item.rating_a is not None:
                    rating_a.append(item.rating_a)

            def avg(ratings):
                return round(sum(ratings) / len(ratings), 2) if ratings else 0

            chart_data_mfo["series"][0]["data"].append(avg(rating_q))
            chart_data_mfo["series"][1]["data"].append(avg(rating_e))
            chart_data_mfo["series"][2]["data"].append(avg(rating_t))
            chart_data_mfo["series"][3]["data"].append(avg(rating_a))

    # IPCR chart data for trend line
    ipcr_list = IPCR.query.options(
        joinedload(IPCR.period),
        joinedload(IPCR.sections).joinedload(EvaluationSection.section_items)
    ).filter_by(employee_id=employee.id) \
     .join(EvaluationPeriod) \
     .order_by(EvaluationPeriod.start_date).all()

    chart_data = []
    for ipcr in ipcr_list:
        rating_a_values = [
            item.rating_a for section in ipcr.sections
            for item in section.section_items if item.rating_a is not None
        ]
        avg_rating_a = round(sum(rating_a_values) / len(rating_a_values), 2) if rating_a_values else 0
        chart_data.append({
            "period": ipcr.period.name if ipcr.period else "N/A",
            "rating_a": avg_rating_a
        })

    casual_history = []
    if casual_details:
        casual_history = CasualEmployeeHistory.query.filter_by(employee_id=employee.id) \
            .order_by(CasualEmployeeHistory.contract_start.desc()).all()    

    termination_history = EmploymentTerminationHistory.query.filter_by(
    employee_id=employee.id
    ).order_by(EmploymentTerminationHistory.terminated_at.desc()).all()

    return render_template(
        'admin/DetailEmployee.html', 
        title="Employee Details",
        employee=employee,
        permanent_details=permanent_details,
        casual_details=casual_details,
        job_order_details=job_order_details,
        latest_ipcr=latest_ipcr,
        ai_summary=ai_summary,
        ai_suggestions=ai_suggestions,
        ai_training_recommendations=ai_training_recommendations,
         chart_data=chart_data,
         benefits=benefits,
        chart_data_mfo=chart_data_mfo,
        eligible_for_bonus=eligible_for_bonus,
        bonus_period_name=bonus_period_name,
        casual_history=casual_history,
        termination_history=termination_history
    )


@app.route("/Head/Calendar", methods=['GET'])
@login_required
@role_required('head')
def CalendarHead():
    now = datetime.utcnow()
    current_day = now.strftime('%A')  # e.g., Wednesday
    current_date = now.strftime('%d %b, %Y')  # e.g., 25 Jul, 2025

    # Query only active (ongoing or future) events
    active_events = CalendarEvent.query.filter(
        (CalendarEvent.end_date == None) | (CalendarEvent.end_date >= now)
    ).all()

    # Count how many events exist per label
    event_counts = defaultdict(int)
    for event in active_events:
        event_counts[event.label] += 1

    return render_template(
        'admin/calendarAdmin.html', 
        title="Calendar",
        current_day=current_day,
        current_date=current_date,
        event_counts=event_counts
    )



@app.route("/Head/Credit")
@login_required
@role_required('head')
def HeadCredit():
    head_employee = current_user.employee
    if not head_employee or not head_employee.department:
        flash("You are not assigned to any department.", "warning")
        return redirect(url_for("homeHead"))

    department = head_employee.department

    # Get all active employees in the head's department
    employees = Employee.query.filter(
    Employee.employment_status == 'active',
    Employee.is_deleted == False,
    or_(
        Employee.department_id == department.id,  # permanent & job order
        Employee.casual_details.has(assigned_department_id=department.id)  # casuals
    )
    ).all()

    employee_credits = []
    transactions_by_employee = defaultdict(list)

    # Totals for department
    total_vacation_earned = 0
    total_vacation_used = 0
    total_vacation_remaining = 0

    total_sick_earned = 0
    total_sick_used = 0
    total_sick_remaining = 0

    for emp in employees:
        # Skip Job Order employees
        if emp.job_order_details:
            continue

        # Skip casual employees not assigned to this department
        if emp.casual_details and emp.casual_details.assigned_department_id != department.id:
            continue

        # Vacation credits
        vacation_earned = sum(tx.amount for tx in emp.credit_transactions
                              if tx.action == "Earned" and tx.leave_type == "Vacation")
        vacation_used   = sum(tx.amount for tx in emp.credit_transactions
                              if tx.action == "Used"   and tx.leave_type == "Vacation")
        vacation_remaining = vacation_earned - vacation_used

        # Sick credits
        sick_earned = sum(tx.amount for tx in emp.credit_transactions
                          if tx.action == "Earned" and tx.leave_type == "Sick")
        sick_used   = sum(tx.amount for tx in emp.credit_transactions
                          if tx.action == "Used"   and tx.leave_type == "Sick")
        sick_remaining = sick_earned - sick_used

        # Add to department totals
        total_vacation_earned += vacation_earned
        total_vacation_used += vacation_used
        total_vacation_remaining += vacation_remaining

        total_sick_earned += sick_earned
        total_sick_used += sick_used
        total_sick_remaining += sick_remaining

        # Determine position
        if emp.permanent_details:
            position = emp.permanent_details.position.title
        elif emp.casual_details:
            position = emp.casual_details.position.title
        else:
            position = "-"

        # Append to employee summary
        employee_credits.append({
            "id": emp.id,
            "name": f"{emp.first_name} {emp.last_name}",
            "position": position,
            "vacation_earned": vacation_earned,
            "vacation_used": vacation_used,
            "vacation_remaining": vacation_remaining,
            "sick_earned": sick_earned,
            "sick_used": sick_used,
            "sick_remaining": sick_remaining,
        })

        # Collect transactions, sorted latest first
        txs = sorted(emp.credit_transactions, key=lambda tx: tx.timestamp, reverse=True)
        transactions_by_employee[emp.id] = txs

    return render_template(
        "admin/credithistory.html",
        title="Department Credits",
        department=department,
        employee_credits=employee_credits,
        transactions_by_employee=transactions_by_employee,
        # Totals
        total_vacation_earned=round(total_vacation_earned, 1),
        total_vacation_used=round(total_vacation_used, 1),
        total_vacation_remaining=round(total_vacation_remaining, 1),
        total_sick_earned=round(total_sick_earned, 1),
        total_sick_used=round(total_sick_used, 1),
        total_sick_remaining=round(total_sick_remaining, 1),
        total_employees=len(employees)
    )



# Employee Section
@app.route('/Employee/Home', methods=['GET', 'POST'])
@login_required
@role_required('employee')
def EmployeeHome():
    employee = Employee.query.filter_by(id=current_user.employee_id, is_deleted=False).first()
    if not employee:
        flash('Employee record not found.', 'danger')
        return redirect(url_for('logout'))

    # Get all IPCR entries for this employee, ordered by period
    ipcr_entries = IPCR.query.filter_by(employee_id=employee.id).order_by(IPCR.period_id).all()

    # Construct chart_data as a list of dicts with 'period' and 'rating_a'
    # Construct chart_data with average rating_a per period
    chart_data = []
    for ipcr in ipcr_entries:
        rating_a_list = []
        for section in ipcr.sections:
            for item in section.section_items:
                if item.rating_a is not None:
                    rating_a_list.append(item.rating_a)

        avg_rating_a = round(sum(rating_a_list) / len(rating_a_list), 2) if rating_a_list else 0

        period_name = ipcr.period.name if ipcr.period else f"Period {ipcr.period_id}"
        chart_data.append({
            'period': period_name,
            'rating_a': avg_rating_a
        })

    active_period = EvaluationPeriod.query.filter_by(is_active=True).first()
    ipcr_submission_open = False
    ipcr_submitted = False
    ipcr_status = "none"  # Default to no IPCR

    if active_period:
        ipcr_submission_open = True
        ipcr = IPCR.query.filter_by(employee_id=employee.id, period_id=active_period.id).first()
        if ipcr:
            if ipcr.graded:
                ipcr_status = "graded"
            elif ipcr.submitted:
                ipcr_submitted = True
                ipcr_status = "submitted"
            else:
                ipcr_status = "returned"


    permit_requests = PermitRequest.query.filter_by(employee_id=employee.id).order_by(PermitRequest.date_requested.desc()).all()


    # Inside your EmployeeHome route...

    latest_ipcr = IPCR.query.filter_by(employee_id=employee.id).order_by(IPCR.period_id.desc()).first()

    chart_data_mfo = {
        "categories": [],
        "series": [
            {"name": "Quality (Q)", "data": []},
            {"name": "Efficiency (E)", "data": []},
            {"name": "Timeliness (T)", "data": []},
            {"name": "Average (A)", "data": []}
        ],
        "rating_legend": [
        {"label": "Very Satisfactory (VS) 4.5 to 5.0"},
        {"label": "Satisfactory (S) 4.0 to 4.49"},
        {"label": "Fair (F) 3.5 to 3.99"},
        {"label": "Poor (P) 3.0 to 3.49"},
        {"label": "Very Poor (VP) below 3.0"}
    ]

    }

    if latest_ipcr:
        for section in latest_ipcr.sections:
            # Category label like: "Core - 2024 Q1"
            mfo_label = f"{section.type} - {latest_ipcr.period.name if latest_ipcr.period else 'Unknown Period'}"
            chart_data_mfo["categories"].append(mfo_label)

            rating_q, rating_e, rating_t, rating_a = [], [], [], []

            for item in section.section_items:
                if item.rating_q is not None:
                    rating_q.append(item.rating_q)
                if item.rating_e is not None:
                    rating_e.append(item.rating_e)
                if item.rating_t is not None:
                    rating_t.append(item.rating_t)
                if item.rating_a is not None:
                    rating_a.append(item.rating_a)

            def avg(ratings):
                return round(sum(ratings) / len(ratings), 2) if ratings else 0

            chart_data_mfo["series"][0]["data"].append(avg(rating_q))
            chart_data_mfo["series"][1]["data"].append(avg(rating_e))
            chart_data_mfo["series"][2]["data"].append(avg(rating_t))
            chart_data_mfo["series"][3]["data"].append(avg(rating_a))


            
    # AI Insight fields
    ai_summary = None
    ai_suggestions = None
    ai_training_recommendations = None

    if latest_ipcr and latest_ipcr.ai_insight:
        ai_insight = latest_ipcr.ai_insight
        ai_summary = ai_insight.ai_summary

        try:
            ai_suggestions = json.loads(ai_insight.ai_suggestion or "[]")
        except Exception:
            ai_suggestions = [ai_insight.ai_suggestion] if ai_insight.ai_suggestion else []

        try:
            ai_training_recommendations = json.loads(ai_insight.ai_training_recommendations or "[]")
        except Exception:
            ai_training_recommendations = [ai_insight.ai_training_recommendations] if ai_insight.ai_training_recommendations else []


    return render_template('users/UserHome.html',
                           title="Home",
                           ipcr_submission_open=ipcr_submission_open,
                           ipcr_submitted=ipcr_submitted,
                           ipcr_status=ipcr_status,
                           permit_requests=permit_requests,
                           chart_data=chart_data,
                           chart_data_mfo=chart_data_mfo,
                            ai_summary=ai_summary,
                           ai_suggestions=ai_suggestions,
                           ai_training_recommendations=ai_training_recommendations)  




@app.route('/Employee/Performance/Submit', methods=['GET', 'POST'])
@login_required
@role_required('employee')
def EmployeeSubmitIPCR():
    # Fetch the active evaluation period from the database
    active_period = EvaluationPeriod.query.filter_by(is_active=True).first()

    # Get the current employee's full name
    if current_user.employee:
        emp = current_user.employee
        full_name = f"{emp.first_name} {emp.middle_name or ''} {emp.last_name}".strip()
    else:
        full_name = "N/A"

    # Fetch the most recent IPCR
    last_ipcr = IPCR.query.filter_by(employee_id=current_user.employee.id) \
                          .order_by(IPCR.id.desc()).first()

    # Prepare prefill data
    prefill_data = []

    if last_ipcr:
        for section in last_ipcr.sections:
            for item in section.section_items:
                prefill_data.append({
                    "type": section.type,
                    "mfo": item.mfo or "",
                    "success_indicator": item.success_indicator or "",
                    "allotted_budget": item.allotted_budget or "",
                    "accomplishment": item.accomplishment or ""
                    })

    # Determine if the last IPCR was returned (drafted, not submitted or graded)
    force_prefill = False
    if last_ipcr and not last_ipcr.submitted and not last_ipcr.graded:
        force_prefill = True


    return render_template(
        'users/submitIPCR.html',
        title="Submit IPCR",
        active_period=active_period,
        full_name=full_name,
        prefill_data=prefill_data,
        force_prefill=force_prefill,
    )



@app.route('/Employee/Performance/Record', methods=['GET', 'POST'])
@login_required
@role_required('employee')
def EmployeeIPCRRecord():
    ipcrs = IPCR.query.filter_by(employee_id=current_user.employee.id).order_by(IPCR.id.desc()).all()

    return render_template('users/IPCRRecord.html', title="IPCR Record", ipcrs=ipcrs)



@app.route('/submit-ipcr', methods=['POST'])
@login_required
@role_required('employee')
def submit_ipcr():
    try:
        data = request.get_json()
        employee = current_user.employee

        # ✅ Get active period
        active_period = EvaluationPeriod.query.filter_by(is_active=True).first()
        if not active_period:
            flash("No active evaluation period found.", "danger")
            return jsonify({'error': 'No active evaluation period'}), 400

        # ✅ Find existing IPCR
        ipcr = IPCR.query.filter_by(employee_id=employee.id, period_id=active_period.id).first()

        # ✅ Determine if submission is late
        is_late = date.today() > active_period.end_date

        if ipcr:
            if ipcr.graded:
                flash("Cannot edit IPCR after it has been graded.", "warning")
                return jsonify({'error': 'IPCR already graded'}), 403

            # ✅ Delete old sections & items
            for section in ipcr.sections:
                SectionItem.query.filter_by(section_id=section.id).delete()
                db.session.delete(section)
        else:
            # ✅ Create new IPCR
            ipcr = IPCR(employee_id=employee.id, period_id=active_period.id)
            db.session.add(ipcr)
            db.session.flush()

        # ✅ Update submission status
        ipcr.submitted = True
        ipcr.late_submission = is_late
        first_submission = False

        if not ipcr.date_submitted:
            ipcr.date_submitted = datetime.utcnow()
            first_submission = True

        # ✅ Add all section data
        for section_data in data.get('sections', []):
            section_type = section_data.get('type', 'Unknown')
            section = EvaluationSection(type=section_type, ipcr_id=ipcr.id)
            db.session.add(section)
            db.session.flush()

            for item in section_data.get('items', []):
                accountable_name = f"{employee.last_name}, {employee.first_name} {employee.middle_name or ''}".strip()
                section_item = SectionItem(
                    section_id=section.id,
                    mfo=(item.get('mfo') or '').strip(),
                    success_indicator=(item.get('success_indicator') or '').strip(),
                    allotted_budget=(item.get('allotted_budget') or '').strip(),
                    accountable=accountable_name,
                    accomplishment=(item.get('accomplishment') or '').strip()
                )
                db.session.add(section_item)

        # ✅ Commit main IPCR and sections first
        db.session.commit()

        # ✅ Notify department head only on first submission
        if first_submission:
            head_users = Users.query.join(Employee, Users.employee_id == Employee.id).filter(
                Employee.department_id == employee.department_id,
                Users.role == 'head',
                Employee.employment_status == 'active'
            ).all()

            submission_status = "LATE" if ipcr.late_submission else "on time"

            for head_user in head_users:
                notif = UserMessage(
                    sender_id=current_user.id,
                    recipient_id=head_user.id,
                    subject="IPCR Submission Notification",
                    body=(
                        f"Please be informed that {employee.first_name} {employee.last_name} "
                        f"has submitted their IPCR for the period '{active_period.name}' "
                        f"({submission_status})."
                    ),
                    message_type='ipcr_submission',
                    timestamp=datetime.utcnow()
                )
                db.session.add(notif)

            db.session.commit()  # ✅ Commit notifications separately

        return jsonify({'redirect': url_for('EmployeeIPCRRecord')})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f"An error occurred: {str(e)}"}), 500




@app.route('/ipcr/view/<int:ipcr_id>')
@login_required
@role_required('employee')
def IPCRView(ipcr_id):
    ipcr = IPCR.query.get_or_404(ipcr_id)
    sections = ipcr.sections

    # Get employee and department for header info
    employee = ipcr.employee
    department = employee.department if employee else None

    summary_counts = {'Core': 0, 'Support': 0}
    average_ratings = {}
    weights = {'Core': 0.9, 'Support': 0.1}  # Adjust weights as needed

    for section in sections:
        category = section.type
        if category in summary_counts:
            for item in section.section_items:
                if item.rating_a is not None:
                    summary_counts[category] += 1
                    average_ratings.setdefault(category, []).append(float(item.rating_a))

    final_average = {}
    total_weighted = 0
    category_count = 0

    for category in ['Core', 'Support']:
        ratings = average_ratings.get(category, [])
        count = summary_counts[category]

        if ratings:
            total = sum(ratings)
            avg = round(total / len(ratings), 2)
            weighted = round(avg * weights[category], 4)
            computation = f"{' + '.join(map(str, ratings))} = {total} ÷ {len(ratings)} = {avg} × {weights[category]} = {weighted}"
            total_weighted += weighted
            category_count += 1
        else:
            avg = None
            weighted = None
            computation = "-"

        final_average[category] = {
            'count': count,
            'average': avg,
            'weighted': weighted,
            'computation': computation
        }

    final_overall = round(total_weighted, 4) if category_count > 0 else None
    average_rating = round(final_overall, 2) if final_overall is not None else None

    def get_adjective(rating):
        if rating is None:
            return "-"
        elif rating >= 4.5:
            return "Very Satisfactory"
        elif rating >= 3.5:
            return "Satisfactory"
        elif rating >= 2.5:
            return "Fair"
        elif rating >= 1.5:
            return "Poor"
        else:
            return "Very Poor"

    adjective_rating = get_adjective(average_rating)

     # --- NEW: Build workflow ---
    dept_head = (
        Employee.query
        .join(PermanentEmployeeDetails)
        .join(Position)
        .filter(
            Employee.department_id == employee.department_id,  # same department as IPCR owner
            Position.type == 'Head',                          # must be a Department Head
            Employee.is_deleted == False                      # exclude deleted employees
        )
        .first()
    )

        # HR Staff (non-head)
    hr_staff = (
        Employee.query
        .join(Users, Employee.user)                # join employee → user
        .join(UserPermission, Users.permissions)   # join user → permissions
        .join(PermanentEmployeeDetails)
        .join(Position)
        .filter(
            Employee.department_id == 15,
            Position.type != 'Head',                     # not the HR head
            UserPermission.permission == 'write_performance',  # must have this permission
            UserPermission.is_allowed == True,           # and it must be allowed
            Employee.is_deleted == False
        )
        .all()
    )


        # HR Head
    hr_head = (
            Employee.query
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(
                Position.id == 98,
                Employee.is_deleted == False
            )
            .first()
    )

    workflow = [
        {
            "step": 1,
            "name": f"{employee.first_name} {employee.middle_name or ''} {employee.last_name}",
            "position": employee.permanent_details.position.title if employee.permanent_details and employee.permanent_details.position else "",
            "description": "Submit IPCR form to Department Head"
        },
        {
            "step": 2,
            "name": f"{dept_head.first_name} {dept_head.middle_name or ''} {dept_head.last_name}" if dept_head else "-",
            "position": dept_head.permanent_details.position.title if dept_head and dept_head.permanent_details and dept_head.permanent_details.position else "",
            "description": "Grade IPCR form and provide feedback if needed."
        },
        {
            "step": 3,
            "staff": [
                {
                    "name": f"{staff.first_name} {staff.middle_name or ''} {staff.last_name}",
                    "position": staff.permanent_details.position.title if staff.permanent_details and staff.permanent_details.position else ""
                }
                for staff in hr_staff
            ] if hr_staff else [],
            "description": "Receive submission, check completeness, and forward to HR Head."
        },
        {
            "step": 4,
            "name": f"{hr_head.first_name} {hr_head.middle_name or ''} {hr_head.last_name}" if hr_head else "-",
            "position": hr_head.permanent_details.position.title if hr_head and hr_head.permanent_details and hr_head.permanent_details.position else "",
            "description": "Consolidate graded IPCR forms in the system for compliance and reporting."
        },
    ]

    return render_template(
        'users/ViewIPCR.html',
        title="IPCR View",
        ipcr=ipcr,
        sections=sections,
        employee=employee,
        department=department,
        final_average=final_average,
        final_overall=final_overall,
        average_rating=average_rating,
        adjective_rating=adjective_rating,
        workflow=workflow  # pass workflow to template
    )





@app.route("/User/Credit")
@login_required
@role_required('employee')
def UserCredit():
    emp = current_user.employee

    if not emp:
        flash("You are not linked to an employee record.", "warning")
        return redirect(url_for("EmployeeHome"))  # ✅ redirect to user dashboard

    # Skip Job Order employees
    if emp.job_order_details:
        flash("Job Order employees do not have credits.", "warning")
        return redirect(url_for("EmployeeHome"))

    # If casual employee, ensure assigned department is set
    if emp.casual_details and not emp.casual_details.assigned_department:
        flash("You are not assigned to any department.", "warning")
        return redirect(url_for("EmployeeHome"))

    department = emp.department if emp.permanent_details else (
        emp.casual_details.assigned_department if emp.casual_details else None
    )

    # --- Compute leave credits by type ---
    leave_summary = {}
    for leave_type in ["Vacation", "Sick"]:
        earned = sum(tx.amount for tx in emp.credit_transactions 
                     if tx.action == "Earned" and tx.leave_type == leave_type)
        used = sum(tx.amount for tx in emp.credit_transactions 
                   if tx.action == "Used" and tx.leave_type == leave_type)
        remaining = earned - used
        leave_summary[leave_type] = {
            "earned": earned,
            "used": used,
            "remaining": remaining
        }

    # Determine position
    if emp.permanent_details and emp.permanent_details.position:
        position = emp.permanent_details.position.title
    elif emp.casual_details and emp.casual_details.position:
        position = emp.casual_details.position.title
    else:
        position = "-"

    # Employee credit summary
    employee_credit = {
        "id": emp.id,
        "name": f"{emp.first_name} {emp.last_name}",
        "position": position,
        "leave_summary": leave_summary
    }

    # Transactions (latest first)
    transactions = sorted(emp.credit_transactions, key=lambda tx: tx.timestamp, reverse=True)

    return render_template(
        "users/credithistory.html",
        title="My Credits",
        department=department,
        employee_credit=employee_credit,
        transactions=transactions
    )




@app.route('/api/departments', methods=['GET'])
def get_departments():
    departments = Department.query.all()
    data = [{"id": d.id, "name": d.name} for d in departments]
    return jsonify(data)

# newapi
@app.route('/api/employees/<int:department_id>', methods=['GET'])
def get_employees_by_department(department_id):
    # Permanent Employees
    permanent = (
        db.session.query(Employee)
        .join(PermanentEmployeeDetails)
        .filter(
            Employee.is_deleted == False,
            Employee.department_id == department_id
        )
        .all()
    )

    # Casual Employees
    casual = (
        db.session.query(Employee)
        .join(CasualEmployeeDetails)
        .filter(
            Employee.is_deleted == False,
            CasualEmployeeDetails.assigned_department_id == department_id
        )
        .all()
    )

    # Job Order Employees
    job_order = (
        db.session.query(Employee)
        .join(JobOrderDetails)
        .filter(
            Employee.is_deleted == False,
            JobOrderDetails.assigned_department_id == department_id
        )
        .all()
    )

    # Combine all results
    all_employees = permanent + casual + job_order

    data = [
        {"id": emp.id, "name": f"{emp.first_name} {emp.last_name}"}
        for emp in all_employees
    ]

    return jsonify(data)



@app.route('/Report/Issue/')
@login_required
@role_required('employee')
def ReportIssue():
    # Fetch all issues reported by the current user
    issues = IssueReport.query.filter_by(reporter_user_id=current_user.id) \
                              .order_by(IssueReport.created_at.desc()) \
                              .all()

    return render_template(
        "users/ReportIssue.html",
        issues=issues
    )



@app.route('/report-issue', methods=['POST'])
@login_required
@role_required('employee')
def report_issue():
    employee_id = request.form.get('employee')  # Employee.id from the form
    title = request.form.get('title')
    description = request.form.get('description')


    if not employee_id or not title or not description:
        flash('All fields are required.', 'danger')
        return redirect(request.referrer or url_for('ReportIssue'))

    # Get the Employee record (make sure not deleted)
    employee = Employee.query.filter_by(id=employee_id, is_deleted=False).first()
    if not employee:
        flash('Employee not found.', 'danger')
        return redirect(request.referrer or url_for('ReportIssue'))

    # Get the User linked to the Employee
    user = Users.query.filter_by(employee_id=employee.id).first()
    if not user:
        flash('User account for this employee not found.', 'danger')
        return redirect(request.referrer or url_for('ReportIssue'))

    reported_user_id = user.id  # The actual Users.id foreign key

    # Prevent self-reporting
    if reported_user_id == current_user.id:
        flash("You cannot report yourself.", "danger")
        return redirect(request.referrer or url_for('ReportIssue'))

    # Create and save the issue report
    issue = IssueReport(
        reporter_user_id=current_user.id,
        reported_user_id=reported_user_id,
        title=title,
        description=description
    )

    db.session.add(issue)
    db.session.commit()


    # --- Notify HR ---
    hr_users = Users.query.filter_by(role='hr').all()
    for hr in hr_users:
        hr_subject = f"Issue Report: {title}"
        
        # Avoid duplicate notifications for the same subject
        existing_msg_to_hr = UserMessage.query.filter_by(
            recipient_id=hr.id,
            subject=hr_subject
        ).first()
        if existing_msg_to_hr:
            continue

        hr_body = f"""📢 <strong>New Issue Report</strong><br><br>

        <p>Dear <strong>{hr.name}</strong>,</p>

        <p><strong>{current_user.name}</strong> has reported an issue against 
        <strong>{employee.first_name} {employee.last_name}</strong>.</p>

        <p><strong>Title:</strong> {title}</p>
        <p><strong>Description:</strong>{description}</p>

        <p>Please review this issue in the HR system.</p>

        <hr>
        <p><em>⚠ This is an automated message. Please do not reply.</em></p>
        <p>– HR System</p>
        """

        db.session.add(UserMessage(
            sender_id=current_user.id,   # or system user_id (e.g., 1)
            recipient_id=hr.id,
            subject=hr_subject,
            body=hr_body,
            message_type='system'
        ))

    db.session.commit()

    flash('Issue report submitted successfully!', 'success-timed')
    return redirect(url_for('ReportIssue'))




@app.route('/Users/permit', methods=['GET', 'POST'])
@login_required
@role_required('employee')
def Userspermit():
    employee_id = current_user.employee.id 

    # Leave Permits (for this employee only)
    leave_permits = (
        PermitRequest.query
        .filter_by(permit_type='Leave', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Attach latest rejection history + user name to each leave permit
    for permit in leave_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name              # 👈 who rejected
            permit.rejected_remarks = history.remarks   # 👈 rejection remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # Travel Order Permits
    travel_orders = (
        PermitRequest.query
        .filter_by(permit_type='Travel Order', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

    # Attach latest rejection history + user name to each travel order
    for permit in travel_orders:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name          # name of rejector
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # Clearance Permits
    clearance_permits = (
        PermitRequest.query
        .filter_by(permit_type='Clearance Form', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )


         # Attach latest rejection history + user name to each clearance permit 👇
    for permit in clearance_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    # COE Permits
    coe_permits = (
        PermitRequest.query
        .filter_by(permit_type='Certification of Employment', employee_id=employee_id)
        .order_by(PermitRequest.date_requested.desc())
        .all()
    )

        # Attach latest rejection history + user name to each COE permit 👇
    for permit in coe_permits:
        rejection = (
            db.session.query(PermitRequestHistory, Users)
            .join(Users, PermitRequestHistory.action_by == Users.id)
            .filter(
                PermitRequestHistory.permit_request_id == permit.id,
                PermitRequestHistory.action == "Rejected"
            )
            .order_by(PermitRequestHistory.timestamp.desc())
            .first()
        )
        if rejection:
            history, user = rejection
            permit.rejected_by = user.name
            permit.rejected_remarks = history.remarks
        else:
            permit.rejected_by = None
            permit.rejected_remarks = None

    return render_template(
        'users/permitUser.html', 
        title="My Permit Requests", 
        leave_permits=leave_permits,
        travel_orders=travel_orders,
        clearance_permits=clearance_permits,
        coe_permits=coe_permits
    )





@app.route('/employee/myprofile', methods=['GET', 'POST'])
@login_required
@role_required('employee')  # adjust if needed
def employeeaccount():
    form = UpdateSuperAdminProfileForm()
    employee = current_user.employee

    # Pre-fill form on GET
    if request.method == 'GET':
        if employee:
            form.first_name.data = employee.first_name
            form.middle_name.data = employee.middle_name
            form.last_name.data = employee.last_name

            # Pre-fill permanent_details if available
            if employee.permanent_details:
                form.date_of_birth.data = employee.permanent_details.date_of_birth
                form.gender.data = employee.permanent_details.sex
                form.tin.data = employee.permanent_details.tin

        form.email.data = current_user.email

    # Handle form submission
    if form.submit.data and form.validate_on_submit():
        if employee:
            employee.first_name = form.first_name.data.strip()
            employee.middle_name = form.middle_name.data.strip() if form.middle_name.data else None
            employee.last_name = form.last_name.data.strip()

            # Update permanent_details fields if present
            if employee.permanent_details:
                employee.permanent_details.date_of_birth = form.date_of_birth.data
                employee.permanent_details.sex = form.gender.data
                employee.permanent_details.tin = form.tin.data

            # Combine first, middle, and last name (skip empty values)
            full_name = " ".join(filter(None, [
                form.first_name.data.strip(),
                form.middle_name.data.strip() if form.middle_name.data else None,
                form.last_name.data.strip()
            ]))
            current_user.name = full_name

        # Update email
        current_user.email = form.email.data.strip()

        # Update profile picture if uploaded
        if form.image_file.data and form.image_file.data.filename != '':
            picture_file = save_picture(form.image_file.data)
            current_user.image_file = picture_file

        db.session.commit()
        flash('Your profile has been updated.', 'success')
        return redirect(url_for('employeeaccount'))

    # Handle avatar image
    image_filename = current_user.image_file if current_user.image_file else 'default.png'
    image_path = url_for('static', filename='img/avatars/' + image_filename)

    return render_template(
        'users/AccountUser.html',
        title="My Profile",
        form=form,
        image_file=image_path
    )





@app.route('/employee/update/password', methods=['GET', 'POST'])
@login_required
@role_required('employee')  # Ensure this decorator restricts access properly
def employee_update_password():
    form2 = UpdateSuperAdminPasswordForm()  

    if request.method == 'POST' and form2.validate_on_submit():
        # Verify current password
        if not bcrypt.check_password_hash(current_user.password_hash, form2.current_password.data):
            flash('Incorrect current password. Please try again.', 'danger')
        else:
            # Hash and save the new password
            new_hashed_password = bcrypt.generate_password_hash(form2.password.data).decode('utf-8')
            current_user.password_hash = new_hashed_password
            current_user.must_reset_password = False
            db.session.commit()
            flash('Your password has been updated.', 'success-timed')
            return redirect(url_for('employee_update_password'))

    # Query only this user's login attempts
    logins = LoginActivity.query.filter_by(user_id=current_user.id).order_by(LoginActivity.timestamp.desc()).all()

    return render_template('users/ResetPassUser.html', title="Update Password", form2=form2, logins=logins)





@app.route('/Employee/Inbox/')
@login_required
@role_required('employee')
def EmployeeInbox():


    all_users = Users.query.all()
    
    # Group users by department name
    grouped_users = defaultdict(list)
    for user in all_users:
        if user.id == current_user.id:
            continue
        if user.employee and user.employee.department:
            dept_name = user.employee.department.name
        else:
            dept_name = "No Department"
        grouped_users[dept_name].append(user)

    
    inbox_messages = UserMessage.query.filter_by(
        recipient_id=current_user.id,
        is_deleted=False,
        is_sent_copy=False
    ).order_by(UserMessage.timestamp.desc()).all()

    sent_messages = UserMessage.query.filter_by(
    sender_id=current_user.id,
    is_sent_copy=True,
    is_deleted=False
    ).order_by(UserMessage.timestamp.desc()).all()

    trash_messages = UserMessage.query.filter(
        UserMessage.is_deleted == True,
        or_(
            and_(
                UserMessage.recipient_id == current_user.id,
                UserMessage.is_sent_copy == False
            ),
            and_(
                UserMessage.sender_id == current_user.id,
                UserMessage.is_sent_copy == True
            )
        )
    ).order_by(UserMessage.timestamp.desc()).all()

        
    return render_template('users/InboxUser.html', title="Inbox", grouped_users=grouped_users,inbox=inbox_messages, sent=sent_messages, trash=trash_messages)


@app.route('/Employee/Calendar/')
@login_required
@role_required('employee')
def CalendarEmployee():
    now = datetime.utcnow()
    current_day = now.strftime('%A')  # e.g., Wednesday
    current_date = now.strftime('%d %b, %Y')  # e.g., 25 Jul, 2025

    # Query only active (ongoing or future) events
    active_events = CalendarEvent.query.filter(
        (CalendarEvent.end_date == None) | (CalendarEvent.end_date >= now)
    ).all()

    # Count how many events exist per label
    event_counts = defaultdict(int)
    for event in active_events:
        event_counts[event.label] += 1

    return render_template(
        'users/calendarUser.html',
        title="Calendar",
        current_day=current_day,
        current_date=current_date,
        event_counts=event_counts
    )



@app.route("/User/travel", methods=['GET'])
@login_required
@role_required('employee')
def travel_logs_User():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search = request.args.get('search', '').strip()

    # Get the logged-in employee ID
    employee_id = current_user.employee.id  

    query = (
        db.session.query(TravelLog)
        .join(TravelOrder)
        .join(PermitRequest)
        .join(Employee)
        .options(
            joinedload(TravelLog.travel_order)
            .joinedload(TravelOrder.permit)
            .joinedload(PermitRequest.employee)
        )
        .filter(Employee.id == employee_id)  # Only logs of the logged-in user
    )

    if search:
        like = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(Employee.first_name).ilike(like),
                func.lower(Employee.last_name).ilike(like),
                func.lower(Employee.middle_name).ilike(like),
                func.lower(TravelOrder.destination).ilike(like),
                func.lower(TravelOrder.purpose).ilike(like),
                func.lower(TravelLog.tracking_id).ilike(like),
                func.lower(TravelLog.status).ilike(like),
                # Full name variations
                func.lower(func.concat(Employee.last_name, ', ', Employee.first_name)).ilike(like),
                func.lower(func.concat(Employee.first_name, ' ', Employee.last_name)).ilike(like),
            )
        )

    logs_paginated = query.order_by(
        case((TravelLog.status == 'Approved', 1), else_=0),
        desc(TravelLog.tracking_id)
    ).paginate(page=page, per_page=per_page)

    return render_template(
        'users/travellogs.html',
        title="Travel Logs",
        logs=logs_paginated,
        search=search  
    )



# LANDING
@app.route("/")
@app.route("/home")
# @login_required
def home():
    job_postings = JobPosting.query.all()  # or use filter/order_by as needed
    return render_template('landing/index.html', title="Home", job_postings=job_postings)

@app.route("/community")
# @login_required
def community():
    return render_template('landing/community.html',title="Community")


@app.route("/cuisine")
# @login_required
def cuisine():
    return render_template('landing/cuisine.html',title="Cuisine")

@app.route("/culture")
# @login_required
def culture():
    return render_template('landing/culture.html',title="Culture")


@app.route("/livelihood")
# @login_required
def livelihood():
    return render_template('landing/livelihood.html',title="Livelihood")

@app.route("/heath")
# @login_required
def health():
    return render_template('landing/service-details.html',title="Health")

@app.route("/social")
# @login_required
def social():
    return render_template('landing/social_welfare.html',title="Social")

@app.route("/civil")
# @login_required
def civil():
    return render_template('landing/civil.html',title="Civil")

@app.route("/business")
# @login_required
def business():
    return render_template('landing/business.html',title="Business")

@app.route("/agriculture")
# @login_required
def agriculture():
    return render_template('landing/agriculture.html',title="Agriculture")

@app.route("/emergency")
# @login_required
def emergency():
    return render_template('landing/emergency.html',title="Emergency")

@app.route("/Jobs")
def joblist():
    job_postings = JobPosting.query.\
        filter_by(status='Open').\
        order_by(JobPosting.created_at.desc()).\
        all()
    return render_template('landing/joblist.html', title="Jobs", job_postings=job_postings)








# Config
UPLOAD_FOLDER = 'static/uploads/resumes'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Saved the Resume in folder
def save_resume(resume_file):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(resume_file.filename)
    resume_filename = random_hex + f_ext
    resume_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], resume_filename)

    os.makedirs(os.path.dirname(resume_path), exist_ok=True)  # Ensure the folder exists
    resume_file.save(resume_path)

    return resume_filename  # Save just the filename in DB


# Extract text using pdfplumber
def extract_text_from_pdf(pdf_path):
    text = ""
    print(f"[INFO] Starting text extraction for: {pdf_path}")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                print(f"[pdfplumber] Page {i + 1} text:\n{page_text[:500] if page_text else '[NO TEXT FOUND]'}\n{'-'*50}")
                if page_text:
                    text += page_text
        if text.strip():
            print("[INFO] Text extraction with pdfplumber succeeded.")
            return text.strip()
        else:
            print("[WARN] No text extracted from PDF using pdfplumber.")
    except Exception as e:
        print(f"[ERROR] Text extraction failed: {e}")
    
    return ""



# Used to clean the extraction from AI
def clean_json(text):
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]  # Remove ```json\n
    if text.startswith("```"):
        text = text[3:]  # Remove ```
    if text.endswith("```"):
        text = text[:-3]  # Remove ending ```
    text = text.strip()
    return text

# AI connection
def analyze_resume(resume_text, job_title=None, job_description=None, job_qualifications=None):
    model = genai.GenerativeModel(model_name="gemini-2.0-flash")

    # Convert ';;;' separator to human-readable list
    if job_qualifications:
        if ';;;' in job_qualifications:
            job_qualifications = "\n".join([q.strip() for q in job_qualifications.split(';;;') if q.strip()])

    prompt = f"""
    You are an experienced HR professional with a technical background. Analyze the applicant’s Personal Data Sheet (PDS) and compare it to the job opening.

    Output your analysis **strictly in JSON format**, like the example below:

    {{
    "application_score": "Give a score from 0–100 based on how well the applicant’s PDS matches the specific job title, description, and qualifications. 
    Weigh the evaluation as follows: Education 25%, Work Experience 40%, Eligibility 15%, Trainings/Voluntary Work/Other Info 20%. 
    Only award points for education, experience, and credentials that are relevant to the job requirements. 
    Consider qualifications that exceed the minimum requirements as fully satisfying them. 
    Be strict only if the applicant is missing a required qualification.",
    "phone": "<extracted phone number from the PDS, if available>",
    "resume_match": "Write a 1–2 sentence summary of how the applicant’s education, experience, and eligibility align with the job requirements.",
    "education": ["<degree, institution, year (if available)>", "..."],
    "experience": ["<job title - company (years)>", "..."],
    "eligibility": ["<exam name, rating, year>", "..."],
    "trainings": ["<training title (hours, year)>", "..."],
    "voluntary_work": ["<org name, role, year, hours>", "..."],
    "other_info": {{
        "skills": "<comma-separated skills>",
        "recognitions": "<awards or honors>",
        "memberships": "<memberships>"
    }},
    "strengths": ["Identify 2–3 specific strengths based on the applicant’s education, experience, eligibility, or trainings that are relevant to the given job title, description, and qualifications."],
    "weaknesses": ["Identify gaps, areas for improvement, or missing qualifications that could affect the applicant's fit for the job title, description, and qualifications. Include any skills, experience, or credentials that could be stronger or are less aligned with the role. You may also note minor areas for development, even if the applicant meets most requirements."],
    "summary": "Write a short paragraph (2–3 sentences) summarizing the applicant’s overall fit for the role."
    }}

    Resume:
    {resume_text}
    """

    if job_title:
        prompt += f"\n\nJob Title:\n{job_title}"
    if job_description:
        prompt += f"\n\nJob Description:\n{job_description}"
    if job_qualifications:
        prompt += f"\n\nJob Qualifications:\n{job_qualifications}"

    response = model.generate_content(prompt)

    print("===== AI RAW RESPONSE START =====")
    print(response.text[:2000])
    print("===== AI RAW RESPONSE END =====")

    try:
        clean_text = clean_json(response.text)
        structured_data = json.loads(clean_text)
    except json.JSONDecodeError as e:
        print(f"Failed to decode AI response as JSON. Error: {str(e)}")
        return None

    return structured_data







# Extract the extracted ai insigigth by block
def extract_block(label, text):
    pattern = rf"{label}:\s*(.*?)(?=\n(?:[A-Z][a-z]+|[A-Z\s]+):|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None

def extract_sections(text):
    def extract_list(section):
        return re.findall(r"(?:\*|\-)\s+(.*)", section)

    data = {}

    # Extract Application Score
    try:
        score_match = re.search(r"\*{0,2}Application Score:\*{0,2}\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if score_match:
            data['application_score'] = float(score_match.group(1))
            print(f"Extracted Application Score: {data['application_score']}")
        else:
            data['application_score'] = None
            print("Application score not found.")
    except Exception as e:
        data['application_score'] = None
        print(f"Error extracting application score: {e}")


    # Extract Resume Match
    try:
        match = re.search(r"Resume Match:\s*(.*?)(?=\n[A-Z][a-zA-Z\s]+:|\Z)", text, re.DOTALL)
        data['resume_match'] = match.group(1).strip() if match else None

    except:
        data['resume_match'] = None

    # Extract Education
    try:
        edu_block = extract_block("Education", text)
        data['extracted_education'] = json.dumps(extract_list(edu_block)) if edu_block else None
    except:
        data['extracted_education'] = None

    # Extract Skills
    try:
        skills_block = extract_block("Skills", text)
        data['extracted_skills'] = json.dumps(extract_list(skills_block)) if skills_block else None
    except:
        data['extracted_skills'] = None

    # Extract Experience
    try:
        exp_block = extract_block("Experience", text)
        if exp_block:
            data['extracted_experience'] = json.dumps(extract_list(exp_block))
        else:
            data['extracted_experience'] = None
    except Exception as e:
        data['extracted_experience'] = None
        print(f"Error extracting experience: {e}")


    # Extract Strengths
    try:
        strengths_block = extract_block("Strengths", text)
        if strengths_block:
            data['strengths'] = json.dumps(extract_list(strengths_block))
        else:
            data['strengths'] = None
    except Exception as e:
        data['strengths'] = None
        print(f"Error extracting strengths: {e}")

    # Extract Weaknesses
    try:
        weaknesses_block = extract_block("Weaknesses", text)
        if weaknesses_block:
            data['weaknesses'] = json.dumps(extract_list(weaknesses_block))
        else:
            data['weaknesses'] = None
    except Exception as e:
        data['weaknesses'] = None
        print(f"Error extracting weaknesses: {e}")

    # Extract Summary
    try:
        data['summary'] = re.search(r"Summary:\s*(.*)", text, re.DOTALL).group(1).strip()
    except:
        data['summary'] = None

    # Extract Phone Number
    try:
        phone_match = re.search(r"\*{0,2}Phone:\*{0,2}\s*([\d\s\+\-\(\)]+)", text, re.IGNORECASE)
        if phone_match:
            data['phone'] = phone_match.group(1).strip()
            print(f"Extracted Phone: {data['phone']}")
        else:
            data['phone'] = None
            print("Phone number not found.")
    except Exception as e:
        data['phone'] = None
        print(f"Error extracting phone: {e}")


    return data




def is_pds(text):
    """
    Checks if the uploaded PDF contains the 'PERSONAL DATA SHEET' header.
    Returns True if found, False otherwise.
    """
    return "PERSONAL DATA SHEET" in text.upper()

@app.route("/apply", methods=["POST"])
def apply():
    name = request.form.get("name")
    email = request.form.get("email")
    job_id = request.form.get("job_id")
    resume = request.files.get("resume")

    if not resume or not allowed_file(resume.filename):
        flash("Invalid file type. Please upload a PDF", "danger")
        return redirect(request.referrer)

    # Check duplicate application
    existing = Applicant.query.filter_by(job_id=job_id, email=email).first()
    if existing:
        flash("You have already applied for this job.", "warning")
        return redirect(request.referrer)

    # Split name
    name_parts = name.strip().split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    # Save uploaded file
    resume_filename = save_resume(resume)
    resume_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], resume_filename)
    resume_text = extract_text_from_pdf(resume_path)

    if not resume_text.strip():
        flash("The uploaded resume appears to be empty or not machine-readable. Please upload a valid text-based PDF.", "danger")
        return redirect(request.referrer)

    # PDS validation
    if not is_pds(resume_text):
        flash("The uploaded PDF is not a valid Personal Data Sheet (PDS).", "danger")
        return redirect(request.referrer)


    # Job details
    job = JobPosting.query.get(job_id)
    job_title = job.title if job else None
    job_description = job.description if job else None
    job_qualifications = job.qualifications if job else None

    # Analyze with Gemini
    insights = analyze_resume(
        resume_text=resume_text,
        job_title=job_title,
        job_description=job_description,
        job_qualifications=job_qualifications,
    )

    phone = insights.get("phone")

    # Create applicant record
    applicant = Applicant(
        job_id=job_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        pds_path=resume_filename,   # ✅ matches model field
        status='Received',
        applied_at=datetime.utcnow(),

        # AI Fields
        application_score=insights.get("application_score"),
        pds_match=insights.get("resume_match"),

        education="\n".join(insights.get("education", [])),
        work_experience="\n".join(insights.get("experience", [])),
        eligibility="\n".join(insights.get("eligibility", [])),
        trainings="\n".join(insights.get("trainings", [])),
        voluntary_work="\n".join(insights.get("voluntary_work", [])),

        other_skills=insights.get("other_info", {}).get("skills"),
        recognitions=insights.get("other_info", {}).get("recognitions"),
        memberships=insights.get("other_info", {}).get("memberships"),

        strengths="\n".join(insights.get("strengths", [])[:3]),  # max 3
        weaknesses="\n".join(insights.get("weaknesses", [])[:2]),  # max 2
        summary=insights.get("summary"),
    )

    db.session.add(applicant)
    db.session.commit()

    # Confirmation email
    try:
        msg = Message(
            subject="Application Received - Victoria Municipal Office",
            recipients=[applicant.email]
        )
        msg.body = f"""
        Dear {applicant.first_name} {applicant.last_name},

        Thank you for applying to the {job.title} position at the Victoria Municipal Office.

        We have received your application and will be reviewing it shortly.

        Best regards,  
        HR Department
        Victoria Municipal Office
        """
        mail.send(msg)
        flash("Application submitted and confirmation email sent.", "success-timed")
    except Exception as e:
        app.logger.error(f"Email failed: {e}")
        flash("Application submitted, but confirmation email failed to send.", "warning")

    # --- Notify HR Users with write_hiring access ---
    hr_users = (
        Users.query
        .join(UserPermission, UserPermission.user_id == Users.id)
        .filter(
            Users.role == 'hr',
            UserPermission.permission == 'write_hiring',
            UserPermission.is_allowed == True
        )
        .all()
    )

    for hr in hr_users:
        hr_subject = f"New Application for {job_title}"
        existing_msg_to_hr = UserMessage.query.filter_by(
            recipient_id=hr.id,
            subject=hr_subject
        ).first()
        if existing_msg_to_hr:
            continue

        hr_body = f"""📢 <strong>New Job Application Notification</strong><br><br>
        <p>Dear <strong>{hr.name}</strong>,</p>
        <p>A new applicant <strong>{applicant.first_name} {applicant.last_name}</strong>
        has applied for the <strong>{job_title}</strong> position.</p>
        <p>Please review the application in the system.</p>
        
        <hr>
        <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
        <p>– HR System</p>
        """

        db.session.add(UserMessage(
            sender_id=1,  # system/admin
            recipient_id=hr.id,
            subject=hr_subject,
            body=hr_body,
            message_type='system'
        ))

    db.session.commit()
    flash("Applicant has been successfully applied.", "success-timed")
    return redirect(url_for("joblist"))



@app.route('/Hiring/Applicants/Approve/<int:applicant_id>', methods=['POST'])
def approve_applicant(applicant_id):
    applicant = Applicant.query.get_or_404(applicant_id)
    applicant.status = 'Under Review'
    db.session.commit()
    flash("Applicant has been approved and moved to Interviewed.", "success-timed")
    return redirect(request.referrer or url_for('JobApplicants', job_id=applicant.job_id))


@app.route('/Hiring/Applicants/Reject/<int:applicant_id>', methods=['POST'])
def reject_applicant(applicant_id):
    applicant = Applicant.query.get_or_404(applicant_id)
    applicant.status = 'Rejected'
    db.session.commit()

    try:
        msg = Message(
            subject="Application Status - Victoria Municipal Office",
            recipients=[applicant.email]
        )
        msg.body = f"""
        Dear {applicant.first_name} {applicant.last_name},

        Thank you for applying to the {applicant.job_posting.title} position at the Victoria Municipal Office.

        We appreciate your interest and the time you invested in the application process. However, we regret to inform you that you were not selected for the position.

        We encourage you to apply for future openings and wish you the best in your job search.

        Sincerely,
        HR Department
        Victoria Municipal Office
        """
        mail.send(msg)
        flash("Applicant has been rejected and notified via email.", "success-timed")
    except Exception as e:
        app.logger.error(f"Email failed: {e}")
        flash("Applicant rejected, but email notification failed.", "warning")

    flash("Applicant has been rejected.", "success-timed")
    return redirect(request.referrer or url_for('JobApplicants', job_id=applicant.job_id))



@app.route("/Hiring/ManageApplicants", methods=['GET', 'POST'])
@login_required
def ManageHiringApplicant():
    applicants_underReviewed = Applicant.query.filter_by(status='Under Review').all()
    applicants_interviewed = Applicant.query.filter_by(status='Interviewed').all()
    applicants_rejected = Applicant.query.filter_by(status='Rejected').all()
    applicants_hired = Applicant.query.filter_by(status='Hired').all()
    return render_template('superAdmin/ManageHiring.html',title="ManageApplicants", applicants_underReviewed=applicants_underReviewed,applicants_interviewed=applicants_interviewed,applicants_rejected=applicants_rejected,applicants_hired=applicants_hired)






@app.route('/schedule_interview', methods=['POST'])
@login_required
def schedule_interview():
    applicant_id = request.form.get('applicant_id')
    interview_date = request.form.get('interview_date')
    interview_time = request.form.get('interview_time')
    interview_method = request.form.get('interview_method')
    interview_notes = request.form.get('interview_notes')

    applicant = Applicant.query.get(applicant_id)
    if not applicant:
        flash('Applicant not found.', 'danger')
        return redirect(request.referrer or url_for('ManageHiringApplicant'))

    try:
        # ✅ Parse date/time safely
        scheduled_date = datetime.strptime(interview_date, '%Y-%m-%d').date() if interview_date else None
        scheduled_time = datetime.strptime(interview_time, '%H:%M').time() if interview_time else None

        # ✅ Use current user's employee record if available
        if current_user.employee:
            interviewer_name = f"{current_user.employee.first_name} {current_user.employee.last_name}"
        else:
            interviewer_name = current_user.name  # fallback to user.name field

        # ✅ Create the Interview record
        interview = Interview(
            applicant_id=applicant.id,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            method=interview_method,
            interviewer=interviewer_name,
            interview_notes=interview_notes,
            status='Scheduled',
            result='Pending',
            created_at=datetime.utcnow()
        )

        # ✅ Update applicant status
        applicant.status = "Interviewed"

        db.session.add(interview)
        db.session.commit()

        # ✅ Send email to applicant
        msg = Message(
            subject="Interview Invitation - Victoria Municipal Office",
            recipients=[applicant.email]
        )
        msg.body = f"""
        Dear {applicant.first_name} {applicant.last_name},

        We are pleased to inform you that you have been shortlisted for the position of {applicant.job_posting.title}.

        Your interview is scheduled as follows:

        📅 Date: {interview.scheduled_date.strftime('%B %d, %Y')}
        ⏰ Time: {interview.scheduled_time.strftime('%I:%M %p')}
        💬 Method: {interview.method}
        👤 Interviewer: {interview.interviewer}
        {f"📝 Notes: {interview.interview_notes}" if interview.interview_notes else ""}

        Best regards,  
        HR Department  
        Victoria Municipal Office
        """
        mail.send(msg)

        flash('Interview scheduled successfully and email sent!', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Error scheduling interview: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('ManageHiringApplicant'))



@app.route('/reject_applicant', methods=['POST'])
@login_required
def reject_applicant_Hiring():
    applicant_id = request.form.get('applicant_id')
    rejection_reason = request.form.get('rejection_reason')  # NEW

    if not applicant_id:
        flash('Applicant ID is missing.', 'danger')
        return redirect(url_for('ManageHiringApplicant'))

    applicant = Applicant.query.get(applicant_id)

    if applicant:
        # Update applicant's status
        applicant.status = 'Rejected'

        # Also update interview result if interview exists
        interview = Interview.query.filter_by(applicant_id=applicant.id).first()
        if interview:
            interview.result = 'Rejected'
            interview.rejection_reason = rejection_reason  # Save reason in Interview table
            interview.status = 'Completed'  # Mark interview as done, if you want
            interview.interviewer = current_user.name

        db.session.commit()
        flash('Applicant rejected successfully.', 'success-timed')
    else:
        flash('Applicant not found.', 'danger')

    return redirect(url_for('ManageHiringApplicant'))



@app.route('/approve_applicant', methods=['POST'])
@login_required
def approve_applicant_Hiring():
    applicant_id = request.form.get('applicant_id')
    approval_notes = request.form.get('approval_notes') 

    print(f" Received request to approve applicant_id: {applicant_id}")
    
    if not applicant_id:
        flash('Applicant ID is missing.', 'danger')
        print("Applicant ID missing in form submission.")
        return redirect(url_for('ManageHiringApplicant'))

    applicant = Applicant.query.get(applicant_id)
    print(f" Fetched applicant: {applicant}")

    if not applicant:
        flash('Applicant not found.', 'danger')
        print(" No applicant found with that ID.")
        return redirect(url_for('ManageHiringApplicant'))

    try:
        # Update applicant status
        applicant.status = 'Hired'
        print(f"✅ Applicant status set to 'Hired' for applicant ID {applicant.id}")

        # Update interview info
        interview = Interview.query.filter_by(applicant_id=applicant.id).first()
        if interview:
            interview.result = 'Approved'
            interview.approval_notes = approval_notes
            interview.status = 'Completed'
            interview.interviewer = current_user.name
            print(f" Interview updated for applicant ID {applicant.id}")
        else:
            print(" No interview found for applicant.")

        # Get job posting info
        job_posting = applicant.job_posting
        print(f"Job posting: {job_posting}")

        department_id = job_posting.department_id if job_posting else None
        employee_status = job_posting.job_position_type if job_posting else 'Unknown'
        print(f" Department ID: {department_id}, Status: {employee_status}")

        # ✅ Block hiring if job posting is already closed
        if job_posting and job_posting.status == 'Closed':
            flash(f'The job posting \"{job_posting.title}\" is already closed. You cannot approve more applicants.', 'danger')
            print(" Job posting is already closed.")
            return redirect(url_for('ManageHiringApplicant'))

        # Create Employee record
        employee = Employee(
            first_name=applicant.first_name,
            last_name=applicant.last_name,
            department_id=department_id,
            status=employee_status
        )
        db.session.add(employee)
        db.session.flush()  # Get employee.id
        print(f" Created employee record: {employee.id}")

        # Create child record based on employee status
        if employee_status.lower() == 'casual':
            print(" Creating CasualEmployeeDetails...")

            # Ensure position exists for department
            position = Position.query.filter_by(
                title=job_posting.title,
                department_id=department_id
            ).first()

            if not position:
                print(f" No position found for title '{job_posting.title}' in department {department_id}. Creating new position.")
                position = Position(
                    title=job_posting.title,
                    department_id=department_id,
                    type='Employee'
                )
                db.session.add(position)
                db.session.flush()
            else:
                print(f" Found existing position: {position.id} - '{position.title}'")

            casual_details = CasualEmployeeDetails(
                employee_id=employee.id,
                position_id=position.id,
                name_extension=None,
                equivalent_salary='N/A',
                daily_wage=0.0,
                contract_start=datetime.utcnow().date(),
                contract_end=datetime.utcnow().date(),
                assigned_department_id=department_id
            )
            db.session.add(casual_details)

        elif employee_status.lower() == 'job order':
            print(" Creating JobOrderDetails...")
            job_order_details = JobOrderDetails(
                employee_id=employee.id,
                position_title=job_posting.title if job_posting else 'Unknown',
                date_hired=datetime.utcnow().date()
            )
            db.session.add(job_order_details)
        
        elif employee_status.lower() == 'permanent':
            print(" Creating PermanentEmployeeDetails...")

            # Ensure position exists for department
            position = Position.query.filter_by(
                title=job_posting.title,
                department_id=department_id
            ).first()

            if not position:
                print(f" No position found for title '{job_posting.title}' in department {department_id}. Creating new position.")
                position = Position(
                    title=job_posting.title,
                    department_id=department_id,
                    type='Employee',
                    number_of_positions=1  # default to 1 if new
                )
                db.session.add(position)
                db.session.flush()
            else:
                print(f" Found existing position: {position.id} - '{position.title}'")

                # Count how many employees are already using this position
                assigned_count = PermanentEmployeeDetails.query.filter_by(position_id=position.id).count()
                print(f" Position {position.title} has {assigned_count}/{position.number_of_positions} filled.")

                if assigned_count >= position.number_of_positions:
                    position.number_of_positions = assigned_count + 1

            employee.status = "P"

            # If slot is available, create permanent details
            permanent_details = PermanentEmployeeDetails(
                employee_id=employee.id,
                item_number=f"ITEM-{employee.id}",   # ⚠️ auto-generated for now
                position_id=position.id,
                salary_grade=None,
                authorized_salary=None,
                actual_salary=None,
                step=None,
                area_code=None,
                area_type=None,
                level=None,
                sex='Not Specified',  # ⚠️ Replace with actual applicant.sex if available
                date_original_appointment=datetime.utcnow().date()
            )
            db.session.add(permanent_details)

        # Create User Account
        department = Department.query.get(department_id)
        department_password = generate_department_password(department.name)
        login_id = f"{applicant.first_name[0]}{applicant.last_name}".lower()
        login_id = re.sub(r'\W+', '', login_id)
        base_email = f"{login_id}@example.com"
        default_password = bcrypt.generate_password_hash(department_password).decode('utf-8')
        full_name = f"{applicant.first_name} {applicant.last_name}".strip()


        user = Users(
            login_id=login_id,
            name=full_name,
            email=base_email,
            password_hash=default_password,
            role='Employee',
            employee_id=employee.id,
            must_reset_password=True
        )
        db.session.add(user)

        db.session.commit()
        flash('Applicant approved, employee and user account created successfully.', 'success-timed')

        # Auto-close the job posting if enough applicants have been hired
        if job_posting:
            hired_count = Applicant.query.filter_by(
                job_posting_id=job_posting.id,
                status='Hired'
            ).count()

            if hired_count >= job_posting.number_of_openings:
                job_posting.status = 'Closed'
                job_posting.updated_at = datetime.utcnow()

                # Reject all other non-hired applicants for this job posting
                non_hired_applicants = Applicant.query.filter(
                    Applicant.job_posting_id == job_posting.id,
                    Applicant.status != 'Hired'
                ).all()

                for non_hired in non_hired_applicants:
                    non_hired.status = 'Rejected'

                db.session.commit()
                flash(f'Job posting \"{job_posting.title}\" has been closed (hiring goal met). Remaining applicants were rejected.', 'info')

    except Exception as e:
        db.session.rollback()
        print(f" Exception occurred: {e}")
        flash(f'An error occurred: {str(e)}', 'danger')

    return redirect(url_for('ManageHiringApplicant'))





@app.route('/calendar/add', methods=['POST'])
@login_required
def add_event():
    title = request.form.get('title')
    label = request.form.get('label')
    start_date = request.form.get('start_date')  # format: 2025-05-25T12:00
    end_date = request.form.get('end_date')
    location = request.form.get('location')

    try:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%dT%H:%M')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%dT%H:%M') if end_date else None

        tz = ZoneInfo("Asia/Manila")
        start_date_obj = start_date_obj.replace(tzinfo=tz)
        if end_date_obj:
            end_date_obj = end_date_obj.replace(tzinfo=tz)

        now = datetime.now(tz)

    except ValueError:
        flash('Invalid date/time format.', 'danger')
        return redirect(url_for('adminHome'))

    if start_date_obj < now:
        flash('Start date cannot be in the past.', 'danger')
        return redirect(request.referrer or url_for('adminHome'))

    if end_date_obj and end_date_obj <= start_date_obj:
        flash('End date must be after the start date.', 'danger')
        return redirect(request.referrer or url_for('adminHome'))


    new_event = CalendarEvent(
        title=title,
        label=label,
        start_date=start_date_obj,
        end_date=end_date_obj,
        location=location,
        user_id=current_user.id
    )

    db.session.add(new_event)
    db.session.commit()
    flash('Event added successfully!', 'success-timed')
    return redirect(request.referrer)


@app.route('/edit_event', methods=['POST'])
@login_required
def edit_event():
    event_id = request.form.get('event_id')
    event = CalendarEvent.query.get(event_id)

    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('adminHome'))

    # Optional security check
    if event.user_id != current_user.id:
        flash('Unauthorized to modify this event.', 'danger')
        return redirect(url_for('adminHome'))

    # If delete button was clicked
    if request.form.get('delete') == '1':
        db.session.delete(event)
        db.session.commit()
        flash('Event deleted successfully.', 'success-timed')
        return redirect(url_for('adminHome'))

    # Gather inputs
    title = request.form.get('title')
    label = request.form.get('label')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    location = request.form.get('location')

    try:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%dT%H:%M')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%dT%H:%M') if end_date else None

        tz = ZoneInfo("Asia/Manila")
        start_date_obj = start_date_obj.replace(tzinfo=tz)
        if end_date_obj:
            end_date_obj = end_date_obj.replace(tzinfo=tz)

        now = datetime.now(tz)

    except ValueError:
        flash('Invalid date/time format.', 'danger')
        return redirect(request.referrer or url_for('adminHome'))

    # Validation checks
    if not title or not label:
        flash('Title and label are required.', 'danger')
        return redirect(request.referrer or url_for('adminHome'))

    if start_date_obj < now:
        flash('Start date cannot be in the past.', 'danger')
        return redirect(request.referrer or url_for('adminHome'))

    if end_date_obj and end_date_obj <= start_date_obj:
        flash('End date must be after the start date.', 'danger')
        return redirect(request.referrer or url_for('adminHome'))

    # Update event
    event.title = title
    event.label = label
    event.start_date = start_date_obj
    event.end_date = end_date_obj
    event.location = location if location else None

    db.session.commit()
    flash('Event updated successfully!', 'success-timed')
    return redirect(request.referrer or url_for('adminHome'))



@app.context_processor
def inject_permit_counts():
    count = 0

    if current_user.is_authenticated and current_user.role == 'HR':
        statuses_to_include = ['Pending', 'In Progress']

        # ===== LEAVE =====
        if current_user.has_permission('read_leave'):
            leave_permits = PermitRequest.query.filter(
                PermitRequest.permit_type == 'Leave',
                PermitRequest.status.in_(statuses_to_include),
                func.trim(PermitRequest.current_stage).in_(["HR"])
            ).count()
            count += leave_permits

        # ===== TRAVEL ORDER =====
        if current_user.has_permission('read_travel'):
            travel_permits = PermitRequest.query.filter(
                PermitRequest.permit_type == 'Travel Order',
                PermitRequest.status.in_(statuses_to_include),
                func.trim(PermitRequest.current_stage).in_(["HR"])
            ).count()
            count += travel_permits

        # ===== CLEARANCE =====
        if current_user.has_permission('read_clearance'):
            clearance_permits = PermitRequest.query.filter(
                PermitRequest.permit_type == 'Clearance Form',
                PermitRequest.status.in_(statuses_to_include),
                func.trim(PermitRequest.current_stage).in_(["HR"])
            ).count()
            count += clearance_permits

        # ===== COE =====
        if current_user.has_permission('read_coe'):
            coe_permits = PermitRequest.query.filter(
                PermitRequest.permit_type == 'Certification of Employment',
                PermitRequest.status.in_(statuses_to_include),
                func.trim(PermitRequest.current_stage).in_(["HR"])
            ).count()
            count += coe_permits

        # ===== DEPARTMENT PERMITS =====
        head_employee = current_user.employee
        if head_employee and head_employee.department_id:
            department_id = head_employee.department_id
            employee_ids = [emp.id for emp in Employee.query.filter_by(department_id=department_id).all()]

            dept_pending_leave = PermitRequest.query.filter(
                PermitRequest.permit_type == 'Leave',
                PermitRequest.employee_id.in_(employee_ids),
                PermitRequest.current_stage == 'Head'
            ).count()

            dept_pending_travel = PermitRequest.query.filter(
                PermitRequest.permit_type == 'Travel Order',
                PermitRequest.employee_id.in_(employee_ids),
                PermitRequest.current_stage == 'Head'
            ).count()

            dept_pending_clearance = PermitRequest.query.filter(
                PermitRequest.permit_type == 'Clearance Form',
                PermitRequest.employee_id.in_(employee_ids),
                PermitRequest.current_stage == 'Head'
            ).count()

            dept_total = dept_pending_leave + dept_pending_travel + dept_pending_clearance
            count += dept_total

    return dict(pending_permit_count=count)


@app.context_processor
def inject_applicant_badge():
    applicants_received = Applicant.query.filter_by(status='Received').all()
    return {
        'applicants_received': applicants_received
    }



@app.route('/submit_leave', methods=['POST'])
@login_required
def submit_leave():
    date_from = request.form.get('date_filing')
    date_to = request.form.get('date_end')
    leave_type = request.form.get('leave_type')

   
    # Get salary raw string from form (e.g., "₱1,200.00/day")
    salary_raw = request.form.get('salary')
    salary = None
    if salary_raw:
        try:
            salary = float(
                salary_raw.replace("₱", "")
                        .replace(",", "")
                        .replace("/day", "")
                        .strip()
            )
        except ValueError:
            salary = None

    try:
        date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else None
        date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else None
        today = date.today()

        # Validation checks
        if not date_from_obj or not date_to_obj:
            flash("Please provide both start and end dates.", "danger")
            return redirect(request.referrer)

        if date_from_obj < today:
            flash("Start date cannot be in the past.", "danger")
            return redirect(request.referrer)

        if date_to_obj < date_from_obj:
            flash("End date cannot be before the start date.", "danger")
            return redirect(request.referrer)
        
        days_before_leave = (date_from_obj - today).days
        if leave_type.lower() != 'sick leave' and days_before_leave < 7:
            flash("Leave applications must be filed at least 7 days in advance (except Sick Leave).", "danger")
            return redirect(request.referrer)

        if date_from_obj and date_to_obj:
            leave_days = (date_to_obj - date_from_obj).days + 1
        else:
            leave_days = 0

        credit_to_deduct = round(leave_days * 0.1, 2)

    except ValueError:
        flash("Invalid date format.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        employee = current_user.employee
        credit = employee.credit_balance

        if not credit:
            flash("Credit balance not found.", "danger")
            return redirect(request.referrer or url_for('Userspermit'))

        # Only check balance if leave type requires deduction
        deduct_credits = leave_type.lower() in ['vacation leave', 'sick leave']

        # Prevent duplicate request
        existing_leave = db.session.query(LeaveApplication).join(PermitRequest).filter(
            PermitRequest.employee_id == employee.id,
            PermitRequest.permit_type == 'Leave',
            LeaveApplication.leave_type == leave_type,
            LeaveApplication.date_from == date_from_obj,
            LeaveApplication.date_to == date_to_obj,
            PermitRequest.status.in_(['Pending', 'Approved'])
        ).first()

        if existing_leave:
            flash("You have already submitted a leave request for this date range and type.", "warning")
            return redirect(request.referrer or url_for('Userspermit'))

        # Save permit and application
        permit = PermitRequest(
            employee_id=employee.id,
            permit_type='Leave',
            date_requested=datetime.utcnow(),
            status='Pending',
            current_stage='Head'
        )
        db.session.add(permit)
        db.session.flush()

        leave = LeaveApplication(
            permit_id=permit.id,
            leave_type=leave_type,
            working_days=str(leave_days),
            date_from=date_from_obj,
            date_to=date_to_obj,
            salary=salary
        )
        db.session.add(leave)
        db.session.commit()

                    
        # --- Notify Department Head (same department) ---

        head_users = []
        notified_head = False
        target_department_id = employee.approval_department_id

        if target_department_id:
            head_users = (
                Users.query.join(Employee)
                .filter(
                    db.func.lower(Users.role) == 'head',
                    Employee.department_id == target_department_id,
                    Users.id != employee.user.id  # skip self-notification
                )
                .all()
            )

        for head in head_users:
            subject = f"Leave request needs your approval ({employee.user.name})"
            body = f"""📝 <strong>Leave Request Approval Needed</strong><br><br>
            <p>Dear <strong>{head.name}</strong>,</p>
            <p>Employee <strong>{employee.user.name}</strong> has requested a 
            <strong>{leave.leave_type}</strong> leave from 
            <strong>{leave.date_from.strftime('%B %d, %Y')}</strong> to 
            <strong>{leave.date_to.strftime('%B %d, %Y')}</strong> 
            ({leave.working_days} working day(s)).</p>
            <p>The request is <strong>awaiting your approval</strong> as the Department Head.</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please log in to the system to take action.</em></p>
            <p>– HR System</p>
            """

            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=head.id,
                subject=subject,
                body=body,
                message_type='system'
            ))
            notified_head = True


        # --- Notify HR Head (if no dept head OR HR employee ang nag-file) ---
        if not notified_head or employee.user.role.lower() == "hr":
            hr_head_users = (
                Users.query
                .join(Employee)
                .join(PermanentEmployeeDetails)
                .join(Position)
                .filter(db.func.lower(Position.title) == "municipal government department head i")
                .all()
            )

            for hr in hr_head_users:
                if hr.id == employee.user.id:
                    continue  # skip self-notif

                db.session.add(UserMessage(
                    sender_id=current_user.id,
                    recipient_id=hr.id,
                    subject=f"New Leave Application Submitted ({employee.user.name})",
                    body=f"""📢 <strong>Leave Application Submitted</strong><br><br>
                    <p>Dear <strong>{hr.name}</strong>,</p>
                    <p>Employee <strong>{employee.user.name}</strong> filed a 
                    <strong>{leave.leave_type}</strong> leave from 
                    <strong>{leave.date_from.strftime('%B %d, %Y')}</strong> to 
                    <strong>{leave.date_to.strftime('%B %d, %Y')}</strong> 
                    ({leave.working_days} working day(s)).</p>
                    <p>This application is now pending <strong>Head approval</strong>.</p>
                    <hr>
                    <p><em>⚠ Automated notification. Please log in for monitoring.</em></p>
                    <p>– HR System</p>
                    """,
                    message_type='system'
                ))

        db.session.commit()


        flash('Leave application submitted successfully and notifications sent!', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting leave application: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))






# Travel order uploads (PDF, DOCX, Images)
app.config['TRAVEL_UPLOAD_FOLDER'] = os.path.join(app.root_path, "static", "uploads", "travel_orders")
app.config['TRAVEL_ALLOWED_EXTENSIONS'] = {'pdf', 'docx', 'jpg', 'jpeg', 'png'}
os.makedirs(app.config['TRAVEL_UPLOAD_FOLDER'], exist_ok=True)

def allowed_travel_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['TRAVEL_ALLOWED_EXTENSIONS']


@app.route('/submit_travel_order', methods=['POST'])
@login_required
def submit_travel_order():
    departure_datetime_str = request.form.get('departure_datetime')
    destination = request.form.get('destination')
    purpose = request.form.get('purpose')
    file = request.files.get('attachment')  # <-- input name="attachment"

    #  Basic validation
    if not departure_datetime_str or not destination or not purpose:
        flash('Please fill in all required fields.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        departure_datetime = datetime.strptime(departure_datetime_str, '%Y-%m-%dT%H:%M')
        now = datetime.now()

        if departure_datetime < now:
            flash('Departure date/time cannot be in the past.', 'danger')
            return redirect(request.referrer)

        MAX_ADVANCE_DAYS = 365
        if (departure_datetime.date() - now.date()).days > MAX_ADVANCE_DAYS:
            flash(f"Travel order cannot be set more than {MAX_ADVANCE_DAYS} days in advance.", "danger")
            return redirect(request.referrer)

    except ValueError:
        flash('Invalid date/time format.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        employee = current_user.employee

        # ✅ Prevent duplicate travel order
        existing_order = db.session.query(TravelOrder).join(PermitRequest).filter(
            PermitRequest.employee_id == employee.id,
            PermitRequest.permit_type == 'Travel Order',
            TravelOrder.destination == destination,
            TravelOrder.date_departure == departure_datetime,
            PermitRequest.status.in_(['Pending', 'Approved'])
        ).first()

        if existing_order:
            flash('You have already submitted a travel order for this destination and date.', 'warning')
            return redirect(request.referrer or url_for('Userspermit'))

        # ✅ Save PermitRequest
        permit = PermitRequest(
            employee_id=employee.id,
            permit_type='Travel Order',
            date_requested=datetime.utcnow(),
            status='Pending',
            current_stage='Head'
        )
        db.session.add(permit)
        db.session.flush()

        # ✅ Handle file upload (if provided)
        file_path = None
        relative_path = None
        if file and allowed_travel_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"  # avoid conflicts
            file_path = os.path.join(app.config['TRAVEL_UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            relative_path = f"uploads/travel_orders/{unique_filename}"

        # ✅ Save TravelOrder
        travel_order = TravelOrder(
            permit_id=permit.id,
            destination=destination,
            purpose=purpose,
            date_departure=departure_datetime,
            attachment=relative_path  # <-- Add this column in TravelOrder model
        )
        db.session.add(travel_order)
        db.session.commit()

         # ✅ Determine target department for approval (Permanent vs Casual/JO)
        target_department_id = employee.department_id
        if employee.casual_details and employee.casual_details.assigned_department_id:
            target_department_id = employee.casual_details.assigned_department_id
        elif employee.job_order_details and employee.job_order_details.assigned_department_id:
            target_department_id = employee.job_order_details.assigned_department_id

        # ✅ Notify only the Head of that department
        head_users = []
        if target_department_id:
            head_users = (
                Users.query.join(Employee)
                .filter(
                    db.func.lower(Users.role) == 'head',
                    Employee.department_id == target_department_id,
                    Users.id != employee.user.id   # don't notify same employee
                )
                .all()
            )

        for head in head_users:
            head_subject = f"Travel Order needs your approval ({employee.user.name})"
            head_body = f"""📌 <strong>Travel Order Approval Needed</strong><br><br>
            <p>Dear <strong>{head.name}</strong>,</p>
            <p>Employee <strong>{employee.user.name}</strong> has filed a 
            <strong>Travel Order</strong> with the following details:</p>
            <p>
            <strong>Destination:</strong> {destination}<br>
            <strong>Purpose:</strong> {purpose}<br>
            <strong>Departure:</strong> {departure_datetime.strftime('%B %d, %Y %I:%M %p').lstrip("0")}
            </p>
            <p>The request is <strong>awaiting your approval</strong> as the Department Head.</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please log in to the system to take action.</em></p>
            <p>– HR System</p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=head.id,
                subject=head_subject,
                body=head_body,
                message_type='system'
            ))

        db.session.commit()
        flash('Travel Order submitted successfully with file uploaded. Notifications sent to Head!', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting travel order: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))




@app.route('/submit-clearance', methods=['POST'])
@login_required
def submit_clearance():
    purpose = request.form.get('purpose')
    other_purpose = request.form.get('other_specify')
    position = request.form.get('position')
    office_assignment = request.form.get('office_assignment')
    

    date_from = request.form.get('date_from')
    date_to = request.form.get('date_to')

    try:
        date_from_parsed = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
        date_to_parsed = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None
        today = date.today()

        # ✅ Date validations
        if date_from_parsed and date_from_parsed < today:
            flash("Start date cannot be in the past.", "danger")
            return redirect(request.referrer )

        if date_from_parsed and date_to_parsed and date_to_parsed < date_from_parsed:
            flash("End date cannot be before the start date.", "danger")
            return redirect(request.referrer)

        # 🔍 Check for duplicate clearance form
        existing_clearance = db.session.query(ClearanceForm).join(PermitRequest).filter(
            PermitRequest.employee_id == current_user.employee.id,
            PermitRequest.permit_type == 'Clearance Form',
            PermitRequest.status.in_(['Pending', 'Approved']),
            ClearanceForm.clearance_purpose == purpose,
            ClearanceForm.date_from == date_from_parsed,
            ClearanceForm.date_to == date_to_parsed,
        ).first()

        if existing_clearance:
            flash('You have already submitted a clearance request for this purpose and date range.', 'warning')
            return redirect(request.referrer or url_for('Userspermit'))

        # ✅ Create PermitRequest
        new_permit = PermitRequest(
            employee_id=current_user.employee.id,
            permit_type='Clearance Form',
            status='Pending',
            current_stage='Head', 
            date_requested=datetime.utcnow(),
        )
        db.session.add(new_permit)
        db.session.flush()

        # ✅ Create ClearanceForm
        clearance = ClearanceForm(
            permit_id=new_permit.id,
            clearance_purpose=purpose,
            other_purpose=other_purpose if purpose == 'Other' else None,
            date_from=date_from_parsed,
            date_to=date_to_parsed,
        )
        db.session.add(clearance)

         # ✅ Determine target department (Permanent vs Casual/JO)
        employee = current_user.employee
        target_department_id = employee.department_id
        if employee.casual_details and employee.casual_details.assigned_department_id:
            target_department_id = employee.casual_details.assigned_department_id
        elif employee.job_order_details and employee.job_order_details.assigned_department_id:
            target_department_id = employee.job_order_details.assigned_department_id

        # ✅ Notify only the Head of that department
        head_users = []
        if target_department_id:
            head_users = (
                Users.query.join(Employee)
                .filter(
                    db.func.lower(Users.role) == 'head',
                    Employee.department_id == target_department_id,
                    Users.id != employee.user.id  # skip notifying self
                )
                .all()
            )

        for head in head_users:
            subject = f"Clearance Request needs your approval ({employee.user.name})"
            body = f"""📢 <strong>Clearance Request Approval Needed</strong><br><br>
            <p>Dear <strong>{head.name}</strong>,</p>
            <p>Employee <strong>{employee.user.name}</strong> has submitted a <strong>Clearance Form</strong>:</p>
            <p>
            <strong>Purpose:</strong> {purpose if purpose != 'Other' else other_purpose}<br>
            <strong>Date From:</strong> {date_from_parsed.strftime('%B %d, %Y') if date_from_parsed else 'N/A'}<br>
            <strong>Date To:</strong> {date_to_parsed.strftime('%B %d, %Y') if date_to_parsed else 'N/A'}
            </p>
            <p>The request is <strong>awaiting your approval</strong> as the Department Head.</p>
            <hr>
            <p><em>⚠ Automated notification. Do not reply.</em></p>
            """

            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=head.id,
                subject=subject,
                body=body,
                message_type='system'
            ))

        # ✅ Commit once for everything (atomic transaction)
        db.session.commit()
        flash('Clearance request submitted successfully and sent to Head for approval.', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting clearance request: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))








@app.route('/submit-coe', methods=['POST'])
@login_required
def submit_coe():
    try:
        employee = current_user.employee
        if not employee:
            flash('You must be linked to an employee to submit this request.', 'danger')
            return redirect(url_for('Userspermit'))  # Adjust as needed

        # Check for existing COE request with Pending 
        existing_coe = PermitRequest.query.filter_by(
            employee_id=employee.id,
            permit_type='Certification of Employment'
        ).filter(PermitRequest.status.in_(['Pending'])).first()

        if existing_coe:
            flash('You already have a Certification of Employment request pending.', 'warning')
            return redirect(request.referrer or url_for('Userspermit'))

        reason = request.form.get("reason", "").strip()
        reason = reason if reason else None

        duplicate_reason = None  # <--- define it here

        if reason:
            duplicate_reason = (
                db.session.query(COERequest)
                .join(PermitRequest, COERequest.permit_id == PermitRequest.id)
                .filter(
                    PermitRequest.employee_id == employee.id,
                    PermitRequest.permit_type == 'Certification of Employment',
                    PermitRequest.status == 'Pending',
                    db.func.lower(COERequest.reason) == reason.lower()
                )
                .first()
            )

        if duplicate_reason:
            flash(f'You already have a pending COE request for this reason ("{reason}").', 'warning')
            return redirect(request.referrer or url_for('Userspermit'))

        # Create new permit request
        permit = PermitRequest(
            employee_id=employee.id,
            permit_type='Certification of Employment',
            date_requested=datetime.utcnow(),
            status='Pending',
            current_stage='HR' 
        )
        db.session.add(permit)
        db.session.flush()

        # Create linked COERequest
        coe_request = COERequest(permit_id=permit.id,reason=reason)
        db.session.add(coe_request)

        hr_users = (
        Users.query
        .join(UserPermission)
        .filter(
            db.func.lower(Users.role) == 'hr',
            UserPermission.permission == 'write_coe',
            UserPermission.is_allowed == True
        )
        .all()
        )

        for hr in hr_users:
            subject = f"Certification of Employment Request submitted ({employee.user.name})"
            body = f"""📌 <strong>Certification of Employment Request Pending</strong><br><br>
            <p>Dear <strong>{hr.name}</strong>,</p>
            <p>Employee <strong>{employee.user.name}</strong> has submitted a 
            <strong>Certification of Employment (COE)</strong> request.</p>
            <p><strong>Reason:</strong> {reason or "N/A"}</p>
            <p>The request is now <strong>awaiting your review</strong> as HR.</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not replay.</em></p>
            """

            db.session.add(UserMessage(
                sender_id=current_user.id,   # employee as sender
                recipient_id=hr.id,
                subject=subject,
                body=body,
                message_type='system'
            ))

        db.session.commit()
        flash('Certification of Employment request submitted successfully and sent to Head.', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash('An error occurred while submitting the request.', 'danger')
        print(f"Error submitting COE: {e}")

    return redirect(request.referrer or url_for('Userspermit'))




@app.route("/edit-coe-reason", methods=["POST"])
@login_required
def edit_coe_reason():
    permit_id = request.form.get("permit_id")
    reason = request.form.get("reason", "").strip()
    reason = reason if reason else None  # store as NULL if empty

    permit = PermitRequest.query.get_or_404(permit_id)

    # Safety check: only allow editing if pending and owned by current user
    if permit.status != "Pending" or permit.employee_id != current_user.employee.id:
        flash("You can only edit pending requests.", "danger")
        return redirect(request.referrer)

    if permit.coe_detail:
        permit.coe_detail.reason = reason
        db.session.commit()
        flash("Reason updated successfully.", "success-timed")
    else:
        flash("No COE detail found for this request.", "danger")

    return redirect(request.referrer)


@app.route('/update_leave', methods=['POST'])
@login_required
def update_leave():
    permit_id = request.form.get('permit_id')
    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('EmployeePermits'))

    # Fetch parent PermitRequest
    permit = PermitRequest.query.get(permit_id)
    if not permit or permit.permit_type != "Leave":
        flash("Invalid leave application.", "danger")
        return redirect(request.referrer or url_for('EmployeePermits'))

    # Fetch child LeaveApplication
    leave = LeaveApplication.query.filter_by(permit_id=permit.id).first()
    if not leave:
        flash("Leave application details not found.", "danger")
        return redirect(request.referrer or url_for('EmployeePermits'))

    try:
        # ✅ Parse form values
        leave_type = request.form.get('leave_type')
        date_from = request.form.get('date_filing')
        date_to = request.form.get('date_end')
        salary_raw = request.form.get('salary')

        date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
        date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
        today = date.today()

        # ✅ Validation rules
        if date_from_obj < today:
            flash("Start date cannot be in the past.", "danger")
            return redirect(request.referrer or url_for('EmployeePermits'))

        if date_to_obj < date_from_obj:
            flash("End date cannot be before the start date.", "danger")
            return redirect(request.referrer or url_for('EmployeePermits'))


        #  Salary parsing
        salary = None
        if salary_raw:
            try:
                salary = float(
                    salary_raw.replace("₱", "")
                              .replace(",", "")
                              .replace("/day", "")
                              .strip()
                )
            except ValueError:
                salary = None

        # ✅ Update LeaveApplication fields
        leave.leave_type = leave_type
        leave.date_from = date_from_obj
        leave.date_to = date_to_obj
        leave.salary = salary

        db.session.commit()
        flash("Leave application updated successfully.", "success-timed")

    except ValueError:
        flash("Invalid date format.", "danger")
        return redirect(request.referrer or url_for('EmployeePermits'))
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating leave: {e}", "danger")

    return redirect(request.referrer or url_for('EmployeePermits'))



@app.route('/edit_travel', methods=['POST'])
@login_required
def edit_travel():
    permit_id = request.form.get('permit_id')
    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('EmployeePermits'))

    permit = PermitRequest.query.get(permit_id)
    if not permit or not permit.travel_detail:
        flash("Invalid travel request.", "danger")
        return redirect(request.referrer or url_for('EmployeePermits'))

    # Get form inputs
    date_departure_str = request.form.get('date_departure')
    destination = request.form.get('destination')
    purpose = request.form.get('purpose')
    file = request.files.get('attachment')  # <-- allow new file upload

    # ✅ Required field check
    if not date_departure_str or not destination or not purpose:
        flash("Please provide all required fields.", "danger")
        return redirect(request.referrer or url_for('EmployeePermits'))

    try:
        date_departure = datetime.strptime(date_departure_str, '%Y-%m-%dT%H:%M')
        now = datetime.now()

        # ✅ Future date check
        if date_departure < now:
            flash("Departure date/time cannot be in the past.", "danger")
            return redirect(request.referrer or url_for('EmployeePermits'))

        # ✅ Max advance check (1 year)
        MAX_ADVANCE_DAYS = 365
        if (date_departure.date() - now.date()).days > MAX_ADVANCE_DAYS:
            flash(f"Travel order cannot be set more than {MAX_ADVANCE_DAYS} days in advance.", "danger")
            return redirect(request.referrer or url_for('EmployeePermits'))

        # ✅ Prevent duplicate travel orders (excluding current one)
        existing_order = db.session.query(TravelOrder).join(PermitRequest).filter(
            PermitRequest.employee_id == permit.employee_id,
            PermitRequest.permit_type == 'Travel Order',
            TravelOrder.destination == destination,
            TravelOrder.date_departure == date_departure,
            PermitRequest.status.in_(['Pending', 'Approved']),
            TravelOrder.id != permit.travel_detail.id
        ).first()

        if existing_order:
            flash("Another travel order already exists for this destination and date.", "warning")
            return redirect(request.referrer or url_for('EmployeePermits'))

        # ✅ Update details
        permit.travel_detail.date_departure = date_departure
        permit.travel_detail.destination = destination
        permit.travel_detail.purpose = purpose

        # ✅ Handle file update (optional with cleanup)
        if file and allowed_travel_file(file.filename):
            # Delete old file if exists
            old_file = permit.travel_detail.attachment
            if old_file:
                old_file_path = os.path.join(app.root_path, "static", old_file.replace("/", os.sep))
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)

            # Save new file
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            file_path = os.path.join(app.config['TRAVEL_UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)

            # Save browser-friendly relative path (always `/`)
            relative_path = f"uploads/travel_orders/{unique_filename}"
            permit.travel_detail.attachment = relative_path

        db.session.commit()
        flash("Travel order updated successfully.", "success-timed")

    except ValueError:
        flash("Invalid date format. Please use the correct format.", "danger")
        return redirect(request.referrer or url_for('EmployeePermits'))
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating travel order: {e}", "danger")

    return redirect(request.referrer or url_for('EmployeePermits'))




@app.route('/update_clearance', methods=['POST'])
@login_required
def update_clearance():
    permit_id = request.form.get('permit_id')
    if not permit_id:
        flash('Permit ID is missing.', 'danger')
        return redirect(request.referrer)

    permit = PermitRequest.query.get(permit_id)
    if not permit or permit.employee_id != current_user.employee.id:
        flash('Unauthorized or invalid permit.', 'danger')
        return redirect(request.referrer)

    # Update clearance form (child)
    if permit.clearance_detail:
        detail = permit.clearance_detail
    else:
        detail = ClearanceForm(permit_id=permit.id)
        db.session.add(detail)

    purpose = request.form.get('purpose')
    other_specify = request.form.get('other_specify')

    detail.clearance_purpose = purpose
    detail.other_purpose = other_specify if purpose == "Other" else None

    # ✅ Date validation
    date_from = request.form.get('date_from')
    date_to = request.form.get('date_to')

    try:
        date_from_parsed = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else None
        date_to_parsed = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else None
        today = date.today()

        if date_from_parsed and date_from_parsed < today:
            flash("Start date cannot be in the past.", "danger")
            return redirect(request.referrer)

        if date_from_parsed and date_to_parsed and date_to_parsed < date_from_parsed:
            flash("End date cannot be before the start date.", "danger")
            return redirect(request.referrer)

        detail.date_from = date_from_parsed
        detail.date_to = date_to_parsed

    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
        return redirect(request.referrer)

    try:
        db.session.commit()
        flash('Clearance request updated successfully!', 'success-timed')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating clearance: {e}', 'danger')

    return redirect(request.referrer)



@app.route('/cancel_permit', methods=['POST'])
@login_required
def cancel_permit():
    permit_id = request.form.get('permit_id')
    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('EmployeePermits'))

    permit = PermitRequest.query.get(permit_id)
    if not permit:
        flash("Invalid permit request.", "danger")
        return redirect(request.referrer or url_for('EmployeePermits'))

    # Optional: Only allow cancel if request is still pending
    if permit.status not in ["Pending"]:
        flash("This request cannot be cancelled because it is already processed.", "warning")
        return redirect(request.referrer or url_for('EmployeePermits'))

    try:
        permit.status = "Cancelled"
        permit.current_stage = "User Cancelled"
        db.session.commit()
        flash(f"{permit.permit_type} request cancelled successfully.", "success-timed")
    except Exception as e:
        db.session.rollback()
        flash(f"Error cancelling request: {e}", "danger")

    return redirect(request.referrer)


# OK 
@app.route('/approve_leave/hr', methods=['POST'])
@login_required
@role_required('hr') 
def approve_leave_hr():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks')

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Leave':
        flash('Invalid permit type.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    # ✅ Only allow HR to approve if stage is HR
    if permit.current_stage != 'HR':
        flash("This leave request is not in HR stage anymore.", "warning")
        return redirect(request.referrer or url_for('Userspermit'))

    leave = LeaveApplication.query.filter_by(permit_id=permit.id).first()
    if not leave:
        flash('Associated leave application not found.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    employee = permit.employee

    # ✅ Move workflow to Head after HR approval
    permit.status = 'In Progress'
    permit.current_stage = 'Mayor'
    permit.hr_remarks = remarks
    permit.date_released = datetime.utcnow()

    # ✅ Log history
    history_entry = PermitRequestHistory(
        permit_request_id=permit.id,
        action_by=current_user.id,
        action='Approved',
        remarks=remarks
    )
    db.session.add(history_entry)

    # ✅ Notify employee
    subject = f"Your {leave.leave_type} leave has been approved by HR"
    remarks_section = f"<p><strong>HR Remarks:</strong> {remarks}</p>" if remarks else ""

    body = f"""✅ <strong>Leave Approval Notification</strong><br><br>
    <p>Dear <strong>{employee.user.name}</strong>,</p>
    <p>Your <strong>{leave.leave_type}</strong> request from 
    <strong>{leave.date_from.strftime('%B %d, %Y')}</strong> to 
    <strong>{leave.date_to.strftime('%B %d, %Y')}</strong> 
    ({leave.working_days} working day(s)) has been <strong>Approved by HR</strong> 
    and is now forwarded to <strong>Mayor</strong>.</p>
    {remarks_section}

    <hr>
    <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
    <p>– HR System</p>
    """

    db.session.add(UserMessage(
        sender_id=current_user.id,
        recipient_id=employee.user.id,
        subject=subject,
        body=body,
        message_type='system'
    ))


    # ✅ Notify Mayor
    mayor_employee = (
        Employee.query
        .join(PermanentEmployeeDetails)
        .join(Position)
        .filter(db.func.lower(Position.title) == "municipal mayor")
        .first()
    )

    mayor_user = mayor_employee.user if mayor_employee and mayor_employee.user else None

    if mayor_user:
        mayor_subject = "Leave Request Requires Your Approval"
        mayor_body = f"""📝 <strong>Leave Request Pending Final Approval</strong><br><br>
        <p>Dear <strong>{mayor_user.name}</strong>,</p>
        <p>A <strong>{leave.leave_type}</strong> leave request filed by 
        <strong>{employee.user.name}</strong> from 
        <strong>{leave.date_from.strftime('%B %d, %Y')}</strong> to 
        <strong>{leave.date_to.strftime('%B %d, %Y')}</strong> 
        ({leave.working_days} working day(s)) has been approved by HR 
        and now requires your <strong>final approval</strong>.</p>
        <p><strong>HR Remarks:</strong> {remarks or "None"}</p>

        <hr>
        <p><em>⚠ This is an automated notification. Please log in to the system to take action.</em></p>
        <p>– HR System</p>
        """
        db.session.add(UserMessage(
            sender_id=current_user.id,
            recipient_id=mayor_user.id,
            subject=mayor_subject,
            body=mayor_body,
            message_type='system'
        ))

    try:
        db.session.commit()
        flash(f'Leave application approved by HR and forwarded to Mayor.', 'success-timed')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to approve leave: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))


# OK 
@app.route('/approve_leave/head', methods=['POST'])
@login_required
def approve_leave_head():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks')

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Leave':
        flash('Invalid permit type.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    if permit.current_stage == 'User Cancelled' or permit.status == 'Cancelled':
        flash("This leave request has already been cancelled by the employee.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    # ✅ Only allow Head to approve if stage is Head
    if permit.current_stage != 'Head':
        flash("This leave request is not in Head stage anymore.", "warning")
        return redirect(request.referrer or url_for('Userspermit'))

    leave = LeaveApplication.query.filter_by(permit_id=permit.id).first()
    if not leave:
        flash('Associated leave application not found.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    employee = permit.employee

    # ✅ Move workflow to Mayor after Head approval
    permit.status = 'In Progress'
    permit.current_stage = 'HR'
    permit.head_remarks = remarks

    # ✅ Log history
    history_entry = PermitRequestHistory(
        permit_request_id=permit.id,
        action_by=current_user.id,
        action='Approved',
        remarks=remarks
    )
    db.session.add(history_entry)

    # ✅ Notify employee
    subject = f"Your {leave.leave_type} leave has been approved by Department Head"
    remarks_section = f"<p><strong>Head Remarks:</strong> {remarks}</p>" if remarks else ""

    body = f"""✅ <strong>Leave Approval Notification</strong><br><br>
    <p>Dear <strong>{employee.user.name}</strong>,</p>
    <p>Your <strong>{leave.leave_type}</strong> request from 
    <strong>{leave.date_from.strftime('%B %d, %Y')}</strong> to 
    <strong>{leave.date_to.strftime('%B %d, %Y')}</strong> 
    ({leave.working_days} working day(s)) has been <strong>Approved by your Department Head</strong> 
    and is now forwarded to <strong>Mayor</strong>.</p>
    {remarks_section}

    <hr>
    <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
    <p>– HR System</p>
    """

    db.session.add(UserMessage(
        sender_id=current_user.id,
        recipient_id=employee.user.id,
        subject=subject,
        body=body,
        message_type='system'
    ))


    # ✅ Notify HR users instead of Mayor
    hr_users = (
    Users.query
    .join(UserPermission)
    .filter(
        db.func.lower(Users.role) == 'hr',
        UserPermission.permission == 'write_leave',
        UserPermission.is_allowed == True
    )
    .all()
    )

    for hr in hr_users:
        hr_subject = f"Leave Request Requires Your Approval ({employee.user.name})"
        hr_body = f"""📝 <strong>Leave Request Pending Approval</strong><br><br>
        <p>Dear <strong>{hr.name}</strong>,</p>
        <p>A <strong>{leave.leave_type}</strong> leave request filed by 
        <strong>{employee.user.name}</strong> from 
        <strong>{leave.date_from.strftime('%B %d, %Y')}</strong> to 
        <strong>{leave.date_to.strftime('%B %d, %Y')}</strong> 
        ({leave.working_days} working day(s)) has been approved by the Department Head 
        and now requires your approval.</p>
        <p><strong>Head Remarks:</strong> {remarks or "None"}</p>

        <hr>
        <p><em>⚠ This is an automated notification. Please log in to the system to take action.</em></p>
        <p>– HR System</p>
        """
        db.session.add(UserMessage(
            sender_id=current_user.id,
            recipient_id=hr.id,
            subject=hr_subject,
            body=hr_body,
            message_type='system'
        ))

    try:
        db.session.commit()
        flash(f'Leave application approved by Head and forwarded to Mayor.', 'success-timed')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to approve leave: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))




@app.route('/approve_leave/mayor', methods=['POST'])
@login_required
@role_required('head') 
def approve_leave_mayor():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks')

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Leave':
        flash('Invalid permit type.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    leave = LeaveApplication.query.filter_by(permit_id=permit.id).first()
    if not leave:
        flash('Associated leave application not found.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    employee = permit.employee
    credit = employee.credit_balance

    leave_type = leave.leave_type.lower()
    deduct_credits = leave_type in ['vacation leave', 'sick leave', 'force leave']

    try:
        leave_days = float(leave.working_days)  # 1 day = 1.0 credit
    except ValueError:
        flash("Invalid number of leave days recorded.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    deducted = 0.0
    unpaid = 0.0

    if deduct_credits:
        if leave_type in ['vacation leave', 'force leave']:
            available = int(credit.vacation_remaining)
            requested = int(leave_days)
            reserved_for_force_leave = 5

            if leave_type == 'vacation leave':
                # ✅ Keep 5 days in reserve
                usable_vacation = max(0, available - reserved_for_force_leave)
            else:
                # ✅ Force leave can use everything, even the reserved 5 days
                usable_vacation = available

            deducted = min(usable_vacation, requested)
            unpaid = requested - deducted

            # Update vacation leave balance
            if deducted > 0:
                credit.update_vacation(used=deducted)

            db.session.add(CreditTransaction(
                employee_id=employee.id,
                leave_type="Vacation",
                action="Used",
                amount=-deducted,
                notes=f'{leave.leave_type} approved by Mayor (Deducted {deducted}, Unpaid {unpaid}) — {"Reserved 5 days for Force Leave" if leave_type=="vacation leave" else "All credits usable for Force Leave"}',
                timestamp=datetime.utcnow()
            ))

        elif leave_type == 'sick leave':  # ✅ aligned properly now
            available = credit.sick_remaining
            available_whole_days = int(available)  # ✅ only whole days count
            deducted = min(available_whole_days, int(leave_days))
            unpaid = leave_days - deducted

            credit.update_sick(used=deducted)

            db.session.add(CreditTransaction(
                employee_id=employee.id,
                leave_type="Sick",
                action="Used",
                amount=deducted,
                notes=f'Sick leave approved by Mayor (Deducted {deducted}, Unpaid {unpaid})',
                timestamp=datetime.utcnow()
            ))

    leave.paid_days = int(deducted)
    
    # ✅ Finalize workflow
    permit.status = 'Completed'
    permit.current_stage = 'Completed'
    permit.mayor_remarks = remarks

    # ✅ Log history
    history_entry = PermitRequestHistory(
        permit_request_id=permit.id,
        action_by=current_user.id,
        action='Approved by Mayor',
        remarks=remarks
    )
    db.session.add(history_entry)

    # ✅ Notify employee
    subject = f"Your {leave.leave_type} leave has been finally approved by the Mayor"
    remarks_section = f"<p><strong>Mayor Remarks:</strong> {remarks}</p>" if remarks else ""

    unpaid_section = ""
    if unpaid > 0:
        unpaid_section = f"<p>⚠ Note: {unpaid} day(s) are considered <strong>Unpaid Leave</strong> due to insufficient credits.</p>"

    body = f"""🎉 <strong>Final Leave Approval Notification</strong><br><br>
    <p>Dear <strong>{employee.user.name}</strong>,</p>
    <p>Your <strong>{leave.leave_type}</strong> request from 
    <strong>{leave.date_from.strftime('%B %d, %Y')}</strong> to 
    <strong>{leave.date_to.strftime('%B %d, %Y')}</strong> 
    ({leave.working_days} working day(s)) has been <strong>Approved by the Mayor</strong>.</p>
    {remarks_section}
    <p>✅ {deducted} credit(s) deducted from your {leave.leave_type} balance.</p>
    {unpaid_section}

    <hr>
    <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
    <p>– HR System</p>
    """

    db.session.add(UserMessage(
        sender_id=current_user.id,
        recipient_id=employee.user.id,
        subject=subject,
        body=body,
        message_type='system'
    ))

    try:
        db.session.commit()
        flash(f'Leave approved by Mayor. {deducted} credit(s) deducted, {unpaid} day(s) unpaid.', 'success-timed')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to approve leave: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))





@app.route('/reject_leave', methods=['POST'])
@login_required
def reject_leave():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('hr_remarks')

    # ✅ Basic validation
    if not permit_id:
        flash('Missing permit ID.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    if not remarks or remarks.strip() == '':
        flash('Remarks are required to reject a leave application.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        # ✅ Get LeaveApplication by permit_id
        leave_application = LeaveApplication.query.filter_by(permit_id=permit_id).first()
        if not leave_application:
            flash('Leave application not found.', 'danger')
            return redirect(request.referrer or url_for('Userspermit'))

        permit_request = leave_application.permit

        # ✅ Can only reject if still active
        if permit_request.status in ['Rejected', 'Completed']:
            flash('This leave application can no longer be rejected.', 'warning')
            return redirect(request.referrer or url_for('Userspermit'))

        # ✅ Update permit request
        permit_request.status = 'Rejected'
        permit_request.current_stage = 'Rejected'

        # Save remarks based on who rejected
        permit_request.hr_remarks = remarks.strip()

        # ✅ Log rejection in history
        history_entry = PermitRequestHistory(
            permit_request_id=permit_request.id,
            action_by=current_user.id,
            action='Rejected',
            remarks=remarks.strip()
        )
        db.session.add(history_entry)

        # ✅ Notify employee
        employee = permit_request.employee
        subject = f"Your {leave_application.leave_type} leave has been rejected"

        body = f"""❌ <strong>Leave Rejection Notification</strong><br><br>
        <p>Dear <strong>{employee.user.name}</strong>,</p>
        <p>Your <strong>{leave_application.leave_type}</strong> request from 
        <strong>{leave_application.date_from.strftime('%B %d, %Y')}</strong> to 
        <strong>{leave_application.date_to.strftime('%B %d, %Y')}</strong> 
        ({leave_application.working_days} working day(s)) has been <strong>Rejected</strong>.</p>
        <p><strong>Remarks:</strong> {remarks.strip()}</p>

        <hr>
        <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
        <p>– HR System</p>
        """

        db.session.add(UserMessage(
            sender_id=current_user.id,
            recipient_id=employee.user.id,
            subject=subject,
            body=body,
            message_type='system'
        ))

        db.session.commit()
        flash('Leave application rejected successfully.', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while rejecting the leave application: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))




@app.route('/approve_travel', methods=['POST'])
@login_required
def approve_travel():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks', '').strip()

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    # Get permit
    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Travel Order':
        flash('Invalid permit type.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    travel_order = TravelOrder.query.filter_by(permit_id=permit_id).first()
    if not travel_order:
        flash('Travel Order not found for this permit.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    
    if permit.current_stage == 'User Cancelled' or permit.status == 'Cancelled':
        flash("This Travel request has already been cancelled by the employee.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    # Only allow HR to approve at HR stage
    if permit.current_stage != 'HR':
        flash('You are not authorized to approve at this stage.', 'warning')
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        # Log approval in PermitRequestHistory
        history_entry = PermitRequestHistory(
            permit_request_id=permit.id,
            action_by=current_user.id,
            action='Approved',
            remarks=remarks
        )
        db.session.add(history_entry)

        # Update permit current_stage → next stage (HR → Head → Mayor → Completed)
        permit.current_stage = 'Mayor'
        permit.hr_remarks = remarks
        permit.status = 'In Progress'  # still pending until Head/Major approves

        # Notify the Mayor
        mayor_employee = (
        Employee.query
        .join(PermanentEmployeeDetails)
        .join(Position)
        .filter(db.func.lower(Position.title) == "municipal mayor")
        .first()
        )

        mayor_user = mayor_employee.user if mayor_employee and mayor_employee.user else None
        if mayor_user:
            subject = "Travel Order Requires Your Approval"
            body = f"""⏳ <strong>Travel Order Pending Approval</strong><br><br>
            <p>Dear <strong>{mayor_user.name}</strong>,</p>
            <p>A Travel Order filed by <strong>{permit.employee.user.name}</strong> 
            to <strong>{travel_order.destination}</strong> on 
            <strong>{travel_order.date_departure.strftime('%B %d, %Y')}</strong> 
            is awaiting your approval.</p>
            <p>HR Remarks: {remarks or 'None'}</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=mayor_user.id,
                subject=subject,
                body=body,
                message_type='system'
            ))

        # ✅ Notify the requesting employee as well
        employee_user = permit.employee.user
        if employee_user:
            emp_subject = "Your Travel Order has been Approved by HR"
            emp_body = f"""✅ <strong>Travel Order Update</strong><br><br>
            <p>Dear <strong>{employee_user.name}</strong>,</p>
            <p>Your Travel Order request to <strong>{travel_order.destination}</strong> on 
            <strong>{travel_order.date_departure.strftime('%B %d, %Y')}</strong> 
            has been <strong>approved by HR</strong>.</p>
            <p>Remarks: {remarks or 'None'}</p>
            <p>Next Step: Waiting for approval from Mayor.</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=employee_user.id,
                subject=emp_subject,
                body=emp_body,
                message_type='system'
            ))

        db.session.commit()
        flash(f'Travel Order approved by HR and sent to Mayor for next approval.', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Failed to approve travel order: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))




@app.route('/approve_travel_head', methods=['POST'])
@login_required
def approve_travel_head():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks', '').strip()

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    # Get permit
    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Travel Order':
        flash('Invalid permit type.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    travel_order = TravelOrder.query.filter_by(permit_id=permit_id).first()
    if not travel_order:
        flash('Travel Order not found for this permit.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    # Only allow Department Head to approve at Head stage
    if permit.current_stage != 'Head':
        flash('You are not authorized to approve at this stage.', 'warning')
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        # Log approval in PermitRequestHistory
        history_entry = PermitRequestHistory(
            permit_request_id=permit.id,
            action_by=current_user.id,
            action='Approved',
            remarks=remarks
        )
        db.session.add(history_entry)

        # Update permit current_stage → next stage (Head → Mayor)
        permit.current_stage = 'HR'
        permit.hr_remarks = remarks
        permit.status = 'In Progress'

        hr_users = (
        Users.query
        .join(UserPermission)
        .filter(
            db.func.lower(Users.role) == 'hr',
            UserPermission.permission == 'write_travel',
            UserPermission.is_allowed == True
        )
        .all()
        )

        for hr in hr_users:
            subject = "Travel Order Requires HR Processing"
            body = f"""⏳ <strong>Travel Order Pending HR Review</strong><br><br>
            <p>Dear <strong>{hr.name}</strong>,</p>
            <p>A Travel Order filed by <strong>{permit.employee.user.name}</strong> 
            to <strong>{travel_order.destination}</strong> on 
            <strong>{travel_order.date_departure.strftime('%B %d, %Y %I:%M %p')}</strong> 
            has been <strong>approved by the Department Head</strong> and now awaits your processing.</p>
            <p><strong>Head Remarks:</strong> {remarks or 'None'}</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=hr.id,
                subject=subject,
                body=body,
                message_type='system'
            ))


         # 🔹 Notify the employee (requester)
        requester_user = permit.employee.user
        if requester_user:
            subject = "Your Travel Order was Approved by Department Head"
            body = f"""✅ <strong>Travel Order Update</strong><br><br>
            <p>Dear <strong>{requester_user.name}</strong>,</p>
            <p>Your Travel Order request to <strong>{travel_order.destination}</strong> 
            on <strong>{travel_order.date_departure.strftime('%B %d, %Y %I:%M %p')}</strong> 
            has been <strong>approved by your Department Head</strong> and is now forwarded to 
            the <strong>HR</strong>.</p>
            <p><strong>Head Remarks:</strong> {remarks or 'None'}</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=requester_user.id,
                subject=subject,
                body=body,
                message_type='system'
            ))

        db.session.commit()
        flash(f'Travel Order approved by Head and sent to Mayor for next approval.', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Failed to approve travel order: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))



@app.route('/approve_travel_mayor', methods=['POST'])
@login_required
def approve_travel_mayor():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks', '').strip()

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    # Get permit
    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Travel Order':
        flash('Invalid permit type.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    travel_order = TravelOrder.query.filter_by(permit_id=permit_id).first()
    if not travel_order:
        flash('Travel Order not found for this permit.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    # ✅ Only allow Mayor to approve at Mayor stage
    if permit.current_stage != 'Mayor':
        flash('You are not authorized to approve at this stage.', 'warning')
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        # Log approval in PermitRequestHistory
        history_entry = PermitRequestHistory(
            permit_request_id=permit.id,
            action_by=current_user.id,
            action='Approved',
            remarks=remarks
        )
        db.session.add(history_entry)

        # ✅ Update permit (Mayor → Completed)
        permit.current_stage = 'Completed'
        permit.hr_remarks = remarks
        permit.status = 'Completed'

        # ✅ Create a TravelLog for tracking
        last_tracking = db.session.query(
            db.func.max(db.cast(TravelLog.tracking_id, db.Integer))
        ).scalar()
        next_tracking_id = str((last_tracking or 0) + 1)

        travel_log = TravelLog(
            travel_order_id=travel_order.id,
            status='Pending',  
            tracking_id=next_tracking_id,
            
        )
        db.session.add(travel_log)

        # ✅ Notify the requesting employee that their Travel Order was approved
        employee_user = permit.employee.user if permit.employee and permit.employee.user else None

        if employee_user:
            subject = "Your Travel Order Has Been Approved ✅"
            body = f"""🎉 <strong>Travel Order Approved</strong><br><br>
            <p>Dear <strong>{employee_user.name}</strong>,</p>
            <p>Your Travel Order request to <strong>{travel_order.destination}</strong> on 
            <strong>{travel_order.date_departure.strftime('%B %d, %Y %I:%M %p')}</strong> 
            has been <strong>fully approved</strong> by the Municipal Mayor.</p>
            <p><strong>Mayor's Remarks:</strong> {remarks or 'None'}</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=employee_user.id,
                subject=subject,
                body=body,
                message_type='system'
            ))

        db.session.commit()
        flash(f'Travel Order approved by Mayor. Request is now completed. Tracking ID: {next_tracking_id}', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Failed to approve travel order: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))




@app.route('/reject_travel_order', methods=['POST'])
@login_required
def reject_travel_order():
    permit_id = request.form.get('travel_order_id')
    remarks = request.form.get('hr_remarks', '').strip()

    if not permit_id:
        flash('Missing travel order ID.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    if not remarks:
        flash('Remarks are required to reject the travel order.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        travel_order = TravelOrder.query.filter_by(permit_id=permit_id).first()
        if not travel_order:
            flash('Travel order not found.', 'danger')
            return redirect(request.referrer or url_for('Userspermit'))

        permit_request = travel_order.permit

        # Prevent rejecting if already finished
        if permit_request.status in ['Rejected', 'Completed']:
            flash('This travel order can no longer be rejected.', 'warning')
            return redirect(request.referrer or url_for('Userspermit'))

        # ✅ Allow HR, Head, or Mayor to reject
        if permit_request.current_stage not in ['HR', 'Head', 'Mayor']:
            flash('You are not authorized to reject at this stage.', 'warning')
            return redirect(request.referrer or url_for('Userspermit'))

        # ✅ Update permit request
        permit_request.status = 'Rejected'
        permit_request.current_stage = 'Rejected'
        permit_request.hr_remarks = remarks  # always store remarks here

        # ✅ Log rejection in history
        history_entry = PermitRequestHistory(
            permit_request_id=permit_request.id,
            action_by=current_user.id,
            action='Rejected',
            remarks=remarks
        )
        db.session.add(history_entry)

        # ✅ Create TravelLog entry
        last_tracking = db.session.query(
            db.func.max(db.cast(TravelLog.tracking_id, db.Integer))
        ).scalar()
        next_tracking_id = str((last_tracking or 0) + 1)

        travel_log = TravelLog(
            travel_order_id=travel_order.id,
            status='Rejected',
            tracking_id=next_tracking_id,
            notes=f"Rejected at {permit_request.current_stage} stage. {remarks}"
        )
        db.session.add(travel_log)

        # ✅ Format datetime safely
        departure_str = travel_order.date_departure.strftime('%B %d, %Y %I:%M %p')
        departure_str = departure_str.replace(' 0', ' ')  # remove leading zero from hour

        # ✅ Notify employee
        employee = permit_request.employee
        subject = "Your Travel Order has been rejected"
        body = f"""❌ <strong>Travel Order Rejection Notification</strong><br><br>
        <p>Dear <strong>{employee.user.name}</strong>,</p>
        <p>Your Travel Order request to <strong>{travel_order.destination}</strong> 
        on <strong>{departure_str}</strong> 
        for the purpose of <strong>{travel_order.purpose}</strong> has been 
        <strong>Rejected</strong>.</p>
        <p><strong>Remarks:</strong> {remarks}</p>
        <hr>
        <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
        """

        db.session.add(UserMessage(
            sender_id=current_user.id,
            recipient_id=employee.user.id,
            subject=subject,
            body=body,
            message_type='system'
        ))

        db.session.commit()
        flash('Travel order rejected successfully.', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while rejecting the travel order: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))




@app.route('/reject_clearance', methods=['POST'])
@login_required
def reject_clearance():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks', '').strip()

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Clearance Form':
        flash('Invalid permit type.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        # ✅ Log rejection in PermitRequestHistory
        history_entry = PermitRequestHistory(
            permit_request_id=permit.id,
            action_by=current_user.id,
            action='Rejected',
            remarks=remarks
        )
        db.session.add(history_entry)

        # ✅ Update permit status
        permit.status = 'Rejected'
        permit.hr_remarks = remarks
        permit.current_stage = 'Rejected'

        # ✅ Notify the employee
        employee = permit.employee
        subject = "Your Clearance Request has been Rejected"
        remarks_section = f"<p><strong>Remarks:</strong> {remarks}</p>" if remarks else ""

        body = f"""❌ <strong>Clearance Request Rejection Notification</strong><br><br>
        <p>Dear <strong>{employee.user.name}</strong>,</p>
        <p>Your <strong>Clearance Form</strong> request has been <strong>Rejected</strong>.</p>
        {remarks_section}
        <hr>
        <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
        <p>– HR System</p>
        """

        db.session.add(UserMessage(
            sender_id=current_user.id,
            recipient_id=employee.user.id,
            subject=subject,
            body=body,
            message_type='system'
        ))

        db.session.commit()
        flash('Clearance form rejected successfully.', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Failed to reject clearance form: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))


@app.route('/approve_clearance', methods=['POST'])
@login_required
def approve_clearance():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks', '').strip()

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    # Get permit
    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Clearance Form':
        flash('Invalid permit type.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    clearance = ClearanceForm.query.filter_by(permit_id=permit_id).first()
    if not clearance:
        flash('Clearance Form not found for this permit.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))



    # ✅ Only allow HR to approve at HR stage
    if permit.current_stage != 'HR':
        flash('You are not authorized to approve at this stage.', 'warning')
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        # ✅ Log approval in PermitRequestHistory
        history_entry = PermitRequestHistory(
            permit_request_id=permit.id,
            action_by=current_user.id,
            action='Approved',
            remarks=remarks
        )
        db.session.add(history_entry)

        # ✅ Update permit current_stage → next stage
        permit.current_stage = 'Mayor'
        permit.hr_remarks = remarks
        permit.status = 'In Progress'  # still pending until Head/Mayor approves

        requesting_employee = permit.employee

         # ✅ Find the Mayor
        mayor_employee = (
        Employee.query
        .join(PermanentEmployeeDetails)
        .join(Position)
        .filter(db.func.lower(Position.title) == "municipal mayor")
        .first()
        )
        
        mayor_user = mayor_employee.user if mayor_employee and mayor_employee.user else None

        # ✅ Notify the Mayor
        if mayor_user:
            subject = "Clearance Request Requires Your Approval"
            body = f"""⏳ <strong>Clearance Request Pending Final Approval</strong><br><br>
            <p>Dear <strong>{mayor_user.name}</strong>,</p>
            <p>A Clearance Request filed by <strong>{permit.employee.user.name}</strong> 
            (Purpose: <strong>{clearance.clearance_purpose if clearance.clearance_purpose != 'Other' else clearance.other_purpose}</strong>) 
            has been <strong>approved by HR</strong> and is now awaiting your final approval.</p>
            <p>HR Remarks: {remarks or 'None'}</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=mayor_user.id,
                subject=subject,
                body=body,
                message_type='system'
            ))

        # ✅ Notify the requesting employee as well
        employee_user = permit.employee.user
        if employee_user:
            emp_subject = "Your Clearance Request has been Approved by HR"
            emp_body = f"""✅ <strong>Clearance Request Update</strong><br><br>
            <p>Dear <strong>{employee_user.name}</strong>,</p>
            <p>Your Clearance Request 
            (Purpose: <strong>{clearance.clearance_purpose if clearance.clearance_purpose != 'Other' else clearance.other_purpose}</strong>) 
            has been <strong>approved by HR</strong>.</p>
            <p>Remarks: {remarks or 'None'}</p>
            <p>Next Step: Waiting for approval from Mayor.</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=employee_user.id,
                subject=emp_subject,
                body=emp_body,
                message_type='system'
            ))

        db.session.commit()
        flash(f'Clearance request approved by HR and sent to Mayor for next approval.', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Failed to approve clearance: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))



@app.route('/approve_clearance_head', methods=['POST'])
@login_required
def approve_clearance_head():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks', '').strip()

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    # Get permit
    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Clearance Form':
        flash('Invalid permit type.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    clearance = ClearanceForm.query.filter_by(permit_id=permit_id).first()
    if not clearance:
        flash('Clearance Form not found for this permit.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    if permit.current_stage == 'User Cancelled' or permit.status == 'Cancelled':
        flash("This Clearance request has already been cancelled by the employee.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    # ✅ Only allow Head to approve at Head stage
    if permit.current_stage != 'Head':
        flash('You are not authorized to approve at this stage.', 'warning')
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        # ✅ Log approval in PermitRequestHistory
        history_entry = PermitRequestHistory(
            permit_request_id=permit.id,
            action_by=current_user.id,
            action='Approved',
            remarks=remarks
        )
        db.session.add(history_entry)

        # ✅ Update permit current_stage → Mayor
        permit.current_stage = 'HR'
        permit.hr_remarks = remarks
        permit.status = 'In Progress'  # still pending until Mayor approves

        requesting_employee = permit.employee

        hr_users = (
        Users.query
        .join(UserPermission)
        .filter(
            db.func.lower(Users.role) == 'hr',
            UserPermission.permission == 'write_clearance',
            UserPermission.is_allowed == True
        )
        .all()
        )

        # ✅ Notify all HR users
        for hr in hr_users:
            subject = "Clearance Request Requires HR Review"
            body = f"""⏳ <strong>Clearance Request Pending HR Review</strong><br><br>
            <p>Dear <strong>{hr.name}</strong>,</p>
            <p>A Clearance Request filed by <strong>{permit.employee.user.name}</strong> 
            (Purpose: <strong>{clearance.clearance_purpose if clearance.clearance_purpose != 'Other' else clearance.other_purpose}</strong>) 
            has been <strong>approved by the Department Head</strong> and is now awaiting HR review.</p>
            <p>Head Remarks: {remarks or 'None'}</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=hr.id,
                subject=subject,
                body=body,
                message_type='system'
            ))

        # ✅ Notify the requesting employee as well
        employee_user = permit.employee.user
        if employee_user:
            emp_subject = "Your Clearance Request has been Approved by Your Department Head"
            emp_body = f"""✅ <strong>Clearance Request Update</strong><br><br>
            <p>Dear <strong>{employee_user.name}</strong>,</p>
            <p>Your Clearance Request 
            (Purpose: <strong>{clearance.clearance_purpose if clearance.clearance_purpose != 'Other' else clearance.other_purpose}</strong>) 
            has been <strong>approved by your Department Head</strong>.</p>
            <p>Remarks: {remarks or 'None'}</p>
            <p>Next Step: Waiting for approval from HR.</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=employee_user.id,
                subject=emp_subject,
                body=emp_body,
                message_type='system'
            ))

        db.session.commit()
        flash(f'Clearance request approved by Department Head and sent to Mayor for final approval.', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Failed to approve clearance: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))



@app.route('/approve_clearance_mayor', methods=['POST'])
@login_required
def approve_clearance_mayor():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks', '').strip()

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    # Get permit
    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Clearance Form':
        flash('Invalid permit type.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    clearance = ClearanceForm.query.filter_by(permit_id=permit_id).first()
    if not clearance:
        flash('Clearance Form not found for this permit.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    # ✅ Only allow Mayor to approve at Mayor stage
    if permit.current_stage != 'Mayor':
        flash('You are not authorized to approve at this stage.', 'warning')
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        # ✅ Log approval in PermitRequestHistory
        history_entry = PermitRequestHistory(
            permit_request_id=permit.id,
            action_by=current_user.id,
            action='Approved',
            remarks=remarks
        )
        db.session.add(history_entry)

        # ✅ Finalize the permit
        permit.current_stage = 'Completed'
        permit.status = 'Completed'
        permit.hr_remarks = remarks

        # ✅ Notify the employee
        employee_user = permit.employee.user
        if employee_user:
            subject = "Your Clearance Request has been Fully Approved"
            body = f"""🎉 <strong>Clearance Request Approved</strong><br><br>
            <p>Dear <strong>{employee_user.name}</strong>,</p>
            <p>Your Clearance Request 
            (Purpose: <strong>{clearance.clearance_purpose if clearance.clearance_purpose != 'Other' else clearance.other_purpose}</strong>) 
            has been <strong>fully approved by the Municipal Mayor</strong>.</p>
            <p>Remarks: {remarks or 'None'}</p>
            <p>Status: <strong>Approved & Completed</strong></p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=employee_user.id,
                subject=subject,
                body=body,
                message_type='system'
            ))

        db.session.commit()
        flash('Clearance request fully approved by Mayor. Employee has been notified.', 'success-timed')

    except Exception as e:
        db.session.rollback()
        flash(f'Failed to approve clearance: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('Userspermit'))




@app.route('/approve_coe', methods=['POST'])
@login_required
def approve_coe():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks', '').strip()

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    # ✅ Get permit
    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Certification of Employment':
        flash("Invalid permit type.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))


    if permit.current_stage == 'User Cancelled' or permit.status == 'Cancelled':
        flash("This COE request has already been cancelled by the employee.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    # ✅ Ensure it's still at HR stage
    if permit.current_stage != 'HR':
        flash("You are not authorized to approve at this stage.", "warning")
        return redirect(request.referrer or url_for('Userspermit'))

    try:
        # ✅ Log approval in history
        history_entry = PermitRequestHistory(
            permit_request_id=permit.id,
            action_by=current_user.id,
            action='Approved',
            remarks=remarks
        )
        db.session.add(history_entry)

        # ✅ Update permit status
        permit.status = 'Completed'
        permit.current_stage = 'Completed'
        permit.hr_remarks = remarks
        permit.date_released = datetime.utcnow()

        # ✅ Notify the requesting employee
        employee_user = permit.employee.user
        if employee_user:
            subject = "Your Certification of Employment (COE) request has been approved"
            body = f"""✅ <strong>COE Approval Notification</strong><br><br>
            <p>Dear <strong>{employee_user.name}</strong>,</p>
            <p>Your <strong>Certification of Employment</strong> request has been <strong>Approved</strong> by HR.</p>
            <p>Remarks: {remarks or 'None'}</p>
            <hr>
            <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
            <p>– HR System</p>
            """
            db.session.add(UserMessage(
                sender_id=current_user.id,
                recipient_id=employee_user.id,
                subject=subject,
                body=body,
                message_type='system'
            ))

        db.session.commit()
        flash("COE request approved successfully. Employee has been notified.", "success-timed")

    except Exception as e:
        db.session.rollback()
        flash(f"Failed to approve COE: {str(e)}", "danger")

    return redirect(request.referrer or url_for('Userspermit'))



@app.route('/reject_coe', methods=['POST'])
@login_required
def reject_coe():
    permit_id = request.form.get('permit_id')
    remarks = request.form.get('remarks')

    if not permit_id:
        flash("Missing permit ID.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    if not remarks or remarks.strip() == '':
        flash("Remarks are required to reject a COE request.", "danger")
        return redirect(request.referrer or url_for('Userspermit'))

    permit = PermitRequest.query.get_or_404(permit_id)

    if permit.permit_type != 'Certification of Employment':
        flash('Invalid permit type.', 'danger')
        return redirect(request.referrer or url_for('Userspermit'))

    # Update permit
    permit.status = 'Rejected'
    permit.hr_remarks = remarks.strip()

    # ✅ Notify the employee
    employee = permit.employee
    subject = "Your Certification of Employment (COE) request has been rejected"

    remarks_section = f"<p><strong>HR Remarks:</strong> {remarks}</p>"

    body = f"""❌ <strong>COE Request Rejection Notification</strong><br><br>
    <p>Dear <strong>{employee.user.name}</strong>,</p>
    <p>Your <strong>Certification of Employment</strong> request has been <strong>Rejected</strong>.</p>
    {remarks_section}

    <hr>
    <p><em>⚠ This is an automated notification. Please do not reply.</em></p>
    <p>– HR System</p>
    """

    db.session.add(UserMessage(
        sender_id=current_user.id,
        recipient_id=employee.user.id,
        subject=subject,
        body=body,
        message_type='system'
    ))

    try:
        db.session.commit()
        flash("COE request rejected successfully. Employee has been notified.", "success-timed")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to reject COE: {str(e)}", "danger")

    return redirect(request.referrer or url_for('Userspermit'))





@app.route('/Hr/Give/Responsibilities', methods=['POST'])
def update_user_responsibilities():
    user_id = request.form.get('user_id')
    user = Users.query.get(user_id)

    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('ManageUserCase'))

    # Define all possible permissions
    permissions = [
        'read_performance', 'write_performance',
        'read_hiring', 'write_hiring',
        'read_leave', 'write_leave',
        'read_travel', 'write_travel',
        'read_clearance', 'write_clearance',
        'read_coe', 'write_coe'
    ]

    # Process each permission checkbox
    for perm in permissions:
        is_allowed = perm in request.form  # checkbox checked?
        existing = UserPermission.query.filter_by(user_id=user.id, permission=perm).first()

        if existing:
            existing.is_allowed = is_allowed
        else:
            new_perm = UserPermission(user_id=user.id, permission=perm, is_allowed=is_allowed)
            db.session.add(new_perm)

    try:
        db.session.commit()
        flash("User permissions updated successfully.", "success-timed")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to update permissions: {str(e)}", "danger")

    return redirect(url_for('ManageUserCase'))



@app.route('/api/user_permissions/<int:user_id>')
def api_user_permissions(user_id):
    permissions = UserPermission.query.filter_by(user_id=user_id).all()
    # Permissions format: ['read_performance', 'write_leave', ...]
    perms = {perm.permission: perm.is_allowed for perm in permissions}
    return jsonify(perms)



@app.route('/pds')
def pds():
    return render_template('landing/pds.html')
