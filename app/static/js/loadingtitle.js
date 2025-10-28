const positions = {
    "Office of the Municipal Mayor": [
    "Municipal Mayor",
    "Executive Assistant V",
    "Administrative Assistant V (Private Secretary)",
    "Security Agent II",
    "Licensing Officer I",
    "License Inspector I",
    "Supply Officer II",
    "Environmental Management Specialist II",
    "Administrative Assistant IV (Bookbinder IV)",
    "Administrative Assistant III (Bookbinder III)",
    "Administrative Aide III (Driver I)",
    "Administrative Aide I (Utility Worker I)",
    "Administrative Aide III (Utility Worker II)",
  ],

    "Office of the Municipal Vice Mayor": [
  "Municipal Vice Mayor",
  "Administrative Assistant V (Private Secretary)",
],

"Office of the Sangguniang Bayan": [
"Sangguniang Bayan Member",
"Sangguniang Bayan Member (LNB President)",
"Sangguniang Bayan Member (SK President)",
"Secretary to the Sangguniang Bayan I",
"Local Legislative Staff Officer I",
"Administrative Aide VI (Clerk III)",
"Local Legislative Staff Employee II",
"Administrative Aide IV (Driver II)",
"Administrative Aide III (Driver I)",
"Administrative Aide III (Utility Worker II)",
"Administrative Aide II (Bookbinder I)",
"Administrative Aide I (Utility Worker I)",
],

"Office of the Municipal Planning and Development Coordinator": [
"Municipal Planning and Development Coordinator I",
"Economic Researcher",
"Administrative Assistant I (Bookbinder III)",
"Administrative Aide VI (Clerk III)",
"Administrative Aide II (Bookbinder I)",
"Administrative Aide I (Utility Worker I)",
],

"Office of the Municipal Civil Registrar": [
"MUNICIPAL CIVIL REGISTRAR",
"REGISTRATION OFFICER II",
"REGISTRATION OFFICER I",
"ADMINISTRATIVE ASSISTANT II (Data Controller II)",
"ADMINISTRATIVE ASSISTANT II (Data Controller I)",
"ADMINISTRATIVE AIDE II (Book binder I)",
],

  "Office of the Municipal Budget Officer": [
  "Municipal Budget Officer I",
  "Administrative Officer II (Budget Officer I)",
  "Administrative Assistant II (Budget Assistant)",
  "Administrative Aide I (Utility Worker I)",
],

    "Office of the Municipal Assessor": [
  "Municipal Assessor",
  "Assistant Municipal Assessor",
  "Local Assessment Operations Officer I",
  "Local Assessment Operations Officer III",
  "Assessment Clerk III",
  "Assessment Clerk II",
  "Administrative Aide VI (Clerk II)",
  "Administrative Aide I (Utility Worker I)",
],


      "Office of the Municipal Accountant": [
  "Municipal Accountant",
  "Administrative Officer IV (Management and Audit Analyst II)",
  "Administrative Assistant III (Senior Bookkeeper)",
  "Administrative Assistant II (Bookkeeper)",
  "Administrative Aide VI (Accounting Clerk II)",
  "Administrative Aide II (Bookbinder I)",
  "Administrative Aide I (Utility Worker I)",
],

    "Office of the Municipal Treasurer": [
  "Municipal Treasurer",
  "Assistant Municipal Treasurer",
  "Local Revenue Collection Officer II",
  "Local Revenue Collection Officer I",
  "Revenue Collection Clerk II",
  "Revenue Collection Clerk III",
  "Administrative Aide VI (Clerk III)",
  "Administrative Aide IV (Cash Clerk I)",
  "Administrative Aide III (Utility Worker II)",
  "Administrative Aide II (Bookbinder I)",
  "Administrative Aide I (Utility Worker I)",
],

    "Office of the Municipal Health Officer": [
  "Municipal Health Officer",
  "Nurse II",
  "Nurse I",
  "Midwife III",
  "Midwife II",
  "Sanitation Inspector III",
  "Sanitation Inspector I",
  "Driver II",
  "Laboratory Technician",
  "Dental Aide",
  "Nursing Attendant I",
  "Barangay Health Aide",
  "Medical Technologist I",
  "Nutritionist-Dietitian II",
  "Nutritionist-Dietitian I",
  "Administrative Aide I (Utility Worker I)",
],

    "Office of the Municipal Social Welfare Development Officer": [
  "Municipal Social Welfare and Development Officer I",
  "Social Welfare Officer II",
  "Social Welfare Assistant",
  "Administrative Assistant I (Bookbinder III)",
  "Social Welfare Aide",
  "Daycare Worker I",
  "Administrative Aide I (Utility Worker I)",
],

    "Office of the Municipal Agriculturist": [
  "Municipal Agriculturist",
  "Agriculturist II",
  "Agricultural Technologist",
  "Meat Inspector I",
  "Farm Foreman",
  "Administrative Aide III (Utility Worker II)",
  "Farm Worker I",
],

    "Office of the Municipal Engineer": [
  "Municipal Engineer",
  "Engineer I",
  "Engineering Assistant",
  "Draftsman I",
  "Administrative Aide VI (Utility Foreman)",
  "Engineering Aide",
  "Administrative Aide III (Driver I)",
  "Administrative Aide I (Utility Worker I)",
],

    "Office of the Municipal Disaster Risk Reduction Management Officer": [
  "Municipal Government Department Head I (LDRRMO)",
  "Local Disaster Risk Reduction Management Officer II",
  "Local Disaster Risk Reduction Management Officer I",
  "Administrative Aide III (Driver I)",
  "Administrative Aide I (Utility Worker I)",
],

    "Office of the BPLO": [
  "BPLO Head / Business Permits and Licensing Officer",
  "Assistant BPLO Head (If Applicable)",
  "Licensing Officer I",
  "Licensing Officer II",
  "Business Permit Evaluator",
  "Business Permit Inspector",
  "Revenue Collection Clerk",
  "Administrative Officer",
  "Administrative Assistant I",
  "Administrative Assistant II",
  "Administrative Aide I",
  "Administrative Aide II",
  "Data Encoder (COS/JO)",
  "Customer Relations Assistant (COS/JO)",
  "Utility Worker (COS/JO)",
  "Messenger (COS/JO)",
],

    "Office of the Municipal Environment and Natural Resources Officer": [
      "Municipal Environment and Natural Resources Officer",
      "Assistant Municipal Environment and Natural Resources Officer",
      "Environmental Management Specialist I",
      "Environmental Management Specialist II",
      "Environmental Management Specialist III",
      "Forester",
      "Waste Management Coordinator",
      "Research Assistant / Researcher",
      "Technical Staff (COS/JO)",
      "Environmental Planner (if applicable)",
      "GIS Specialist / Technician",
      "Administrative Officer",
      "Administrative Assistant I",
      "Administrative Assistant II",
      "Administrative Aide I",
      "Administrative Aide II",
      "Data Encoder (COS/JO)",
      "Utility Worker (COS/JO)",
      "Messenger (COS/JO)"
    ],

    
  };
  
  function updatePositionOptions(orgUnitId, positionSelectId) {
    const orgUnitSelect = document.getElementById(orgUnitId);
    const positionSelect = document.getElementById(positionSelectId);
  
    if (orgUnitSelect && positionSelect) {
      orgUnitSelect.addEventListener('change', function() {
        const selectedOrg = this.value;
        
        // Clear options
        positionSelect.innerHTML = '';
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.disabled = true;
        defaultOption.selected = true;
        defaultOption.textContent = 'Select Position Title';
        positionSelect.appendChild(defaultOption);
  
        if (positions[selectedOrg]) {
          positions[selectedOrg].forEach(function(position) {
            const option = document.createElement('option');
            option.value = position;
            option.textContent = position;
            positionSelect.appendChild(option);
          });
        }
      });
    }
  }
  
  // Initialize for both modals
  updatePositionOptions('organizationalUnitSelect', 'positionTitleSelect');
