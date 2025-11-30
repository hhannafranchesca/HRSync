from fpdf import FPDF
import os
from flask import current_app
from datetime import  datetime
from calendar import monthrange
from collections import defaultdict
import textwrap
import io
import tempfile
from app.models import Users, UserSignature, Employee, PermanentEmployeeDetails, Position


from fpdf import FPDF

class WidePDF(FPDF):
    # 🔹 Override para lahat ng cell text ay uppercase
    def cell(self, w, h=0, txt='', border=0, ln=0, align='', fill=False, link=''):
        txt = txt.upper() if txt else ''
        super().cell(w, h, txt, border, ln, align, fill, link)

    def multi_cell(self, w, h, txt='', border=0, align='J', fill=False):
        txt = txt.upper() if txt else ''
        super().multi_cell(w, h, txt, border, align, fill)

    def header(self):
        self.set_font("Arial", "B", 7)
        self.cell(0, 8, "DEPARTMENT: MUNICIPALITY OF VICTORIA", ln=True, align="L")
        self.set_font("Arial", "", 10)
        self.ln(2)

    def _boxed_multiline(self, w, h, txt, align='C'):
        x0, y0 = self.get_x(), self.get_y()
        self.rect(x0, y0, w, h)
        lines = txt.count('\n') + 1
        line_h = h / lines
        self.multi_cell(w, line_h, txt, border=0, align=align)
        self.set_xy(x0 + w, y0)

    def table_header(self):
        self.set_font("Arial", "B", 5)

        headers = [
            "ORGANIZATIONAL UNIT\n(1)", "ITEM\nNUMBER\n(2)", "POSITION TITLE (3)", "SALARY\nGRADE\n(4)",
            "AUTHORIZED\nANNUAL\nSALARY (5)", "ACTUAL\nANNUAL\nSALARY (6)", "STEP\n(7)", "AREA\nCODE\n(8)",
            "AREA\nTYPE\n(9)", "LEVEL\n(10)", "LAST NAME (11)", "FIRST NAME\n(12)", "MIDDLE\nNAME\n(13)",
            "SEX\n(14)", "DATE OF\nBIRTH (15)", "TIN(16)", "UMID\nNO.\n(17)", "DATE OF\nORIGINAL\nAPPOINTMENT\n(18)",
            "DATE OF LAST\nPROMOTION/\nAPPT\n(19)", "STATUS\n(20)", "CIVIL SERVICE\nELIGIBILITY\n(21)",
            "COMMENTS/\nANNOTATION\n(22)"
        ]

        widths = [35, 10, 45, 15, 15, 15, 8, 8, 8, 8, 20,
                  18, 16, 7, 13, 9, 10, 15, 15, 10, 23, 15]

        total_h = 7
        for w, title in zip(widths, headers):
            self._boxed_multiline(w, total_h, title, align='C')

        self.ln(total_h)
        

    def table_row(self, emp):
        self.set_font("Arial", "", 5)

        values = [
            emp.department.name,
            emp.permanent_details.item_number,
            emp.permanent_details.position.title,
            emp.permanent_details.salary_grade,
            emp.permanent_details.authorized_salary,
            emp.permanent_details.actual_salary,
            emp.permanent_details.step,
            emp.permanent_details.area_code,
            emp.permanent_details.area_type,
            emp.permanent_details.level,
            emp.last_name,
            emp.first_name,
            emp.middle_name,
             "M" if emp.permanent_details.sex and emp.permanent_details.sex.lower().startswith("m")
        else "F" if emp.permanent_details.sex and emp.permanent_details.sex.lower().startswith("f")
        else "",
            emp.permanent_details.date_of_birth.strftime('%Y-%m-%d') if emp.permanent_details.date_of_birth else "",
            emp.permanent_details.tin,
            emp.permanent_details.date_original_appointment.strftime('%Y-%m-%d') if emp.permanent_details.date_original_appointment else "",
            emp.permanent_details.date_last_promotion.strftime('%Y-%m-%d') if emp.permanent_details.date_last_promotion else "N/A",
            emp.status,
            emp.permanent_details.eligibility,
            emp.permanent_details.comments
        ]

        widths = [35, 10, 45, 15, 15, 15, 8, 8, 8, 8, 20,
                18, 16, 7, 13, 19, 15, 15, 10, 23, 15]

        wrap_cols = {0, 2}  # Department name + Position title
        line_height = 3.5

        # --- Pass 1: compute lines needed per cell ---
        num_lines_per_col = []
        for i, (w, val) in enumerate(zip(widths, values)):
            text = str(val).upper() if val else ""
            if i in wrap_cols:
                # let FPDF calculate wrapping (approximation)
                words = text.split()
                line = ""
                lines = 1
                for word in words:
                    if self.get_string_width(line + " " + word) > (w - 2):
                        lines += 1
                        line = word
                    else:
                        line += " " + word
                num_lines_per_col.append(lines)
            else:
                num_lines_per_col.append(1)

        max_lines = max(num_lines_per_col)
        row_height = max_lines * line_height

        # --- Pass 2: render cells ---
        y_start = self.get_y()
        for i, (w, val) in enumerate(zip(widths, values)):
            x = self.get_x()
            text = str(val).upper() if val else ""

            # Draw border
            self.rect(x, y_start, w, row_height)

            if i in wrap_cols:
                # Print wrapped text inside the cell
                self.multi_cell(w, line_height, text, border=0, align='L')
                # Return cursor to right of the cell
                self.set_xy(x + w, y_start)
            else:
                # Print single-line text, vertically aligned top
                self.cell(w, row_height, text, border=0, align='L')

        # Move to next row
        self.ln(row_height)

    def table_row_vacant(self, position, department=None):
        self.set_font("Arial", "", 5)

        values = [
            department.name if department else "-", "-", position.title, "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "Vacant", "-", "-"
        ]

        widths = [25, 10, 30, 15, 15, 15, 8, 8, 8, 8,
                  25, 25, 25, 8, 13, 22, 15, 15, 10, 18, 15]

        wrap_cols = {0, 2}
        line_height = 3.5

        max_lines = 1
        for i, (w, val) in enumerate(zip(widths, values)):
            text = str(val).upper() if val else ""
            if i in wrap_cols:
                str_width = self.get_string_width(text)
                num_lines = str_width / (w - 1)
                lines = int(num_lines) + 1
                max_lines = max(max_lines, lines)

        row_height = max_lines * line_height

        for i, (w, val) in enumerate(zip(widths, values)):
            x = self.get_x()
            y = self.get_y()
            text = str(val).upper() if val else ""

            if i in wrap_cols:
                self.multi_cell(w, line_height, text, border=0, align='L')
                self.set_xy(x, y)
                self.cell(w, row_height, '', border=1)
                self.set_xy(x + w, y)
            else:
                self.set_xy(x, y)
                self.cell(w, row_height, text, border=1, align='L')

        self.ln(row_height)

    def footer(self):
        # Page number footer
        self.set_y(-15)
        self.set_font('Arial', 'I', 6)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')





#casual
class CasualJobPDF(FPDF):
    def header(self):
        self.set_y(2)
        self.set_font('Arial', '', 8)

        # Left side
        self.set_x(10)
        self.cell(100, 5, 'CS Form No. 34-C', ln=True, align='L')
        self.set_x(10)
        self.cell(100, 5, 'Revised 2018', ln=True, align='L')

        # Right side
        self.set_xy(289, 0)
        self.multi_cell(60, 5, "For\nLocal Government Unit", border=1, align='C')

        self.ln(1)
        self.set_font('Arial', 'B', 9)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of Victoria', ln=True, align='C')
        self.ln(3)
        self.set_font('Arial', 'B', 11)
        self.cell(0, 5, 'PLANTILLA OF CASUAL APPOINTMENTS', ln=True, align='C')
        self.ln(4)
        self.set_font('Arial', '', 9)
        self.cell(40, 3, 'Department/Office:', ln=0)
        self.set_font('Arial', 'B', 9)
        self.cell(70, 3, 'OFFICE OF THE MUNICIPAL MAYOR', border='B', ln=0)
        self.cell(95, 3, '', ln=0)
        self.set_font('Arial', '', 9)
        self.cell(30, 3, 'Source of Funds:', ln=0)
        self.set_font('Arial', 'B', 9)
        self.cell(100, 3, 'GENERAL FUND - OFFICE OF THE MUNICIPAL MAYOR', border='B', ln=1)
        self.ln(3)
        self.set_font('Arial', 'B', 9)
        self.cell(0, 4, 'INSTRUCTION:')
        self.ln(3)
        self.set_font('Arial', '', 7)
        self.multi_cell(0, 4,
            "(1) Only a maximum of fifteen (15) appointees must be listed on each page of the Plantilla of Casual Appointments.\n"
            "(2) Indicate 'NOTHING FOLLOWS' on the row following the name of the last appointee on the last page of the Plantilla.\n"
            "(3) Provide proper pagination (Page n of n page/s)."
        )
        self.ln(3)

    def table_header(self):
        self.set_font('Arial', 'B', 6)

        # Widths
        extra_cell_width = 3
        name_width = 100 - extra_cell_width  # Now 97
        position_width = 55
        salary_width = 35
        wage_width = 30
        period_width = 60
        ack_width = 60

        # === Row 1: Top Headers ===
        x = self.get_x()
        y = self.get_y()

        # Add 2 stacked 3x4mm cells (only aligned with NAME OF APPOINTEE/S)
        self.set_xy(x, y)
        self.cell(extra_cell_width, 4, '', border=1)
        self.set_xy(x, y + 4)
        self.cell(extra_cell_width, 4, '', border=1)

        # NAME OF APPOINTEE/S (adjusted to fit right of stacked cells)
        self.set_xy(x + extra_cell_width, y)
        self.cell(name_width, 8, "NAME OF APPOINTEE/S", border=1, align='C')

       # POSITION TITLE header (2 lines, centered vertically + horizontally)
        x = self.get_x()
        y = self.get_y()

        # Box ng buong header (16 height)
        self.cell(position_width, 16, "", border=1)

        # Text content
        text = "POSITION TITLE\n(Do not abbreviate)"

        # === Step 1: compute text height
        line_height = 3
        num_lines = text.count("\n") + 1
        text_height = num_lines * line_height   # total height ng text

        # === Step 2: compute vertical offset para gitna sa 16
        offset_y = y + (16 - text_height) / 2

        # === Step 3: render text sa gitna
        self.set_xy(x, offset_y)
        self.multi_cell(position_width, line_height, text, align='C')

        # Lipat cursor sa kanan ng box
        self.set_xy(x + position_width, y)


        self.cell(salary_width, 16, "EQUIVALENT SALARY", border=1, align='C')
        self.cell(wage_width, 16, "DAILY WAGE", border=1, align='C')
        self.cell(period_width, 8, "PERIOD OF EMPLOYMENT", border=1, align='C')
        self.cell(ack_width, 8, "ACKNOWLEDGEMENT OF APPOINTEE", border=1, align='C')
        self.ln(8)

        # === Row 2: Sub Headers (unchanged) ===
        self.cell(31, 8, "Last Name", border=1, align='C')                     # reduced by 3mm
        self.cell(29, 8, "First Name", border=1, align='C')

        x = self.get_x()
        y = self.get_y()

        # Total height: 8mm, 3 lines = 8 / 3 ≈ 2.67 per line
        self.multi_cell(15, 2.67, "NAME\nEXTENSION\n(JR/III)", border=1, align='C')

        # Reset X position to the right of the cell para tuloy tuloy ang next cell
        self.set_xy(x + 15, y)
        self.cell(25, 8, "Middle Name", border=1, align='C')
        self.cell(position_width, 0, '', border=0)
        self.cell(salary_width, 0, '', border=0)
        self.cell(wage_width, 0, '', border=0)
        self.cell(period_width * 0.5, 8, "From (MM/DD/YYYY)", border=1, align='C')
        self.cell(period_width * 0.5, 8, "To (MM/DD/YYYY)", border=1, align='C')
        self.cell(ack_width * 0.5, 8, "Signature", border=1, align='C')
        self.cell(ack_width * 0.5, 8, "Date Received", border=1, align='C')

        self.ln(8)


    def table_row(self, emp, row_number):
        self.set_font("Arial", "", 6)

        values = [
            row_number,
            (emp.last_name or "").upper(),
            (emp.first_name or "").upper(),
            (emp.casual_details.name_extension or "N/A").upper(),
            (emp.middle_name or "").upper(),
            emp.casual_details.position.title,
            emp.casual_details.equivalent_salary,
            emp.casual_details.daily_wage,
            emp.casual_details.contract_start.strftime('%m/%d/%Y') if emp.casual_details.contract_start else 'N/A',
            emp.casual_details.contract_end.strftime('%m/%d/%Y') if emp.casual_details.contract_end else 'N/A',
            '', '',  # Signature and Date Received
        ]

        widths = [3, 28, 29, 15, 25, 55, 35, 30, 30, 30, 30, 30]
        row_height = 5

        # 👉 Define per-column alignment
        alignments = [
            'C',  # Row number
            'L',  # Last Name
            'L',  # First Name
            'L',  # Name Extension
            'L',  # Middle Name
            'L',  # Position
            'C',  # Equivalent Salary
            'C',  # Daily Wage
            'C',  # Contract Start
            'C',  # Contract End
            'C',  # Signature
            'C',  # Date Received
        ]

        for idx, value in enumerate(values):
            self.cell(widths[idx], row_height, str(value), border=1, align=alignments[idx])

        self.ln(row_height)

        

        if self.get_y() > 250:
            self.add_page()
            self.table_header()


    def casual_layout_table(self, names=[]):
        self.table_header()

        # ✅ Filter only employees with casual_details and active status
        filtered = [
            emp for emp in names
            if emp.casual_details
            and getattr(emp.casual_details, 'employment_status', '').strip().lower() == 'active'
        ]

        for i, emp in enumerate(filtered, 1):
            self.table_row(emp, i)
        
    def table_note_row(self, text):
        self.set_font("Arial", "", 5)  # small font
        row_height = 3  # smaller row height for tight lines
        widths = [3, 28, 29, 15, 25, 55, 35, 30, 30, 30, 30, 30]
        total_width = sum(widths)

        x = self.get_x()
        y = self.get_y()

        # Split text into exactly 2 lines
        lines = text.split('\n')
        if len(lines) > 2:
            lines = [lines[0], ' '.join(lines[1:])]
        elif len(lines) < 2:
            lines.append('')

        height = row_height * 2 + 1  # add tiny extra for padding

        # Draw double border
        self.rect(x, y, total_width, height)              # outer border
        self.rect(x+0.1, y+0.1, total_width-0.2, height-0.2)  # inner border

        # Print each line tightly
        for i, line in enumerate(lines):
            self.set_xy(x + 1, y + i*row_height + 0.5)  # minimal vertical offset
            self.cell(total_width-2, row_height, line, border=0, ln=0, align='L')

        # Move cursor after the note
        self.set_y(y + height)


    def table_blank_row(self, height=1):
        """
        Adds an empty row across the table width.
        """
        total_width = 3 + 28 + 29 + 15 + 25 + 55 + 35 + 30 + 30 + 30 + 30 + 30
        self.cell(total_width, height, '', border=1, ln=1)

    def footer(self):
        self.ln(3)
        start_y = self.get_y()

        self.set_font('Arial', 'B', 8)
        self.set_xy(10, start_y)
        self.cell(25, 5, 'CERTIFICATION', ln=0, align='C')
        self.cell(140, 5, 'CERTIFICATION', ln=0, align='C')
        self.cell(105, 5, 'CERTIFICATION AND SIGNATURE OF APPOINTING OFFICER / AUTHORITY', ln=0, align='C')
        self.cell(30, 5, 'CSC NOTATION', ln=1, align='C')

        self.ln(2)
        content_start_y = self.get_y()

        self.set_xy(10, content_start_y)
        self.set_font('Arial', '', 7)
        self.multi_cell(65, 3.5, 'This is to certify that all requirements and supporting papers pursuant to CSC MC No. 24, s. 2017, as amended, have been complied with, reviewed and found in order.', align='L')

        self.set_xy(94, content_start_y)
        self.multi_cell(65, 3.5, 'This is to certify that funds are available pursuant to Appropriation Ordinance No. 61, series of 2024.', align='L')

        self.set_xy(180, content_start_y)
        self.multi_cell(80, 3.5, 'This is to certify that all pertinent provisions of Sec. 325 of RA 7160 (Local Government Code of 1991) have been complied with in the issuance of appointments of the above-mentioned persons.', align='L')

        self.set_xy(280, content_start_y)
        self.multi_cell(60, 3.5, ' ', align='L')

        name_start_y = content_start_y + 18

        self.set_xy(10, name_start_y)
        self.set_font('Arial', 'B', 8)
        self.cell(65, 5, 'LLOYD MORGAN O. PERLEZ', border='B', ln=1, align='C')
        self.set_x(10)
        self.set_font('Arial', '', 7)
        self.cell(65, 4, 'MGDH I (HRMO)', ln=1, align='C')
        self.set_x(10)
        self.cell(10, 4, 'Date:', ln=0)
        self.cell(55, 4, '', border='B', ln=1)

        self.set_xy(95, name_start_y)
        self.set_font('Arial', 'B', 8)
        self.cell(65, 5, 'M.A. ROWENA R. GUTIERREZ', border='B', ln=1, align='C')
        self.set_x(95)
        self.set_font('Arial', '', 7)
        self.cell(65, 4, 'Municipal Accountant', ln=1, align='C')
        self.set_x(95)
        self.cell(10, 4, 'Date:', ln=0)
        self.cell(55, 4, '', border='B', ln=1)

        self.set_xy(180, name_start_y)
        self.set_font('Arial', 'B', 8)
        self.cell(80, 5, 'HON. DWIGHT KAMPITAN, MD', border='B', ln=1, align='C')
        self.set_x(180)
        self.set_font('Arial', '', 7)
        self.cell(80, 4, 'Municipal Mayor', ln=1, align='C')
        self.set_x(180)
        self.cell(10, 4, 'Date:', ln=0)
        self.cell(70, 4, '', border='B', ln=1)

        # CSC Official Block (same style)
        self.set_xy(280, name_start_y)
        self.set_font('Arial', 'B', 8)
        self.cell(65, 5, '', border='B', ln=1, align='C')   # ✅ ginawang border B para pareho
        self.set_x(280)
        self.set_font('Arial', '', 7)
        self.cell(65, 4, 'CSC Official:', ln=1, align='C')   # ✅ title line
        self.set_x(280)
        self.cell(10, 4, 'Date:', ln=0)
        self.cell(55, 4, '', border='B', ln=1)
        self.set_y(-13)
        self.set_font('Arial', 'I', 6)
        self.cell(0, 10, 'Page %s' % self.page_no(), 0, 0, 'C')


# job order 

class JobOrderPDF(FPDF):
    def jo_layout_table(self, year=None, month=None, days=None, names=[], departments_dict={}):
        today = datetime.today()
        if year is None:
            year = today.year
        if month is None:
            month = today.month
        if days is None:
            days = monthrange(year, month)[1]

        # === Layout Configuration ===
        page_width = 215.9
        margin_space = 10
        margin_right = 10
        usable_width = page_width - margin_space - margin_right

        blank_cell_width = 7
        name_col_width = 60
        last_col_width = 18.9
        col_width = (usable_width - blank_cell_width - name_col_width - last_col_width) / days
        row_height = 5   # ✅ dati 7, binawasan ng 2

        highlight_days = {1, 5, 6, 9, 12, 13}

        # === Department Mapping (ALL CAPS) ===
        department_name_map = {
            "Office of the Municipal Mayor": "OFFICE OF THE MUN. MAYOR (1011)",
            "Office of the Municipal Vice Mayor": "OFFICE OF THE MUN.VICE MAYOR (1016)",
            "Office of the Municipal Human Resource Management Officer": "OFFICE OF THE MUN. HRMO (1031)",
            "Office of the Municipal Planning and Development Coordinator": "MPDC OFFICE(1041)",
            "Office of the Municipal Treasurer": "OFFICE OF THE MUN. TREASURER (1091)",
            "Office of the Municipal Accountant": "OFFICE OF THE MUN. ACCOUNTANT(1081)",
            "Office of the Municipal Auditor": "OFFICE OF THE AUDITOR",
            "Office of the Municipal Budget Officer": "OFFICE OF THE BUDGET(1071)",
            "Office of the Municipal Civil Registrar": "OFFICE OF THE MCR(1051)",
            "Office of the Municipal Assessor": "OFFICE OF THE MUN. ASSESSOR(1101)",
            "Office of the Municipal Social Welfare Development Officer": "OFFICE OF THE MSWDO(7611)",
            "Office of the Municipal Agriculturist": "D.A OFFICE(8711)",
            "Office of the Municipal Engineer": "OFFICE OF MUN. ENGINEER(8751)",
            "Office of the Municipal Environment and Natural Resources Officer": "MENRO",
            "Office of the Municipal Disaster Risk Reduction Management Officer": "MDRRM",
            "Office of the Municipal Health Officer": "HEALTH",
            "General Services Office": "UTILITY BUILDING",
            "Municipal Tourism Office": "MUNICIPAL BUILDING, PLAZA AND PARKS",
            "Office of the Sangguniang Bayan": "PNP",
            "Office of The Secretary to the Sangguniang Bayan": "MUNICIPAL STREET AND BRIDGES",
            "Public Employment Services Office": "SPECIAL JOB ORDER"
        }

        department_order = [
            "OFFICE OF THE MUN. MAYOR (1011)",
            "OFFICE OF THE MUN.VICE MAYOR (1016)",
            "OFFICE OF THE MUN. HRMO (1031)",
            "MPDC OFFICE(1041)",
            "OFFICE OF THE MUN. TREASURER (1091)",
            "OFFICE OF THE MUN. ACCOUNTANT(1081)",
            "OFFICE OF THE AUDITOR",
            "OFFICE OF THE BUDGET(1071)",
            "OFFICE OF THE MCR(1051)",
            "OFFICE OF THE MUN. ASSESSOR(1101)",
            "OFFICE OF THE MSWDO(7611)",
            "D.A OFFICE(8711)",
            "OFFICE OF MUN. ENGINEER(8751)",
            "MENRO",
            "UTILITY BUILDING",
            "HEALTH",
            "MUNICIPAL BUILDING, PLAZA AND PARKS",
            "PNP",
            "MUNICIPAL STREET AND BRIDGES",
            "MDRRM",
            "SPECIAL JOB ORDER",
            "UNASSIGNED"
        ]

        # === HEADER ROW 1 ===
        self.set_font("Arial", "B", 7)
        self.set_x(margin_space)
        self.cell(blank_cell_width, row_height, "", border=1)

        self.set_fill_color(196, 101, 56)
        self.set_font("Arial", "B", 16)
        self.cell(name_col_width, row_height * 2, str(year), border=1, align='C', fill=True)

        self.set_font("Arial", "B", 8)
        self.set_fill_color(255, 217, 102)
        self.cell(col_width * days, row_height, datetime(year, month, 1).strftime('%B').upper(), border=1, align='C', fill=True)

        self.set_fill_color(197, 224, 180) #GREEN
        self.cell(last_col_width, row_height, "No. of", border=1, align='C', fill=True)
        self.ln(row_height)

        # === HEADER ROW 2: Day Numbers ===
        self.set_x(margin_space)
        self.cell(blank_cell_width, row_height, "", border=1)
        self.cell(name_col_width, row_height, "", border="LR")

        for day in range(1, days + 1):
            self.set_text_color(215, 67, 67) if day in highlight_days else self.set_text_color(0, 0, 0)
            self.set_fill_color(248, 203, 173)
            self.cell(col_width, row_height, str(day), border=1, align='C', fill=True)

        self.set_text_color(0, 0, 0)
        self.set_fill_color(255, 192, 192)
        self.cell(last_col_width, row_height, "Days", border=1, align='C', fill=True)
        self.ln(row_height)

        # === GROUP EMPLOYEES BY DEPARTMENT (FILTER ACTIVE ONLY) ===
        self.set_font("Arial", "", 7)
        dept_employees = defaultdict(list)

        for emp in names:
            status = getattr(emp, 'employment_status', '').strip().lower()
            if status != 'active':
                continue

            raw_dept_name = (
                emp.job_order_details.assigned_department.name
                if emp.job_order_details and emp.job_order_details.assigned_department
                else "UNASSIGNED"
            )
            display_name = department_name_map.get(raw_dept_name, raw_dept_name.upper())
            dept_employees[display_name].append(emp)

        # === Sort based on department_order ===
        def dept_sort_key(name):
            return department_order.index(name) if name in department_order else len(department_order)

        sorted_departments = sorted(dept_employees.items(), key=lambda x: dept_sort_key(x[0]))

        global_counter = 1
        for dept_name, employees in sorted_departments:
            self.set_x(margin_space)
            self.set_fill_color(169, 209, 142)
            self.set_font("Arial", "B", 6)

            # ✅ Draw one full-width cell that includes row number space
            full_width = blank_cell_width + name_col_width + (col_width * days) + last_col_width
            self.cell(full_width, row_height, "            " + dept_name, border=1, align='L', fill=True)  # ← 2 spaces added here

            self.ln(row_height)

            self.set_font("Arial", "", 7)

            for emp in employees:
                middle = (emp.middle_name.strip()[0] + '.' if emp.middle_name and emp.middle_name.strip() else '')
                # Last name uppercase, first & middle as is
                emp_name = f"{emp.last_name.upper()}, {emp.first_name} {middle}".strip()

                self.set_x(margin_space)
                self.cell(blank_cell_width, row_height, str(global_counter), border=1, align='C')
                self.cell(name_col_width, row_height, emp_name, border=1)

                for day in range(1, days + 1):
                    self.set_fill_color(180, 199, 231) if day in highlight_days else self.set_fill_color(255, 255, 255)
                    self.cell(col_width, row_height, "", border=1, fill=True)

                self.set_fill_color(197, 224, 180)
                self.cell(last_col_width, row_height, "-", border=1, align='C', fill=True)

                self.ln(row_height)
                global_counter += 1






#IPCR 

def clean_text(text):
    if not text:
        return ""
    replacements = {
        '’': "'",
        '‘': "'",
        '“': '"',
        '”': '"',
        '–': '-',
        '—': '--',
        '…': '...',
        '•': '-',   # ← important: ito yung cause ng error mo
        # Add more replacements if needed
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

class PerformanceReportPDF(FPDF):
    def __init__(self, *args, start_date=None, end_date=None,mayor_name=None,head_name=None, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_date = start_date
        self.end_date = end_date
        self.show_header = True
        self.head_name = head_name or "(Head of Department)"
        self.mayor_name = mayor_name or "HON. [NAME NOT SET]"  # ✅ safely store it
        self.employee = employee
        self.department_name = employee.department.name if employee and employee.department else "Unknown Department"

        # Determine department from employee object
        if employee:
            # Use assigned department if casual/job order; else default to employee.department
            if hasattr(employee, 'casual_details') and employee.casual_details and employee.casual_details.assigned_department:
                self.department_name = employee.casual_details.assigned_department.name
            elif hasattr(employee, 'job_order_details') and employee.job_order_details and employee.job_order_details.assigned_department:
                self.department_name = employee.job_order_details.assigned_department.name
            elif hasattr(employee, 'department') and employee.department:
                self.department_name = employee.department.name
            else:
                self.department_name = "Unknown Department"
        else:
            self.department_name = "Unknown Department"

    def get_employee_name_and_position(self, emp):
        if not emp:
            return "(Employee Name), (Position)"
        middle_initial = f"{emp.middle_name[0]}." if emp.middle_name else ""
        full_name = f"{emp.first_name} {middle_initial} {emp.last_name}"

        # Determine position
        position = None
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title

        position_text = position or "(Position)"
        return f"{full_name}, {position_text}"
    

    def header(self):
        if not self.show_header:
            return

        self.set_font('Arial', 'B', 11)
        self.cell(0, 6, f'{self.department_name}', ln=True, align='C')
        self.ln(1)
        self.set_font("Arial", "B", 11)
        self.cell(0, 6, "Individual Performance Commitment and Review (IPCR)", ln=True, align="C")
        self.ln(2)
        self.set_font("Arial", "", 8)
        self.set_left_margin(20)
        self.set_x(20)

        # Period text components
        if self.start_date and self.end_date:
            start_month = self.start_date.strftime("%B")
            end_month = self.end_date.strftime("%B")
            year = self.end_date.strftime("%Y")
        else:
            start_month, end_month, year = None, None, None

        # Employee text
        employee_text = self.get_employee_name_and_position(self.employee)

        # --- Mixed formatting writing sequence ---
        self.set_font("Arial", "", 9)
        self.write(5, "         I, ")

        # Bold + Underlined employee name and position
        self.set_font("Arial", "BU", 9)
        self.write(5, employee_text)

        self.set_font("Arial", "", 9)
        self.write(5, ", from ")

        # Bold + Underlined department name
        self.set_font("Arial", "BU", 9)
        self.write(5, self.department_name)

        self.set_font("Arial", "", 9)
        self.write(5, " department, commit to deliver and agree to be rated on the attainment of the following targets in accordance with the indicated measures for the period ")

        # --- Period formatting (no underline on "to") ---
        if start_month and end_month and year:
            # Start month (bold + underline)
            self.set_font("Arial", "BU", 9)
            self.write(5, start_month + " ")

            # "to" (normal, no underline)
            self.set_font("Arial", "", 9)
            self.write(5, "to ")

            # End month + year (bold + underline)
            self.set_font("Arial", "BU", 9)
            self.write(5, f"{end_month} {year}")
        else:
            # Fallback if no valid date range
            self.set_font("Arial", "BU", 9)
            self.write(5, "the given period")

        # End the sentence
        self.set_font("Arial", "", 9)
        self.write(5, ".")

        self.ln(8)  # Spacing after header text


        self.set_left_margin(10)
        page_width = 290.4
        right_margin = 10

        # === Employee Details ===
        middle_initial = f"{self.employee.middle_name[0]}." if self.employee.middle_name else ""
        employee_name = f"{self.employee.first_name} {middle_initial} {self.employee.last_name}".strip()

        # Determine position based on employment type
        if self.employee.permanent_details and self.employee.permanent_details.position:
            employee_position = self.employee.permanent_details.position.title
        elif self.employee.casual_details and self.employee.casual_details.position:
            employee_position = self.employee.casual_details.position.title
        elif self.employee.job_order_details:
            employee_position = self.employee.job_order_details.position_title
        else:
            employee_position = "Position Not Set"

        # === Common rightward shift ===
        shift_right = 15

        # === Employee Name (Bold + Underlined, right aligned) ===
        self.set_font("Arial", "BU", 8)
        name_width = self.get_string_width(employee_name)
        x_name = page_width - right_margin - name_width + shift_right
        y_name = self.get_y()
        self.set_xy(x_name, y_name)
        self.cell(name_width, 5, employee_name, ln=True)

        # === Employee Position (Normal, centered below name) ===
        self.set_font("Arial", "", 8)
        position_width = self.get_string_width(employee_position)
        x_position = x_name + (name_width - position_width) / 2  # center under name
        self.set_xy(x_position, self.get_y())
        self.cell(position_width, 5, employee_position, ln=True)

        # === Add spacing before Date ===
        self.ln(5)

        # === "Date:" aligned with start of employee name ===
        self.set_font("Arial", "B", 8)
        text = "Date:"
        text_width = self.get_string_width(text)
        self.set_x(x_name)
        self.cell(text_width, 6, text, ln=True)



        self.set_font("Arial", "", 9)
        self.cell(0, 6, "Approved By:", ln=True)

                        # Define per-cell widths (adjust individually!)
        cell_height = 20
        line_height = 5

        start_x = self.get_x()
        start_y = self.get_y()

        # Padding from edges
        padding = 30
        mayor_offset = 45
        left_shift = 15  # move left block closer to center

        # === Head of Department info ===
        head_name = getattr(self, "head_name", "(Head Not Set)")  # use head_name from route
        department_name = getattr(self, "department_name", "Department Not Set")

        # Head name (bold)
        self.set_font("Arial", "B", 9)
        name_width = self.get_string_width(head_name)
        x_name = start_x + padding + left_shift
        y_name = start_y + 4
        self.set_xy(x_name, y_name)
        self.cell(name_width, line_height, head_name, border=0, align="L")

        # Department name (smaller font, centered under head name)
        self.set_font("Arial", "", 9)
        dept_width = self.get_string_width(department_name)
        x_dept = x_name + (name_width - dept_width) / 2
        y_dept = y_name + line_height + 1
        self.set_xy(x_dept, y_dept)
        self.cell(dept_width, line_height, department_name, border=0, align="L")

        # === Mayor info ===
        from app.models import Employee, Position  # make sure you import at the top of your PDF module

        # Get the employee with position "MUNICIPAL MAYOR"
        mayor_employee = Employee.query.join(Employee.permanent_details).join(PermanentEmployeeDetails.position)\
            .filter(Position.title.ilike("MUNICIPAL MAYOR")).first()

        if mayor_employee:
            middle_initial = f"{mayor_employee.middle_name[0]}." if mayor_employee.middle_name else ""
            mayor_name = f"HON. {mayor_employee.first_name.upper()} {middle_initial.upper()} {mayor_employee.last_name.upper()}, MD"

        else:
            mayor_name = "HON. MAYOR (NOT SET)"

        
        mayor_title = "Mayor of Victoria"

        # Mayor name (bold)
        self.set_font("Arial", "B", 9)
        name_width = self.get_string_width(mayor_name)
        x_mayor = self.w - name_width - padding - mayor_offset
        y_mayor = start_y + 4
        self.set_xy(x_mayor, y_mayor)
        self.cell(name_width, line_height, mayor_name, border=0, align="R")

        # Mayor title (smaller font, centered under mayor name)
        self.set_font("Arial", "", 9)
        title_width = self.get_string_width(mayor_title)
        x_title = x_mayor + (name_width - title_width) / 2
        y_title = y_mayor + line_height + 1
        self.set_xy(x_title, y_title)
        self.cell(title_width, line_height, mayor_title, border=0, align="L")

        # Move cursor down for next section
        self.set_y(max(y_dept, y_title) + line_height + 10)

    def table_header(self, colored=True):
        self.set_font("Arial", "B", 10)
        
        # ✅ Main header color — yellow
        self.set_fill_color(255, 217, 102)  # yellow
        
        x_start = self.get_x()
        y_start = self.get_y()

        # Column widths
        widths = [70, 70, 70]
        texts = [
            "Major Final Output",
            "Success Indicators\n(Targets + Measures)",
            "Actual\nAccomplishments/\nExpenses",
            "Rating",
            "Remarks"
        ]

        line_height = 5
        max_lines = max(t.count('\n') + 1 for t in texts[:-2])
        rating_height = 2 * line_height
        header_height = max(max_lines * line_height, rating_height)
        x = x_start

        # First 3 columns
        for i in range(3):
            self.set_xy(x, y_start)
            self.rect(x, y_start, widths[i], header_height, style='DF')  # fill + border
            v_offset = (header_height - ((texts[i].count('\n') + 1) * line_height)) / 2
            self.set_xy(x + 1, y_start + v_offset)
            self.multi_cell(widths[i] - 2, line_height, texts[i], align='C')
            x += widths[i]

        # Rating column
        rating_width = 80
        sub_width = rating_width / 4
        self.set_xy(x, y_start)
        self.rect(x, y_start, rating_width, header_height, style='DF')

        # “Rating” label
        self.set_xy(x, y_start)
        self.cell(rating_width, header_height / 2, "Rating", border=1, align='C', fill=True)

        # Subcolumns (Q, E, T, A)
        self.set_xy(x, y_start + header_height / 2)
        for ch in ["Quality", "Efficiency", "Time", "Average"]:
            self.cell(sub_width, header_height / 2, ch, border=1, align='C', fill=True)
        x += rating_width

        # Remarks column
        remarks_width = 44
        self.set_xy(x, y_start)
        self.cell(remarks_width, header_height, texts[4], border=1, align='C', fill=True)

        # Reset for next rows
        self.set_xy(x_start, y_start + header_height)
        self.set_font("Arial", "", 8)

    def table_row(self, data):
        self.set_font("Arial", "", 10)
        line_height = 5
        widths = [70, 70, 70, 80, 44]
        rating_width = widths[3] / 4

        col_texts = [
            data['mfo'],
            data['success_indicators'],
            data['actual'],
            "",  # placeholder for rating subcolumns
            data['remarks']
        ]

        rating_texts = [
            str(data['rating'].get('Q', '')),
            str(data['rating'].get('E', '')),
            str(data['rating'].get('T', '')),
            str(data['rating'].get('A', ''))  # Average rating
        ]

        all_cells = []

        # Wrap first 3 columns
        for i, text in enumerate(col_texts[:3]):
            wrapped = self.multi_cell(widths[i], line_height, text, split_only=True)
            all_cells.append((wrapped, widths[i], text))

        # Rating subcolumns (Q, E, T, A)
        for rt in rating_texts:
            wrapped = self.multi_cell(rating_width, line_height, rt, split_only=True)
            all_cells.append((wrapped, rating_width, rt))

        # Remarks
        wrapped = self.multi_cell(widths[4], line_height, col_texts[4], split_only=True)
        all_cells.append((wrapped, widths[4], col_texts[4]))

        max_lines = max(len(w[0]) for w in all_cells)
        row_height = max_lines * line_height

        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.table_header(colored=False)
            self.set_font("Arial", "", 8)

        y = self.get_y()
        x = self.get_x()

        # Correct indices for rating columns
        rating_start_index = 3  # first rating (Q) is at index 3 in all_cells
        average_index = rating_start_index + 3  # A is the 4th rating → index 6

        for i, (wrapped, width, text) in enumerate(all_cells):
            self.set_xy(x, y)
            start_y = self.get_y()

            # Only the "A" rating column is red
            if i == average_index:
                self.set_text_color(255, 0, 0)  # red
            else:
                self.set_text_color(0, 0, 0)    # black

            # Draw text
            self.multi_cell(width, line_height, str(text), border=0, align='C')
            self.set_text_color(0, 0, 0)  # reset color for next cell

            end_y = self.get_y()
            current_height = end_y - start_y

            # Fill remaining vertical space
            if current_height < row_height:
                self.set_xy(x, start_y + current_height)
                self.cell(width, row_height - current_height, "", border=0)

            # Draw border
            self.rect(x, y, width, row_height)
            x += width

        self.set_y(y + row_height)

    def core_function_row(self, text):
        self.set_font("Arial", "B", 10)
        self.set_fill_color(180, 199, 231)  # blue
        self.set_x(self.l_margin)
        self.cell(334, 7, "CORE FUNCTION: " + text, border=1, align='L', fill=True)
        self.ln()

    def support_function_row(self, text):
        self.set_font("Arial", "B", 10)
        self.set_fill_color(180, 199, 231)  # blue
        self.set_x(self.l_margin)
        self.cell(334, 7, "SUPPORT FUNCTION: " + text, border=1, align='L', fill=True)
        self.ln()



    def new_table_rows_custom_color(self, rows, blue_rows=None, height=5):
        """
        Adds multiple rows with custom text.
        - `blue_rows` is a list of row indices (0-based) that should have blue in Cells 2-4
        - Cells 1 & 5 are white and merged vertically
        - Cell 1 has text label aligned vertically centered
        """
        widths = [70, 70, 70, 60, 64]
        if blue_rows is None:
            blue_rows = []

        total_height = height * len(rows)  # total height for merged Cells 1 & 5

        # Draw merged Cell 1 (leftmost tall cell) with text
        self.set_x(self.l_margin)
        self.set_fill_color(255, 255, 255)
        # Border = 1 (all sides)
        self.cell(widths[0], total_height, "Average Rating", border=1, align='C', fill=True, ln=0)

        # Draw merged Cell 5 (rightmost tall cell)
        self.set_x(self.l_margin + widths[0] + widths[1] + widths[2] + widths[3])
        self.set_fill_color(255, 255, 255)
        self.cell(widths[4], total_height, "", border=1, align='C', fill=True)

        # Draw the inner rows (Cells 2–4)
        for i, row in enumerate(rows):
            if isinstance(row, dict):
                category = row.get("category", "")
                mfo = row.get("mfo", "")
                rating = row.get("rating", "")
            else:
                category, mfo, rating = row

            # Start at the x position after Cell 1
            self.set_x(self.l_margin + widths[0])
            self.set_font("Arial", "", 9)

            # Cells 2-4
            if i in blue_rows:
                self.set_fill_color(180, 199, 231)  # blue
            else:
                self.set_fill_color(255, 255, 255)  # white

            self.cell(widths[1], height, category, border=1, align='C', fill=True)
            self.cell(widths[2], height, mfo, border=1, align='C', fill=True)
            self.cell(widths[3], height, rating, border=1, align='C', fill=True)

            self.ln()

        self.ln(5)
    def assessed_by_table(self, rows, height=7, left_offset=10):
        widths = [120, 30, 80, 30]  # [Assessed by, Date, Final Rating by, Date]
        header_height = height

        # --- Draw Header Function ---
        def draw_header():
            self.set_fill_color(180, 199, 231)  # light blue header
            self.set_font("Arial", "B", 9)
            self.set_x(self.l_margin + left_offset)
            self.cell(widths[0], header_height, "Assessed by:", border=1, align='C', fill=True)
            self.cell(widths[1], header_height, "Date", border=1, align='C', fill=True)
            self.cell(widths[2], header_height, "Final Rating By:", border=1, align='C', fill=True)
            self.cell(widths[3], header_height, "Date", border=1, align='C', fill=True)
            self.ln(header_height)

        # Start printing table body (no header yet)
        self.set_font("Arial", "B", 9)

        for row in rows:
            if isinstance(row, dict):
                assessed_by = row.get("col1", "")
                date1 = row.get("col2", "")
                final_by = row.get("col3", "")
                date2 = row.get("col4", "")
            else:
                assessed_by, date1, final_by, date2 = row

            assessed_lines = assessed_by.split("\n")
            assessed_height = height * len(assessed_lines)

            # --- Page space check ---
            if self.get_y() + header_height + assessed_height > self.page_break_trigger:
                self.add_page()
                draw_header()

            # --- Draw Header only if first row on page ---
            if abs(self.get_y() - self.t_margin) < 2:
                draw_header()

            # --- Draw Table Row ---
            x_start = self.l_margin + left_offset
            y_start = self.get_y()

            # First column (multi-line names)
            self.set_xy(x_start, y_start)
            self.multi_cell(widths[0], height, assessed_by, border="TLR", align='C')

            # Other columns
            self.set_xy(x_start + widths[0], y_start)
            self.cell(widths[1], assessed_height, date1, border="TLR", align='C')
            self.cell(widths[2], assessed_height, "", border="TLR", align='C')  # leave blank, name will be drawn later
            self.cell(widths[3], assessed_height, date2, border="TLR", align='C')
            self.ln(assessed_height)

            # ✅ Draw the mayor's name exactly on the pink line (bottom of 'Final Rating By' cell)
            if final_by:
                # Move the cursor right above the bottom border of that cell
                name_y = self.get_y() - 4  # adjust -4 to align perfectly with your pink line
                self.set_xy(x_start + widths[0] + widths[1], name_y)
                self.cell(widths[2], 2, final_by, border=0, align='C')
            self.ln()

        # --- Bottom Labels ---
        self.set_font("Arial", "B", 9)
        x_start = self.l_margin + left_offset
        y_start = self.get_y()
        row_height = 6

        self.set_xy(x_start, y_start)
        self.cell(widths[0], row_height, "Performance Management Team", border=1, align='C')
        self.cell(widths[1], row_height, "", border="LRB", align='C', ln=0)
        self.cell(widths[2], row_height, "Head of Office", border=1, align='C')
        self.cell(widths[3], row_height, "", border="LRB", align='C')
        self.ln(row_height)





#COE 
# === COE PDF CLASS ===
class CertificationPDF(FPDF):
    def draw_spaced_text(self, x, y, text, spacing, font="Arial", style="B", size=16):
        """Draws a title with evenly spaced letters"""
        self.set_font(font, style, size)
        self.set_xy(x, y)
        for char in text:
            self.cell(spacing, 10, char, border=0, ln=0, align='C')

    def header(self):
        """Draw the document header with logos and double line"""
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')

        self.image(os.path.join(base_path, 'victoria.png'), x=10, y=6, w=32)
        self.image(os.path.join(base_path, 'victoria1.png'), x=169, y=6, w=32)
        self.image(os.path.join(base_path, 'text.png'), x=50, y=10, w=105)
        self.image(os.path.join(base_path, 'text2.png'), x=48, y=30, w=115)

        self.ln(35)
        self.set_line_width(0.5)
        self.line(0, self.get_y(), 215, self.get_y())            # top line full width
        self.line(0, self.get_y() + 1.2, 215, self.get_y() + 1.2)  # second line
        self.ln(10)

    def add_certification_body(self, permit):


        # === Document date (top right) ===
        permit_date_requested = permit.date_requested.strftime("%B %d, %Y") if permit.date_requested else ""
        self.set_font("Arial", "", 12)
        self.set_xy(160, self.get_y())
        self.cell(40, 10, permit_date_requested, ln=1, align="R")

        # === Title ===
        text = "CERTIFICATION"
        text_width = len(text) * 6
        x_center = (210 - text_width) / 2
        self.draw_spaced_text(x_center, self.get_y(), text, spacing=6)
        self.ln(10)

        # === Employee Details ===
        employee = permit.employee
        employee_name = f"{employee.first_name} {employee.last_name}"

        # ✅ Handle position safely
        if employee.status in ['Permanent', 'P', 'CT', 'Contractual', 'Contract Teacher', 'E', 'Elective'] and employee.permanent_details and employee.permanent_details.position:
            position = employee.permanent_details.position.title
        elif employee.status in ['Casual', 'C'] and employee.casual_details and employee.casual_details.position:
            position = employee.casual_details.position.title
        elif employee.status in ['Job Order', 'JO'] and employee.job_order_details and employee.job_order_details.position:
            position = employee.job_order_details.position.title
        else:
            position = "N/A"

        department = employee.department.name if employee.department else "N/A"

        # === Employment start date ===
        if employee.status in ['Permanent', 'P', 'E', 'Elective','CT', 'Contractual', 'Contract Teacher'] and employee.permanent_details and employee.permanent_details.date_original_appointment:
            employment_start = employee.permanent_details.date_original_appointment.strftime("%B %d, %Y")
        elif employee.status in ['Casual', 'C'] and employee.casual_details and employee.casual_details.contract_start:
            employment_start = employee.casual_details.contract_start.strftime("%B %d, %Y")
        elif employee.status in ['Job Order', 'JO'] and employee.job_order_details and employee.job_order_details.date_hired:
            employment_start = employee.job_order_details.date_hired.strftime("%B %d, %Y")
        else:
            employment_start = "N/A"

        # === Greeting ===
        self.set_font("Arial", "", 12)
        self.set_x(20)
        self.cell(0, 10, "To whom it may concern:", ln=1, align='L')
        self.ln(5)

        # === Intro Line ===
        page_width = 210
        right_margin_offset = 22
        intro_text = "This is to certify that based on the records kept and filed in this office,"
        text_width = self.get_string_width(intro_text)
        x_position = page_width - right_margin_offset - text_width
        self.set_x(x_position)
        self.cell(text_width, 10, intro_text, ln=1)

        # === Main Body ===
        left_margin = 20
        right_margin = 15
        usable_width = page_width - left_margin - right_margin
        line_height = 10
        x = left_margin
        y = self.get_y()

        sentence_parts = [
            (employee_name, "B"),
            ("is", ""), ("presently", ""), ("employed", ""), ("as", ""),
            (position, "B"),
            ("in", ""), ("the", ""),
            (department, "B"),
            (f", this municipality from {employment_start} to present.", "")
        ]

        for phrase, style in sentence_parts:
            self.set_font("Arial", style, 12)
            for word in phrase.split(" "):
                word += " "
                word_width = self.get_string_width(word)
                if x + word_width > page_width - right_margin:
                    y += line_height
                    x = left_margin
                self.set_xy(x, y)
                self.cell(word_width, line_height, word, border=0)
                x += word_width

        self.ln(line_height + 2)

        # === End Statement ===
        left_margin = 20
        right_margin = 15
        usable_width = page_width - left_margin - right_margin
        indent = 22
        line_height = 8

        first_line = "This certification is issued upon request of the above-named person."
        self.set_x(left_margin + indent)
        self.multi_cell(usable_width - indent, line_height, first_line, align='L')

        self.ln(2)
        second_line = "for whatever legal purpose it may serve."
        self.set_x(left_margin)
        self.multi_cell(usable_width, line_height, second_line, align='L')

        # === Signatory Section ===
        self.ln(20)
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, "LLOYD MORGAN O. PERLEZ", ln=1, align="R")
        self.set_font("Arial", "", 12)
        self.cell(320, 4, "MGDHH I (HRMO)", ln=1, align="C")

        # === Insert Signature Image (if available) ===
        dept_head_user = (
            Users.query
            .join(Employee)
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(Position.title == 'MUNICIPAL GOVERNMENT DEPARTMENT HEAD I')
            .first()
        )

        if dept_head_user:
            sig_record = UserSignature.query.filter_by(user_id=dept_head_user.id).first()
            if sig_record and sig_record.signature:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_sig:
                    tmp_sig.write(sig_record.signature)
                    tmp_sig.flush()
                    sig_path = tmp_sig.name

                scale = 1.8
                sig_w = 29 * scale
                sig_h = 13 * scale
                sig_x = (self.w - sig_w) / 2 + 69
                sig_y = self.get_y() - 27

                self.image(sig_path, x=sig_x, y=sig_y, w=sig_w, h=sig_h)





class TravelOrderPDF(FPDF):
    def add_travel_order_form(
        self,
        permit,
        department=None,
        position=None,
        head_approved=False,
        head_approver=None,
        head_approver_position=None,
        head_signature=None,        # ✅ added
        head_of_office=None,    
        head_approver_id=None,
        current_stage=None
    ):
        self.set_auto_page_break(auto=False)  
        self.add_page()
        self.set_font("Arial", "B", 10)

        line_height = 7
        page_width = self.w - self.l_margin - self.r_margin
        col_width = page_width / 2
        x_left = self.l_margin
        x_right = x_left + col_width

        # --- Helper for two equal-height columns ---
              # --- Helper for two equal-height columns (no duplicate boxes) ---
        def equal_row(left_text, right_text):
            y = self.get_y()
            
            # Left cell (without top/bottom borders yet)
            self.set_xy(x_left, y)
            self.multi_cell(col_width, line_height, left_text, border="LR")
            h_left = self.get_y() - y

            # Right cell (same)
            self.set_xy(x_right, y)
            self.multi_cell(col_width, line_height, right_text, border="LR")
            h_right = self.get_y() - y

            # Compute maximum height
            max_h = max(h_left, h_right)

            # Fill missing space in shorter cell
            if h_left < max_h:
                self.set_xy(x_left, y + h_left)
                self.multi_cell(col_width, max_h - h_left, "", border="LR")
            if h_right < max_h:
                self.set_xy(x_right, y + h_right)
                self.multi_cell(col_width, max_h - h_right, "", border="LR")

            # Draw top and bottom borders across both cells
            self.line(x_left, y, x_left + page_width, y)               # top line
            self.line(x_left, y + max_h, x_left + page_width, y + max_h)  # bottom line

            # Move cursor below this row
            self.set_y(y + max_h)

            # Fill the shorter side
            if h_left < max_h:
                self.set_xy(x_left, y + h_left)
                self.multi_cell(col_width, max_h - h_left, "", border="LR")
            elif h_right < max_h:
                self.set_xy(x_right, y + h_right)
                self.multi_cell(col_width, max_h - h_right, "", border="LR")

            self.set_y(y + max_h)

        # === Extract Data ===
        employee = getattr(permit, "employee", None)
        if not employee:
            return

        full_name = f"{employee.first_name or ''} {employee.middle_name or ''} {employee.last_name or ''}".strip()

        position = (
            getattr(employee.permanent_details.position, "title", None)
            if getattr(employee, "permanent_details", None)
            else getattr(employee.casual_details.position, "title", None)
            if getattr(employee, "casual_details", None)
            else getattr(employee.job_order_details, "position_title", None)
            if getattr(employee, "job_order_details", None)
            else "N/A"
        )

        date_requested = permit.date_requested.strftime('%B %d, %Y') if getattr(permit, "date_requested", None) else "N/A"
        departure = (
            permit.travel_detail.date_departure.strftime('%B %d, %Y')
            if getattr(permit, "travel_detail", None) and permit.travel_detail.date_departure
            else "N/A"
        )
        arrival = " "
        destination = getattr(permit.travel_detail, "destination", "N/A") or "N/A"
        purpose = getattr(permit.travel_detail, "purpose", "N/A") or "N/A"
        permit_id = str(getattr(permit, "id", "N/A"))

        # === Header Title ===
        self.set_font("Arial", "B", 14)
        self.cell(page_width, 10, "TRAVEL ORDER", align="C", border=1, ln=1)

        # === Body ===
        self.set_font("Arial", "", 10)
        equal_row("Municipality of VICTORIA\nProvince of LAGUNA",
                  f"Date: {date_requested}\nTravel Order No.: {permit_id}")

        equal_row(f"Name: {full_name}", f"Position: {position}")
        equal_row(f"Date/Time of Departure: {departure}", f"Destination: {destination}")
        equal_row(f"Date/Time of Arrival: {arrival}", "Report No.: ")

        # === Purpose of Travel / Remarks (fix right cell alignment & same height) ===
       # === Purpose of Travel / Remarks (right cell auto-adjusts to left height) ===
        y = self.get_y()

        # Left: draw the purpose text
        self.set_xy(x_left, y)
        self.multi_cell(col_width, line_height, f"Purpose of Travel / Remarks:\n{purpose}", border="LR")
        h_left = self.get_y() - y

        # Right: match same height exactly, keep borders clean
        self.set_xy(x_right, y)
        self.multi_cell(col_width, line_height, "", border="LR")
        h_right = self.get_y() - y

        # If right cell is shorter, fill up missing height
        if h_right < h_left:
            self.set_xy(x_right, y + h_right)
            self.multi_cell(col_width, h_left - h_right, "", border="LR")

        # Draw shared top and bottom lines once (to prevent double borders)
        self.line(x_left, y, x_left + page_width, y)  # top border
        self.line(x_left, y + h_left, x_left + page_width, y + h_left)  # bottom border

        # Move cursor below both cells
        self.set_y(y + h_left)

      # === Recommending Approval & Signature ===

        block_height = 30
        y = self.get_y()
        self.rect(x_left, y, col_width, block_height)
        self.rect(x_right, y, col_width, block_height)

        # Left block
        self.set_xy(x_left + 3, y + 3)
        self.set_font("Arial", "", 10)
        self.cell(col_width, 6, "Recommending Approval:", ln=1, align='L')

        head_name = head_approver or "________________________"
        head_position = head_approver_position or "Head of Department"
        self.set_xy(x_left, y + block_height - 15)
        self.multi_cell(col_width, 5, f"{head_name}\n{head_position}", align='C')

            # ✅ define margin shortcut
        left_margin = self.l_margin

        # ✅ Signature insertion if provided
        if head_signature:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_sig:
                tmp_sig.write(head_signature)
                tmp_sig.flush()
                sig_path = tmp_sig.name

            # Set signature size
            sig_w = 22  # ✅ new width
            sig_h = 22  # adjust height proportionally if needed
            sig_x = left_margin + 38  # small padding from left edge of left block
            sig_y = y + 2  # small padding from top of block

            self.image(sig_path, x=sig_x, y=sig_y, w=sig_w, h=sig_h)
            os.unlink(sig_path)

        # ✅ Display head name below signature (centered inside the left block)
        if head_of_office and head_of_office.strip("_").strip():
            self.set_font("Arial", "B", 10)
            # Center the name inside the left block
            block_width = (self.w - self.l_margin - self.r_margin) / 2
            self.set_xy(left_margin, y + block_height - 12)
            self.cell(block_width, line_height, head_of_office, align="C")

        # Right block
        self.set_xy(x_right + 3, y + 3)
        self.set_font("Arial", "", 10)
        self.multi_cell(col_width, 6, "Signature of Officer/Employee\nAuthorized to Travel:", align='L')

        self.set_y(y + block_height + 2)

            # === APPROVED Section ===
        y_start = self.get_y()
        self.set_font("Arial", "", 10)
        self.cell(0, 6, "A P P R O V E D", ln=1, align='C')

        self.set_font("Arial", "", 10)
        self.ln(4)
        self.cell(0, 6, "HON. DWIGHT C. KAMPITAN", ln=1, align='C')
        self.set_font("Arial", "", 10)
        self.cell(0, 6, "Municipal Mayor", ln=1, align='C')

        # Draw a bounding rectangle around the "APPROVED" section
        y_end = self.get_y()
        page_width = self.w - self.l_margin - self.r_margin
        self.rect(self.l_margin, y_start - 2, page_width, (y_end - y_start) + 4)

        # === Fetch Mayor’s signature dynamically ===
        mayor_user = (
            Users.query
            .join(Employee)
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(Position.title == 'MUNICIPAL MAYOR')
            .first()
        )

        if mayor_user:
            sig_record = UserSignature.query.filter_by(user_id=mayor_user.id).first()
            if sig_record and sig_record.signature:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_sig:
                    tmp_sig.write(sig_record.signature)
                    tmp_sig.flush()
                    sig_path = tmp_sig.name

                # Scale and center signature image
                scale = 2.0
                sig_w = 31 * scale
                sig_h = 13 * scale
                sig_x = (self.w - sig_w) / 2 + 2
                sig_y = self.get_y() - 24
                self.image(sig_path, x=sig_x, y=sig_y, w=sig_w, h=sig_h)

                # Clean up temp file
                try:
                    os.remove(sig_path)
                except Exception:
                    pass

                # Add a line gap to avoid overlap after the signature
                self.ln(4)
        else:
            # In case no mayor or signature is found, just add spacing
            self.ln(4)
        # <— add vertical spacing before the next section

        # === CERTIFICATE OF APPEARANCE ===
        y_start = self.get_y()
        self.set_font("Arial", "", 10)
        self.multi_cell(page_width, 6, "CERTIFICATE OF APPEARANCE", align="C")
        self.ln(2) 
        self.set_font("Arial", "", 10)
        self.set_x(self.l_margin + 5)
        self.multi_cell(
            page_width - 10,
            6,
            "THIS IS TO CERTIFY that the above-named personnel appeared in this office for the purpose stated above on the date/s indicated below.",
            align="L"
        )
        y_end = self.get_y()
        self.rect(self.l_margin, y_start - 2, page_width, (y_end - y_start) + 6)

        # === FROM / TO / PLACE (single cell) ===
        self.ln(4)
        self.multi_cell(page_width, 8, "FROM                             TO                                 PLACE", border=1, align="L")
      # signature row — make it the same width and same left margin
        self.set_font("Arial", "", 10)
        self.set_x(self.l_margin)
        text = "\n\n______________________________________\n  SIGNATURE                         "
        self.multi_cell(page_width, 7, text, align="R", border=1)


#leave
def clean_text(text):
    if not text:
        return ""
    replacements = {
        '’': "'",
        '‘': "'",
        '“': '"',
        '”': '"',
        '–': '-',
        '—': '--',
        '…': '...',
        '•': '-',   # ← important: ito yung cause ng error mo
        # Add more replacements if needed
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

class LeaveApplicationPDF(FPDF):

    
    def __init__(self):
        super().__init__(orientation='P', unit='mm', format=(215.9, 330.2))  # 8.5 x 13"
        self.set_auto_page_break(auto=True, margin=10)
        self.show_header = True  # ✅ this must exist!

    def header(self):
        if not self.show_header:
            return  # Skip header on second page

        self.set_font('Arial', 'B', 5)
        self.set_y(1)
        self.set_x(10)
        self.cell(100, 3.8, 'Civil Service Form No.6', ln=True, align='L')
        self.set_x(10)
        self.cell(100, 3.8, 'Revised 2020', ln=True, align='L')


        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        self.image(os.path.join(base_path, 'victoria2.png'), x=35, y=10, w=22)  # logo

        self.set_font('Arial', 'B', 8)
        self.set_y(12)
        self.cell(0, 4, 'Republic of the Philippines', ln=True, align='C')

        # Province line
        y_laguna = self.get_y()
        self.cell(0, 4, 'Province of Laguna', ln=True, align='C')

            # Compute text position
        text_width = self.get_string_width("Province of Laguna")
        center_x = (self.w - text_width) / 2

        # ✅ Add 35mm gap from end of text
        stamp_x = center_x + text_width + 35

        # Set stamp box near Province of Laguna line
        self.set_xy(stamp_x, y_laguna)
        self.set_font('Arial', '', 5)
        self.multi_cell(35, 5, "Stamp of Date of Receipt", border=1, align='C')


        # ✅ Municipality line (no extra spacing)
        self.set_font('Arial', 'B', 8)
        self.set_y(self.get_y())  # or just remove this line
        self.cell(0, 4, 'Municipality of VICTORIA', ln=True, align='C')

        self.set_font('Arial', 'B', 12)
        self.cell(0, 12, 'APPLICATION FOR LEAVE', ln=True, align='C')
        self.ln(2)


    def add_leave_form(self, department, last_name, first_name, middle_name,
                   date_from, position, salary, selected_leave,
                   head_approved, head_approver, head_approver_position,
                   head_approver_id, current_stage, credit_balance=None):

        self.set_font('Arial', '', 7)

        # Helper to split department into max 5 words in line 2, rest in line 3
        def split_department(text, first_line_words=7):
            words = text.split()
            line1 = ' '.join(words[:first_line_words])
            line2 = ' '.join(words[first_line_words:]) if len(words) > first_line_words else ''
            return line1, line2

        dep_line1, dep_line2 = split_department(department)

        x = self.get_x()
        y = self.get_y()
        line_height = 5

        # ====================
        # Row 1: OFFICE/DEPARTMENT + NAME (3 lines)
        # ====================
        self.rect(x, y, 196, line_height * 3)

        # --- Line 1: Labels ---
        self.set_xy(x, y)
        self.cell(60, line_height, '1. OFFICE/DEPARTMENT:', border=0)
        self.set_x(x + 60 + 15)  #  15mm spacing between label 1 and label 2
        self.cell(20, line_height, '2. NAME:', border=0)
        self.set_x(self.get_x() + 5)
        self.cell(25, line_height, '(Last)', border=0, align='C')
        self.set_x(self.get_x() + 5)
        self.cell(25, line_height, '(First)', border=0, align='C')
        self.set_x(self.get_x() + 5)
        self.cell(25, line_height, '(Middle)', border=0, align='C')

        # --- Line 2: Department data + Name data ---
        self.set_xy(x, y + line_height)
        self.cell(60, line_height, dep_line1, border=0)
        self.set_x(x + 60 + 15 + 20 + 5)  # Match total offset used above
        self.cell(25, line_height, last_name, border=0, align='C')
        self.set_x(self.get_x() + 5)
        self.cell(25, line_height, first_name, border=0, align='C')
        self.set_x(self.get_x() + 5)
        self.cell(25, line_height, middle_name, border=0, align='C')

        # --- Line 3: Department line 2 (if any) ---
        if dep_line2:
            self.set_xy(x, y + line_height * 2)
            self.cell(60, line_height, dep_line2, border=0)

        # Move Y cursor to bottom
        self.set_y(y + line_height * 3)

        # ====================
        # Row 2: DATE OF FILING, POSITION, SALARY (3 lines)
        # ====================
        y2 = self.get_y()
        self.rect(x, y2, 196, line_height * 2)

        # --- Line 1: Labels ---
        self.set_xy(x, y2)
        self.cell(65, line_height, '3. DATE OF FILING:', border=0)
        self.cell(75, line_height, '4. POSITION:', border=0)
        self.cell(10, line_height, '')  #  Extra 10mm spacing
        self.cell(55, line_height, '5. SALARY:', border=0)

        # --- Line 2: Data ---
        self.set_xy(x, y2 + line_height)
        self.cell(65, line_height, date_from, border=0)
        self.cell(75, line_height, position, border=0)
        self.cell(10, line_height, '')  #  Extra 10mm spacing
        self.cell(55, line_height, salary, border=0)

        # Spacer
        self.set_y(y2 + line_height * 2)

        # ====================
        # Row 3: DETAILS OF APPLICATION
        # ====================
        y3 = y2 + line_height * 2
        self.rect(x, y3, 196, 8)
        self.set_xy(x, y3)
        self.set_font('', 'B', 8)
        self.ln(1)
        self.cell(0, 8, '6. DETAILS OF APPLICATION', border=1, align='C', ln=True)
        self.set_font('', '')

        # === Row 3 — 6.A TYPE OF LEAVE TO BE AVAILED OF ===
        self.set_font('Arial', '', 7)
        box_width = 100
        line_height = 6
        x_start = self.get_x()
        y_start = self.get_y()

        # Draw outer border
        self.rect(x_start, y_start, box_width, line_height * 16)

        # Header
        self.set_xy(x_start, y_start)
        self.cell(box_width, line_height, "6.A TYPE OF LEAVE TO BE AVAILED OF:", ln=1)

        # Leave types list
        leave_types = [
            ("Vacation Leave", "Sec. 51, Rule XVI, Omnibus Rules Implementing E.O. No. 292"),
            ("Mandatory/Forced Leave", "Sec. 25, Rule XVI, Omnibus Rules Implementing E.O. No. 292"),
            ("Sick Leave", "Sec. 43, Rule XVI, Omnibus Rules Implementing E.O. No. 292"),
            ("Maternity Leave", "R.A. No. 11210 / IRR issued by CSC, DOLE and SSS"),
            ("Paternity Leave", "R.A. No. 8187 / CSC MC No. 71, s. 1998, as amended"),
            ("Special Privilege Leave", "Sec. 21, Rule XVI, Omnibus Rules Implementing E.O. No. 292"),
            ("Solo Parent Leave", "R.A. No. 8972 / CSC MC No. 8, s. 2004"),
            ("Study Leave", "Sec. 68, Rule XVI, Omnibus Rules Implementing E.O. No. 292"),
            ("10-Day VAWC Leave", "R.A. No. 9262 / CSC MC No. 15, s. 2005"),
            ("Rehabilitation Leave", "Sec. 55, Rule XVI, Omnibus Rules Implementing E.O. No. 292"),
            ("Special Leave Benefits for Women", "R.A. No. 9710 / CSC MC No. 25, s. 2010"),
            ("Special Emergency (Calamity) Leave", "CSC MC No. 2, s. 2012, as amended"),
            ("Adoption Leave", "R.A. No. 8552"),
        ]

        x_box = x_start + 4
        x_text = x_box + 3
        current_y = self.get_y()
        max_leave_width = 60
        ref_indent = 6

        for leave, ref in leave_types:
            # Draw checkbox square
            box_size = 3
            self.rect(x_box, current_y + 1.5, box_size, box_size)

            # ✅ If this leave type is selected, overlay check image (scaled + centered)
            if selected_leave == leave:
                check_size = 2.2  # mas maliit para di lumampas
                offset = (box_size - check_size) / 2
                check_path = os.path.join(current_app.root_path, "static", "img", "landing", "check.png")
                self.image(
                    check_path,
                    x=x_box + offset,
                    y=current_y + 1.5 + offset,
                    w=check_size,
                    h=check_size
                )
            # Draw text
            self.set_xy(x_text, current_y)
            self.set_font("Arial", '', 6)
            leave_width = self.get_string_width(leave)

            if leave_width <= max_leave_width:
                self.cell(0, line_height, f"{leave} ({ref})", ln=1)
                current_y += line_height
            else:
                self.cell(0, line_height, leave, ln=1)
                self.set_xy(x_text + ref_indent, self.get_y())
                self.set_font("Arial", '', 5)
                self.cell(0, line_height, f"({ref})", ln=1)
                current_y += line_height * 2

        # === Others
        self.set_xy(x_text, current_y)
        self.cell(0, line_height, "Others:", ln=1)
        self.rect(x_box, current_y + 1.5, 3, 3)

        if selected_leave == "Others":
            self.image(
                os.path.join(current_app.root_path, "static", "img", "landing", "check.png"),
                x=x_box,
                y=current_y + 1.5,
                w=3,
                h=3
        )


        current_y += line_height
        self.set_xy(x_text, current_y)
        self.cell(60, line_height, "___________________", ln=1)

        # Reset cursor
        self.set_y(y_start + line_height * 16)





        # ✅ DEFINE y_after_6A here
        y_after_6A = self.get_y()

        # CELL right row 3 — 6.B
        # === RIGHT SIDE — 6.B DETAILS OF LEAVE (with checkboxes) ===

        box_x = x_start + 100  # start of right column
        box_y = y_start        # align with 6.A top
        box_w = 96
        line_h = 6

        # Draw the outer container (16 lines × 6mm)
        self.rect(box_x, box_y, box_w, line_h * 16)

        # Line 1: Header
        self.set_font('Arial', '', 7)
        self.set_xy(box_x, box_y)
        self.cell(box_w, line_h, "6.B DETAILS OF LEAVE:", ln=1)

        # Line 2: Italic line
        self.set_font('Arial', 'I', 7)
        self.set_xy(box_x, self.get_y())
        self.cell(box_w, line_h, "  In case of Vacation/Special Privilege Leave:", ln=1)

        # ✅ Define checkbox line function (fixing alignment issue)
        def checkbox_line_right(text):
            y = self.get_y()
            self.rect(box_x + 4, y + 1.5, 3, 3)  # Checkbox square
            self.set_xy(box_x + 10, y)
            self.cell(box_w - 10, line_h, text, ln=1)

        # Lines 3–4
        self.set_font('Arial', '', 7)
        checkbox_line_right("Within the Philippines")
        checkbox_line_right("Abroad (Specify): ____________")

        # Line 5: Sick leave section (italic)
        self.set_font('Arial', 'I', 7)
        self.set_xy(box_x, self.get_y())
        self.cell(box_w, line_h, "  In case of Sick Leave:", ln=1)

        # Lines 6–7
        self.set_font('Arial', '', 7)
        checkbox_line_right("In Hospital (Specify Illness): __________________")
        checkbox_line_right("Out Patient (Specify Illness): __________________")

       # Line 8–9: Special Leave for Women
        self.set_font('Arial', 'I', 7)
        self.set_xy(box_x, self.get_y())
        self.cell(box_w, line_h, "  In case of Special Leave Benefits for Women", ln=1)

        self.set_xy(box_x, self.get_y())  # ✅ ADD THIS
        self.cell(box_w, line_h, "  (Specify Illness): ________________________________", ln=1)

        # Line 10
        self.set_font('Arial', '', 7)
        self.set_xy(box_x, self.get_y())  # ✅ ADD THIS
        self.cell(box_w, line_h, "    _________________________________________________", ln=1)

        # Line 11: Study Leave
        self.set_font('Arial', 'I', 7)
        self.set_xy(box_x, self.get_y())  # ✅ ADD THIS
        self.cell(box_w, line_h, "  In case of Study Leave:", ln=1)

        # Line 12–13
        self.set_font('Arial', '', 7)
        checkbox_line_right("Completion of Master's Degree")
        checkbox_line_right("BAR/Board Examination Review")

       # Line 14: Other Purpose
        self.set_font('Arial', 'I', 7)
        self.set_xy(box_x, self.get_y())  # ✅ ADD THIS
        self.cell(box_w, line_h, "  Other Purpose:", ln=1)

        # Line 15–16
        self.set_font('Arial', '', 7)
        checkbox_line_right("Monetization of Leave Credits")
        checkbox_line_right("Terminal Leave")

        # Reset Y position
        self.set_y(box_y + line_h * 16)


        # CELL left row 4  — 6.A
        # ✅ DEFINE y_after_6B here
        y_after_6B = self.get_y()

        # === 6.C and 6.D (side by side under 6.A/6.B) ===
        y_start_next = max(y_after_6A, y_after_6B)
        self.set_y(y_start_next)



        # 6.C Left
        self.set_xy(x_start, y_start_next)
        self.multi_cell(
            100, 6,
            '6.C NUMBER OF WORKING DAYS APPLIED FOR:\n'
            ' \n'
            '    INCLUSIVE DATES\n'
            '    ______________________________'
            ' \n'
            "\n",
            border=1
        )
        # CELL right row 4 — 6.A
        # 6.D Right
        # Setup box
        box_x = x_start + 100
        box_y = y_start_next
        box_w = 96
        line_h = 6

        # Draw outer container
        self.rect(box_x, box_y, box_w, line_h * 5)

        # 1: Header
        self.set_font('Arial', '', 7)
        self.set_xy(box_x, box_y)
        self.cell(box_w, line_h, "6.D COMMUNICATION", ln=1)

        # 2: [ ] Not Requested
        y = self.get_y()
        self.rect(box_x + 4, y + 1.5, 3, 3)  # Square box
        self.set_xy(box_x + 10, y)
        self.cell(box_w - 10, line_h, "Not Requested", ln=1)

        # 3: [ ] Requested
        y = self.get_y()
        self.rect(box_x + 4, y + 1.5, 3, 3)  # Square box
        self.set_xy(box_x + 10, y)
        self.cell(box_w - 10, line_h, "Requested", ln=1)

        # 4: Line for signature
        self.set_xy(box_x + 10, self.get_y())
        self.cell(box_w - 20, line_h, "__________________________________________", ln=1)

        # 5: Signature label
        self.set_xy(box_x, self.get_y())
        self.cell(box_w, line_h, "                                     (Signature of Application)", ln=1)


        # --- SECTION 7 HEADER ---
        self.set_font('Arial', 'B', 8)
        self.ln(1)
        self.cell(0, 8, '7. DETAILS OF ACTION ON APPLICATION', border=1, align='C', ln=True)
        self.ln(1)
        x_start = self.get_x()
        y_start = self.get_y()

        # CELL right row 5 
        # 7.A CERTIFICATION OF LEAVE CREDITS
        self.set_font('Arial', '', 7)
        box_width = 100
        box_height = 48

        # Draw outer box
        self.rect(x_start, y_start, box_width, box_height)

        # Title
            # --- 7.A CERTIFICATION OF LEAVE CREDITS ---
        self.set_xy(x_start, y_start)
        self.set_font('Arial', 'B', 7)
        self.cell(box_width, 5, '7.A CERTIFICATION OF LEAVE CREDITS', ln=True, align='C')

        self.set_font('Arial', 'B', 7)
        self.cell(box_width, 4.5, f"As of {datetime.today().strftime('%B %d, %Y')}", ln=True, align='C')

        self.set_font('Arial', '', 7)
        table_width = 90
        col_width = table_width / 3
        cell_height = 5
        x_table_start = x_start + (box_width - table_width) / 2
        y_table_start = self.get_y()

        # Header row
        self.set_xy(x_table_start, y_table_start)
        self.cell(col_width, cell_height, '', 1, 0, 'C')
        self.cell(col_width, cell_height, 'Vacation Leave', 1, 0, 'C')
        self.cell(col_width, cell_height, 'Sick Leave', 1, 1, 'C')

        # ✅ Pull credit values
        if credit_balance:
            vac_earned     = f"{credit_balance.vacation_earned:.2f}" if credit_balance.vacation_earned else "0.00"
            vac_used       = f"{credit_balance.vacation_used:.2f}" if credit_balance.vacation_used else "0.00"
            vac_remaining  = f"{credit_balance.vacation_remaining:.2f}" if credit_balance.vacation_remaining else "0.00"

            sick_earned    = f"{credit_balance.sick_earned:.2f}" if credit_balance.sick_earned else "0.00"
            sick_used      = f"{credit_balance.sick_used:.2f}" if credit_balance.sick_used else "0.00"
            sick_remaining = f"{credit_balance.sick_remaining:.2f}" if credit_balance.sick_remaining else "0.00"
        else:
            vac_earned = vac_used = vac_remaining = "0.00"
            sick_earned = sick_used = sick_remaining = "0.00"

        # Table rows
        rows = [
            ('Total Earned', vac_earned, sick_earned),
            ('Less this application', vac_used, sick_used),
            ('Balance', vac_remaining, sick_remaining),
            ('Remaining Leave', vac_remaining, sick_remaining),
        ]

        for row_label, vac_val, sick_val in rows:
            self.set_x(x_table_start)
            self.cell(col_width, cell_height, row_label, 1, 0, 'C')
            self.cell(col_width, cell_height, vac_val, 1, 0, 'C')
            self.cell(col_width, cell_height, sick_val, 1, 1, 'C')

        # Signature block (unchanged)
        self.ln(1.5)
        self.set_font('Arial', 'B', 7)
        self.set_x(x_start)
        self.cell(box_width, 4, '_______________________________', 0, 1, 'C')

        dept_head_user = (
            Users.query
            .join(Employee)
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(Position.title == 'MUNICIPAL GOVERNMENT DEPARTMENT HEAD I')
            .first()
        )

        if dept_head_user:
            sig_record = UserSignature.query.filter_by(user_id=dept_head_user.id).first()
            if sig_record and sig_record.signature:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_sig:
                    tmp_sig.write(sig_record.signature)
                    tmp_sig.flush()
                    sig_path = tmp_sig.name

                # Adjust size and position
             # Adjust size and position
                # Adjust size and position
                    scale = 1.0   # mas maliit pa
                    sig_w = 29 * scale
                    sig_h = 13 * scale

                    # Position relative sa box (x_start)
                    sig_x = x_start + 38   # pwesto mo sa kaliwa
                    sig_y = self.get_y() - sig_h - 1 + 7 # binaba ng 9 units

                    self.image(sig_path, x=sig_x, y=sig_y, w=sig_w, h=sig_h)

        self.cell(box_width, 3.8, 'LLOYD MORGAN O. PERLEZ', 0, 1, 'C')
        self.cell(box_width, 3.8, 'MOH I (HRMO)', 0, 0, 'C')
            
        # 🔍 Step: Measure total used height
        y_end = self.get_y()
        used_height = y_end - y_start
        remaining_height = box_height - used_height

        # ⚖️ Final: Fill the gap if there's remaining space
        if remaining_height > 0:
            self.set_x(x_start)



        # CELL right row 5 
        y_after_7A = y_start + box_height


       # === RIGHT SIDE — 7.B RECOMMENDATION (with checkboxes) ===
      # === RIGHT SIDE — 7.B RECOMMENDATION (with checkboxes) ===
        box_x = x_start + 100  # start of right column
        box_y = y_start
        box_w = 96
        line_h = 6
        box_height = 8 * line_h  # ✅ fix kulang sa height

        # Draw border box
        self.rect(box_x, box_y, box_w, box_height)

        # Line 1: Header
        self.set_font('Arial', '', 7)
        self.set_xy(box_x, box_y)
        self.cell(box_w, line_h, "7.B RECOMMENDATION:", ln=1)

        # Helper function for checkbox lines with optional check image
        def checkbox_line_7B(text, checked=False):
            y = self.get_y()
            box_size = 3
            # draw checkbox square
            self.rect(box_x + 4, y + 1.5, box_size, box_size)

            if checked:
                # try overlaying the check image centered inside the box
                try:
                    check_path = os.path.join(current_app.root_path, "static", "img", "landing", "check.png")
                    check_size = 2.2
                    offset = (box_size - check_size) / 2
                    self.image(
                        check_path,
                        x=box_x + 4 + offset,
                        y=y + 1.5 + offset,
                        w=check_size,
                        h=check_size
                    )
                except Exception:
                    # fallback: draw a simple check character if image fails
                    self.set_font('Arial', 'B', 8)
                    self.text(box_x + 4.2, y + 3.8, "✓")
                    self.set_font('Arial', '', 7)

            self.set_xy(box_x + 10, y)
            self.cell(box_w - 10, line_h, text, ln=1)

        # Line 2–3: checkbox lines -- use head_approved to check "For approval"
        checkbox_line_7B("For approval", checked=head_approved)
        checkbox_line_7B("For disapproval due to: ______________", checked=False)

        # Lines 4–6: Empty lines
        self.set_xy(box_x + 10, self.get_y())
        self.cell(box_w - 10, line_h, "__________________________________________", ln=1)
        self.set_x(box_x + 10)
        self.cell(box_w - 10, line_h, "__________________________________________", ln=1)
        self.set_x(box_x + 10)
        self.cell(box_w - 10, line_h, "__________________________________________", ln=1)

        self.ln(4)

        def format_name_with_middle_initial(full_name: str) -> str:
            parts = full_name.split()

            if len(parts) < 3:
                # Kung wala talagang middle name (e.g. "Juan Cruz")
                return full_name

            # Last = huling word
            last = parts[-1]

            # Middle = second-to-last word
            middle = parts[-2]

            # First = lahat ng nasa unahan bago ang middle at last
            first = " ".join(parts[:-2])

            # Kung initial na ang middle (may "." o single char)
            if middle.endswith(".") or len(middle) == 1:
                middle_initial = middle
            else:
                middle_initial = middle[0].upper() + "."

            return f"{first} {middle_initial} {last}"


            # -------------------
        # ✅ INSERT HEAD SIGNATURE (OVERLAPPING)
        # -------------------
        if head_approver:
            formatted_name = format_name_with_middle_initial(head_approver)

            # Name & position first (so image will go on top)
            self.set_font('Arial', 'B', 7)
            self.set_xy(box_x, self.get_y())
            self.cell(box_w, 3.5, formatted_name, ln=1, align="C")

            if head_approver_position:
                self.set_xy(box_x, self.get_y())
                self.set_font('Arial', '', 7)
                self.cell(box_w, 3.5, head_approver_position, ln=1, align="C")

            # Then draw signature on top of text
            sig_record = UserSignature.query.filter_by(user_id=head_approver_id).first()
            if sig_record and sig_record.signature:
                # Save to temp file
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_sig:
                    tmp_sig.write(sig_record.signature)
                    tmp_sig.flush()
                    sig_path = tmp_sig.name

                scale = 1.8  # 1.0 = original, >1 = palaki, <1 = paliit
                sig_w = 25 * scale
                sig_h = 8 * scale

                sig_x = box_x + (box_w - sig_w) / 2
                sig_y = self.get_y() - (sig_h + 1)  # move up to overlap text
                self.image(sig_path, x=sig_x, y=sig_y, w=sig_w, h=sig_h)
        else:
            # Default fallback
            self.set_xy(box_x, self.get_y())
            self.set_font('Arial', '', 7)
            self.cell(box_w, 3.5, "(Authorized Officer)", ln=1, align="C")



        y_after_7B = self.get_y()

        y_max = max(y_after_7A, y_after_7B)
        self.set_xy(x_start, y_max)
        self.cell(196, 40, '', border=1)

        self.set_xy(x_start, y_max)
        self.multi_cell(107.5, 3, 
                                '\n'
                                '7.C APPROVED FOR:\n\n'
                                '    _______ days with pay\n'
                                '    _______ days without pay\n'
                                '    _______ others (Specify)', border=0)

        self.set_xy(x_start + 100.5, y_max)
        self.multi_cell(50, 3,   '\n'
                                '7.D DISAPPROVED DUE TO:\n\n'
                                '    _______________________________\n'
                                '    _______________________________\n'
                                '    _______________________________', border=0)

            # -------------------
        # Municipal Mayor Section
        # -------------------
        self.ln(4)
        self.set_font('Arial', 'B', 7)
        self.cell(180, 4, '____________________________________', ln=True, align='C')
        self.cell(180, 4, '    HON. DWIGHT C. KAMPITAN, MD', ln=True, align='C')
        self.cell(180, 3, '          Municipal Mayor', ln=True, align='C')

       # ✅ Insert Mayor's signature
        # Query Users linked to Employee who has position title "MUNICIPAL MAYOR"
        mayor_user = (
            Users.query
            .join(Employee)
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(Position.title == 'MUNICIPAL MAYOR')
            .first()
        )

        if mayor_user:
            sig_record = UserSignature.query.filter_by(user_id=mayor_user.id).first()
            if sig_record and sig_record.signature:
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_sig:
                    tmp_sig.write(sig_record.signature)
                    tmp_sig.flush()
                    sig_path = tmp_sig.name

                # Adjust size and position
                scale = 2.0  # scale signature
                sig_w = 31 * scale
                sig_h = 13 * scale
                sig_x = (self.w - sig_w) / 2 - 3  # center horizontally
                sig_y = self.get_y() - 22  # sit above the line

                self.image(sig_path, x=sig_x, y=sig_y, w=sig_w, h=sig_h)
                


#2ND PAGE 

    def add_instructions_page(self):
        self.show_header = False
        self.add_page()

        # Column settings
        left_x = 10
        right_x = 110
        text_width = 90
        line_height = 4.5
        max_width = 90

        # Title
        self.set_font('Arial', 'B', 8)
        self.cell(190, 8, 'INSTRUCTIONS AND REQUIREMENTS', ln=True, align='C', border=1)
        self.ln(3)

        # Intro left column (Line 1–3)
        tight_line_height = 3.2  # Mas dikit-dikit
        self.set_font('Arial', '', 7)
        x = left_x
        y_start = self.get_y()
        self.y = y_start

        line1_words = [
            ("Application", ""), ("for", ""), ("any", ""), ("type", ""), ("of", ""), 
            ("leave", ""), ("shall", ""), ("be", ""), ("made", ""), ("on", ""), 
            ("this", ""), ("Form", ""), ("and", ""), ("to", "BU")
        ]
        for word, style in line1_words:
            self.set_font('Arial', style, 7)
            word_width = self.get_string_width(word + " ")
            if x + word_width > left_x + max_width:
                self.y += tight_line_height
                x = left_x
            self.set_xy(x, self.y)
            self.cell(word_width, tight_line_height, word + " ", border=0)
            x += word_width

        line2_words = [
            ("be", "BU"), ("accomplished", "BU"), ("at", "BU"), ("least", "BU"), 
            ("in", "BU"), ("duplicate", "BU"), ("with", ""), ("documentary", ""), 
            ("requirements,", ""), ("as", "")
        ]
        for word, style in line2_words:
            self.set_font('Arial', style, 7)
            word_width = self.get_string_width(word + " ")
            if x + word_width > left_x + max_width:
                self.y += tight_line_height
                x = left_x
            self.set_xy(x, self.y)
            self.cell(word_width, tight_line_height, word + " ", border=0)
            x += word_width

        # Final word: "follows:"
        self.set_font('Arial', '', 7)
        word = "follows:"
        word_width = self.get_string_width(word)
        self.y += tight_line_height
        x = left_x
        self.set_xy(x, self.y)
        self.cell(word_width, tight_line_height, word, border=0)

        # Preserve position after intro text
        y_left_continue = self.y + tight_line_height

        # RIGHT column — Independent paragraph
        right_paragraph = (
            "         TPO or PPO has been filed with the said office shall be sufficient\n"
            "         to support the application for the ten-day leave ; or\n"
            "     d. In the absence of the BPO/TPO/PPO or the certification, a police\n"
            "         report specifying the details of the occurrence of violence on the\n"
            "         victim and a medical certificate may be considered, at the\n"
            "         discretion of the immediate supervisor of the woman employee\n"
            "         concerned."
        )
        self.set_xy(right_x, y_start)
        self.set_font('Arial', '', 7)
        self.multi_cell(text_width, tight_line_height, right_paragraph, border=0, align='J')

        # Return to left column for next section
        self.y = y_left_continue
        self.set_xy(left_x, self.y)


        def section(title, content):
            indent_spaces = "     "
            lines = content.split('\n')
            tight_line_height = 3.2  # ← adjust to control vertical spacing

            self.set_xy(left_x, self.y)
            self.set_font('Arial', 'B', 7)
            self.cell(text_width, tight_line_height, title, ln=False)

            self.y += tight_line_height
            self.set_xy(left_x, self.y)
            self.set_font('Arial', '', 7)

            for line in lines:
                self.set_x(left_x)
                indented_line = indent_spaces + line.strip()

                # Handle underlining
                if "Sick Leave" in title:
                    if "medical certificate" in indented_line:
                        before, _, after = indented_line.partition("medical certificate")
                        self.cell(self.get_string_width(before), tight_line_height, before, ln=0)
                        self.set_font('Arial', 'U', 7)
                        self.cell(self.get_string_width("medical certificate"), tight_line_height, "medical certificate", ln=0)
                        self.set_font('Arial', '', 7)
                        self.cell(0, tight_line_height, after, ln=1)
                        continue
                    if "affidavit" in indented_line:
                        before, _, after = indented_line.partition("affidavit")
                        self.cell(self.get_string_width(before), tight_line_height, before, ln=0)
                        self.set_font('Arial', 'U', 7)
                        self.cell(self.get_string_width("affidavit"), tight_line_height, "affidavit", ln=0)
                        self.set_font('Arial', '', 7)
                        self.cell(0, tight_line_height, after, ln=1)
                        continue

                self.multi_cell(text_width, tight_line_height, indented_line, border=0, align='J')

            self.y = self.get_y() + 1
        


        # === Sections 1–9 ===
        section("1.  Vacation Leave",
            "It shall be filed five (5) days in advance, whenever possible, of the\n"
            "effective date of such leave. Vacation leave within the Philippines or\n"
            "abroad shall be indicated in the form for purposes of securing travel\n"
            "authority and completing clearance from money and work\n"
            "accountabilities.")

    # ... (continue with sections 2 to 9 as before)

        section("2.  Mandatory/Forced Leave",
            "Annual five-day vacation leave shall be forfeited if not taken during the\n"
            "year. In case the scheduled leave has been cancelled in the exigency\n"
            "of the service by the head of agency, it shall no longer be deducted from\n"
            "the accumulated vacation leave. Availment of one (1) day or more\n"
            "Vacation Leave (VL) shall be considered for complying the\n"
            "mandatory/forced leave subject to the conditions under Section 25, Rule\n"
            "XVI of the Omnibus Rules Implementing E.O. No. 292.")

       # === Section 3. Sick Leave ===
        section("3.  Sick Leave",
            "- It shall be filed immediately upon employee's return from such leave.\n"
            "- If filed in advance or exceeding five (5) days, application shall be\n"
            "  accompanied by a medical certificate. In case medical consultation\n"
            "  was not availed of, an affidavit should be executed by an applicant.")


        section("4.  Maternity Leave - 105 days",
            "- Proof of pregnancy e.g. ultrasound, doctor's certificate on the\n"
            "  expected date of delivery\n"
            "- Accomplished Notice of Allocation of Maternity Leave Credits (CS\n"
            "  Form No. 6a), if needed\n"
            "- Seconded female employees shall enjoy maternity leave with full pay\n"
            "  in the recipient agency.")

        section("5.  Paternity Leave - 7 days",
            "Proof of child's delivery e.g. birth certificate, medical certificate and\n"
            "marriage contract.")

        section("6.  Special Privilege Leave - 3 days",
            "It shall be filed/approved for at least one (1) week prior to availment,\n"
            "except on emergency cases. Special privilege leave within the\n"
            "Philippines or abroad shall be indicated in the form for purposes of\n"
            "securing travel authority and completing clearance from money and work\n"
            "accountabilities.")

        section("7.  Solo Parent Leave - 7 days",
            "It shall be filed in advance or whenever possible five (5) days before\n"
            "going on such leave with updated Solo Parent Identification Card.")

        section("8.  Study Leave - up to 6 months",
            "- Shall meet the agency's internal requirements, if any;\n"
            "- Contract between the agency head or authorized representative and\n"
            "  the employee concerned.")

        section("9.  VAWC Leave - 10 days",
            "- It shall be filed in advance or immediately upon the woman\n"
            "  employee's return from such leave.\n"
            "- It shall be accompanied by any of the following supporting documents:\n"
            "  a. Barangay Protection Order (BPO) obtained from the barangay;\n"
            "  b. Temporary/Permanent Protection Order (TPO/PPO) obtained from\n"
            "     the court;\n"
            "  c. If the protection order is not yet issued, by the barangay court\n"
            "     a certification issued by the Punong Barangay/Kagawad or\n"
            "     Prosecutor or the Clerk of Court about the application for the BPO.")

        # Save last Y of left column
        left_column_end_y = self.y

        # === RIGHT COLUMN: Sections 10–15 ===

        right_y_start = y_start + 25
        self.set_xy(right_x, right_y_start)
        def right_section(title, content):
            tight_line_height = 3.2  # adjust as needed
            self.set_font('Arial', 'B', 7)
            self.set_x(right_x)
            self.cell(text_width, tight_line_height, title, ln=True)
            self.set_font('Arial', '', 7)
            self.set_x(right_x)
            self.multi_cell(text_width, tight_line_height, content, border=0, align='J')
            self.ln(1)



        right_section(
            "10. Rehabilitation Leave - up to 6 months",
            textwrap.indent(
                "- Application shall be made within one (1) week from the time of the\n accident except when a longer period is warranted.\n"
                "- Letter request supported by relevant reports such as the police\n report, if any.\n"
                "- Medical certificate on the nature of the injuries, the course of\n treatment involved, and the need to undergo rest, recuperation, and\n rehabilitation, as the case may be.\n"
                "- Written concurrence of a government physician should be obtained\n relative to the recommendation for rehabilitation if the attending\n physician is a private practitioner, particularly on the duration of the\n period of rehabilitation.",
                prefix="     "  # 5-space indent
            )
        )

                
        right_section(
            "11. Special Leave Benefits for Women - up to 2 months",
            textwrap.indent(
                "- The application may be filed in advance, at least five (5) days\n prior to the scheduled date of the gynecological surgery that will be\n undergone by the employee. In case of emergency, the application\n for special leave shall be filled immediately upon employee's return\n but during confinement the agency shall be notified of said surgery.\n"
                "- The application shall be accompanied by a medical certificate filled\n out by the proper medical authorities, e.g., the attending surgeon\n accompanied by a clinical summary reflecting the gynecological\n disorder which shall be addressed or was addressed by the said\n surgery; the histopathological report; the operative technique used\n for the surgery; the teachnique used\n for the surgery; the duration of the surgery including the peri-\n operative period (period of confinement around surgery); as well as\n the employees estimated period of recuperation for t he same.",
                prefix="     "
            )
        )

        right_section(
            "12. Special Emergency (Calamity) Leave - up to 5 days",
            textwrap.indent(
                "- The special emergency leave can be applied for a maximum of five\n (5) straight working days or staggered basis within thirty (30) days\n from the actual occurrence of the natural calamity/disaster. Said\n privilege shall be enjoyed once a year, not in every instance of\n calamity or disaster.\n"
                "- The head of office shall take full responsibility for the grant of special\n emergency leave and verification of the employee's eligibility to be\n granted thereof. Said verification shall include: validation of place of\n residence based on latest available records of the affected\n employee; verification that the place of residence is covered in the\n declaration of calamity area by the proper government agency; and\n such other proofs as may be necessary.",
                prefix="     "
            )
        )

        right_section(
            "13. Monetization of Leave Credits",
            textwrap.indent(
                "Application for monetization of fifty percent (50%) or more of the\n accumulated leave credits shall be accompanied by letter request to\n the head of the agency stating the valid and justifiable reasons.",
                prefix="     "
            )
        )

        right_section(
            "14. Terminal Leave",
            textwrap.indent(
                "Proof of employee's resignation or retirement or separation from theservice.",
                prefix="     "
            )
        )

        right_section(
            "15. Adoption Leave",
            textwrap.indent(
                "Application for adoption leave shall be filed with an authenticated\n copy of the Pre-Adoptive Placement Authority issued by the\n Department of Social Welfare and Development (DSWD).",
                prefix="     "
            )
        )

        # Save last Y of right column
        right_column_end_y = self.get_y()

        # === Final alignment ===
        self.set_y(max(left_column_end_y, right_column_end_y) + 5)

        # Set common styles
        self.set_font('Arial', '', 7)
        paragraph_width = 215.9 - 30  # 15mm side margins originally
        left_margin = 10  # moved 5mm to the left
        line_height = 3.2

        # === Draw 30mm line ===
        line_y = self.get_y()
        self.line(left_margin, line_y, left_margin + 30, line_y)

        # Move slightly below the line before writing text
        self.set_y(line_y + 2)

        # === First line ===
        self.set_x(left_margin)
        line1 = "- For leave of absence for thirty (30) calendar days or more and terminal leave, application shall be accoumpanied by a "
        underline_part1 = "clreance form money, property and"
        self.cell(self.get_string_width(line1), line_height, line1, ln=False)
        self.set_font('Arial', 'U', 7)
        self.cell(self.get_string_width(underline_part1), line_height, underline_part1, ln=True)

        # === Second line (aligned to new left margin) ===
        self.set_x(left_margin)
        underline_part2 = "work-related accountabilities"
        self.set_font('Arial', 'U', 7)
        self.cell(self.get_string_width(underline_part2), line_height, underline_part2, ln=False)

        # Non-underlined trailing text
        self.set_font('Arial', '', 7)
        trailing_text = " (pursuant to CSC Memorandum No. 2, s. 1985)"
        self.cell(0, line_height, trailing_text, ln=True)

                        


                 
                    






#CLEARANCE

class ClearanceFormPDF(FPDF):
    def __init__(self):
        super().__init__(orientation='P', unit='mm', format=(215.9, 330.2))  # 8.5 x 13"
        self.set_auto_page_break(auto=True, margin=10)

    def header(self):

        self.set_font('Arial', 'B', 8)
        self.set_y(self.get_y()) 
        self.set_x(10)
        self.cell(100, 3.4, 'CS Form No. 7', ln=True, align='L')
        self.set_x(10)
        self.cell(100, 3.4, 'Series of 2017', ln=True, align='L')

        self.set_font('Arial', 'B', 11)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')  # dati 8
        self.cell(0,5, 'Province of Laguna', ln=True, align='C')          
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')     
        self.set_font('Arial', 'B', 13) 
        self.cell(0, 5, 'CLEARANCE FORM', ln=True, align='C')      
        self.set_font('Arial', '', 7)  
        self.cell(0, 3, '(Instructions at the back)', ln=True, align='C')       
        self.ln(3)  


    def add_clearance_form(
        self, 
        leave_type, date_from, position, office_assignment, name, 
        salary_grade, step, head_of_office, permit, clearance, 
            employee: Employee, effectivity_period, other_text=None, head_signature=None, 
        ):

            # Layout setup
        page_width = 215.9
        left_margin = 10
        small_cell_width = 8
        usable_width = page_width - left_margin * 2 - small_cell_width
        total_width = small_cell_width + usable_width
        line_height = 5
        large_cell_height = 50  # 10 lines × 5mm

        # ✅ Path for check image
        check_path = os.path.join(current_app.root_path, "static", "img", "landing", "check.png")
        box_size = 3
        check_size = 2.0
        box_spacing = 1.5
        label_width = 35

        # Helper: draw check if condition is True
        def draw_check_if(condition, x, y):
            if condition:
                x_center = x + (box_size - check_size) / 2
                y_center = y + (box_size - check_size) / 2
                self.image(check_path, x=x_center, y=y_center, w=check_size, h=check_size)

        # --- Row 1: Purpose Header ---
        self.set_x(left_margin)
        self.set_font('Arial', 'B', 10)
        self.cell(small_cell_width, line_height, 'I', border=1)
        self.cell(usable_width, line_height, 'Purpose', border=1, ln=True)

        # --- Row 2: Big Box ---
        y_start = self.get_y()
        self.set_x(left_margin)
        self.cell(total_width, large_cell_height, '', border=1, ln=True)

        # --- Date of Application (Right) ---
        box_width = 60
        x_right = page_width - 10 - box_width
        y_line = y_start + line_height * 1
        y_label = y_line + line_height

    # --- Date of Application ---
        if permit and permit.date_requested:
            date_requested_str = permit.date_requested.strftime('%B %d, %Y')  # e.g. September 11, 2025
        else:
            date_requested_str = "N/A"

        self.set_font('Arial', '', 10)

        # 🔥 Adjusted underline (shorter by 10px each side) + lowered Y by 2
        short_width = box_width - 20
        self.set_xy(x_right + 10, y_line )
        self.cell(short_width, line_height, date_requested_str, align='C', border="B")

        # Label stays centered below
        self.set_xy(x_right, y_label)
        self.cell(box_width, line_height, 'Date of Application', align='C', border=0)

        # --- TO: MUNICIPALITY OF VICTORIA ---
        to_text = "TO:"
        recipient_text = "MUNICIPALITY OF VICTORIA"
        x_to = left_margin + 2
        y_to = y_start + line_height * 3

        self.set_xy(x_to, y_to)
        self.set_font('Arial', 'B', 10)
        self.cell(self.get_string_width(to_text) + 2, line_height, to_text, ln=0)

        self.set_font('Arial', 'BU', 10)
        x_municipality = self.get_x() + 10
        self.set_x(x_municipality)
        self.cell(0, line_height, recipient_text, ln=1)

        # --- Application Statement ---
        x_start = x_municipality
        y_start = self.get_y()
        self.set_xy(x_start, y_start)
        self.set_font('Arial', '', 10)
        self.cell(0, line_height,
                  "I hereby apply for clearance from money, property, and work-related accountabilities for:",
                  ln=1)

        # === FIRST ROW OF PURPOSES ===
        y_row1 = self.get_y()
        self.set_xy(x_start, y_row1)
        purpose_label = "Purpose:"
        self.cell(self.get_string_width(purpose_label) + 2, line_height, purpose_label, ln=0)

        # ☐ Transfer
        x_col1 = self.get_x()
        self.rect(x_col1, y_row1 + 1.5, box_size, box_size)
        draw_check_if(leave_type.lower() == "transfer", x_col1, y_row1 + 1.5)
        self.set_x(x_col1 + box_size + box_spacing)
        self.cell(label_width, line_height, "Transfer", ln=0)

        # ☐ Resignation
        x_col2 = self.get_x()
        self.rect(x_col2, y_row1 + 1.5, box_size, box_size)
        draw_check_if(leave_type.lower() == "resignation", x_col2, y_row1 + 1.5)
        self.set_x(x_col2 + box_size + box_spacing)
        self.cell(label_width, line_height, "Resignation", ln=0)

        # ☐ Other Mode of Separation
        x_col3 = self.get_x()
        self.rect(x_col3, y_row1 + 1.5, box_size, box_size)
        draw_check_if(leave_type.lower() == "other", x_col3, y_row1 + 1.5)
        self.set_x(x_col3 + box_size + box_spacing)
        text_x_start = self.get_x()
        self.cell(0, line_height, "Other Mode of Separation", ln=1)

        # === SECOND ROW ===
        y_row2 = self.get_y()

        # ☐ Retirement
        self.set_xy(x_col1, y_row2)
        self.rect(x_col1, y_row2 + 1.5, box_size, box_size)
        draw_check_if(leave_type.lower() == "retirement", x_col1, y_row2 + 1.5)
        self.set_x(x_col1 + box_size + box_spacing)
        self.cell(label_width, line_height, "Retirement", ln=0)

        # ☐ Leave
        self.set_x(x_col2)
        self.rect(x_col2, y_row2 + 1.5, box_size, box_size)
        draw_check_if(leave_type.lower() == "leave", x_col2, y_row2 + 1.5)
        self.set_x(x_col2 + box_size + box_spacing)
        self.cell(label_width, line_height, "Leave", ln=0)

      # --- Please specify (handles "Other") with underline ---
        self.set_xy(text_x_start, y_row2)
        self.set_font('Arial', '', 10)

        label_text = "Please specify: "
        if leave_type.lower() == "other" and other_text:
            data_text = other_text
        else:
            data_text = ""

        # Print the label + data
        full_text = label_text + data_text
        self.cell(0, line_height, full_text, ln=1)

        # Draw underline right under the data
        underline_x_start = text_x_start + self.get_string_width(label_text)
        underline_y = self.get_y() - line_height + 4

    
        desired_width = 44  # in mm, adjust as you like
        self.line(underline_x_start, underline_y,
                underline_x_start + desired_width, underline_y)

        # Leave one blank line
        self.cell(0, line_height, "", ln=1)

            # --- Effectivity/Inclusive Period (from ClearanceForm) ---
        x_effectivity = x_municipality
        y_effectivity = self.get_y()
        self.set_xy(x_effectivity, y_effectivity)
        self.set_font('Arial', '', 10)

        label = "Effectivity/Inclusive Period: "
        self.cell(self.get_string_width(label), line_height, label, border=0)

        # --- Build the effectivity text ---
        effectivity_parts = []

        if clearance.date_from:
            effectivity_parts.append(clearance.date_from.strftime('%B %d, %Y'))

        if clearance.date_to:
            if clearance.date_from:
                effectivity_parts.append("to " + clearance.date_to.strftime('%B %d, %Y'))
            else:
                effectivity_parts.append(clearance.date_to.strftime('%B %d, %Y'))

        effectivity_text = " ".join(effectivity_parts) if effectivity_parts else "________________________"

        # --- Print the text with underline ---
        date_width = 120  # controls the underline length
        self.cell(date_width, line_height, effectivity_text, border="B", ln=1, align="L")





        # === Setup box size and position ===
        new_box_height = line_height * 5  # total height = 5 rows
        column_width = (page_width - left_margin * 2) / 2

        y_new_box = self.get_y() + line_height  # ⬅️ Shifted 1 line (5mm) downward

        # === Draw the two-column bordered box ===
        self.set_xy(left_margin, y_new_box)

        # Draw full rectangle border first
        box_total_width = column_width * 2
        self.rect(left_margin, y_new_box, box_total_width, new_box_height)

        # Draw vertical dividing line to make 2 columns
        self.line(left_margin + column_width, y_new_box, left_margin + column_width, y_new_box + new_box_height)

        # === INNER CONTENT starts here ===
        self.set_font('Arial', '', 10)
        padding = 2  # left padding inside each column

        base_y = y_new_box  # <-- use updated base Y

        x_left_text = left_margin + padding
        label = "Office of Assignment: "

        # Draw label
        self.set_xy(x_left_text, base_y + line_height * 1 - 3)  # ⬅ moved up 3
        self.set_font("Arial", "", 9)
        self.cell(self.get_string_width(label), line_height, label, border=0)

        # Value position (right after label)
        self.set_font("Arial", "", 8)
        value_x = self.get_x()
        value_y = base_y + line_height * 1 - 3  # ⬅ moved up 3
        value_width = column_width - (value_x - x_left_text) - padding

        # Print wrapped value (multi_cell automatically wraps)
        self.set_xy(value_x, value_y)
        self.multi_cell(value_width, line_height, office_assignment, border=0)

        line_count = int((self.get_y() - value_y) / line_height)
        underline_y = value_y + line_height * line_count
        self.line(value_x + 2, underline_y, value_x + value_width - 2, underline_y)

# Position
        # --- Position / SG / STEP ---
        x_left_text = left_margin + padding
        label = "Position/SG/STEP: "

        # Draw label
        self.set_xy(x_left_text, base_y + line_height * 3 - 3)  # moved up 3
        self.set_font("Arial", "", 9)
        self.cell(self.get_string_width(label), line_height, label, border=0)

        # Value position (right after label)
        self.set_font("Arial", "", 8)
        value_x = self.get_x()
        value_y = base_y + line_height * 3 - 3  # moved up 3
        value_width = column_width - (value_x - x_left_text) - padding

        # Format the value string (position + SG + Step)
        position_text = f"{position} / SG {salary_grade} / Step {step}"

        # Print wrapped value
        self.set_xy(value_x, value_y)
        self.multi_cell(value_width, line_height, position_text, border=0)

        # Underline (just below last line, raised by 2)
                # Underline (just below last line, raised by 2)
        line_count = int((self.get_y() - value_y) / line_height)
        underline_y = value_y + line_height * line_count
        self.line(value_x + 2, underline_y, value_x + value_width - 2, underline_y)

        # === RIGHT COLUMN CONTENT ===
        x_right_text = left_margin + column_width + padding

    # Employee Name
        # Employee Name (centered)
        self.set_xy(x_right_text, base_y + line_height * 2)
        self.set_font('Arial', '', 9)
        self.cell(column_width - 2 * padding, line_height, f"{name}", border=0, align='C')
        # Draw line under the text, 2 units lower, 20 units shorter, shifted 10 units right
        self.line(x_right_text + 10, base_y + line_height * 2 + 5, x_right_text + column_width - 2 * padding - 10, base_y + line_height * 2 + 5)

        # Name and Signature Label
        self.set_xy(x_right_text, base_y + line_height * 3)
        self.set_font('Arial', '', 10)
        self.cell(column_width - 2 * padding, line_height, "Name and Signature of Employee", border=0, align='C')

        # Move cursor below the box for next content
        self.set_y(y_new_box + new_box_height)

        #row 4 cell title
        self.set_x(left_margin)
        self.set_font('Arial', 'B', 10)
        self.cell(small_cell_width, line_height, 'II', border=1)
        self.cell(usable_width, line_height, 'CLEARANCE FROM WORK-RELATED ACCOUNTABILITIES ', border=1, ln=True)

 #row5 cell 
             # === Row 5: Certification with signature lines ===
        row5_height = line_height * 5  # ~25mm tall
        row5_width = total_width
        y_row5 = self.get_y()

        # Draw bordered box
        self.set_xy(left_margin, y_row5)
        self.cell(row5_width, row5_height, "", border=1, ln=1)

        # --- Certification text (centered once at top of box) ---
        row5_text = (
            "We hereby certify that this applicant is cleared of the "
            "work-related accountabilities from this Unit/Office/Dept."
        )
        self.set_font("Arial", "", 10)
        text_w = row5_width - 20
        self.set_xy(left_margin + 10, y_row5 + 5)  # fixed position inside box
        self.multi_cell(text_w, line_height, row5_text, border=0, align="C")

        # --- Signature section (aligned at bottom of box) ---
        sig_y = y_row5 + row5_height - 12 + 2
        # Immediate Supervisor
        self.set_xy(left_margin + 20, sig_y)
        self.cell(70, line_height, "____________________________________", align="C")
        self.set_xy(left_margin + 20, sig_y + 5)
        self.cell(70, line_height, "Immediate Supervisor", align="C")

        # Head of Office line and label
        self.set_xy(left_margin + 120, sig_y)
        self.cell(70, line_height, "____________________________________", align="C")
        self.set_xy(left_margin + 120, sig_y + 5)
        self.cell(70, line_height, "Head of Office", align="C")

        # Head signature (use passed parameter!)
       # Head signature (use passed parameter!)
        if head_signature:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_sig:
                tmp_sig.write(head_signature)
                tmp_sig.flush()
                sig_path = tmp_sig.name

            sig_w = 60
            sig_h = 30
            sig_x = left_margin + 120 + (70 - sig_w) / 2
            sig_y_sig = sig_y - sig_h + 15  # ↓ lower by 15 mm
            self.image(sig_path, x=sig_x, y=sig_y_sig, w=sig_w, h=sig_h)
            os.unlink(sig_path)


        # Head name (use original baseline)
        if head_of_office and head_of_office.strip("_").strip():
            self.set_font("Arial", "B", 10)
            self.set_xy(left_margin + 120, sig_y - 1)  # slight adjustment
            self.cell(70, line_height, head_of_office, align="C")





            
        # Add padding inside the box
        self.set_xy(left_margin + 2, y_row5 + 1.5)
        self.set_font('Arial', '', 10)
        self.multi_cell(row5_width - 4, line_height, border=0, align='J')

        # Move Y down after the box
        self.set_y(y_row5 + row5_height)

        #row 6 cell
        self.set_x(left_margin)
        self.set_font('Arial', 'B', 10)
        self.cell(small_cell_width, line_height, 'III', border=1)
        self.cell(usable_width, line_height, 'CLEARANCE FROM MONEY AND PROPRTY ACCOUNTABLITIES', border=1, ln=True)

        #ROW 7 CELL
        self.set_font('Arial', 'B', 10)

        # === Define column widths ===
        col1_w = 95
        col2_w = 15
        col3_w = 15
        col4_w = 50
        col5_w = 0  # Let FPDF compute remaining width automatically (optional: set manually if needed)

        header_height = 10  # Use 10mm height per cell (for consistent height)

        y_header = self.get_y()
        x_start = self.get_x()

        # Column 1: Name of Unit/Office/Department
        self.set_xy(x_start, y_header)
        self.multi_cell(col1_w, header_height, "Name of Unit/Office/Department", border=1, align='C')
        
        # Column 2: Cleared
        self.set_xy(x_start + col1_w, y_header)
        self.multi_cell(col2_w, header_height, "Cleared", border=1, align='C')

               # Column 3: Not Cleared
        self.set_xy(x_start + col1_w + col2_w, y_header)
        self.multi_cell(col3_w, header_height / 2, "Not\nCleared", border=1, align='C')

        # Column 4: Name of Clearing Officer/Official
        self.set_xy(x_start + col1_w + col2_w + col3_w, y_header)
        self.multi_cell(col4_w, header_height / 2, "Name of Clearing\nOfficer/Official", border=1, align='C')

        # Column 5: Signature (adjust remaining width)
        x_col5 = x_start + col1_w + col2_w + col3_w + col4_w
        self.set_xy(x_col5, y_header)
        remaining_width = self.w - x_col5 - self.r_margin
        self.multi_cell(remaining_width, header_height, "Signature", border=1, align='C')

        # Move cursor below the tallest cell
        self.set_y(y_header + header_height)

        self.set_font('Arial', '', 10)

        # Compute total width (same as full table width)
        total_width = col1_w + col2_w + col3_w + col4_w + remaining_width
        label_height = 7  # thinner height than headers

        # Position below previous row
        y_label = self.get_y()
        self.set_xy(x_start, y_label)

        # GRAY
        self.set_fill_color(179, 179, 179)  # RGB for #b3b3b3


        self.cell(total_width, label_height, "1.   Administration Sector", border=1, ln=1, align='L', fill=True)

        # Optional: move cursor after the gray row
        self.set_y(y_label + label_height)

        #table 1

        self.set_font('Arial', '', 10)


        col1_w = 95
        col2_w = 15
        col3_w = 15
        col4_w = 50

        
        x_start = self.get_x()
        y_row = self.get_y()

        self.set_xy(x_start, y_row)
        self.multi_cell(col1_w, 5, "             Supply and Property Procurement and\n     a.     Management Services", border=1, align='L')

        self.set_xy(x_start + col1_w, y_row)
        self.multi_cell(col2_w, 10, "", border=1, align='C')

        self.set_xy(x_start + col1_w + col2_w, y_row)
        self.multi_cell(col3_w, 10, "", border=1, align='C')

        x_col4 = x_start + col1_w + col2_w + col3_w
        self.set_xy(x_col4, y_row)

        self.set_font('Arial', 'B', 10)
        self.cell(col4_w, 5, "FLORDELUZ M. SAMORIN", border='LTR', ln=1, align='C')

        self.set_font('Arial', '', 10)
        self.set_x(x_col4)
        self.cell(col4_w, 5, "MSWDO/GSO Designate", border='LBR', ln=1, align='C')

        x_col5 = x_col4 + col4_w
        remaining_width = self.w - x_col5 - self.r_margin
        self.set_xy(x_col5, y_row)
        self.multi_cell(remaining_width, 10, "", border=1, align='C')

        self.set_y(y_row + 10)

        #table 2
        self.set_font('Arial', '', 10)

        # --- Column Widths ---
        col1_w = 95
        col2_w = 15
        col3_w = 15
        col4_w = 50

        
        x_start = self.get_x()
        y_row = self.get_y()

        self.set_xy(x_start, y_row)
        self.multi_cell(col1_w, 5, "              \n     b.     As to money accountability", border=1, align='L')

        self.set_xy(x_start + col1_w, y_row)
        self.multi_cell(col2_w, 10, "", border=1, align='C')

        self.set_xy(x_start + col1_w + col2_w, y_row)
        self.multi_cell(col3_w, 10, "", border=1, align='C')

        x_col4 = x_start + col1_w + col2_w + col3_w
        self.set_xy(x_col4, y_row)

        self.set_font('Arial', 'B', 10)
        self.cell(col4_w, 5, "FE C. REYES", border='LTR', ln=1, align='C')

        self.set_font('Arial', '', 10)
        self.set_x(x_col4)
        self.cell(col4_w, 5, "Mun. Treasurer", border='LBR', ln=1, align='C')

        x_col5 = x_col4 + col4_w
        remaining_width = self.w - x_col5 - self.r_margin
        self.set_xy(x_col5, y_row)
        self.multi_cell(remaining_width, 10, "", border=1, align='C')

        self.set_y(y_row + 10)


         #table 3
        self.set_font('Arial', '', 10)

        # --- Column Widths ---
        col1_w = 95
        col2_w = 15
        col3_w = 15
        col4_w = 50

        
        x_start = self.get_x()
        y_row = self.get_y()

        self.set_xy(x_start, y_row)
        self.multi_cell(col1_w, 5, "              \n     c.     Human Resource Welfare & Assistance", border=1, align='L')

        self.set_xy(x_start + col1_w, y_row)
        self.multi_cell(col2_w, 10, "", border=1, align='C')

        self.set_xy(x_start + col1_w + col2_w, y_row)
        self.multi_cell(col3_w, 10, "", border=1, align='C')

        x_col4 = x_start + col1_w + col2_w + col3_w
        self.set_xy(x_col4, y_row)

        self.set_font('Arial', 'B', 10)
        self.cell(col4_w, 5, "", border='LTR', ln=1, align='C')

        self.set_font('Arial', '', 10)
        self.set_x(x_col4)
        self.cell(col4_w, 5, "", border='LBR', ln=1, align='C')

        x_col5 = x_col4 + col4_w
        remaining_width = self.w - x_col5 - self.r_margin
        self.set_xy(x_col5, y_row)
        self.multi_cell(remaining_width, 10, "", border=1, align='C')

        self.set_y(y_row + 10)


        #table 4
        self.set_font('Arial', '', 10)

        # --- Column Widths ---
        col1_w = 95
        col2_w = 15
        col3_w = 15
        col4_w = 50
        
        x_start = self.get_x()
        y_row = self.get_y()

        self.set_xy(x_start, y_row)
        self.multi_cell(col1_w, 5, "              \n             c.1. As to Statement of Assets and Liabilities", border=1, align='L')

        self.set_xy(x_start + col1_w, y_row)
        self.multi_cell(col2_w, 10, "", border=1, align='C')

        self.set_xy(x_start + col1_w + col2_w, y_row)
        self.multi_cell(col3_w, 10, "", border=1, align='C')

        x_col4 = x_start + col1_w + col2_w + col3_w
        self.set_xy(x_col4, y_row)

        self.set_font('Arial', 'B', 10)
        self.cell(col4_w, 5, "LLOYD MORGAN O.PERLEZ", border='LTR', ln=1, align='C')
      
        self.set_font('Arial', '', 10)
        self.set_x(x_col4)
        self.cell(col4_w, 5, "MGDH I (HRMO)", border='LBR', ln=1, align='C')

        x_col5 = x_col4 + col4_w
        remaining_width = self.w - x_col5 - self.r_margin
        self.set_xy(x_col5, y_row)
        self.multi_cell(remaining_width, 10, "", border=1, align='C')

        self.set_y(y_row + 10)


         #table 5
        self.set_font('Arial', '', 10)

        # --- Column Widths ---
        col1_w = 95
        col2_w = 15
        col3_w = 15
        col4_w = 50

        x_start = self.get_x()
        y_row = self.get_y()

        full_text = "             c.1. As to leave without pay (LAWOP) "
        text_width = self.get_string_width(full_text)

        # === Draw the full cell border first ===
        self.set_xy(x_start, y_row)
        self.cell(col1_w, 10, "", border='1')  # Background with border

        # === Overwriting text area below by 1mm ===
        self.set_xy(x_start, y_row + 1)
        self.set_font('Arial', '', 10)
        self.cell(text_width, 10, full_text, border='', ln=0)  # No border — draw manually

        # === Draw bold part ===
        self.set_font('Arial', 'B', 10)
        self.cell(col1_w - text_width, 10, "NO LAWOP", border='', ln=1)

        # === Draw manual left border to fix the visual gap ===
        self.line(x_start, y_row, x_start, y_row + 10)  # Full-height left border

        # === Column 2: Cleared ===
        self.set_font('Arial', '', 10)
        self.set_xy(x_start + col1_w, y_row)
        self.multi_cell(col2_w, 10, "", border=1, align='C')

        # === Column 3: Not Cleared ===
        self.set_xy(x_start + col1_w + col2_w, y_row)
        self.multi_cell(col3_w, 10, "", border=1, align='C')

        # === Column 4: Officer (bold + normal) ===
        x_col4 = x_start + col1_w + col2_w + col3_w
        self.set_xy(x_col4, y_row)
        self.set_font('Arial', 'B', 10)
        self.cell(col4_w, 5, "LLOYD MORGAN O.PERLEZ", border='LTR', ln=1, align='C')

        self.set_font('Arial', '', 10)
        self.set_x(x_col4)
        self.cell(col4_w, 5, "MGDH I (HRMO)", border='LBR', ln=1, align='C')

        # === Column 5: Signature ===
        x_col5 = x_col4 + col4_w
        remaining_width = self.w - x_col5 - self.r_margin
        self.set_xy(x_col5, y_row)
        self.multi_cell(remaining_width, 10, "", border=1, align='C')

        # === Move cursor below the row ===
        self.set_y(y_row + 10)


        #row 9 cell title
        self.set_x(left_margin)
        self.set_font('Arial', 'B', 10)
        self.cell(small_cell_width, line_height, 'IV', border=1)
        self.cell(usable_width, line_height, 'CERTIFICATION OF NO PENDING ADMINISTRATIVE CASE: ', border=1, ln=True)

        #table 6
        self.set_font('Arial', '', 10)

        # --- Column Widths ---
        col1_w = 95
        col2_w = 15
        col3_w = 15
        col4_w = 50
        
        x_start = self.get_x()
        y_row = self.get_y()

      # Draw the bordered container first
        self.set_xy(x_start, y_row)
        self.cell(col1_w, 10, "", border=1)

        # Indentation for text
        indent = x_start + 2  # adjust as needed for padding

        # Line 1
        self.set_font('Arial', '', 8)
        self.set_xy(indent, y_row + 0.5)
        self.cell(col1_w - 4, 2.8, "              As to pending admin case and previous", ln=True)

        # Line 2
        self.set_xy(indent, y_row + 3)
        self.cell(col1_w - 4, 2.8, "              penalties/dismissal from service in admin case and/or", ln=True)

        # Line 3: "a." in size 10, rest in size 5
        self.set_font('Arial', '', 10)
        self.set_xy(indent, y_row + 5.5)
        self.cell(5, 3, "   a.", ln=False)

        self.set_font('Arial', '', 8)
        self.set_xy(indent + 5, y_row + 5.9)
        self.cell(col1_w - 9, 2.8, "       Accountability by virtue of fine/forfeiture", ln=True)


        self.set_xy(x_start + col1_w, y_row)
        self.multi_cell(col2_w, 10, "", border=1, align='C')

        self.set_xy(x_start + col1_w + col2_w, y_row)
        self.multi_cell(col3_w, 10, "", border=1, align='C')

        x_col4 = x_start + col1_w + col2_w + col3_w
        self.set_xy(x_col4, y_row)

        self.set_font('Arial', 'B', 10)
        self.cell(col4_w, 5, "LLOYD MORGAN O.PERLEZ", border='LTR', ln=1, align='C')
      
        self.set_font('Arial', '', 10)
        self.set_x(x_col4)
        self.cell(col4_w, 5, "MGDH I (HRMO)", border='LBR', ln=1, align='C')

        x_col5 = x_col4 + col4_w
        remaining_width = self.w - x_col5 - self.r_margin
        self.set_xy(x_col5, y_row)
        self.multi_cell(remaining_width, 10, "", border=1, align='C')

        self.set_y(y_row + 10)

        self.set_font('Arial', '', 10)
        cell_width = 196
        line_height = 6
        total_height = line_height * 2  # 2 lines total

        # Step 1: Draw the container box first
        x = self.get_x()
        y = self.get_y()
        self.rect(x, y, cell_width, total_height)  # full box around both lines

        # Offset for shifting contents
        shift = 25

        # Step 2: Line 1 — checkbox + text
        self.rect(x + shift + 2, y + 1.5, 3, 3)  # small square (shifted)
        self.set_xy(x + shift + 8, y)            # text aligned with box
        self.cell(0, line_height, "with pending administrative case", ln=1)

        # Step 3: Line 2 — checkbox + text
        self.rect(x + shift + 2, y + line_height + 1.5, 3, 3)  # second square (shifted)
        self.set_xy(x + shift + 8, y + line_height)
        self.cell(0, line_height, "with ongoing investigation (no formal charge yet)", ln=1)

        # Move Y cursor below the full cell
        self.set_y(y + total_height)



        #row 10 cell title
        self.set_x(left_margin)
        self.set_font('Arial', 'B', 10)
        self.cell(small_cell_width, line_height, 'V', border=1)
        self.cell(usable_width, line_height, 'C E R T I F I C A T I O N ', border=1, ln=True)


        
        #cell last
        self.set_font('Arial', '', 10)
        cell_width = 196
        line_height = 5

        # Draw the empty cell with border (total height: 7 lines × 5mm = 35mm)
        x_start = self.get_x()
        y_start = self.get_y()
       # Total height still 35mm (7 lines)
        self.rect(x_start, y_start, cell_width, line_height * 7)

        # Start writing from line 5 instead of 7
        self.set_xy(x_start, y_start + line_height * 4)

        # Line 5: Bold Name
        self.set_font('Arial', 'B', 10)
        self.cell(cell_width, line_height, "DWIGHT C. KAMPITAN, M.D.", ln=1, align='C')
          # ✅ Insert Mayor's signature
        mayor_user = (
            Users.query
            .join(Employee)
            .join(PermanentEmployeeDetails)
            .join(Position)
            .filter(Position.title == 'MUNICIPAL MAYOR')
            .first()
        )

        if mayor_user:
             sig_record = UserSignature.query.filter_by(user_id=mayor_user.id).first()
        if sig_record and sig_record.signature:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_sig:
                tmp_sig.write(sig_record.signature)
                tmp_sig.flush()
                sig_path = tmp_sig.name

            scale = 2.0
            sig_w = 31 * scale
            sig_h = 13 * scale
            sig_x = (self.w - sig_w) / 2 + 2
            sig_y = self.get_y() - 18
            self.image(sig_path, x=sig_x, y=sig_y, w=sig_w, h=sig_h)


        # Line 6: Title
        self.set_font('Arial', '', 10)
        self.set_x(x_start)
        self.cell(cell_width, line_height, "Municipal Mayor", ln=1, align='C')



#REPORT PDF
# TRAVEL HISTORY 
def clean_text(text):
    """Replace unsupported Unicode characters with Latin-1 equivalents."""
    if not text:
        return ''
    return (
        text.replace('—', '-')    # em dash to hyphen
            .replace('–', '-')    # en dash to hyphen
            .replace('“', '"')    # left quote to straight quote
            .replace('”', '"')    # right quote to straight quote
            .replace('’', "'")    # right single quote to apostrophe
            .replace('‘', "'")    # left single quote to apostrophe
    )

class TravelLogPDF(FPDF):
    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5  # center of A4 landscape page
        logo_width = 18
        gap_from_text = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap_from_text - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap_from_text, y=8, w=logo_width)

        # Text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(2)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'TRAVEL RECORD', ln=True, align='C')
        self.ln(5)

        # Table header
        self.set_fill_color(197, 224, 180)
        self.set_font('Arial', 'B', 9)
        headers = ['Employee Name', 'Destination', 'Purpose', 'Date of Departure', 'Log Date', 'Tracking ID', 'Status']
        col_widths = [50, 40, 60, 40, 40, 25, 25]  # Adjust widths to fit A4
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_log_row(self, log):
        self.set_font('Arial', '', 8)
        col_widths = [50, 40, 60, 40, 40, 25, 25]
        line_height = 4

        # Prepare data
        data = [
            clean_text(f"{log['last_name']}, {log['first_name']} {log['middle_name'][0] + '.' if log.get('middle_name') else ''}"),
            clean_text(log['destination']),
            clean_text(log['purpose']),
            clean_text(log['date_departure'].strftime('%B %d, %Y %I:%M %p') if log.get('date_departure') else '-'),
            clean_text(log['log_date'].strftime('%B %d, %Y %I:%M %p') if log.get('log_date') else '-'),
            clean_text(log['tracking_id']),
            clean_text(log['status']),
        ]

        # Determine max lines for row
        max_lines = 1
        for i in range(len(data)):
            num_lines = self.get_string_width(data[i]) / (col_widths[i] - 2)
            estimated_lines = int(num_lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines
        x_start = self.get_x()
        y_start = self.get_y()

        for i in range(len(data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)





#JOB HIRING 
#UNDER REVIEW 
class UnderReviewPDF(FPDF):
    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5

        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(2)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'UNDER REVIEW APPLICANTS', ln=True, align='C')
        self.ln(5)

        # Table header
        self.set_fill_color(197, 224, 180)
        self.set_font('Arial', 'B', 9)
        headers = [
            'Position', 'Department', 'Applicant Name', 'Email', 'Phone', 
            'Job Type', 'Score', 'Status',
        ]
        # Adjusted column widths to fit A4 landscape
        col_widths = [40, 40, 50, 40, 30, 30, 20, 25]

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()
        self.col_widths = col_widths

    def add_applicant_row(self, applicant):
        self.set_font('Arial', '', 8)
        line_height = 4
        col_widths = self.col_widths

        data = [
            applicant.job_posting.title if applicant.job_posting else 'N/A',
            applicant.job_posting.department.name if applicant.job_posting and applicant.job_posting.department else 'N/A',
            f"{applicant.first_name} {applicant.last_name}",
            applicant.email,
            applicant.phone if applicant.phone else 'N/A',
            applicant.job_posting.job_position_type if applicant.job_posting else 'N/A',
            str(applicant.application_score) if applicant.application_score is not None else 'N/A',
            applicant.status,
        ]

         # Calculate max lines in row
        max_lines = 1
        for i in range(len(data)):
            lines = self.get_string_width(str(data[i])) / (col_widths[i] - 2)
            estimated_lines = int(lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines

        # --- Page break check ---
        if self.get_y() + row_height > self.h - 20:
            self.add_page()

        x_start = self.get_x()
        y_start = self.get_y()

        for i in range(len(data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)


# interview
class InterviewApplicantPDF(FPDF):
    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header Text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(2)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'INTERVIEW APPLICANTS', ln=True, align='C')
        self.ln(5)

        # Table headers (without Resume)
        self.set_fill_color(197, 224, 180)
        self.set_font('Arial', 'B', 9)
        headers = ['Position', 'Department', 'Applicant Name', 'Email', 'Phone',
                   'Role', 'Interview Date/Time', 'Method', 'Interview Status']
        col_widths = [28, 28, 40, 40, 25, 25, 33, 25, 33]  # adjusted to fit A4 without Resume
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_applicant_row(self, applicant):
        self.set_font('Arial', '', 8)
        line_height = 4
        col_widths = self.col_widths

        interview = applicant.interviews[0] if applicant.interviews else None

        date_time = (
            f"{interview.scheduled_date.strftime('%b %d, %Y')} - {interview.scheduled_time.strftime('%I:%M %p')}"
            if interview and getattr(interview, 'scheduled_date', None) and getattr(interview, 'scheduled_time', None)
            else "Not Set"
        )

        status = getattr(interview, 'status', 'No Interview') if interview else 'No Interview'

        data = [
            applicant.job_posting.title if applicant.job_posting else 'N/A',
            applicant.job_posting.department.name if applicant.job_posting and applicant.job_posting.department else 'N/A',
            f"{applicant.first_name} {applicant.last_name}",
            getattr(applicant, 'email', 'N/A'),
            getattr(applicant, 'phone', 'N/A'),
            applicant.job_posting.job_position_type if applicant.job_posting else 'N/A',
            date_time,
            getattr(interview, 'method', 'N/A') if interview else 'N/A',
            status
        ]

        # Calculate row height
        max_lines = 1
        for i in range(len(data)):
            lines = self.get_string_width(str(data[i])) / (col_widths[i] - 2)
            estimated_lines = int(lines) + 1
            max_lines = max(max_lines, estimated_lines)
        row_height = line_height * max_lines

         # --- Page break check ---
        if self.get_y() + row_height > self.h - 20:
            self.add_page()


        x_start = self.get_x()
        y_start = self.get_y()

        for i in range(len(data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, str(data[i]), border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)



#ACCEPTED APPLICANT 
class AcceptedApplicantPDF(FPDF):
    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header Text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(2)
        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'ACCEPTED/HIRED APPLICANTS', ln=True, align='C')
        self.ln(5)

        # Table headers
        self.set_fill_color(197, 224, 180)
        self.set_font('Arial', 'B', 9)
        headers = ['Position', 'Department', 'Applicant Name', 'Email', 'Phone', 'Role',
                   'Interview Date/Time', 'Method', 'Interviewer', 'Interview Result', 'Approval Notes']

        col_widths = [25, 25, 30, 30, 20, 20, 33, 20, 20, 27, 30]  # adjusted to fit A4 landscape
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_applicant_row(self, applicant):
        self.set_font('Arial', '', 8)
        line_height = 4
        col_widths = self.col_widths

        interview = applicant.interviews[0] if applicant.interviews else None

        date_time = (
            f"{interview.scheduled_date.strftime('%b %d, %Y')} - {interview.scheduled_time.strftime('%I:%M %p')}"
            if interview and getattr(interview, 'scheduled_date', None) and getattr(interview, 'scheduled_time', None)
            else "Not Set"
        )

        result = getattr(interview, 'result', 'No Result') if interview else 'No Result'
        approval_notes = getattr(interview, 'approval_notes', 'N/A') if interview else 'N/A'

        data = [
            applicant.job_posting.title if applicant.job_posting else 'N/A',
            applicant.job_posting.department.name if applicant.job_posting and applicant.job_posting.department else 'N/A',
            f"{applicant.first_name} {applicant.last_name}",
            getattr(applicant, 'email', 'N/A'),
            getattr(applicant, 'phone', 'N/A'),
            applicant.job_posting.job_position_type if applicant.job_posting else 'N/A',
            date_time,
            getattr(interview, 'method', 'N/A') if interview else 'N/A',
            getattr(interview, 'interviewer', 'N/A') if interview else 'N/A',
            result,
            approval_notes
        ]

        # Calculate dynamic row height
        max_lines = 1
        for i in range(len(data)):
            lines = self.get_string_width(str(data[i])) / (col_widths[i] - 2)
            estimated_lines = int(lines) + 1
            max_lines = max(max_lines, estimated_lines)
        row_height = line_height * max_lines

         # --- Page break check ---
        if self.get_y() + row_height > self.h - 20:
            self.add_page()


        x_start = self.get_x()
        y_start = self.get_y()

        for i in range(len(data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, str(data[i]), border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)

#REJECTED APPLICANT 
class RejectedApplicantPDF(FPDF):
    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header Text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(2)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'REJECTED APPLICANTS', ln=True, align='C')
        self.ln(5)

        # Table Headers
        self.set_fill_color(255, 204, 204)  # light red
        self.set_font('Arial', 'B', 9)
        headers = [
            'Position', 'Department', 'Applicant Name', 'Email', 'Phone',
            'Role', 'Interview Date/Time', 'Method', 'Interviewer',
            'Interview Result', 'Rejection Reason'
        ]
        # Column widths (must match number of headers)
        col_widths = [22, 25, 28, 28, 20, 20, 33, 26, 25, 27, 30]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_applicant_row(self, applicant):
        self.set_font('Arial', '', 8)
        line_height = 4
        col_widths = self.col_widths

        interview = applicant.interviews[0] if applicant.interviews else None
        date_time = (
            f"{interview.scheduled_date.strftime('%b %d, %Y')} - {interview.scheduled_time.strftime('%I:%M %p')}"
            if interview and getattr(interview, 'scheduled_date', None) and getattr(interview, 'scheduled_time', None)
            else "Not Set"
        )
        result = interview.result if interview and getattr(interview, 'result', None) else 'No Result'
        rejection_reason = interview.rejection_reason if interview and getattr(interview, 'rejection_reason', None) else 'N/A'

        data = [
            applicant.job_posting.title if applicant.job_posting else 'N/A',
            applicant.job_posting.department.name if applicant.job_posting and applicant.job_posting.department else 'N/A',
            f"{applicant.first_name} {applicant.last_name}",
            applicant.email,
            applicant.phone if applicant.phone else 'N/A',
            applicant.job_posting.job_position_type if applicant.job_posting else 'N/A',
            date_time,
            interview.method if interview and getattr(interview, 'method', None) else 'N/A',
            interview.interviewer if interview and getattr(interview, 'interviewer', None) else 'N/A',
            result,
            rejection_reason
        ]

        # --- Compute max number of lines in the row ---
        max_lines = 1
        cell_lines = []
        for i, text in enumerate(data):
            lines = self.multi_cell(col_widths[i], line_height, text, border=0, split_only=True)
            cell_lines.append(lines)
            max_lines = max(max_lines, len(lines))

        row_height = line_height * max_lines

         # --- Page break check ---
        if self.get_y() + row_height > self.h - 20:
            self.add_page()

        x_start = self.get_x()
        y_start = self.get_y()

        # --- Draw each cell individually but with same row height ---
        for i, text in enumerate(data):
            self.set_xy(x_start, y_start)
            # Draw border manually
            self.rect(x_start, y_start, col_widths[i], row_height)
            # Print text inside cell
            self.multi_cell(col_widths[i], line_height, text)
            x_start += col_widths[i]

        # Move Y to the end of the row
        self.set_y(y_start + row_height)


#EMPLOYEE PER HRAD REPORT 
#CASUAL PER  DEPARTMENT 
class HeadCasualEmployeePDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header Text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(2)

        # Head Department line
        self.set_font('Arial', 'B', 11)
        self.cell(0, 6, f'Head of {self.department_name}', ln=True, align='C')
        self.ln(2)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'LIST OF CASUAL EMPLOYEES', ln=True, align='C')
        self.ln(5)

        # Table headers
        self.set_fill_color(222, 234, 246)  # light blue fill
        self.set_font('Arial', 'B', 9)
        headers = ['#', 'Name', 'Extension', 'Position', 'Equivalent Salary', 'Daily Wage', 'Contract Start', 'Contract End']
        col_widths = [20, 50, 20, 60, 35, 30, 30, 30]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_employee_row(self, index, emp):
        self.set_font('Arial', '', 8)
        line_height = 4
        col_widths = self.col_widths

        data = [
            str(index),
            f"{emp.last_name}, {emp.first_name} {emp.middle_name[0] + '.' if emp.middle_name else ''}",
            emp.casual_details.name_extension or 'N/A',
            emp.casual_details.position.title if emp.casual_details and emp.casual_details.position else 'N/A',
            str(emp.casual_details.equivalent_salary or ''),
            str(emp.casual_details.daily_wage or ''),
            emp.casual_details.contract_start.strftime('%m/%d/%Y') if emp.casual_details.contract_start else '',
            emp.casual_details.contract_end.strftime('%m/%d/%Y') if emp.casual_details.contract_end else '',
        ]


        max_lines = 1
        for i in range(len(data)):
            lines = self.get_string_width(data[i]) / (col_widths[i] - 2)
            estimated_lines = int(lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines
        x_start = self.get_x()
        y_start = self.get_y()

        for i in range(len(data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)
  


  

#JO PER DEPARTMENT 
class HeadJobOrderEmployeePDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header Text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(2)

        # Head Department line
        self.set_font('Arial', 'B', 11)
        self.cell(0, 6, f'Head of {self.department_name}', ln=True, align='C')
        self.ln(2)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'LIST OF JOB ORDER EMPLOYEES', ln=True, align='C')
        self.ln(5)

        # Table headers
        self.set_fill_color(222, 234, 246)  # light blue fill
        self.set_font('Arial', 'B', 9)
        headers = ['#', 'Name', 'Department', 'Employment Status', 'Position Title', 'Date Hired']
        col_widths = [10, 60, 60, 40, 60, 40]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_employee_row(self, index, emp):
        self.set_font('Arial', '', 8)
        line_height = 4
        col_widths = self.col_widths

        data = [
            str(index),
            f"{emp.last_name}, {emp.first_name} {emp.middle_name[0] + '.' if emp.middle_name else ''}",
            emp.department.name if emp.department else 'N/A',
            emp.employment_status or 'N/A',
            emp.job_order_details.position_title if emp.job_order_details else 'N/A',
            emp.job_order_details.date_hired.strftime('%m/%d/%Y') if emp.job_order_details and emp.job_order_details.date_hired else 'N/A'
        ]


        max_lines = 1
        for i in range(len(data)):
            lines = self.get_string_width(data[i]) / (col_widths[i] - 2)
            estimated_lines = int(lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines
        x_start = self.get_x()
        y_start = self.get_y()

        for i in range(len(data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)


#PERMANENT  PER DEPARTMENT 
class HeadPermanentEmployeePDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header Text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(2)

        self.set_font('Arial', 'B', 11)
        self.cell(0, 6, f'Head of {self.department_name}', ln=True, align='C')
        self.ln(2)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'LIST OF PERMANENT EMPLOYEES', ln=True, align='C')
        self.ln(5)

        # Table headers
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)
        headers = [
            '#', 'Department', 'Item No.', 'Position', 'Step', 'Level',
            'Name', 'Sex', 'TIN / UMID', 'Date of Appt.', 'Status'
        ]
        col_widths = [7, 45, 20, 50, 12, 12, 45, 15, 30, 25, 10]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_employee_row(self, index, emp):
        self.set_font('Arial', '', 7)
        line_height = 4
        col_widths = self.col_widths

        data = [
            str(index),
            emp.department.name if emp.department else 'N/A',
            emp.permanent_details.item_number or '',
            emp.permanent_details.position.title if emp.permanent_details and emp.permanent_details.position else 'N/A',
            str(emp.permanent_details.step or ''),
            str(emp.permanent_details.level or ''),
            f"{emp.last_name}, {emp.first_name} {emp.middle_name[0] + '.' if emp.middle_name else ''}",
            emp.permanent_details.sex or '',
            f"{emp.permanent_details.tin or ''} / {emp.permanent_details.umid_no or ''}",
            emp.permanent_details.date_original_appointment.strftime('%Y-%m-%d') if emp.permanent_details.date_original_appointment else '',
            emp.status or '',
        ]


        max_lines = 1
        for i in range(len(data)):
            lines = self.get_string_width(data[i]) / (col_widths[i] - 2)
            estimated_lines = int(lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines
        x_start = self.get_x()
        y_start = self.get_y()

        for i in range(len(data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)






#LEAVE REPORT 
#LEAVE APPLCIATION REPORT 

class HeadLeaveApplicationPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')

        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap, y=8, w=logo_width)

        # Title header
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'LEAVE APPLICATION SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

        # Reset font para hindi maapektuhan ang body
        self.set_font('Arial', '', 7)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 5,
                  f" {self.department_name} | Page {self.page_no()} of {{nb}}",
                  align='C')
        
    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit', 'Position Title', 'Full Name',
            'Date Requested', 'Type of Leave',
            'Credits Remaining', 'Paid Days',
            'Status', 'Current Stage', 'Remarks'
        ]

        # 297mm width (A4 Landscape) - 20mm margins = 277mm usable
        self.col_widths = [32, 28, 32, 22, 32, 30, 30, 24, 24, 23]

        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

        self.set_font('Arial', '', 7)


    def add_leave_row(self, index, permit):
        line_height = 4
        col_widths = self.col_widths

        # Format employee name
        first_name = permit.get('first_name', '').strip()
        middle_name = permit.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        last_name = permit.get('last_name', '').strip()
        name = f"{last_name}, {first_name} {middle_initial}".strip()

            # --- Credits Remaining Logic ---
        credits_remaining = "N/A"
        try:
            cb = permit['employee']['credit_balance']
            leave_type = permit['leave_detail']['leave_type'].lower()

            if "vacation" in leave_type:
                credits_remaining = f"{cb.get('vacation_remaining', 0)} Vacation"
            elif "sick" in leave_type:
                credits_remaining = f"{cb.get('sick_remaining', 0)} Sick"
        except Exception:
            pass

        # --- Paid Days Logic ---
        paid_days = "N/A"
        try:
            leave = permit['leave_detail']
            leave_type = leave['leave_type'].lower()

            if "vacation" in leave_type or "sick" in leave_type:
                if leave.get('paid_days') is not None:
                    paid = int(leave['paid_days'])
                    working = int(leave.get('working_days', 0))
                    if paid > 0:
                        unpaid = working - paid
                        paid_days = f"{paid} Paid"
                        if unpaid > 0:
                            paid_days += f", {unpaid} Unpaid"
                    else:
                        paid_days = "Pending Approval"
                else:
                    # Fallback estimate
                    cb = permit['employee']['credit_balance']
                    requested_days = int(leave.get('working_days', 0))
                    if "vacation" in leave_type:
                        paid = min(requested_days, cb.get('vacation_remaining', 0))
                    elif "sick" in leave_type:
                        paid = min(requested_days, cb.get('sick_remaining', 0))
                    else:
                        paid = 0
                    paid_days = f"Est. {paid} day(s)"
            else:
                paid_days = "Not Applicable"
        except Exception:
            pass

        # --- Data row (with new cols) ---
        data = [
            permit.get('department', 'N/A'),
            permit.get('position', 'N/A'),
            name,
            permit.get('date_requested', 'N/A'),
            permit.get('leave_type', 'N/A'),
            credits_remaining,   # ✅ new col
            paid_days,           # ✅ new col
            permit.get('status', '-'),
            permit.get('current_stage', '-'),
            permit.get('remarks', '-')
        ]

        # Color map for Status
        status_color_map = {
            'Approved': (198, 239, 206),
            'Pending': (255, 235, 156),
            'Cancelled': (242, 220, 219),
            'Rejected': (255, 199, 206)
        }
        status = permit.get('status', '-')
        fill_rgb = status_color_map.get(status, None)

        # --- Wrap text per column ---
        wrapped_data = []
        max_lines = 1
        for i, text in enumerate(data):
            words = str(text).split(' ')
            lines, current_line = [], ''
            for word in words:
                if self.get_string_width(current_line + ' ' + word) < col_widths[i] - 2:
                    current_line += (' ' if current_line else '') + word
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)

            wrapped_data.append(lines)
            max_lines = max(max_lines, len(lines))

        row_height = line_height * max_lines

        # --- Check page break ---
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()
            self.set_font('Arial', '', 7)  # reset after header

        x_start = self.get_x()
        y_start = self.get_y()

        # --- Draw row ---
        self.set_font('Arial', '', 7)  # ensure body stays regular
        for i, lines in enumerate(wrapped_data):
            self.set_xy(x_start, y_start)

            # Draw background if Status col
            if i == 7 and fill_rgb:
                self.set_fill_color(*fill_rgb)
                self.rect(x_start, y_start, col_widths[i], row_height, style='DF')
            else:
                self.rect(x_start, y_start, col_widths[i], row_height)

            # Print text inside cell
            text_y = y_start + 1
            for line in lines:
                self.set_xy(x_start + 1, text_y)
                self.cell(col_widths[i] - 2, line_height, line, border=0)
                text_y += line_height

            x_start += col_widths[i]

        # --- Move cursor next row ---
        self.set_y(y_start + row_height)


# REPORT: TRAVEL ORDER
# REPORT: TRAVEL ORDER
class HeadTravelOrderPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'TRAVEL ORDER SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

        # Reset to normal font for table
        self.set_font('Arial', '', 7)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 5,
                  f"{self.department_name} | Page {self.page_no()} of {{nb}}",
                  align='C')

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit', 
            'Position Title', 
            'Full Name', 
            'Date Requested', 
            'Destination', 
            'Status', 
            'Current Stage', 
            'Remarks'
        ]
        col_widths = [35, 30, 35, 25, 50, 20, 30, 45]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

        self.set_font('Arial', '', 7)

    def add_travel_row(self, index, permit):
        line_height = 4
        col_widths = self.col_widths

        # Format name
        first_name = permit.get('first_name', '').strip()
        middle_name = permit.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        last_name = permit.get('last_name', '').strip()
        name = f"{last_name}, {first_name} {middle_initial}".strip()

        data = [
            permit.get('department', 'N/A'),
            permit.get('position', 'N/A'),
            name,
            permit.get('date_requested', 'N/A'),
            permit.get('destination', 'N/A'),
            permit.get('status', 'N/A'),
            permit.get('current_stage', '-'),
            permit.get('remarks', '-')
        ]

        # --- Word-wrap each cell ---
        wrapped_data = []
        max_lines = 1
        for i, text in enumerate(data):
            words = str(text).split(' ')
            lines, current_line = [], ''
            for word in words:
                if self.get_string_width(current_line + ' ' + word) < col_widths[i] - 2:
                    current_line += (' ' if current_line else '') + word
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            wrapped_data.append(lines)
            max_lines = max(max_lines, len(lines))

        row_height = line_height * max_lines

        # --- Check page break ---
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()

        # --- Draw row ---
        x_start = self.l_margin
        y_start = self.get_y()
        for i, lines in enumerate(wrapped_data):
            self.set_xy(x_start, y_start)
            self.rect(x_start, y_start, col_widths[i], row_height)

            text_y = y_start + 1
            for line in lines:
                self.set_xy(x_start + 1, text_y)
                self.cell(col_widths[i] - 2, line_height, line, border=0)
                text_y += line_height

            x_start += col_widths[i]

        self.set_y(y_start + row_height)


# REPORT: CLEARANCE FORM
class HeadClearanceSummaryPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap, y=8, w=logo_width)

        # Header text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        # Report title
        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'CLEARANCE FORM SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(
            0,
            5,
            f"{self.department_name} | Page {self.page_no()} of {{nb}}",
            align='C'
        )

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit',
            'Position Title',
            'Full Name',
            'Date Requested',
            'Purpose',
            'Status',
            'Current Stage',
            'Remarks'
        ]
        col_widths = [40, 40, 40, 25, 45, 20, 35, 27]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()
        self.set_font('Arial', '', 7)  # reset for data rows

    def add_clearance_row(self, index, permit):
        line_height = 4
        col_widths = self.col_widths

        # Extract data
        department = permit.get('department', 'N/A')
        position = permit.get('position', 'N/A')
        first_name = permit.get('first_name', '').strip()
        last_name = permit.get('last_name', '').strip()
        middle_name = permit.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        full_name = f"{last_name}, {first_name} {middle_initial}".strip()
        date_requested = permit.get('date_requested', 'N/A')
        purpose = permit.get('purpose', 'N/A')
        status = permit.get('status', 'N/A')
        current_stage = permit.get('current_stage', '-')
        remarks = permit.get('remarks', '-')

        data = [department, position, full_name,
                date_requested, purpose, status, current_stage, remarks]

        # Calculate required row height
        max_lines = 1
        for i, item in enumerate(data):
            text_width = self.get_string_width(str(item))
            lines = int(text_width / (col_widths[i] - 2)) + 1
            max_lines = max(max_lines, lines)

        row_height = line_height * max_lines

        # Page break check
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()

        y_start = self.get_y()
        x_start = self.l_margin

        # Draw each cell with consistent row height
        for i, item in enumerate(data):
            self.rect(x_start, y_start, col_widths[i], row_height)  # Border
            self.set_xy(x_start + 1, y_start + 1)  # Margin inside cell
            self.multi_cell(col_widths[i] - 2, line_height, str(item), align='L')
            x_start += col_widths[i]

        # Move cursor below row
        self.set_y(y_start + row_height)

# REPORT: COE 
# REPORT: CERTIFICATE OF EMPLOYMENT (COE) SUMMARY
class HeadCOEPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')

        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap, y=8, w=logo_width)

        # Header text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        # Report title
        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'CERTIFICATE OF EMPLOYMENT SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(
            0,
            5,
            f"{self.department_name} | Page {self.page_no()} of {{nb}}",
            align='C'
        )

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Department',
            'Position',
            'Name',
            'Date Requested',
            'Status',
            'Current Stage',
            'Remarks'
        ]
        col_widths = [50, 50, 45, 25, 25, 40, 40]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()
        self.set_font('Arial', '', 7)  # Reset font for data rows

    def add_coe_row(self, permit):
        line_height = 4
        col_widths = self.col_widths

        # Extract permit data
        department = permit.get('department', 'N/A')
        position = permit.get('position', 'N/A')
        first_name = permit.get('first_name', '').strip()
        last_name = permit.get('last_name', '').strip()
        middle_name = permit.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        full_name = f"{last_name}, {first_name} {middle_initial}".strip()
        date_requested = permit.get('date_requested', 'N/A')
        status = permit.get('status', 'N/A')
        current_stage = permit.get('current_stage', '-')
        remarks = permit.get('remarks', '-')

        data = [
            department, position, full_name,
            date_requested, status, current_stage, remarks
        ]

        # Calculate max number of lines
        max_lines = 1
        for i, cell_text in enumerate(data):
            text_width = self.get_string_width(str(cell_text))
            lines = int(text_width / (col_widths[i] - 2)) + 1
            max_lines = max(max_lines, lines)

        row_height = line_height * max_lines

        # Page break check
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()

        # Draw row
        y_start = self.get_y()
        x_start = self.l_margin
        for i, cell_text in enumerate(data):
            self.rect(x_start, y_start, col_widths[i], row_height)
            self.set_xy(x_start + 1, y_start + 1)
            self.multi_cell(col_widths[i] - 2, line_height, str(cell_text))
            x_start += col_widths[i]

        # Move below row
        self.set_y(y_start + row_height)



#EMPLOYEE CREDIT RECORD 
# REPORT: LEAVE CREDITS
class EmployeeCreditPDF(FPDF):
    def __init__(self, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        # Updated columns: Name, Position, Vac Earned/Used/Remaining, Sick Earned/Used/Remaining
        self.col_widths = [50, 80, 25, 25, 25, 25, 25, 25]  
        self.dept_header = None

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'EMPLOYEE LEAVE CREDIT SUMMARY', ln=True, align='C')
        
        # DATE GENERATED
        self.set_font('Arial', 'B', 9)
        today = datetime.now().strftime("%B %d, %Y")
        self.cell(0, 6, f"{today}", ln=True, align='C')
        self.ln(4)

        # Draw multi-row table headers
        self.draw_table_headers()

        # Repeat department name if available
        if self.dept_header:
            self.set_font('Arial', 'B', 8)
            self.set_fill_color(197, 224, 180)
            self.cell(sum(self.col_widths), 6, self.dept_header, border=1, ln=True, align='L', fill=True)

    
    def draw_table_headers(self):
        # First row
        self.set_font('Arial', 'B', 8)
        self.set_fill_color(222, 234, 246)
        self.cell(self.col_widths[0], 6*2, 'Employee Name', border=1, align='C', fill=True)
        self.cell(self.col_widths[1], 6*2, 'Position', border=1, align='C', fill=True)
        self.cell(self.col_widths[2] + self.col_widths[3] + self.col_widths[4], 6, 'Vacation Leave', border=1, align='C', fill=True)
        self.cell(self.col_widths[5] + self.col_widths[6] + self.col_widths[7], 6, 'Sick Leave', border=1, align='C', fill=True)
        self.ln()

        # Second row (indented 30 mm to the right)
        self.cell(130)  # move 30 mm to the right
        sub_headers = ['Earned', 'Used', 'Remaining'] * 2
        for i, sub in enumerate(sub_headers):
            self.cell(self.col_widths[i+2], 6, sub, border=1, align='C', fill=True)
        self.ln()

    def add_department_section(self, dept_name, employees):
        self.dept_header = dept_name.strip()

        # Start new page if needed
        if self.get_y() > 180:
            self.add_page()
        else:
            self.set_font('Arial', 'B', 8)
            self.set_fill_color(197, 224, 180)
            self.cell(sum(self.col_widths), 6, self.dept_header, border=1, ln=True, align='L', fill=True)

        for emp in employees:
            self.check_page_break()
            self.add_employee_row(emp)

    def check_page_break(self):
        if self.get_y() > 190:
            self.add_page()

    def add_employee_row(self, employee):
        self.set_font('Arial', '', 7)
        line_height = 5

        first_name = employee.get('first_name', '').strip()
        last_name = employee.get('last_name', '').strip()
        middle_name = employee.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        name = f"{last_name}, {first_name} {middle_initial}".strip()

        # Position
        pos = "-"
        if employee.get('permanent_details'):
            pos = employee['permanent_details'].position.title
        elif employee.get('casual_details'):
            pos = employee['casual_details'].position.title
        elif employee.get('job_order_details'):
            pos = employee['job_order_details'].position_title

        # Leave credits
        credit = employee.get('credit_balance', {})
        vac_earned = f"{credit.get('vacation_earned', 0.0):.2f}"
        vac_used = f"{credit.get('vacation_used', 0.0):.2f}"
        vac_remaining = f"{credit.get('vacation_remaining', 0.0):.2f}"

        sick_earned = f"{credit.get('sick_earned', 0.0):.2f}"
        sick_used = f"{credit.get('sick_used', 0.0):.2f}"
        sick_remaining = f"{credit.get('sick_remaining', 0.0):.2f}"

        data = [name, pos, vac_earned, vac_used, vac_remaining, sick_earned, sick_used, sick_remaining]
        for i, item in enumerate(data):
            self.cell(self.col_widths[i], line_height, item, border=1, align='C')
        self.ln()





# CREDIT HISTORY RECORD HR 
def safe_text(text):
    """
    Ensures text is safe for FPDF (latin-1).
    Unsupported characters will be replaced with '->'.
    """
    if text is None:
        return "-"

    txt = str(text)
    safe_chars = []

    for ch in txt:
        try:
            ch.encode("latin-1")
            safe_chars.append(ch)  # valid character
        except UnicodeEncodeError:
            safe_chars.append("->")  # invalid character replaced

    return "".join(safe_chars)


# CREDIT HISTORY RECORD HR
class EmployeeCreditHistoryPDF(FPDF):
    def __init__(self, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        # Column widths: Employee, Position, Leave Type, Action, Amount, Notes, Timestamp
        self.col_widths = [50, 50, 30, 25, 50, 40, 35]
        self.dept_header = None

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Text headers
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, safe_text('Republic of the Philippines'), ln=True, align='C')
        self.cell(0, 5, safe_text('Province of Laguna'), ln=True, align='C')
        self.cell(0, 5, safe_text('Municipality of VICTORIA'), ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, safe_text('LEAVE CREDIT TRANSACTION REPORT'), ln=True, align='C')
           # DATE GENERATED
        self.set_font('Arial', 'B', 9)
        today = datetime.now().strftime("%B %d, %Y")
        self.cell(0, 6, f"{today}", ln=True, align='C')
        self.ln(4)

        # Table headers first
        self.draw_table_headers()

        # Department header after table headers
        if self.dept_header:
            self.set_font('Arial', 'B', 8)
            self.set_fill_color(197, 224, 180)
            self.cell(sum(self.col_widths), 6, safe_text(self.dept_header), ln=True, border=1, fill=True)

    def draw_table_headers(self):
        headers = ['Employee', 'Position', 'Leave Type', 'Action', 'Amount', 'Notes', 'Timestamp']
        self.set_font('Arial', 'B', 8)
        self.set_fill_color(222, 234, 246)
        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, safe_text(header), border=1, align='C', fill=True)
        self.ln()

    def add_department_section(self, dept_name, transactions):
        self.dept_header = dept_name.strip()  # Save for header use

        # Page break check
        if self.get_y() > 180:
            self.add_page()
        else:
            # Print department row only once
            self.set_font('Arial', 'B', 8)
            self.set_fill_color(197, 224, 180)
            self.cell(sum(self.col_widths), 6, safe_text(self.dept_header), ln=True, border=1, fill=True)

        # Sort transactions by timestamp (latest first)
        transactions = sorted(transactions, key=lambda t: t.timestamp, reverse=True)

        for tx in transactions:
            self.check_page_break()
            self.add_transaction_row(tx)

    def check_page_break(self):
        if self.get_y() > 190:
            self.add_page()

    def add_transaction_row(self, tx):
        self.set_font('Arial', '', 7)
        emp = tx.employee

        # Full name
        middle_initial = f"{emp.middle_name[0]}." if emp.middle_name else ""
        full_name = f"{emp.last_name}, {emp.first_name} {middle_initial}".strip()

        # Position (depends on employee type)
        if emp.permanent_details:
            pos = emp.permanent_details.position.title
        elif emp.casual_details:
            pos = emp.casual_details.position.title
        elif emp.job_order_details:
            pos = emp.job_order_details.position_title
        else:
            pos = "-"

        # Other fields
        leave_type = tx.leave_type or "-"
        action = tx.action or "-"
        amount = "{0:.1f}".format(tx.amount) if tx.amount is not None else "-"
        notes = tx.notes or "-"
        timestamp = tx.timestamp.strftime('%b %d, %Y %I:%M %p')

        # Row data
        data = [full_name, pos, leave_type, action, amount, notes, timestamp]

        # --- Multi-line row logic ---
        # Step 1: Calculate max row height
        max_height = 0
        for i, item in enumerate(data):
            text = safe_text(item)
            # Temporarily simulate multi_cell
            line_width = self.col_widths[i]
            # Approximate number of lines
            n_lines = self.get_string_width(text) / (line_width - 1)
            n_lines = int(n_lines) + 1
            height = n_lines * 5
            if height > max_height:
                max_height = height

        # Step 2: Draw cells with same height
        y_start = self.get_y()
        for i, item in enumerate(data):
            x_start = self.get_x()
            w = self.col_widths[i]

            # Draw border (rectangle) for the cell
            self.rect(x_start, y_start, w, max_height)

            # Print text inside
            self.multi_cell(w, 5, safe_text(item), border=0)
            self.set_xy(x_start + w, y_start)

        # Step 3: Move cursor to next row
        self.ln(max_height)


#EMPLOYEE TERMINATION REPORT 
#CASUAL TERMINATED 
class HeadTerminatedCasualPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap, y=8, w=logo_width)

        # Header Text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'TERMINATED CASUAL EMPLOYEE SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

        # --- Draw table headers on every page automatically ---
        self.draw_table_headers()

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 7)
        headers = ['#', 'Full Name', 'Name Ext.', 'Position', 'Salary',
                   'Daily Wage', 'From', 'To', 'Department', 'Latest Termination']
        col_widths = [7, 35, 15, 45, 23, 23, 18, 18, 35, 60]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_employee_row(self, index, emp):
        self.set_font('Arial', '', 7)
        line_height = 4
        col_widths = self.col_widths

        # Prepare data
        middle_initial = f"{emp.middle_name[0]}." if emp.middle_name else ""
        full_name = f"{emp.last_name}, {emp.first_name} {middle_initial}".strip()
        extension = emp.casual_details.name_extension or 'N/A'
        position = emp.casual_details.position.title if emp.casual_details.position else 'N/A'
        salary = str(emp.casual_details.equivalent_salary or 'N/A')
        wage = str(emp.casual_details.daily_wage or 'N/A')
        start = emp.casual_details.contract_start.strftime('%m/%d/%Y') if emp.casual_details.contract_start else 'N/A'
        end = emp.casual_details.contract_end.strftime('%m/%d/%Y') if emp.casual_details.contract_end else 'N/A'
        department = emp.casual_details.assigned_department.name if emp.casual_details.assigned_department else 'N/A'

        if emp.termination_records:
            latest = max(emp.termination_records, key=lambda t: t.terminated_at)
            terminated_at = latest.terminated_at.strftime('%m/%d/%Y')
            reason = latest.reason.replace('—', '-')
            terminated_by = f"{latest.user.name} ({latest.user.role})" if latest.user else "System/Unknown (N/A)"
            latest_text = f"{terminated_at} - {reason}\nTerminated by: {terminated_by}"
        else:
            latest_text = "No record"

        data = [str(index), full_name, extension, position, salary, wage,
                start, end, department, latest_text]

        # Compute row height based on the cell with the most lines
        max_lines = 1
        for i, cell_text in enumerate(data):
            lines = self.multi_cell(col_widths[i], line_height, str(cell_text), split_only=True)
            max_lines = max(max_lines, len(lines))
        row_height = line_height * max_lines

        # --- Page break check ---
        if self.get_y() + row_height > self.h - 15:  # 15mm bottom margin
            self.add_page()  # header() will auto-call -> table headers drawn

        x_start = self.get_x()
        y_start = self.get_y()

        # Draw each cell
        for i, cell_text in enumerate(data):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, str(cell_text), border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)



#PERMANENT TERMINATED 
class HeadTerminatedPermanentPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')

        center_x = 148.5
        logo_width = 18
        gap = 30

        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'TERMINATED PERMANENT EMPLOYEE SUMMARY REPORT',
                  ln=True, align='C')
        self.ln(5)

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 7)

        headers = [
            '#', 'Department', 'Item #', 'Position', 'Step', 'Level',
            'Full Name', 'Sex', 'TIN / UMID', 'Original Appt.', 'Status',
            'Latest Termination'
        ]
        # ✅ adjusted widths to fit A4 Landscape
        col_widths = [7, 32, 16, 38, 10, 10, 35, 10, 25, 20, 12, 52]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_employee_row(self, index, emp):
        self.set_font('Arial', '', 7)
        line_height = 4
        col_widths = self.col_widths

        # Prepare data (same as before)
        middle_initial = f"{emp.middle_name[0]}." if emp.middle_name else ""
        full_name = f"{emp.last_name}, {emp.first_name} {middle_initial}".strip()
        department = str(emp.department.name if emp.department else 'N/A')
        item_number = str(emp.permanent_details.item_number or 'N/A')
        position = str(emp.permanent_details.position.title if emp.permanent_details.position else 'N/A')
        step = str(emp.permanent_details.step or 'N/A')
        level = str(emp.permanent_details.level or 'N/A')
        sex = str(emp.permanent_details.sex or 'N/A')
        tin_umid = f"{emp.permanent_details.tin or 'N/A'} / {emp.permanent_details.umid_no or 'N/A'}"
        orig_date = emp.permanent_details.date_original_appointment.strftime('%Y-%m-%d') if emp.permanent_details.date_original_appointment else 'N/A'
        status = str(emp.status or 'N/A')
        
        if emp.termination_records:
            latest = max(emp.termination_records, key=lambda t: t.terminated_at)
            terminated_at = latest.terminated_at.strftime('%m/%d/%Y')
            reason = latest.reason
            terminated_by = f"{latest.user.name} ({latest.user.role})" if latest.user else "System/Unknown (N/A)"
            latest_text = f"{terminated_at} - {reason}\nTerminated by: {terminated_by}"
        else:
            latest_text = "No record"

        data = [str(index), department, item_number, position, step, level,
                full_name, sex, tin_umid, orig_date, status, latest_text]

        # Determine max height of the row by measuring each cell
        cell_heights = []
        for i, text in enumerate(data):
            nb_lines = self.multi_cell(col_widths[i], line_height, str(text), border=0, split_only=True)
            cell_heights.append(len(nb_lines) * line_height)
        row_height = max(cell_heights)

          # --- Page break check ---
        if self.get_y() + row_height > self.h - 15:  # 15mm bottom margin
            self.add_page()

        x_start = self.get_x()
        y_start = self.get_y()

        # Draw each cell
        for i, text in enumerate(data):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, str(text), border=0)
            # Draw rectangle
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)


# job order
class HeadTerminatedJobOrderPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')

        center_x = 148.5
        logo_width = 18
        gap = 30

        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'TERMINATED JOB ORDER EMPLOYEE SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 7)

        headers = ['#', 'Main Dept.', 'Full Name', 'Assigned Dept.', 'Status', 'Latest Termination']
        # Adjusted column widths for the new column
        col_widths = [7, 60, 60, 60, 25, 70]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_employee_row(self, index, emp):
        self.set_font('Arial', '', 7)
        line_height = 4
        col_widths = self.col_widths

        main_dept = emp.department.name if emp.department else 'N/A'
        middle_initial = f"{emp.middle_name[0]}." if emp.middle_name else ""
        full_name = f"{emp.last_name}, {emp.first_name} {middle_initial}".strip()
        assigned_dept = emp.job_order_details.assigned_department.name if emp.job_order_details and emp.job_order_details.assigned_department else '-'
        status = emp.status or 'N/A'

        # Latest termination
        if emp.termination_records:
            latest = max(emp.termination_records, key=lambda t: t.terminated_at)
            terminated_at = latest.terminated_at.strftime('%m/%d/%Y')
            reason = latest.reason
            terminated_by = f"{latest.user.name} ({latest.user.role})" if latest.user else "System/Unknown (N/A)"
            latest_text = f"{terminated_at} - {reason}\nTerminated by: {terminated_by}"
        else:
            latest_text = "No record"

        data = [str(index), main_dept, full_name, assigned_dept, status, latest_text]

        # Compute max row height using multi_cell with split_only
        cell_heights = []
        for i, text in enumerate(data):
            nb_lines = self.multi_cell(col_widths[i], line_height, str(text), border=0, split_only=True)
            cell_heights.append(len(nb_lines) * line_height)
        row_height = max(cell_heights)

          # --- Page break check ---
        if self.get_y() + row_height > self.h - 15:  # 15mm bottom margin
            self.add_page()

        x_start = self.get_x()
        y_start = self.get_y()

        # Draw each cell
        for i, text in enumerate(data):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, str(text), border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)



#IPCR HR DEPARTMENT REPORT 
class HeadDepartmentIPCRPDF(FPDF):
    def __init__(self, period_title="Evaluation Period", orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.period_title = period_title
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'IPCR DEPARTMENT SUMMARY REPORT', ln=True, align='C')
        self.set_font('Arial', 'B', 13)
        self.cell(0, 5, self.period_title, ln=True, align='C')
        self.ln(5)

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 7)

        headers = ['#', 'Division', 'Submitted', 'Graded', 'Status']
        col_widths = [10, 100, 50, 50, 60]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()
    def add_department_row(self, index, data):
        self.set_font('Arial', '', 7)
        line_height = 4
        col_widths = self.col_widths

        submitted = f"{data['ipcr_submitted']} / {data['ipcr_total']} submitted"
        graded = f"{data['ipcr_graded']} / {data['ipcr_total']} graded"

        # Determine status
        is_completed = data['ipcr_graded'] == data['ipcr_total'] and data['ipcr_total'] > 0
        status = "Completed" if is_completed else "Incomplete"

        row_data = [
            str(index),
            data['division'],
            submitted,
            graded,
            status
        ]

        max_lines = 1
        for i in range(len(row_data)):
            lines = self.get_string_width(row_data[i]) / (col_widths[i] - 2)
            estimated_lines = int(lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines
        x_start = self.get_x()
        y_start = self.get_y()

        for i in range(len(row_data)):
            self.set_xy(x_start, y_start)

            # ✅ Apply color only to the Status column
            if i == 4:
                if status == "Completed":
                    self.set_text_color(3, 153, 0)  # #039900
                else:
                    self.set_text_color(201, 0, 0)  # #c90000
            else:
                self.set_text_color(0, 0, 0)  # Black

            self.multi_cell(col_widths[i], line_height, row_data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)
        self.set_text_color(0, 0, 0)  # Reset to default after the row


# IPCR HR EMPLOYEE 

class HeadEmployeeIPCRPDF(FPDF):
    def __init__(self, department_name="Department", period_title="Evaluation Period", orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.period_title = period_title
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 13)
        self.cell(0, 6, self.department_name, ln=True, align='C')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 6, 'IPCR EMPLOYEE REPORT', ln=True, align='C')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 6, self.period_title, ln=True, align='C')
        self.ln(6)

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 7)

        headers = ['#', 'Name', 'Position', 'Submitted', 'Status', 'Graded']
        self.col_widths = [12, 80, 90, 30, 30, 30]

        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_employee_row(self, index, emp, ipcr, grade):
        self.set_font('Arial', '', 7)
        col_widths = self.col_widths
        line_height = 4

        middle_initial = f"{emp.middle_name[0]}." if emp.middle_name else ""
        name = f"{emp.last_name}, {emp.first_name} {middle_initial}"

        if emp.permanent_details:
            position = emp.permanent_details.position.title
        elif emp.casual_details:
            position = emp.casual_details.position.title
        elif emp.job_order_details:
            position = emp.job_order_details.position_title
        else:
            position = "Unknown"

        submitted = "Submitted" if ipcr and ipcr.submitted else "Not Submitted"
        graded = "Rated" if ipcr and ipcr.graded else "Pending Rating"
        rating = f"{grade:.2f}" if grade is not None else "0.00"

        row_data = [str(index), name, position, submitted, graded, rating]

        # Colors for submitted and graded
        # Colors for submitted and graded
        text_colors = {
            "Submitted": (3, 153, 0),
            "Not Submitted": (201, 0, 0),
            "Rated": (3, 153, 0),
            "Pending Rating": (201, 0, 0),
        }


        x_start = self.get_x()
        y_start = self.get_y()
        max_lines = 1

        for i in range(len(row_data)):
            lines = self.get_string_width(row_data[i]) / (col_widths[i] - 2)
            estimated_lines = int(lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines

        for i in range(len(row_data)):
            self.set_xy(x_start, y_start)

            if i in [3, 4]:  # Submitted or Graded columns
                self.set_text_color(*text_colors.get(row_data[i], (0, 0, 0)))
            else:
                self.set_text_color(0, 0, 0)

            self.multi_cell(col_widths[i], line_height, row_data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)
        self.set_text_color(0, 0, 0)  # Reset



# HR ISSUE SUMMARY REPORT 
#HR OPEN REPORT 
class OpenIssueSummaryPDF(FPDF):
    def __init__(self, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.col_widths = []
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 13)
        self.cell(0, 6, 'HUMAN RESOURCE MANAGEMENT OFFICE', ln=True, align='C')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 6, 'ISSUE SUMMARY REPORT', ln=True, align='C')
        self.cell(0, 6, datetime.now().strftime('%B %d, %Y'), ln=True, align='C')
        self.ln(6)

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 7)

        headers = ['#', 'Reported By', 'Reported Employee', 'Title', 'Description', 'Status', 'Date']
        self.col_widths = [10, 35, 35, 35, 120, 18, 25]

        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_issue_row(self, index, issue):
        self.set_font('Arial', '', 7)
        line_height = 4
        col_widths = self.col_widths

        # ✅ Format: LASTNAME, Firstname M.
        if issue.reported and issue.reported.employee:
            emp = issue.reported.employee
            middle_initial = f"{emp.middle_name[0].upper()}." if emp.middle_name else ""
            reported = f"{emp.last_name.upper()}, {emp.first_name} {middle_initial}"
        else:
            reported = "No employee info"

        # ✅ If you also want to format reporter the same way:
        if issue.reporter and issue.reporter.employee:
            emp = issue.reporter.employee
            middle_initial = f"{emp.middle_name[0].upper()}." if emp.middle_name else ""
            reporter = f"{emp.last_name.upper()}, {emp.first_name} {middle_initial}"
        else:
            reporter = "N/A"

        created_at = issue.created_at.strftime('%B %d, %Y') if issue.created_at else "—"

        row_data = [
            str(index),
            reporter,
            reported,
            issue.title,
            issue.description,
            issue.status,
            created_at
        ]

        x_start = self.get_x()
        y_start = self.get_y()
        max_lines = 1

        for i in range(len(row_data)):
            text_width = self.get_string_width(row_data[i])
            lines = text_width / (col_widths[i] - 2)
            estimated_lines = int(lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines

        for i in range(len(row_data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, row_data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)


#HR ISSUE INPROGRESS
class InProgressIssueSummaryPDF(FPDF):
    def __init__(self, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.col_widths = []
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header Text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 13)
        self.cell(0, 6, 'HUMAN RESOURCE MANAGEMENT OFFICE', ln=True, align='C')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 6, 'INPROGRESS ISSUE SUMMARY REPORT', ln=True, align='C')
        self.cell(0, 6, datetime.now().strftime('%B %d, %Y'), ln=True, align='C')
        self.ln(6)

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 7)

        headers = ['#', 'Reported By', 'Reported Employee', 'Title', 'Description', 'Status', 'Date']
        self.col_widths = [10, 35, 35, 35, 120, 18, 25]

        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_issue_row(self, index, issue):
        self.set_font('Arial', '', 7)
        line_height = 4
        col_widths = self.col_widths

        # ✅ Format reporter name (if needed)
        if issue.reporter and issue.reporter.employee:
            emp = issue.reporter.employee
            middle_initial = f"{emp.middle_name[0].upper()}." if emp.middle_name else ""
            reporter = f"{emp.last_name.upper()}, {emp.first_name} {middle_initial}"
        else:
            reporter = issue.reporter.name if issue.reporter else 'N/A'

        # ✅ Format reported name: LASTNAME, Firstname M.
        if issue.reported and issue.reported.employee:
            emp = issue.reported.employee
            middle_initial = f"{emp.middle_name[0].upper()}." if emp.middle_name else ""
            reported = f"{emp.last_name.upper()}, {emp.first_name} {middle_initial}"
        else:
            reported = "No employee info"

        created_at = issue.created_at.strftime('%B %d, %Y') if issue.created_at else "—"

        row_data = [
            str(index),
            reporter,
            reported,
            issue.title,
            issue.description,
            issue.status,
            created_at
        ]

        x_start = self.get_x()
        y_start = self.get_y()
        max_lines = 1

        # Calculate max lines per row
        for i in range(len(row_data)):
            text_width = self.get_string_width(row_data[i])
            lines = text_width / (col_widths[i] - 2)
            estimated_lines = int(lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines

        for i in range(len(row_data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, row_data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)



#HR ISSUE RESOLVE 
class ResolvedIssueSummaryPDF(FPDF):
    def __init__(self, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.col_widths = []
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Insert logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 13)
        self.cell(0, 6, 'HUMAN RESOURCE MANAGEMENT OFFICE', ln=True, align='C')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 6, 'RESOLVED ISSUE SUMMARY REPORT', ln=True, align='C')
        self.cell(0, 6, datetime.now().strftime('%B %d, %Y'), ln=True, align='C')
        self.ln(6)

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 7)

        headers = ['#', 'Reported By', 'Reported Employee', 'Title', 'Description', 'Status', 'Date', 'Remarks']
        self.col_widths = [8, 32, 32, 34, 105, 18, 25, 20]

        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_issue_row(self, index, issue):
        self.set_font('Arial', '', 7)
        line_height = 4
        col_widths = self.col_widths

        # ✅ Format reporter name
        if issue.reporter and issue.reporter.employee:
            emp = issue.reporter.employee
            middle_initial = f"{emp.middle_name[0].upper()}." if emp.middle_name else ""
            reporter = f"{emp.last_name.upper()}, {emp.first_name} {middle_initial}"
        else:
            reporter = issue.reporter.name if issue.reporter else 'N/A'

        # ✅ Format reported name
        if issue.reported and issue.reported.employee:
            emp = issue.reported.employee
            middle_initial = f"{emp.middle_name[0].upper()}." if emp.middle_name else ""
            reported = f"{emp.last_name.upper()}, {emp.first_name} {middle_initial}"
        else:
            reported = "No employee info"

        created_at = issue.created_at.strftime('%B %d, %Y') if issue.created_at else "—"
        remarks = issue.remarks or "No remarks provided."

        row_data = [
            str(index),
            reporter,
            reported,
            issue.title,
            issue.description,
            issue.status,
            created_at,
            remarks
        ]

        x_start = self.get_x()
        y_start = self.get_y()
        max_lines = 1

        # Estimate max line count for wrapping
        for i in range(len(row_data)):
            text_width = self.get_string_width(row_data[i])
            lines = text_width / (col_widths[i] - 2)
            estimated_lines = int(lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines

        for i in range(len(row_data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, row_data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)


#employee ipcr record 
class IPCRSummaryPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.set_auto_page_break(auto=True, margin=15)
        self.col_widths = []
        self.department_name = department_name  # store the department name

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 13)
        self.cell(0, 6, self.department_name, ln=True, align='C')  # ✅ replaced HRMO
        self.set_font('Arial', 'B', 12)
        self.cell(0, 6, 'INDIVIDUAL PERFORMANCE COMMITMENT REVIEW (IPCR)', ln=True, align='C')
        self.cell(0, 6, datetime.now().strftime('%B %d, %Y'), ln=True, align='C')
        self.ln(6)

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 7)

        headers = ['Period', 'Submission Status', 'Grading Status', 'Date Submitted', 'Final Rating']
        self.col_widths = [60, 50, 50, 50, 50]

        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_ipcr_row(self, ipcr):
        self.set_font('Arial', '', 7)
        col_widths = self.col_widths
        line_height = 4

        # Prepare data
        period_str = f"{ipcr.period.name}\n({ipcr.period.start_date.strftime('%b %d, %Y')} - {ipcr.period.end_date.strftime('%b %d, %Y')})"

        if not ipcr.submitted and not ipcr.graded:
            submission_status = "Returned"
        elif ipcr.submitted:
            submission_status = "Submitted"
        else:
            submission_status = "Draft"

        grading_status = "Graded" if ipcr.graded else "Pending"
        date_submitted = ipcr.date_submitted.strftime('%b %d, %Y %I:%M %p') if ipcr.date_submitted else 'N/A'
        rating = f"{ipcr.final_average_rating or 0:.2f}"

        row_data = [period_str, submission_status, grading_status, date_submitted, rating]

        # Calculate max line count
        max_lines = 1
        for data in row_data:
            lines = data.count('\n') + 1
            max_lines = max(max_lines, lines)

        row_height = line_height * max_lines
        x_start = self.get_x()
        y_start = self.get_y()

        for i in range(len(row_data)):
            cell_width = col_widths[i]
            text = row_data[i].strip()

            # Calculate text width and center x manually
            text_lines = text.split('\n')
            num_lines = len(text_lines)
            align = 'C'  # center all columns

            # Draw multiline content centered in the cell
            self.set_xy(x_start, y_start)
            self.multi_cell(cell_width, line_height, text, border=0, align=align)

            # Draw the cell border manually after the content
            self.rect(x_start, y_start, cell_width, row_height)
            x_start += cell_width


        self.set_y(y_start + row_height)






# #HEAD IPCR RECORD 


class HeadIPCRPeriodSummaryPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.set_auto_page_break(auto=True, margin=15)
        self.col_widths = []
        self.department_name = department_name
        self.add_page()

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Municipal logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 13)
        self.cell(0, 6, self.department_name, ln=True, align='C')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 6, 'IPCR Period Summary Report', ln=True, align='C')
        self.cell(0, 6, datetime.now().strftime('%B %d, %Y'), ln=True, align='C')
        self.ln(6)

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = ['Evaluation Period', 'Start Date', 'End Date', 'Submitted', 'Graded', 'Total Employees']
        self.col_widths = [60, 40, 40, 40, 40, 40]

        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 7, header, border=1, align='C', fill=True)
        self.ln()

    def add_period_row(self, period, ipcrs, total_employees):
        self.set_font('Arial', '', 8)
        col_widths = self.col_widths
        line_height = 4

        # Compute submitted & graded counts
        submitted = sum(1 for ipcr in ipcrs if ipcr.submitted)
        graded = sum(1 for ipcr in ipcrs if ipcr.graded)

        # Format period name with date range
        period_str = f"{period.name}\n"
        row_data = [period_str, period.start_date.strftime('%Y-%m-%d'), period.end_date.strftime('%Y-%m-%d'),
                    str(submitted), str(graded), str(total_employees)]

        # Handle multiline height
        max_lines = max(data.count('\n') + 1 for data in row_data)
        row_height = line_height * max_lines

        x_start = self.get_x()
        y_start = self.get_y()

        for i in range(len(row_data)):
            cell_width = col_widths[i]
            text = row_data[i].strip()

            self.set_xy(x_start, y_start)
            self.multi_cell(cell_width, line_height, text, border=0, align='C')
            self.rect(x_start, y_start, cell_width, row_height)

            x_start += cell_width

        self.set_y(y_start + row_height)



        
# user CREDIT RECORD (Current User Only)
class UserCreditPDF(FPDF):
    def __init__(self, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        # Adjusted widths para balance sa table
        self.col_widths = [60, 50, 25, 25, 25, 25, 25, 25]  
        self.dept_header = None

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'EMPLOYEE LEAVE CREDIT SUMMARY', ln=True, align='C')
        if self.dept_name:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 6, f"{self.dept_name}", ln=True, align='C')
        
               # DATE GENERATED
        self.set_font('Arial', 'B', 9)
        today = datetime.now().strftime("%B %d, %Y")
        self.cell(0, 6, f"{today}", ln=True, align='C')
        self.ln(4)

        # Draw table headers lagi
        self.draw_table_headers()

    def draw_table_headers(self):
        # First row
        self.set_font('Arial', 'B', 8)
        self.set_fill_color(222, 234, 246)
        self.cell(self.col_widths[0], 6*2, 'Employee Name', border=1, align='C', fill=True)
        self.cell(self.col_widths[1], 6*2, 'Position', border=1, align='C', fill=True)
        self.cell(self.col_widths[2] + self.col_widths[3] + self.col_widths[4], 6, 'Vacation Leave', border=1, align='C', fill=True)
        self.cell(self.col_widths[5] + self.col_widths[6] + self.col_widths[7], 6, 'Sick Leave', border=1, align='C', fill=True)
        self.ln()

        # Second row (indented 30 mm to the right)
        self.cell(110)  # move 30 mm to the right
        sub_headers = ['Earned', 'Used', 'Remaining'] * 2
        for i, sub in enumerate(sub_headers):
            self.cell(self.col_widths[i+2], 6, sub, border=1, align='C', fill=True)
        self.ln()

    def add_department_section(self, dept_name, employees):
        self.dept_header = dept_name.strip()

        # Start new page if needed
        if self.get_y() > 180:
            self.add_page()
        else:
            self.set_font('Arial', 'B', 8)
            self.set_fill_color(197, 224, 180)
            self.cell(sum(self.col_widths), 6, self.dept_header, border=1, ln=True, align='L', fill=True)

        for emp in employees:
            self.check_page_break()
            self.add_employee_row(emp)

    def check_page_break(self):
        if self.get_y() > 190:
            self.add_page()

    def add_employee_row(self, employee):
        self.set_font('Arial', '', 7)
        line_height = 5

        first_name = employee.get('first_name', '').strip()
        last_name = employee.get('last_name', '').strip()
        middle_name = employee.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        name = f"{last_name}, {first_name} {middle_initial}".strip()

        # Position
        pos = "-"
        if employee.get('permanent_details'):
            pos = employee['permanent_details'].position.title
        elif employee.get('casual_details'):
            pos = employee['casual_details'].position.title
        elif employee.get('job_order_details'):
            pos = employee['job_order_details'].position_title

        # Leave credits
        credit = employee.get('credit_balance', {})
        vac_earned = f"{credit.get('vacation_earned', 0.0):.2f}"
        vac_used = f"{credit.get('vacation_used', 0.0):.2f}"
        vac_remaining = f"{credit.get('vacation_remaining', 0.0):.2f}"

        sick_earned = f"{credit.get('sick_earned', 0.0):.2f}"
        sick_used = f"{credit.get('sick_used', 0.0):.2f}"
        sick_remaining = f"{credit.get('sick_remaining', 0.0):.2f}"

        data = [name, pos, vac_earned, vac_used, vac_remaining, sick_earned, sick_used, sick_remaining]
        for i, item in enumerate(data):
            self.cell(self.col_widths[i], line_height, item, border=1, align='C')
        self.ln()


# CREDIT HISTORY RECORD (Current User Only)
def safe_text(text):
    """
    Ensures text is safe for FPDF (latin-1).
    Unsupported characters will be replaced with '->'.
    """
    if text is None:
        return "-"

    txt = str(text)
    safe_chars = []

    for ch in txt:
        try:
            ch.encode("latin-1")
            safe_chars.append(ch)  # valid character
        except UnicodeEncodeError:
            safe_chars.append("->")  # invalid character replaced

    return "".join(safe_chars)

class UserCreditHistoryPDF(FPDF):
    def __init__(self, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.col_widths = [50, 50, 30, 25, 50, 40, 35]
        self.dept_header = None

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'LEAVE CREDIT TRANSACTION REPORT', ln=True, align='C')
        if self.dept_name:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 6, f"{self.dept_name}", ln=True, align='C')
               # DATE GENERATED
        self.set_font('Arial', 'B', 9)
        today = datetime.now().strftime("%B %d, %Y")
        self.cell(0, 6, f"{today}", ln=True, align='C')
        self.ln(4)

        # Table headers
        self.draw_table_headers()

    def draw_table_headers(self):
        headers = ['Employee', 'Position', 'Leave Type', 'Action', 'Amount', 'Notes', 'Timestamp']
        self.set_font('Arial', 'B', 8)
        self.set_fill_color(222, 234, 246)
        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, safe_text(header), border=1, align='C', fill=True)
        self.ln()

    def add_department_section(self, dept_name, transactions):
        self.dept_header = dept_name.strip()  # Save for header use

        # Page break check
        if self.get_y() > 180:
            self.add_page()
        else:
            # Print department row only once
            self.set_font('Arial', 'B', 8)
            self.set_fill_color(197, 224, 180)
            self.cell(sum(self.col_widths), 6, safe_text(self.dept_header), ln=True, border=1, fill=True)

        # Sort transactions by timestamp (latest first)
        transactions = sorted(transactions, key=lambda t: t.timestamp, reverse=True)

        for tx in transactions:
            self.check_page_break()
            self.add_transaction_row(tx)

    def check_page_break(self):
        if self.get_y() > 190:
            self.add_page()

    def add_transaction_row(self, tx):
        self.set_font('Arial', '', 7)
        emp = tx.employee

        # Full name
        middle_initial = f"{emp.middle_name[0]}." if emp.middle_name else ""
        full_name = f"{emp.last_name}, {emp.first_name} {middle_initial}".strip()

        # Position (depends on employee type)
        if emp.permanent_details:
            pos = emp.permanent_details.position.title
        elif emp.casual_details:
            pos = emp.casual_details.position.title
        elif emp.job_order_details:
            pos = emp.job_order_details.position_title
        else:
            pos = "-"

        # Other fields
        leave_type = tx.leave_type or "-"
        action = tx.action or "-"
        amount = "{0:.1f}".format(tx.amount) if tx.amount is not None else "-"
        notes = tx.notes or "-"
        timestamp = tx.timestamp.strftime('%b %d, %Y %I:%M %p')

        # Row data
        data = [full_name, pos, leave_type, action, amount, notes, timestamp]

        # --- Multi-line row logic ---
        # Step 1: Calculate max row height
        max_height = 0
        for i, item in enumerate(data):
            text = safe_text(item)
            # Temporarily simulate multi_cell
            line_width = self.col_widths[i]
            # Approximate number of lines
            n_lines = self.get_string_width(text) / (line_width - 1)
            n_lines = int(n_lines) + 1
            height = n_lines * 5
            if height > max_height:
                max_height = height

        # Step 2: Draw cells with same height
        y_start = self.get_y()
        for i, item in enumerate(data):
            x_start = self.get_x()
            w = self.col_widths[i]

            # Draw border (rectangle) for the cell
            self.rect(x_start, y_start, w, max_height)

            # Print text inside
            self.multi_cell(w, 5, safe_text(item), border=0)
            self.set_xy(x_start + w, y_start)

        # Step 3: Move cursor to next row
        self.ln(max_height)



# CREDIT HISTORY RECORD (Department Head View)
class HeadCreditPDF(FPDF):
    def __init__(self, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        # Updated columns: Name, Position, Vac Earned/Used/Remaining, Sick Earned/Used/Remaining
        self.col_widths = [60, 50, 25, 25, 25, 25, 25, 25]  
        self.dept_header = None

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Header text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'EMPLOYEE LEAVE CREDIT SUMMARY', ln=True, align='C')
         # DATE GENERATED
        self.set_font('Arial', 'B', 9)
        today = datetime.now().strftime("%B %d, %Y")
        self.cell(0, 6, f"{today}", ln=True, align='C')
        self.ln(4)
        # Draw multi-row table headers
        self.draw_table_headers()

        # Repeat department name if available
        if self.dept_header:
            self.set_font('Arial', 'B', 8)
            self.set_fill_color(197, 224, 180)
            self.cell(sum(self.col_widths), 6, self.dept_header, border=1, ln=True, align='L', fill=True)

    
    def draw_table_headers(self):
        # First row
        self.set_font('Arial', 'B', 8)
        self.set_fill_color(222, 234, 246)
        self.cell(self.col_widths[0], 6*2, 'Employee Name', border=1, align='C', fill=True)
        self.cell(self.col_widths[1], 6*2, 'Position', border=1, align='C', fill=True)
        self.cell(self.col_widths[2] + self.col_widths[3] + self.col_widths[4], 6, 'Vacation Leave', border=1, align='C', fill=True)
        self.cell(self.col_widths[5] + self.col_widths[6] + self.col_widths[7], 6, 'Sick Leave', border=1, align='C', fill=True)
        self.ln()

        # Second row (indented 30 mm to the right)
        self.cell(110)  # move 30 mm to the right
        sub_headers = ['Earned', 'Used', 'Remaining'] * 2
        for i, sub in enumerate(sub_headers):
            self.cell(self.col_widths[i+2], 6, sub, border=1, align='C', fill=True)
        self.ln()

    def add_department_section(self, dept_name, employees):
        self.dept_header = dept_name.strip()

        # Start new page if needed
        if self.get_y() > 180:
            self.add_page()
        else:
            self.set_font('Arial', 'B', 8)
            self.set_fill_color(197, 224, 180)
            self.cell(sum(self.col_widths), 6, self.dept_header, border=1, ln=True, align='L', fill=True)

        for emp in employees:
            self.check_page_break()
            self.add_employee_row(emp)

    def check_page_break(self):
        if self.get_y() > 190:
            self.add_page()

    def add_employee_row(self, employee):
        self.set_font('Arial', '', 7)
        line_height = 5

        first_name = employee.get('first_name', '').strip()
        last_name = employee.get('last_name', '').strip()
        middle_name = employee.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        name = f"{last_name}, {first_name} {middle_initial}".strip()

        # Position
        pos = "-"
        if employee.get('permanent_details'):
            pos = employee['permanent_details'].position.title
        elif employee.get('casual_details'):
            pos = employee['casual_details'].position.title
        elif employee.get('job_order_details'):
            pos = employee['job_order_details'].position_title

        # Leave credits
        credit = employee.get('credit_balance', {})
        vac_earned = f"{credit.get('vacation_earned', 0.0):.2f}"
        vac_used = f"{credit.get('vacation_used', 0.0):.2f}"
        vac_remaining = f"{credit.get('vacation_remaining', 0.0):.2f}"

        sick_earned = f"{credit.get('sick_earned', 0.0):.2f}"
        sick_used = f"{credit.get('sick_used', 0.0):.2f}"
        sick_remaining = f"{credit.get('sick_remaining', 0.0):.2f}"

        data = [name, pos, vac_earned, vac_used, vac_remaining, sick_earned, sick_used, sick_remaining]
        for i, item in enumerate(data):
            self.cell(self.col_widths[i], line_height, item, border=1, align='C')
        self.ln()


# CREDIT SUMMARY REPORT (Department Head View)
def safe_text(text):
    """
    Ensures text is safe for FPDF (latin-1).
    Unsupported characters will be replaced with '->'.
    """
    if text is None:
        return "-"

    txt = str(text)
    safe_chars = []

    for ch in txt:
        try:
            ch.encode("latin-1")
            safe_chars.append(ch)  # valid character
        except UnicodeEncodeError:
            safe_chars.append("->")  # invalid character replaced

    return "".join(safe_chars)

class HeadCreditHistoryPDF(FPDF):
    def __init__(self, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        # Column widths: Employee, Position, Leave Type, Action, Amount, Notes, Timestamp
        self.col_widths = [50, 50, 30, 25, 50, 40, 35]
        self.dept_header = None

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        # Text headers
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, safe_text('Republic of the Philippines'), ln=True, align='C')
        self.cell(0, 5, safe_text('Province of Laguna'), ln=True, align='C')
        self.cell(0, 5, safe_text('Municipality of VICTORIA'), ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, safe_text('LEAVE CREDIT TRANSACTION REPORT'), ln=True, align='C')
        # DATE GENERATED
        self.set_font('Arial', 'B', 9)
        today = datetime.now().strftime("%B %d, %Y")
        self.cell(0, 6, f"{today}", ln=True, align='C')
        self.ln(4)
        # Draw multi-row table headers
        self.draw_table_headers()

        # Department header after table headers
        if self.dept_header:
            self.set_font('Arial', 'B', 8)
            self.set_fill_color(197, 224, 180)
            self.cell(sum(self.col_widths), 6, safe_text(self.dept_header), ln=True, border=1, fill=True)

    def draw_table_headers(self):
        headers = ['Employee', 'Position', 'Leave Type', 'Action', 'Amount', 'Notes', 'Timestamp']
        self.set_font('Arial', 'B', 8)
        self.set_fill_color(222, 234, 246)
        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, safe_text(header), border=1, align='C', fill=True)
        self.ln()

    def add_department_section(self, dept_name, transactions):
        self.dept_header = dept_name.strip()  # Save for header use

        # Page break check
        if self.get_y() > 180:
            self.add_page()
        else:
            # Print department row only once
            self.set_font('Arial', 'B', 8)
            self.set_fill_color(197, 224, 180)
            self.cell(sum(self.col_widths), 6, safe_text(self.dept_header), ln=True, border=1, fill=True)

        # Sort transactions by timestamp (latest first)
        transactions = sorted(transactions, key=lambda t: t.timestamp, reverse=True)

        for tx in transactions:
            self.check_page_break()
            self.add_transaction_row(tx)

    def check_page_break(self):
        if self.get_y() > 190:
            self.add_page()

    def add_transaction_row(self, tx):
        self.set_font('Arial', '', 7)
        emp = tx.employee

        # Full name
        middle_initial = f"{emp.middle_name[0]}." if emp.middle_name else ""
        full_name = f"{emp.last_name}, {emp.first_name} {middle_initial}".strip()

        # Position (depends on employee type)
        if emp.permanent_details:
            pos = emp.permanent_details.position.title
        elif emp.casual_details:
            pos = emp.casual_details.position.title
        elif emp.job_order_details:
            pos = emp.job_order_details.position_title
        else:
            pos = "-"

        # Other fields
        leave_type = tx.leave_type or "-"
        action = tx.action or "-"
        amount = "{0:.1f}".format(tx.amount) if tx.amount is not None else "-"
        notes = tx.notes or "-"
        timestamp = tx.timestamp.strftime('%b %d, %Y %I:%M %p')

        # Row data
        data = [full_name, pos, leave_type, action, amount, notes, timestamp]

        # --- Multi-line row logic ---
        # Step 1: Calculate max row height
        max_height = 0
        for i, item in enumerate(data):
            text = safe_text(item)
            # Temporarily simulate multi_cell
            line_width = self.col_widths[i]
            # Approximate number of lines
            n_lines = self.get_string_width(text) / (line_width - 1)
            n_lines = int(n_lines) + 1
            height = n_lines * 5
            if height > max_height:
                max_height = height

        # Step 2: Draw cells with same height
        y_start = self.get_y()
        for i, item in enumerate(data):
            x_start = self.get_x()
            w = self.col_widths[i]

            # Draw border (rectangle) for the cell
            self.rect(x_start, y_start, w, max_height)

            # Print text inside
            self.multi_cell(w, 5, safe_text(item), border=0)
            self.set_xy(x_start + w, y_start)

        # Step 3: Move cursor to next row
        self.ln(max_height)





# TravelLog USER
class TravelLogUSERPDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4', department_name=None):
        super().__init__(orientation, unit, format)
        self.department_name = department_name  # store department here

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5  # center of A4 landscape
        logo_width = 18
        gap_from_text = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap_from_text - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap_from_text, y=8, w=logo_width)

        # Text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(2)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'TRAVEL RECORD', ln=True, align='C')
        self.ln(4)

             # Department name (dynamic)
        if self.department_name:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 6, f"{self.department_name}", ln=True, align='C')
            self.ln(3)

        # Table headers
        self.set_fill_color(197, 224, 180)
        self.set_font('Arial', 'B', 9)
        headers = ['Employee Name', 'Destination', 'Log Date', 'Purpose', 'Tracking ID']
        self.col_widths = [50, 60, 50, 90, 30]
        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_log_row(self, log):
        self.set_font('Arial', '', 8)
        col_widths = self.col_widths
        line_height = 4

        # Get employee details from TravelOrder → PermitRequest → Employee
        employee = log.travel_order.permit.employee
        middle_initial = f"{employee.middle_name[0]}." if employee.middle_name else ""
        emp_name = f"{employee.last_name}, {employee.first_name} {middle_initial}".strip()

        data = [
            emp_name,
            log.travel_order.destination or "-",
            log.log_date.strftime('%B %d, %Y %I:%M %p') if log.log_date else "-",
            log.travel_order.purpose or "-",
            log.tracking_id or "-"
        ]

        # Estimate max lines per cell
        max_lines = 1
        for i in range(len(data)):
            num_lines = self.get_string_width(data[i]) / (col_widths[i] - 2)
            estimated_lines = int(num_lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines
        x_start = self.get_x()
        y_start = self.get_y()

        for i in range(len(data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)



# Travel Log PDF for Department Head
class TravelLogheadPDF(FPDF):
    def __init__(self, department_name=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.department_name = department_name  # store department name
        self.col_widths = [50, 60, 70, 90, 30]

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')

        center_x = 148.5  # center of A4 landscape
        logo_width = 18
        gap_from_text = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap_from_text - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap_from_text, y=8, w=logo_width)

        # Government headers
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(2)

        # Main title
        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'TRAVEL RECORD', ln=True, align='C')
        self.ln(1)

        # Department name (dynamic)
        if self.department_name:
            self.set_font('Arial', 'B', 12)
            self.cell(0, 6, f"{self.department_name}", ln=True, align='C')
            self.ln(3)

        # Table headers
        self.set_fill_color(197, 224, 180)
        self.set_font('Arial', 'B', 9)
        headers = ['Employee Name', 'Destination', 'Log Date', 'Purpose', 'Tracking ID']
        self.col_widths = [50, 60, 50, 90, 30]
        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

    def add_log_row(self, log):
        self.set_font('Arial', '', 8)
        col_widths = self.col_widths
        line_height = 4

        # Employee details
        employee = log.travel_order.permit.employee
        middle_initial = f"{employee.middle_name[0]}." if employee.middle_name else ""
        emp_name = f"{employee.last_name}, {employee.first_name} {middle_initial}".strip()

        data = [
            emp_name,
            log.travel_order.destination or "-",
            log.log_date.strftime('%B %d, %Y %I:%M %p') if log.log_date else "-",
            log.travel_order.purpose or "-",
            log.tracking_id or "-"
        ]

        # Estimate row height
        max_lines = 1
        for i in range(len(data)):
            num_lines = self.get_string_width(data[i]) / (col_widths[i] - 2)
            estimated_lines = int(num_lines) + 1
            max_lines = max(max_lines, estimated_lines)

        row_height = line_height * max_lines
        x_start = self.get_x()
        y_start = self.get_y()

        # Draw row
        for i in range(len(data)):
            self.set_xy(x_start, y_start)
            self.multi_cell(col_widths[i], line_height, data[i], border=0)
            self.rect(x_start, y_start, col_widths[i], row_height)
            x_start += col_widths[i]

        self.set_y(y_start + row_height)




# hr DEPARTMENT PDF
# hr DEPARTMENT pdf leave
class HRLeaveApplicationPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')

        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap, y=8, w=logo_width)

        # Title header
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'DEPARTMENT LEAVE APPLICATION SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

        # Reset font para hindi maapektuhan ang body
        self.set_font('Arial', '', 7)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 5,
                  f" {self.department_name} | Page {self.page_no()} of {{nb}}",
                  align='C')
        
    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit', 'Position Title', 'Full Name',
            'Date Requested', 'Type of Leave',
            'Credits Remaining', 'Paid Days',
            'Status', 'Current Stage', 'Remarks'
        ]

        # 297mm width (A4 Landscape) - 20mm margins = 277mm usable
        self.col_widths = [32, 28, 32, 22, 32, 30, 30, 24, 24, 23]

        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

        self.set_font('Arial', '', 7)


    def add_leave_row(self, data):
        line_height = 4
        col_widths = self.col_widths

        # Format employee name
        first_name = data.get('first_name', '').strip()
        middle_name = data.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        last_name = data.get('last_name', '').strip()
        name = f"{last_name}, {first_name} {middle_initial}".strip()

        row_data = [
            data.get('department', 'N/A'),
            data.get('position', 'N/A'),
            name,
            data.get('date_requested', 'N/A'),
            data.get('leave_type', 'N/A'),
            data.get('credits_remaining', 'N/A'),
            data.get('paid_days', 'N/A'),
            data.get('status', '-'),
            data.get('current_stage', '-'),
            data.get('remarks', '-')
        ]

        # Color map for Status
        status_color_map = {
            'Approved': (198, 239, 206),
            'Pending': (255, 235, 156),
            'Cancelled': (242, 220, 219),
            'Rejected': (255, 199, 206)
        }
        status = data.get('status', '-')
        fill_rgb = status_color_map.get(status, None)

        # --- Wrap text per column ---
        wrapped_data = []
        max_lines = 1
        for i, text in enumerate(row_data):
            words = str(text).split(' ')
            lines, current_line = [], ''
            for word in words:
                if self.get_string_width(current_line + ' ' + word) < col_widths[i] - 2:
                    current_line += (' ' if current_line else '') + word
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)

            wrapped_data.append(lines)
            max_lines = max(max_lines, len(lines))

        row_height = line_height * max_lines

        # --- Check page break ---
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()
            self.set_font('Arial', '', 7)

        x_start = self.get_x()
        y_start = self.get_y()

        # --- Draw row ---
        self.set_font('Arial', '', 7)
        for i, lines in enumerate(wrapped_data):
            self.set_xy(x_start, y_start)

            if i == 7 and fill_rgb:  # highlight Status col
                self.set_fill_color(*fill_rgb)
                self.rect(x_start, y_start, col_widths[i], row_height, style='DF')
            else:
                self.rect(x_start, y_start, col_widths[i], row_height)

            text_y = y_start + 1
            for line in lines:
                self.set_xy(x_start + 1, text_y)
                self.cell(col_widths[i] - 2, line_height, line, border=0)
                text_y += line_height

            x_start += col_widths[i]

        self.set_y(y_start + row_height)




# REPORT: TRAVEL ORDER
# REPORT: TRAVEL ORDER
class HRTravelOrderPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'DEPARTMENT TRAVEL ORDER SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

        # Reset to normal font for table
        self.set_font('Arial', '', 7)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 5,
                  f"{self.department_name} | Page {self.page_no()} of {{nb}}",
                  align='C')

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit', 
            'Position Title', 
            'Full Name', 
            'Date Requested', 
            'Destination', 
            'Status', 
            'Current Stage', 
            'Remarks'
        ]
        col_widths = [35, 30, 35, 25, 50, 20, 30, 45]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

        self.set_font('Arial', '', 7)

    def add_travel_row(self, index, permit):
        line_height = 4
        col_widths = self.col_widths

        # Format name
        first_name = permit.get('first_name', '').strip()
        middle_name = permit.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        last_name = permit.get('last_name', '').strip()
        name = f"{last_name}, {first_name} {middle_initial}".strip()

        data = [
            permit.get('department', 'N/A'),
            permit.get('position', 'N/A'),
            name,
            permit.get('date_requested', 'N/A'),
            permit.get('destination', 'N/A'),
            permit.get('status', 'N/A'),
            permit.get('current_stage', '-'),
            permit.get('remarks', '-')
        ]

        # --- Word-wrap each cell ---
        wrapped_data = []
        max_lines = 1
        for i, text in enumerate(data):
            words = str(text).split(' ')
            lines, current_line = [], ''
            for word in words:
                if self.get_string_width(current_line + ' ' + word) < col_widths[i] - 2:
                    current_line += (' ' if current_line else '') + word
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            wrapped_data.append(lines)
            max_lines = max(max_lines, len(lines))

        row_height = line_height * max_lines

        # --- Check page break ---
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()

        # --- Draw row ---
        x_start = self.l_margin
        y_start = self.get_y()
        for i, lines in enumerate(wrapped_data):
            self.set_xy(x_start, y_start)
            self.rect(x_start, y_start, col_widths[i], row_height)

            text_y = y_start + 1
            for line in lines:
                self.set_xy(x_start + 1, text_y)
                self.cell(col_widths[i] - 2, line_height, line, border=0)
                text_y += line_height

            x_start += col_widths[i]

        self.set_y(y_start + row_height)





# REPORT: CLEARANCE FORM
class HRClearanceSummaryPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap, y=8, w=logo_width)

        # Header text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        # Report title
        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, ' DEPARTMENT CLEARANCE FORM SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(
            0,
            5,
            f"{self.department_name} | Page {self.page_no()} of {{nb}}",
            align='C'
        )

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit',
            'Position Title',
            'Full Name',
            'Date Requested',
            'Purpose',
            'Status',
            'Current Stage',
            'Remarks'
        ]
        col_widths = [40, 40, 40, 25, 45, 20, 35, 27]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()
        self.set_font('Arial', '', 7)  # reset for data rows

    def add_clearance_row(self, index, permit):
        line_height = 4
        col_widths = self.col_widths

        # Extract data
        department = permit.get('department', 'N/A')
        position = permit.get('position', 'N/A')
        first_name = permit.get('first_name', '').strip()
        last_name = permit.get('last_name', '').strip()
        middle_name = permit.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        full_name = f"{last_name}, {first_name} {middle_initial}".strip()
        date_requested = permit.get('date_requested', 'N/A')
        purpose = permit.get('purpose', 'N/A')
        status = permit.get('status', 'N/A')
        current_stage = permit.get('current_stage', '-')
        remarks = permit.get('remarks', '-')

        data = [department, position, full_name,
                date_requested, purpose, status, current_stage, remarks]

        # Calculate required row height
        max_lines = 1
        for i, item in enumerate(data):
            text_width = self.get_string_width(str(item))
            lines = int(text_width / (col_widths[i] - 2)) + 1
            max_lines = max(max_lines, lines)

        row_height = line_height * max_lines

        # Page break check
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()

        y_start = self.get_y()
        x_start = self.l_margin

        # Draw each cell with consistent row height
        for i, item in enumerate(data):
            self.rect(x_start, y_start, col_widths[i], row_height)  # Border
            self.set_xy(x_start + 1, y_start + 1)  # Margin inside cell
            self.multi_cell(col_widths[i] - 2, line_height, str(item), align='L')
            x_start += col_widths[i]

        # Move cursor below row
        self.set_y(y_start + row_height)




# hEAD DEPARTMENT PDF
# hEAD DEPARTMENT pdf leave
class LeaveApplicationhHeadPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')

        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap, y=8, w=logo_width)

        # Title header
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'DEPARTMENT LEAVE APPLICATION SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

        # Reset font para hindi maapektuhan ang body
        self.set_font('Arial', '', 7)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 5,
                  f" {self.department_name} | Page {self.page_no()} of {{nb}}",
                  align='C')
        
    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit', 'Position Title', 'Full Name',
            'Date Requested', 'Type of Leave',
            'Credits Remaining', 'Paid Days',
            'Status', 'Current Stage', 'Remarks'
        ]

        # 297mm width (A4 Landscape) - 20mm margins = 277mm usable
        self.col_widths = [32, 28, 32, 22, 32, 30, 30, 24, 24, 23]

        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

        self.set_font('Arial', '', 7)


    def add_leave_row(self, data):
        line_height = 4
        col_widths = self.col_widths

        # Format employee name
        first_name = data.get('first_name', '').strip()
        middle_name = data.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        last_name = data.get('last_name', '').strip()
        name = f"{last_name}, {first_name} {middle_initial}".strip()

        row_data = [
            data.get('department', 'N/A'),
            data.get('position', 'N/A'),
            name,
            data.get('date_requested', 'N/A'),
            data.get('leave_type', 'N/A'),
            data.get('credits_remaining', 'N/A'),
            data.get('paid_days', 'N/A'),
            data.get('status', '-'),
            data.get('current_stage', '-'),
            data.get('remarks', '-')
        ]

        # Color map for Status
        status_color_map = {
            'Approved': (198, 239, 206),
            'Pending': (255, 235, 156),
            'Cancelled': (242, 220, 219),
            'Rejected': (255, 199, 206)
        }
        status = data.get('status', '-')
        fill_rgb = status_color_map.get(status, None)

        # --- Wrap text per column ---
        wrapped_data = []
        max_lines = 1
        for i, text in enumerate(row_data):
            words = str(text).split(' ')
            lines, current_line = [], ''
            for word in words:
                if self.get_string_width(current_line + ' ' + word) < col_widths[i] - 2:
                    current_line += (' ' if current_line else '') + word
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)

            wrapped_data.append(lines)
            max_lines = max(max_lines, len(lines))

        row_height = line_height * max_lines

        # --- Check page break ---
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()
            self.set_font('Arial', '', 7)

        x_start = self.get_x()
        y_start = self.get_y()

        # --- Draw row ---
        self.set_font('Arial', '', 7)
        for i, lines in enumerate(wrapped_data):
            self.set_xy(x_start, y_start)

            if i == 7 and fill_rgb:  # highlight Status col
                self.set_fill_color(*fill_rgb)
                self.rect(x_start, y_start, col_widths[i], row_height, style='DF')
            else:
                self.rect(x_start, y_start, col_widths[i], row_height)

            text_y = y_start + 1
            for line in lines:
                self.set_xy(x_start + 1, text_y)
                self.cell(col_widths[i] - 2, line_height, line, border=0)
                text_y += line_height

            x_start += col_widths[i]

        self.set_y(y_start + row_height)




# HEAD: TRAVEL ORDER
# HEAD: TRAVEL ORDER
class TravelOrderHeadPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'DEPARTMENT TRAVEL ORDER SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

        # Reset to normal font for table
        self.set_font('Arial', '', 7)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 5,
                  f"{self.department_name} | Page {self.page_no()} of {{nb}}",
                  align='C')

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit', 
            'Position Title', 
            'Full Name', 
            'Date Requested', 
            'Destination', 
            'Status', 
            'Current Stage', 
            'Remarks'
        ]
        col_widths = [35, 30, 35, 25, 50, 20, 30, 45]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

        self.set_font('Arial', '', 7)

    def add_travel_row(self, index, permit):
        line_height = 4
        col_widths = self.col_widths

        # Format name
        first_name = permit.get('first_name', '').strip()
        middle_name = permit.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        last_name = permit.get('last_name', '').strip()
        name = f"{last_name}, {first_name} {middle_initial}".strip()

        data = [
            permit.get('department', 'N/A'),
            permit.get('position', 'N/A'),
            name,
            permit.get('date_requested', 'N/A'),
            permit.get('destination', 'N/A'),
            permit.get('status', 'N/A'),
            permit.get('current_stage', '-'),
            permit.get('remarks', '-')
        ]

        # --- Word-wrap each cell ---
        wrapped_data = []
        max_lines = 1
        for i, text in enumerate(data):
            words = str(text).split(' ')
            lines, current_line = [], ''
            for word in words:
                if self.get_string_width(current_line + ' ' + word) < col_widths[i] - 2:
                    current_line += (' ' if current_line else '') + word
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            wrapped_data.append(lines)
            max_lines = max(max_lines, len(lines))

        row_height = line_height * max_lines

        # --- Check page break ---
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()

        # --- Draw row ---
        x_start = self.l_margin
        y_start = self.get_y()
        for i, lines in enumerate(wrapped_data):
            self.set_xy(x_start, y_start)
            self.rect(x_start, y_start, col_widths[i], row_height)

            text_y = y_start + 1
            for line in lines:
                self.set_xy(x_start + 1, text_y)
                self.cell(col_widths[i] - 2, line_height, line, border=0)
                text_y += line_height

            x_start += col_widths[i]

        self.set_y(y_start + row_height)





# HEAD: CLEARANCE FORM
class ClearanceSummaryheadPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap, y=8, w=logo_width)

        # Header text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        # Report title
        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, ' DEPARTMENT CLEARANCE FORM SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(
            0,
            5,
            f"{self.department_name} | Page {self.page_no()} of {{nb}}",
            align='C'
        )

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit',
            'Position Title',
            'Full Name',
            'Date Requested',
            'Purpose',
            'Status',
            'Current Stage',
            'Remarks'
        ]
        col_widths = [40, 40, 40, 25, 45, 20, 35, 27]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()
        self.set_font('Arial', '', 7)  # reset for data rows

    def add_clearance_row(self, index, permit):
        line_height = 4
        col_widths = self.col_widths

        # Extract data
        department = permit.get('department', 'N/A')
        position = permit.get('position', 'N/A')
        first_name = permit.get('first_name', '').strip()
        last_name = permit.get('last_name', '').strip()
        middle_name = permit.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        full_name = f"{last_name}, {first_name} {middle_initial}".strip()
        date_requested = permit.get('date_requested', 'N/A')
        purpose = permit.get('purpose', 'N/A')
        status = permit.get('status', 'N/A')
        current_stage = permit.get('current_stage', '-')
        remarks = permit.get('remarks', '-')

        data = [department, position, full_name,
                date_requested, purpose, status, current_stage, remarks]

        # Calculate required row height
        max_lines = 1
        for i, item in enumerate(data):
            text_width = self.get_string_width(str(item))
            lines = int(text_width / (col_widths[i] - 2)) + 1
            max_lines = max(max_lines, lines)

        row_height = line_height * max_lines

        # Page break check
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()

        y_start = self.get_y()
        x_start = self.l_margin

        # Draw each cell with consistent row height
        for i, item in enumerate(data):
            self.rect(x_start, y_start, col_widths[i], row_height)  # Border
            self.set_xy(x_start + 1, y_start + 1)  # Margin inside cell
            self.multi_cell(col_widths[i] - 2, line_height, str(item), align='L')
            x_start += col_widths[i]

        # Move cursor below row
        self.set_y(y_start + row_height)





# MAYORD DEPARTMENT PDF
# MAYUOR DEPARTMENT pdf leave
class MayorLeaveApplicationPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')

        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap, y=8, w=logo_width)

        # Title header
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'MAYOR REQUEST LEAVE APPLICATION SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

        # Reset font para hindi maapektuhan ang body
        self.set_font('Arial', '', 7)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 5,
                  f" {self.department_name} | Page {self.page_no()} of {{nb}}",
                  align='C')
        
    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit', 'Position Title', 'Full Name',
            'Date Requested', 'Type of Leave',
            'Credits Remaining', 'Paid Days',
            'Status', 'Current Stage', 'Remarks'
        ]

        # 297mm width (A4 Landscape) - 20mm margins = 277mm usable
        self.col_widths = [32, 28, 32, 22, 32, 30, 30, 24, 24, 23]

        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

        self.set_font('Arial', '', 7)

    def build_leave_row_data(permit):
        employee = permit.employee

        # --- Employee Info ---
        first_name = employee.first_name if employee else ""
        middle_name = employee.middle_name if employee else ""
        last_name = employee.last_name if employee else ""

        # --- Credits Remaining ---
        credits_remaining = "N/A"
        if employee and employee.credit_balance and permit.leave_detail:
            cb = employee.credit_balance
            leave_type = permit.leave_detail.leave_type.lower()

            if "vacation" in leave_type:
                credits_remaining = f"Vacation: {cb.vacation_remaining} credit(s)"
            elif "sick" in leave_type:
                credits_remaining = f"Sick: {cb.sick_remaining} credit(s)"
            else:
                credits_remaining = "N/A"

        # --- Paid Days ---
        paid_days = "N/A"
        if permit.leave_detail:
            leave = permit.leave_detail
            leave_type = leave.leave_type.lower()

            if "vacation" in leave_type or "sick" in leave_type:
                if leave.paid_days is not None:
                    if leave.paid_days > 0:
                        unpaid = max((leave.working_days or 0) - leave.paid_days, 0)
                        paid_days = f"{leave.paid_days} day(s) Paid"
                        if unpaid > 0:
                            paid_days += f" / {unpaid} Unpaid"
                    else:
                        paid_days = "Pending Approval"
                else:
                    # Estimated if not yet approved
                    if employee and employee.credit_balance:
                        cb = employee.credit_balance
                        requested_days = leave.working_days or 0
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

        return {
            "department": employee.department.name if employee and employee.department else "N/A",
            "position": (
                employee.permanent_details.position.title if employee and employee.permanent_details
                else employee.casual_details.position.title if employee and employee.casual_details
                else employee.job_order_details.position_title if employee and employee.job_order_details
                else "N/A"
            ),
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            "date_requested": str(permit.date_requested.date()) if permit.date_requested else "N/A",
            "leave_type": permit.leave_detail.leave_type if permit.leave_detail else "N/A",
            "credits_remaining": credits_remaining,
            "paid_days": paid_days,
            "status": permit.status or "-",
            "current_stage": permit.current_stage or "-",
            "remarks": permit.remarks or ""
        }



    def add_leave_row(self, data):
        line_height = 4
        col_widths = self.col_widths

        # Format employee name
        first_name = data.get('first_name', '').strip()
        middle_name = data.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        last_name = data.get('last_name', '').strip()
        name = f"{last_name}, {first_name} {middle_initial}".strip()

        row_data = [
            data.get('department', 'N/A'),
            data.get('position', 'N/A'),
            name,
            data.get('date_requested', 'N/A'),
            data.get('leave_type', 'N/A'),
            data.get('credits_remaining', 'N/A'),
            data.get('paid_days', 'N/A'),
            data.get('status', '-'),
            data.get('current_stage', '-'),
            data.get('remarks', '-')
        ]

        # Color map for Status
        status_color_map = {
            'Approved': (198, 239, 206),
            'Pending': (255, 235, 156),
            'Cancelled': (242, 220, 219),
            'Rejected': (255, 199, 206)
        }
        status = data.get('status', '-')
        fill_rgb = status_color_map.get(status, None)

        # --- Wrap text per column ---
        wrapped_data = []
        max_lines = 1
        for i, text in enumerate(row_data):
            words = str(text).split(' ')
            lines, current_line = [], ''
            for word in words:
                if self.get_string_width(current_line + ' ' + word) < col_widths[i] - 2:
                    current_line += (' ' if current_line else '') + word
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)

            wrapped_data.append(lines)
            max_lines = max(max_lines, len(lines))

        row_height = line_height * max_lines

        # --- Check page break ---
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()
            self.set_font('Arial', '', 7)

        x_start = self.get_x()
        y_start = self.get_y()

        # --- Draw row ---
        self.set_font('Arial', '', 7)
        for i, lines in enumerate(wrapped_data):
            self.set_xy(x_start, y_start)

            if i == 7 and fill_rgb:  # highlight Status col
                self.set_fill_color(*fill_rgb)
                self.rect(x_start, y_start, col_widths[i], row_height, style='DF')
            else:
                self.rect(x_start, y_start, col_widths[i], row_height)

            text_y = y_start + 1
            for line in lines:
                self.set_xy(x_start + 1, text_y)
                self.cell(col_widths[i] - 2, line_height, line, border=0)
                text_y += line_height

            x_start += col_widths[i]

        self.set_y(y_start + row_height)




# MAYOR : TRAVEL ORDER
# MAYOR: TRAVEL ORDER
class MayorTravelOrderPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, 'MAYOR REQUEST TRAVEL ORDER SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

        # Reset to normal font for table
        self.set_font('Arial', '', 7)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 5,
                  f"{self.department_name} | Page {self.page_no()} of {{nb}}",
                  align='C')

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit', 
            'Position Title', 
            'Full Name', 
            'Date Requested', 
            'Destination', 
            'Status', 
            'Current Stage', 
            'Remarks'
        ]
        col_widths = [35, 30, 35, 25, 50, 20, 30, 45]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()

        self.set_font('Arial', '', 7)

    def add_travel_row(self, index, permit):
        line_height = 4
        col_widths = self.col_widths

        # Format name
        first_name = permit.get('first_name', '').strip()
        middle_name = permit.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        last_name = permit.get('last_name', '').strip()
        name = f"{last_name}, {first_name} {middle_initial}".strip()

        data = [
            permit.get('department', 'N/A'),
            permit.get('position', 'N/A'),
            name,
            permit.get('date_requested', 'N/A'),
            permit.get('destination', 'N/A'),
            permit.get('status', 'N/A'),
            permit.get('current_stage', '-'),
            permit.get('remarks', '-')
        ]

        # --- Word-wrap each cell ---
        wrapped_data = []
        max_lines = 1
        for i, text in enumerate(data):
            words = str(text).split(' ')
            lines, current_line = [], ''
            for word in words:
                if self.get_string_width(current_line + ' ' + word) < col_widths[i] - 2:
                    current_line += (' ' if current_line else '') + word
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            wrapped_data.append(lines)
            max_lines = max(max_lines, len(lines))

        row_height = line_height * max_lines

        # --- Check page break ---
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()

        # --- Draw row ---
        x_start = self.l_margin
        y_start = self.get_y()
        for i, lines in enumerate(wrapped_data):
            self.set_xy(x_start, y_start)
            self.rect(x_start, y_start, col_widths[i], row_height)

            text_y = y_start + 1
            for line in lines:
                self.set_xy(x_start + 1, text_y)
                self.cell(col_widths[i] - 2, line_height, line, border=0)
                text_y += line_height

            x_start += col_widths[i]

        self.set_y(y_start + row_height)





# MAYOR MO: CLEARANCE FORM
class MayorClearanceSummaryPDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.department_name = department_name
        self.col_widths = []

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        # Logos
        self.image(os.path.join(base_path, 'victoria.png'),
                   x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'),
                   x=center_x + gap, y=8, w=logo_width)

        # Header text
        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        # Report title
        self.set_font('Arial', 'B', 14)
        self.cell(0, 7, ' MAYOR REQUEST CLEARANCE FORM SUMMARY REPORT', ln=True, align='C')
        self.ln(5)

    def footer(self):
        self.set_y(-12)
        self.set_font('Arial', 'I', 7)
        self.cell(
            0,
            5,
            f"{self.department_name} | Page {self.page_no()} of {{nb}}",
            align='C'
        )

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246)
        self.set_font('Arial', 'B', 8)

        headers = [
            'Organizational Unit',
            'Position Title',
            'Full Name',
            'Date Requested',
            'Purpose',
            'Status',
            'Current Stage',
            'Remarks'
        ]
        col_widths = [40, 40, 40, 25, 45, 20, 35, 27]
        self.col_widths = col_widths

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 6, header, border=1, align='C', fill=True)
        self.ln()
        self.set_font('Arial', '', 7)  # reset for data rows

    def add_clearance_row(self, index, permit):
        line_height = 4
        col_widths = self.col_widths

        # Extract data
        department = permit.get('department', 'N/A')
        position = permit.get('position', 'N/A')
        first_name = permit.get('first_name', '').strip()
        last_name = permit.get('last_name', '').strip()
        middle_name = permit.get('middle_name', '').strip()
        middle_initial = f"{middle_name[0]}." if middle_name else ""
        full_name = f"{last_name}, {first_name} {middle_initial}".strip()
        date_requested = permit.get('date_requested', 'N/A')
        purpose = permit.get('purpose', 'N/A')
        status = permit.get('status', 'N/A')
        current_stage = permit.get('current_stage', '-')
        remarks = permit.get('remarks', '-')

        data = [department, position, full_name,
                date_requested, purpose, status, current_stage, remarks]

        # Calculate required row height
        max_lines = 1
        for i, item in enumerate(data):
            text_width = self.get_string_width(str(item))
            lines = int(text_width / (col_widths[i] - 2)) + 1
            max_lines = max(max_lines, lines)

        row_height = line_height * max_lines

        # Page break check
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()
        # Save starting positions
        y_start = self.get_y()
        x_start = self.l_margin

        # Track the max y after writing each cell
        max_y = y_start

        for i, item in enumerate(data):
            self.set_xy(x_start, y_start)
            
            # Draw border later, after we know height
            # Write text
            self.multi_cell(col_widths[i], line_height, str(item), border=0)
            
            # Track bottom y of this cell
            max_y = max(max_y, self.get_y())

            x_start += col_widths[i]

        # Draw borders now using max_y
        x_start = self.l_margin
        for i, w in enumerate(col_widths):
            self.rect(x_start, y_start, w, max_y - y_start)
            x_start += w

        # Move cursor below the tallest cell
        self.set_y(max_y)




# IPCR HEAD DEPARTMEBT 
class HeadDeptIPCREmployeePDF(FPDF):
    def __init__(self, department_name, orientation='L', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.set_auto_page_break(auto=True, margin=15)
        self.department_name = department_name
        self.col_widths = []
        self.add_page()

    def header(self):
        base_path = os.path.join(current_app.root_path, 'static', 'img', 'landing')
        center_x = 148.5
        logo_width = 18
        gap = 30

        self.image(os.path.join(base_path, 'victoria.png'), x=center_x - gap - logo_width, y=8, w=logo_width)
        self.image(os.path.join(base_path, 'victoria1.png'), x=center_x + gap, y=8, w=logo_width)

        self.set_font('Arial', 'B', 10)
        self.cell(0, 5, 'Republic of the Philippines', ln=True, align='C')
        self.cell(0, 5, 'Province of Laguna', ln=True, align='C')
        self.cell(0, 5, 'Municipality of VICTORIA', ln=True, align='C')
        self.ln(3)

        self.set_font('Arial', 'B', 13)
        self.cell(0, 6, self.department_name, ln=True, align='C')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 6, 'Employee IPCR Status Report', ln=True, align='C')
        self.cell(0, 6, datetime.now().strftime('%B %d, %Y'), ln=True, align='C')
        self.ln(6)

    def draw_table_headers(self):
        self.set_fill_color(222, 234, 246) # dark header

        self.set_font('Arial', 'B', 8)

        headers = ['Employee Name', 'Position', 'Status', 'Graded', 'Date Submitted', 'Overall Grade']
        self.col_widths = [60, 70, 40, 30, 40, 30]  # adjusted widths

        for i, header in enumerate(headers):
            self.cell(self.col_widths[i], 7, header, border=1, align='C', fill=True)
        self.ln()
        self.set_text_color(0, 0, 0)  # reset text color

    def add_employee_row(self, emp, ipcr):
        line_height = 5
        self.set_font('Arial', '', 8)  # Ensure font is normal

        # Determine position safely
        if emp.permanent_details and emp.permanent_details.position:
            position = emp.permanent_details.position.title
        elif emp.casual_details and emp.casual_details.position:
            position = emp.casual_details.position.title
        else:
            position = 'Unknown'  # Exclude Job Orders

        # Determine status
        if ipcr:
            if not ipcr.submitted and not ipcr.graded:
                status = 'Returned'
            elif ipcr.submitted:
                status = 'Submitted'
            else:
                status = 'Draft'
            graded = 'Graded' if ipcr.graded else 'Not Graded'
            date_submitted = ipcr.date_submitted.strftime('%Y-%m-%d %I:%M %p') if ipcr.date_submitted else 'N/A'
            overall_grade = str(ipcr.final_average_rating) if ipcr.graded else '0'
        else:
            status = 'No IPCR'
            graded = 'Not Graded'
            date_submitted = 'N/A'
            overall_grade = '0'

        row_data = [
            f"{emp.first_name} {emp.last_name}",
            position,
            status,
            graded,
            date_submitted,
            overall_grade
        ]

        # Compute max lines for row
        max_lines = 1
        for i, text in enumerate(row_data):
            lines = self.multi_cell(self.col_widths[i], line_height, text, border=0, align='C', split_only=True)
            max_lines = max(max_lines, len(lines))
        
        row_height = line_height * max_lines

        # Check if the row fits in current page
        if self.get_y() + row_height > self.page_break_trigger:
            self.add_page()
            self.draw_table_headers()  # redraw header
            self.set_font('Arial', '', 8)  # reset font after adding page

        x_start = self.get_x()
        y_start = self.get_y()

        # Draw each cell
        for i, text in enumerate(row_data):
            self.set_xy(x_start, y_start)
            self.set_font('Arial', '', 8)  # ensure normal font
            self.multi_cell(self.col_widths[i], line_height, text, border=0, align='C')
            self.rect(x_start, y_start, self.col_widths[i], row_height)
            x_start += self.col_widths[i]

        self.set_y(y_start + row_height)
