document.addEventListener('DOMContentLoaded', function () {

    // Universal reusable validation function
    function attachValidation(formSelector, validationRules) {
        const form = document.querySelector(formSelector);

        if (!form) {
            console.error(`Form with selector "${formSelector}" not found.`);
            return;
        }

        form.addEventListener('submit', function (event) {
            event.preventDefault();  // Stop default form submission

            // Clear previous errors
            const errorMessages = form.querySelectorAll('.invalid-feedback');
            errorMessages.forEach(message => message.remove());
            const allInputs = form.querySelectorAll('.form-control, .form-select');
            allInputs.forEach(input => input.classList.remove('is-invalid'));

            let isValid = true;

            function showError(inputElement, message) {
                const errorMessage = document.createElement('div');
                errorMessage.classList.add('invalid-feedback');
                errorMessage.textContent = message;
                inputElement.classList.add('is-invalid');
                inputElement.parentElement.appendChild(errorMessage);
            }

            function addRealTimeValidation(inputElement, validatorFn, errorMessage) {
                inputElement.addEventListener('input', function () {
                    const existingError = inputElement.parentElement.querySelector('.invalid-feedback');
                    if (!validatorFn(inputElement)) {
                        if (!existingError) {
                            showError(inputElement, errorMessage);
                        }
                    } else {
                        inputElement.classList.remove('is-invalid');
                        if (existingError) existingError.remove();
                    }
                });
            }

            function validateRequired(input) {
                return input && input.value.trim() !== "";
            }

            function validateNumber(input) {
                return input && !isNaN(input.value) && input.value.trim() !== "";
            }

            function validateField(input, validatorFn, fieldName) {
                if (!validatorFn(input)) {
                    showError(input, `Please enter a valid ${fieldName}.`);
                    return false;
                }
                return true;
            }

            validationRules.forEach(rule => {
                if (!validateField(rule.input, rule.validator, rule.fieldName)) {
                    isValid = false;
                }
                addRealTimeValidation(rule.input, rule.validator, `Please enter a valid ${rule.fieldName}.`);
            });

            if (isValid) {
                form.submit();
            }
        });
    }

    // === Example Usage ===

    // 1. For the "Add Casual Employee" modal
    attachValidation('#addCasualEmployeeModal form', [
        { input: document.querySelector('#addCasualEmployeeModal form [name="last_name"]'), validator: validateRequired, fieldName: "Last Name" },
        { input: document.querySelector('#addCasualEmployeeModal form [name="first_name"]'), validator: validateRequired, fieldName: "First Name" },
        { input: document.querySelector('#addCasualEmployeeModal form [name="position_title"]'), validator: validateRequired, fieldName: "Position Title" },
        { input: document.querySelector('#addCasualEmployeeModal form [name="salary_grade"]'), validator: validateNumber, fieldName: "Salary Grade" },
        { input: document.querySelector('#addCasualEmployeeModal form [name="daily_wage"]'), validator: validateNumber, fieldName: "Daily Wage" },
        { input: document.querySelector('#addCasualEmployeeModal form [name="employment_from"]'), validator: validateRequired, fieldName: "Employment From" },
        { input: document.querySelector('#addCasualEmployeeModal form [name="employment_to"]'), validator: validateRequired, fieldName: "Employment To" }
    ]);

    // 2. Example: If you add another modal form later
    /*
    attachValidation('#addRegularEmployeeModal form', [
        { input: document.querySelector('#addRegularEmployeeModal form [name="last_name"]'), validator: validateRequired, fieldName: "Last Name" },
        { input: document.querySelector('#addRegularEmployeeModal form [name="first_name"]'), validator: validateRequired, fieldName: "First Name" },
        { input: document.querySelector('#addRegularEmployeeModal form [name="position_title"]'), validator: validateRequired, fieldName: "Position Title" },
        { input: document.querySelector('#addRegularEmployeeModal form [name="salary_grade"]'), validator: validateNumber, fieldName: "Salary Grade" }
    ]);
    */
});