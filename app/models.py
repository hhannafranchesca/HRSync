
from datetime import datetime, timezone

from sqlalchemy import Enum
from app import db, login_manager
from flask_login import UserMixin



class Users(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    login_id = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(70), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='employee')
    image_file = db.Column(db.String(20),nullable=False,default='default.jpg')

    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), unique=True)
    employee = db.relationship('Employee', back_populates='user', uselist=False)

    must_reset_password = db.Column(db.Boolean, default=True)

    def has_permission(self, perm_name):
        return any(
            p.permission == perm_name and p.is_allowed
            for p in self.permissions
        )
        

class UserSignature(db.Model):
    __tablename__ = 'user_signatures'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)

    # Store signature as binary (PNG/JPG)
    signature = db.Column(db.LargeBinary, nullable=False)

    # SHA256 hash of signature (for integrity checks)
    signature_hash = db.Column(db.String(64), nullable=False)

    # Relationship back to user
    user = db.relationship('Users', backref=db.backref('signature_record', uselist=False))



class UserPermission(db.Model):
    __tablename__ = 'user_permissions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    permission = db.Column(db.String(50), nullable=False)
    is_allowed = db.Column(db.Boolean, default=False)

    user = db.relationship('Users', backref='permissions')

    def __repr__(self):
        return f"<UserPermission user_id={self.user_id} permission='{self.permission}' allowed={self.is_allowed}>"



# Main Employee Table
class Employee(db.Model):
    __tablename__ = 'employees'

    id = db.Column(db.Integer, primary_key=True)

    # Personal Info
    last_name = db.Column(db.String(50), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50))
  
    
    # Employment Info
    status = db.Column(db.String(20)) # P, C, JO, etc.
    employment_status = db.Column(db.String(20), default='active') # active, inactive etc
    # Relationship to user account

    # Department Foreign Key (NEW)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))

    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    # Automatic creation of Account (PENDING)
    user = db.relationship('Users', back_populates='employee', uselist=False)

    # Relationships to specific details
    
    permanent_details = db.relationship('PermanentEmployeeDetails', backref='employee', uselist=False)
    casual_details = db.relationship('CasualEmployeeDetails', backref='employee', uselist=False)
    job_order_details = db.relationship('JobOrderDetails', backref='employee', uselist=False)

    # ADDED HERE
    department = db.relationship('Department', backref='employees')

     # Soft delete method
    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.employment_status = 'inactive'

    # Restore from soft delete
    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        db.session.commit()
    
    @property
    def is_department_head(self):
        if self.permanent_details and self.permanent_details.position.type == 'Head':
            return True
        if self.casual_details and self.casual_details.position.type == 'Head':
            return True
        if self.job_order_details and self.job_order_details.position_title.lower() == 'Head':
            return True
        return False
    

    @property
    def approval_department_id(self):
        """Get the department that should handle approvals."""
        if self.casual_details and self.casual_details.assigned_department_id:
            return self.casual_details.assigned_department_id
        if self.job_order_details and self.job_order_details.assigned_department_id:
            return self.job_order_details.assigned_department_id
        return self.department_id  # default for permanent



 

# Permanent Employee Details Table
class PermanentEmployeeDetails(db.Model):
    __tablename__ = 'permanent_employee_details'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    
    item_number = db.Column(db.String(20), nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey('positions.id'), nullable=False)
    salary_grade = db.Column(db.Integer)
    authorized_salary = db.Column(db.String(50))
    actual_salary = db.Column(db.String(50))
    step = db.Column(db.Integer)
    area_code = db.Column(db.String(20))
    area_type = db.Column(db.String(50))
    level = db.Column(db.String(10))
    sex = db.Column(db.String(10), nullable=False)
    date_of_birth = db.Column(db.Date)
    tin = db.Column(db.String(20))
    umid_no = db.Column(db.String(20))
    date_original_appointment = db.Column(db.Date)
    date_last_promotion = db.Column(db.Date)
    eligibility = db.Column(db.String(100))
    comments = db.Column(db.String(255))
    
    position = db.relationship('Position')

# Casual Employee Details Table
class CasualEmployeeDetails(db.Model):
    __tablename__ = 'casual_employee_details'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)

    name_extension = db.Column(db.String(10))  # Example: Jr., Sr., II, etc.
    position_id = db.Column(db.Integer, db.ForeignKey('positions.id'), nullable=False)

    equivalent_salary = db.Column(db.String(100))  # Equivalent salary/pay grade
    daily_wage = db.Column(db.Float)
    contract_start = db.Column(db.Date)
    contract_end = db.Column(db.Date)

    assigned_department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    assigned_department = db.relationship('Department', foreign_keys=[assigned_department_id])  

    position = db.relationship('Position')

# Job Order Employee Details Table
class JobOrderDetails(db.Model):
    __tablename__ = 'job_order_details'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    position_title = db.Column(db.String(100))

    assigned_department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    assigned_department = db.relationship('Department', foreign_keys=[assigned_department_id])

    date_hired = db.Column(db.Date, nullable=True)

    contract_start = db.Column(db.Date, nullable=True)
    contract_end = db.Column(db.Date, nullable=True)


class Department(db.Model):
    __tablename__ = 'departments'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    service = db.Column(db.Text)


    @property
    def service_count(self):
        if not self.service:
            return 0
        # Split the services by comma, strip spaces, and count
        return len([s.strip() for s in self.service.split(',') if s.strip()])


class Position(db.Model):
    __tablename__ = 'positions'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # Position type (e.g., "head", "employee")
    number_of_positions = db.Column(db.Integer, default=1, nullable=False)  # Number of positions for this title

    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))

    department = db.relationship('Department', backref='positions')



class JobOrderHistory(db.Model):
    __tablename__ = 'job_order_history'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)

    # Snapshot of details
    position_title = db.Column(db.String(100))
    assigned_department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    assigned_department = db.relationship('Department', foreign_keys=[assigned_department_id])

    contract_start = db.Column(db.Date)
    contract_end = db.Column(db.Date)

    # End of contract details
    return_date = db.Column(db.Date, nullable=False)  # When the contract was ended
    reason = db.Column(db.String(100), nullable=False)

    archived_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", backref="job_order_history")
    

class CasualEmployeeHistory(db.Model):
    __tablename__ = 'casual_employee_history'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)

    # Snapshot of details
    position_id = db.Column(db.Integer, db.ForeignKey('positions.id'))
    equivalent_salary = db.Column(db.String(100))
    daily_wage = db.Column(db.Float)
    contract_start = db.Column(db.Date)
    contract_end = db.Column(db.Date)

    # Return details
    return_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(100), nullable=False)

    archived_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", backref="casual_history")
    position = db.relationship("Position")


# BAGO
class EmploymentTerminationHistory(db.Model):
    __tablename__ = 'employment_termination_history'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    employment_type = db.Column(db.String(20), nullable=False)  # "permanent", "casual", "job_order"

    reason = db.Column(db.String(255), nullable=False)
    terminated_at = db.Column(db.DateTime, default=datetime.utcnow)
    terminated_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # who terminated

    employee = db.relationship('Employee', backref='termination_records')
    user = db.relationship('Users', backref='terminated_employees')



class PermanentSalaryHistory(db.Model):
    __tablename__ = 'permanent_salary_history'

    id = db.Column(db.Integer, primary_key=True)
    permanent_employee_id = db.Column(db.Integer, db.ForeignKey('permanent_employee_details.id'), nullable=False)

    previous_salary = db.Column(db.String(50))
    new_salary = db.Column(db.String(50))
    effective_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(255))
    updated_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    permanent_employee = db.relationship('PermanentEmployeeDetails', backref='salary_history')


class JobLog(db.Model):
    __tablename__ = 'job_logs'

    id = db.Column(db.Integer, primary_key=True)
    job_name = db.Column(db.String(100), unique=True, nullable=False)
    last_run = db.Column(db.DateTime, nullable=False)


class PermanentEmployeeBenefitEligibility(db.Model):
    __tablename__ = 'permanent_benefit_eligibility'

    id = db.Column(db.Integer, primary_key=True)
    permanent_employee_id = db.Column(db.Integer, db.ForeignKey('permanent_employee_details.id'), nullable=False)

    benefit_name = db.Column(db.String(100), nullable=False)
    eligibility_years = db.Column(db.Integer, nullable=False)  # e.g., 10 years
    is_eligible = db.Column(db.Boolean, default=False)
    eligible_since = db.Column(db.Date, nullable=True)

    checked_at = db.Column(db.DateTime, default=datetime.utcnow)
    checked_by = db.Column(db.String(100))  # e.g., 'System', 'HR Officer'

    permanent_employee = db.relationship('PermanentEmployeeDetails', backref='benefit_eligibility')



class UserMessage(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    is_sent_copy = db.Column(db.Boolean, default=False)  # for sent box
    message_type = db.Column(db.String(50), nullable=False, default='personal')

    sender = db.relationship('Users', foreign_keys=[sender_id], backref='sent_messages')
    recipient = db.relationship('Users', foreign_keys=[recipient_id], backref='received_messages')


class MessageAttachment(db.Model):
    __tablename__ = 'message_attachments'

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    

    message = db.relationship('UserMessage', backref='attachments')


class LoginActivity(db.Model):
    __tablename__ = 'login_activities'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(100))
    success = db.Column(db.Boolean, default=True)

    user = db.relationship('Users', backref='login_activities')


# SETUP THE EVALUATION CYCLE
class EvaluationPeriod(db.Model):
    __tablename__ = 'evaluation_periods' 
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

       # Inside EvaluationPeriod
    ipcrs = db.relationship('IPCR', backref='period', lazy=True)
    

 
    


# individual employee’s performance report, submitted by the employee and graded by the department head.
class IPCR(db.Model):
    __tablename__ = 'ipcrs'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'))
    period_id = db.Column(db.Integer, db.ForeignKey('evaluation_periods.id'))
    submitted = db.Column(db.Boolean, default=False)
    graded = db.Column(db.Boolean, default=False)
    late_submission = db.Column(db.Boolean, default=False) 
    final_overall_rating = db.Column(db.Float)
    final_average_rating = db.Column(db.Float)
    adjective_rating = db.Column(db.String(50))  # e.g., "Outstanding"

    date_submitted = db.Column(db.DateTime, nullable=True)

    employee = db.relationship('Employee', backref='ipcrs')


# Each IPCR has sections like Core Functions or Strategic Objectives. This table stores each of those sections.
class EvaluationSection(db.Model):
    __tablename__ = 'evaluation_sections'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50))  # 'Strategic Objective', 'Core Function', etc.
    ipcr_id = db.Column(db.Integer, db.ForeignKey('ipcrs.id'), nullable=True)

    # Relationships for easy access from both IPCR
    ipcr = db.relationship('IPCR', backref='sections')
    section_items = db.relationship('SectionItem', backref='section', lazy=True)

# Stores each row inside an evaluation section. A row represents an item to be graded, like a specific MFO or success indicator.
class SectionItem(db.Model):
    __tablename__ = 'section_items'
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('evaluation_sections.id'))
    mfo = db.Column(db.String(255))
    success_indicator = db.Column(db.Text)
    allotted_budget = db.Column(db.String(100))
    accountable = db.Column(db.String(255))
    accomplishment = db.Column(db.Text)
    rating_q = db.Column(db.Float)
    rating_e = db.Column(db.Float)
    rating_t = db.Column(db.Float)
    rating_a = db.Column(db.Float)
    remarks = db.Column(db.Text)



class AIInsight(db.Model):
    __tablename__ = 'ai_insights'
    id = db.Column(db.Integer, primary_key=True)

    # Foreign keys to IPCR
    ipcr_id = db.Column(db.Integer, db.ForeignKey('ipcrs.id'), nullable=True)

    ai_summary = db.Column(db.Text, nullable=True)
    ai_suggestion = db.Column(db.Text, nullable=True)
    ai_training_recommendations = db.Column(db.Text, nullable=True)

    last_updated = db.Column(db.DateTime, nullable=True)

    # Relationships for easy access
    ipcr = db.relationship('IPCR', backref=db.backref('ai_insight', uselist=False))




# JOB HIRING

class JobPosting(db.Model):
    __tablename__ = 'job_postings'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    description = db.Column(db.Text)
    qualifications = db.Column(db.Text)
    job_position_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.Enum('Open', 'Closed'), default='Open', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    number_of_openings = db.Column(db.Integer, nullable=False, default=1)

    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    department = db.relationship('Department', backref='job_postings')
    applicants = db.relationship('Applicant', backref='job_posting', cascade='all, delete-orphan')

     # Soft delete method
    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        db.session.commit()

    # Restore from soft delete
    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        db.session.commit()


class Applicant(db.Model):
    __tablename__ = 'applicants'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job_postings.id'), nullable=False)

    # Basic Info
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)

    # Uploaded PDS
    pds_path = db.Column(db.String(255), nullable=True)

    # Status
    status = db.Column(
        db.Enum('Received', 'Under Review', 'Interviewed', 'Hired', 'Rejected'),
        default='Received',
        nullable=False
    )
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)

    # AI scoring & insights
    application_score = db.Column(db.Float)
    pds_match = db.Column(db.Text)
    strengths = db.Column(db.Text)     # e.g. "Leadership, Teamwork"
    weaknesses = db.Column(db.Text)    # e.g. "Needs more supervisory experience"
    summary = db.Column(db.Text)       # HR-style evaluation

    # Flattened PDS data
    education = db.Column(db.Text)         # JSON string or plain text list of education
    work_experience = db.Column(db.Text)   # JSON string or plain text list of experiences
    eligibility = db.Column(db.Text)       # JSON string or plain text list of eligibility records
    voluntary_work = db.Column(db.Text)    # JSON string or plain text list
    trainings = db.Column(db.Text)         # JSON string or plain text list
    other_skills = db.Column(db.Text)      # extracted skills
    recognitions = db.Column(db.Text)      # awards/recognition
    memberships = db.Column(db.Text)       # org memberships

    interviews = db.relationship('Interview', backref='applicant', lazy=True, cascade="all, delete-orphan")





class Interview(db.Model):
    __tablename__ = 'interviews'

    id = db.Column(db.Integer, primary_key=True)
    applicant_id = db.Column(db.Integer, db.ForeignKey('applicants.id'), nullable=False)
    
    scheduled_date = db.Column(db.Date, nullable=False)
    scheduled_time = db.Column(db.Time, nullable=False)
    method = db.Column(db.String(100))  # Zoom, In-person, etc.
    interviewer = db.Column(db.String(100))
    interview_notes = db.Column(db.Text)
    status = db.Column(db.Enum('Scheduled', 'Completed', 'Cancelled'), default='Scheduled')
    result = db.Column(db.Enum('Pending', 'Approved', 'Rejected'), default='Pending')
    rejection_reason = db.Column(db.Text, nullable=True)
    approval_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


   

class IssueReport(db.Model):
    __tablename__ = 'issue_reports'

    id = db.Column(db.Integer, primary_key=True)
    reporter_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)        # The user who reports
    reported_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)        # The user being reported

    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='Open')  # Example statuses: Open, In Progress, Resolved, Closed

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    remarks = db.Column(db.Text, nullable=True)

    # Relationships to Users
    reporter = db.relationship('Users', foreign_keys=[reporter_user_id], backref='issues_reported')
    reported = db.relationship('Users', foreign_keys=[reported_user_id], backref='issues_received')




# PERMITS


class PermitRequest(db.Model):
    __tablename__ = 'permit_requests'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    permit_type = db.Column(
        db.Enum('Leave', 'Travel Order', 'Clearance Form', 'Certification of Employment', name='permit_type_enum'),
        nullable=False
    )

    date_requested = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='Pending')  # Pending, Approved, Released, Rejected
    
    # Track approval stage (HR → Head → Mayor → Completed)
    current_stage = db.Column(db.String(50), default='HR')
    
    hr_remarks = db.Column(db.Text)
    date_released = db.Column(db.DateTime, nullable=True)

    employee = db.relationship("Employee", backref="permit_requests")

    history = db.relationship(
        "PermitRequestHistory",
        backref="permit",
        lazy=True,
        cascade="all, delete-orphan"
    )


# BAGO (PAID DAYS COLUMN)
class LeaveApplication(db.Model):
    __tablename__ = 'leave_applications'

    id = db.Column(db.Integer, primary_key=True)
    permit_id = db.Column(db.Integer, db.ForeignKey('permit_requests.id'), unique=True)
    leave_type = db.Column(db.String(50), nullable=False)
    working_days = db.Column(db.String(50), nullable=False)
    date_from = db.Column(db.Date, nullable=False)
    date_to = db.Column(db.Date, nullable=False)
    salary = db.Column(db.String(50), nullable=True)
    
    paid_days = db.Column(db.Integer, nullable=True, default=0)

    permit = db.relationship("PermitRequest", backref=db.backref("leave_detail", uselist=False))


# BAGO (ATTACHMENT COLUMN)
class TravelOrder(db.Model):
    __tablename__ = 'travel_orders'

    id = db.Column(db.Integer, primary_key=True)
    permit_id = db.Column(db.Integer, db.ForeignKey('permit_requests.id'), unique=True)
    
    destination = db.Column(db.String(100), nullable=False)
    purpose = db.Column(db.Text)
    date_departure = db.Column(db.DateTime)

    attachment = db.Column(db.String(255), nullable=True) 

    permit = db.relationship("PermitRequest", backref=db.backref("travel_detail", uselist=False))



class TravelLog(db.Model):
    __tablename__ = 'travel_logs'

    id = db.Column(db.Integer, primary_key=True)

    travel_order_id = db.Column(db.Integer, db.ForeignKey('travel_orders.id'), nullable=False)

    status = db.Column(
        db.Enum(
            'Pending', 
            'Approved', 
            name='travel_status_enum'
        ),
        nullable=False
    )

    log_date = db.Column(db.DateTime, nullable=True)
    tracking_id = db.Column(db.String(50), nullable=True)  # moved here
    notes = db.Column(db.Text, nullable=True)

    travel_order = db.relationship("TravelOrder", backref=db.backref("travel_logs", lazy=True, cascade="all, delete-orphan"))


class ClearanceForm(db.Model):
    __tablename__ = 'clearance_forms'

    id = db.Column(db.Integer, primary_key=True)
    permit_id = db.Column(db.Integer, db.ForeignKey('permit_requests.id'), unique=True)

    clearance_purpose = db.Column(db.String(255), nullable=True)
    other_purpose = db.Column(db.String(255), nullable=True)
    
    # SUPERUSER MAG ADD
    date_from = db.Column(db.Date, nullable=True)
    date_to = db.Column(db.Date, nullable=True)

    permit = db.relationship("PermitRequest", backref=db.backref("clearance_detail", uselist=False))


# BAGO (REASON COLUMN)
class COERequest(db.Model):
    __tablename__ = 'coe_requests'

    id = db.Column(db.Integer, primary_key=True)
    permit_id = db.Column(db.Integer, db.ForeignKey('permit_requests.id'), unique=True)
    reason = db.Column(db.String(255), nullable=True)

    permit = db.relationship("PermitRequest", backref=db.backref("coe_detail", uselist=False))


class PermitRequestHistory(db.Model):
    __tablename__ = 'permit_request_history'

    id = db.Column(db.Integer, primary_key=True)
    permit_request_id = db.Column(db.Integer, db.ForeignKey('permit_requests.id'))
    action_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.Enum('Submitted', 'Approved', 'Rejected', name='permit_action_enum'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    remarks = db.Column(db.String(255))

    # Store snapshot filename for the specific approval event
    signature_snapshot = db.Column(db.String(255), nullable=True)

    # SHA256 hash of (permit_id + user_id + timestamp + signature bytes)
    hash = db.Column(db.String(64), nullable=True)



# CaLendar

class CalendarEvent(db.Model):
    __tablename__ = 'calendar_events'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    title = db.Column(db.String(100), nullable=False)
    label = db.Column(
    db.Enum(
        'Meeting',
        'Training',
        'Leave',
        'Official Travel',
        'Holiday',
        'Public Event',
        'Administrative'
    ),
    nullable=False
    )
    
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=True)
    location = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('Users', backref='calendar_events')

    def __repr__(self):
        return f'<CalendarEvent {self.title} by User {self.user_id}>'



# BAGO (UPDATE COLUMNS FOR BOTH VACATION AND SICK LEAVE)
class EmployeeCredit(db.Model):
    __tablename__ = 'employee_credits'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False, unique=True)

    # Separate leave balances
    vacation_earned = db.Column(db.Float, default=0.0)
    vacation_used = db.Column(db.Float, default=0.0)
    vacation_remaining = db.Column(db.Float, default=0.0)

    sick_earned = db.Column(db.Float, default=0.0)
    sick_used = db.Column(db.Float, default=0.0)
    sick_remaining = db.Column(db.Float, default=0.0)

    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", backref=db.backref("credit_balance", uselist=False))

    def update_vacation(self, earned=0.0, used=0.0):
        self.vacation_earned += earned
        self.vacation_used += used
        self.vacation_remaining = self.vacation_earned - self.vacation_used
        self.last_updated = datetime.utcnow()

    def update_sick(self, earned=0.0, used=0.0):
        self.sick_earned += earned
        self.sick_used += used
        self.sick_remaining = self.sick_earned - self.sick_used
        self.last_updated = datetime.utcnow()


class CreditTransaction(db.Model):
    __tablename__ = 'credit_transactions'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)

    leave_type = db.Column(db.String(20), nullable=False)  
    # "Vacation", "Sick"

    action = db.Column(db.String(20))  # "Earned", "Used"
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.String(255))

    employee = db.relationship("Employee", backref="credit_transactions")
