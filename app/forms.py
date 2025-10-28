from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from flask_login import current_user
from wtforms import EmailField, StringField, PasswordField,SubmitField,BooleanField, ValidationError, DateField, SelectField, RadioField, TextAreaField, DecimalField, IntegerField, FieldList, FormField,MultipleFileField
from wtforms.validators import DataRequired, Length,Email, EqualTo, Optional,NumberRange,Regexp
from app.models import Users




class LoginForm(FlaskForm):

    login = StringField('Email or Login ID', validators=[DataRequired()])

    password = PasswordField('Password',validators=[DataRequired()])

    remember = BooleanField('Remember Me')

    submit = SubmitField('Login')


class RegisterForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=50)])

    email = StringField('Email', validators=[DataRequired(), Email()])

    password = PasswordField(
        'Password', 
        validators=[
            DataRequired(),
            Length(min=8, message="Password must be at least 8 characters long."),
            Regexp(
                r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]+$',
                message="Password must contain both letters and numbers."
            )
        ]
    )


    confirm_password = PasswordField(
        'Confirm Password',
        validators=[
            DataRequired(),
            EqualTo('password', message="Passwords must match."),
            Length(min=8, message="Password must be at least 8 characters long."),
            Regexp(
                r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]+$',
                message="Password must contain both letters and numbers."
            )
        ]
    )

    submit = SubmitField('Sign Up')

    # Optional: Custom validator to ensure email is unique
    def validate_email(self, email):
        user = Users.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is already registered. Please choose a different one.')
        


class AddEmployeeForm(FlaskForm):
    # Account Info
    email = EmailField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    role = SelectField('Role', choices=[('employee', 'Employee'), ('hr', 'HR')], validators=[DataRequired()])

    # Employee Info
    organizational_unit = SelectField(
        'Organizational Unit', 
        choices=[
            ('HR Department', 'HR Department'),
            ('Finance Department', 'Finance Department'),
            ('Planning Division', 'Planning Division'),
            ('Engineering Office', 'Engineering Office'),
            ("Mayor's Office", "Mayor's Office")
        ], 
        validators=[DataRequired()]
    )
    item_number = StringField('Item Number', validators=[DataRequired()])
    position_title = StringField('Position Title', validators=[DataRequired()])

    salary_grade = IntegerField('Salary Grade', validators=[Optional()])
    authorized_salary = StringField('Authorized Salary', validators=[Optional()])
    actual_salary = StringField('Actual Salary', validators=[Optional()])
    step = IntegerField('Step', validators=[Optional()])

    area_code = StringField('Area Code', validators=[Optional()])
    area_type = StringField('Area Type', validators=[Optional()])
    level = StringField('Level', validators=[Optional()])

    last_name = StringField('Last Name', validators=[DataRequired()])
    first_name = StringField('First Name', validators=[DataRequired()])
    middle_name = StringField('Middle Name', validators=[Optional()])

    sex = SelectField('Sex', choices=[('Male', 'Male'), ('Female', 'Female')], validators=[Optional()])
    date_of_birth = DateField('Date of Birth', validators=[Optional()])
    tin = StringField('TIN', validators=[Optional()])
    umid_no = StringField('UMID No.', validators=[Optional()])

    date_original_appointment = DateField('Date of Original Appointment', validators=[Optional()])
    date_last_promotion = DateField('Date of Last Promotion', validators=[Optional()])

    status = StringField('Status', validators=[Optional()])
    eligibility = StringField('Civil Service Eligibility', validators=[Optional()])
    comments = TextAreaField('Comments/Annotation', validators=[Optional()])




    
class EmployeeForm(FlaskForm):
    organizational_unit = SelectField('Organizational Unit', choices=[
        ('', 'Select Organizational Unit'),
        ('Office of the Municipal Mayor', 'Office of the Municipal Mayor'),
        ('Office of the Municipal Human Resource Management Officer', 'Office of the Municipal Human Resource Management Officer'),
        # Add all your options here...
    ], validators=[DataRequired()])

    item_number = StringField('Item Number', validators=[DataRequired()])
    position_title = SelectField('Position Title', choices=[
        ('', 'Select Position Title'),
        # Fill dynamically in your view if needed
    ], validators=[DataRequired()])

    salary_grade = IntegerField('Salary Grade', validators=[DataRequired()])
    authorized_salary = StringField('Authorized Salary', validators=[DataRequired()])
    actual_salary = StringField('Actual Salary', validators=[DataRequired()])
    step = IntegerField('Step', validators=[DataRequired()])

    area_code = StringField('Area Code', validators=[DataRequired()])
    area_type = StringField('Area Type', validators=[DataRequired()])
    level = StringField('Level', validators=[DataRequired()])

    last_name = StringField('Last Name', validators=[DataRequired()])
    first_name = StringField('First Name', validators=[DataRequired()])
    middle_name = StringField('Middle Name', validators=[DataRequired()])
    sex = SelectField('Sex', choices=[('Male', 'Male'), ('Female', 'Female')], validators=[DataRequired()])
    date_of_birth = DateField('Date of Birth', validators=[DataRequired()])
    tin = StringField('TIN', validators=[DataRequired()])
    umid_no = StringField('UMID No.', validators=[DataRequired()])

    date_original_appointment = DateField('Date of Original Appointment', validators=[DataRequired()])
    date_last_promotion = DateField('Date of Last Promotion', validators=[DataRequired()])
    status = StringField('Status', validators=[DataRequired()])

    eligibility = StringField('Civil Service Eligibility', validators=[DataRequired()])
    comments = StringField('Comments/Annotation', validators=[DataRequired()])

    submit = SubmitField('Add Employee')



class UpdateSuperAdminProfileForm(FlaskForm):
    # From Users
    first_name = StringField('First Name', validators=[DataRequired()])
    middle_name = StringField('Middle Name')  # Optional
    last_name = StringField('Last Name', validators=[DataRequired()])
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    image_file = FileField('Upload New Photo', validators=[FileAllowed(['jpg', 'png'])])
    signature_file = FileField('Signature', validators=[FileAllowed(['jpg', 'png'])])

    date_of_birth = DateField(
        'Date of Birth',
        format='%Y-%m-%d',
        validators=[Optional()]
    )
    tin = StringField('TIN', validators=[Optional()])
    gender = SelectField(
        'Gender',
        choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')],
        validators=[Optional()]
    )


    submit = SubmitField('Save changes')

    def validate_email(self, email):
        if email.data != current_user.email:
            user = Users.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('That Email is already taken!')


class UpdateSuperAdminPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=4, message='Password must be at least 4 characters.')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match.')
    ])

    current_password = PasswordField('Current Password', validators=[
        DataRequired(message='Please enter your current password.')
    ])

    submit = SubmitField('Change Password')


class ForceResetForm(FlaskForm):
    email = StringField('New Email', validators=[DataRequired(), Email()])
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Update Account')
