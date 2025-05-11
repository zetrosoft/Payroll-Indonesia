# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 10:37:34 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, add_to_date, date_diff
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

# Import BPJS calculation module
from payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs
from payroll_indonesia.override.salary_slip.bpjs_calculator import calculate_bpjs_components

# Import centralized tax calculation
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components

# Import standardized cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value, clear_cache

# Import constants
from payroll_indonesia.constants import (
    CACHE_MEDIUM,
    CACHE_LONG,
    MAX_DATE_DIFF,
    VALID_TAX_STATUS,
)

# Define exports for proper importing by other modules
__all__ = [
    "IndonesiaPayrollSalarySlip",
    "setup_fiscal_year_if_missing",
    "check_fiscal_year_setup",
    "clear_salary_slip_caches",
    "extend_salary_slip_functionality",
]


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll
    Extends hrms.payroll.doctype.salary_slip.salary_slip.SalarySlip

    Key features for Indonesian payroll:
    - BPJS calculations (Kesehatan, JHT, JP, JKK, JKM)
    - PPh 21 tax calculations with gross or gross-up methods
    - TER (Tarif Efektif Rata-rata) method support per PMK 168/PMK.010/2023
      - Implemented with 3 TER categories (TER A, TER B, TER C) based on PTKP
    - Integration with Employee Tax Summary
    """

    def validate(self):
        """
        Validate salary slip and calculate Indonesian components.
        Handles BPJS and tax calculations with appropriate error handling.
        """
        try:
            # Additional validations for Indonesian payroll
            self._validate_input_data()

            # Call parent validation after our validations
            super().validate()

            # Initialize additional fields
            self._initialize_payroll_fields()

            # Get employee document
            employee = self._get_employee_doc()

            # Additional validation for tax ID fields
            self._validate_tax_fields(employee)

            # Calculate BPJS components
            self._calculate_bpjs(employee)

            # Calculate tax components using centralized function
            calculate_tax_components(self, employee)

            # Final verifications
            self._verify_ter_settings()
            self._generate_tax_id_data(employee)
            self._check_or_create_fiscal_year()

            self.add_payroll_note("Validasi berhasil: Komponen BPJS dan Pajak dihitung.")

        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # For other errors, log and re-raise
            frappe.log_error(
                f"Error validating salary slip for {self.employee}: {str(e)}",
                "Salary Slip Validation Error",
            )
            frappe.throw(
                _("Error validating salary slip: {0}").format(str(e)), title=_("Validation Failed")
            )

    def _validate_input_data(self):
        """
        Validate basic input data for salary slip including:
        - Gross pay is non-negative
        - Posting date is within payroll entry range
        """
        # Validate gross pay is non-negative
        if hasattr(self, "gross_pay") and self.gross_pay < 0:
            frappe.throw(
                _("Gross pay cannot be negative. Current value: {0}").format(self.gross_pay),
                title=_("Invalid Gross Pay"),
            )

        # Validate posting date within payroll entry date range if linked to payroll entry
        if hasattr(self, "payroll_entry") and self.payroll_entry and hasattr(self, "posting_date"):
            try:
                payroll_entry_doc = frappe.get_doc("Payroll Entry", self.payroll_entry)
                start_date = getdate(payroll_entry_doc.start_date)
                end_date = getdate(payroll_entry_doc.end_date)
                posting_date = getdate(self.posting_date)

                # Check if posting date is within range
                if posting_date < start_date or posting_date > end_date:
                    frappe.throw(
                        _("Posting date {0} must be within payroll period {1} to {2}").format(
                            posting_date, start_date, end_date
                        ),
                        title=_("Invalid Posting Date"),
                    )

                # Check if the posting date is too far from the period
                days_diff = min(
                    date_diff(posting_date, start_date), date_diff(end_date, posting_date)
                )
                if days_diff > MAX_DATE_DIFF:  # Using constant instead of 31
                    frappe.throw(
                        _(
                            "Posting date {0} is too far from the payroll period ({1} to {2})"
                        ).format(posting_date, start_date, end_date),
                        title=_("Invalid Posting Date"),
                    )
            except Exception as e:
                if isinstance(e, frappe.exceptions.ValidationError):
                    raise

                frappe.log_error(
                    f"Error validating posting date: {str(e)}",
                    "Posting Date Validation Error",
                )
                frappe.throw(
                    _("Error validating posting date: {0}").format(str(e)),
                    title=_("Validation Error"),
                )

    def _validate_tax_fields(self, employee):
        """
        Validate required tax fields when PPh 21 component is present:
        - NPWP (Tax ID) should be present
        - Status Pajak (Tax Status) should be set
        """
        # Check if PPh 21 component exists in deductions
        has_pph21 = False
        if hasattr(self, "deductions"):
            for deduction in self.deductions:
                if deduction.salary_component == "PPh 21" and flt(deduction.amount) > 0:
                    has_pph21 = True
                    break

        # Only validate tax fields if PPh 21 is being calculated
        if has_pph21:
            # Validate NPWP exists
            npwp = getattr(self, "npwp", "") or getattr(employee, "npwp", "")
            if not npwp:
                frappe.throw(
                    _(
                        "NPWP (Tax ID) is required for PPh 21 calculation. Please update employee record."
                    ),
                    title=_("Missing NPWP"),
                )

            # Validate status_pajak (Tax Status) exists
            status_pajak = getattr(employee, "status_pajak", "")
            if not status_pajak:
                frappe.throw(
                    _(
                        "Tax status (Status Pajak) is required for PPh 21 calculation. Please update employee record."
                    ),
                    title=_("Missing Tax Status"),
                )

            # Check if status_pajak is valid
            if status_pajak not in VALID_TAX_STATUS:
                frappe.throw(
                    _("Invalid tax status: {0}. Should be one of: {1}").format(
                        status_pajak, ", ".join(VALID_TAX_STATUS)
                    ),
                    title=_("Invalid Tax Status"),
                )

    def _initialize_payroll_fields(self):
        """
        Initialize additional payroll fields with default values.
        Ensures all required fields exist with proper default values.
        """
        try:
            defaults = {
                "biaya_jabatan": 0,
                "netto": 0,
                "total_bpjs": 0,
                "is_using_ter": 0,
                "ter_rate": 0,
                "ter_category": "",
                "koreksi_pph21": 0,
                "payroll_note": "",
                "npwp": "",
                "ktp": "",
                "is_final_gabung_suami": 0,
            }

            # Set defaults for fields that don't exist or are None
            for field, default in defaults.items():
                if not hasattr(self, field) or getattr(self, field) is None:
                    setattr(self, field, default)

            return defaults
        except Exception as e:
            # This is a critical initialization step - throw
            frappe.log_error(
                f"Error initializing payroll fields for {self.name if hasattr(self, 'name') else 'New Salary Slip'}: {str(e)}",
                "Payroll Field Initialization Error",
            )
            frappe.throw(
                _("Could not initialize payroll fields: {0}").format(str(e)),
                title=_("Field Initialization Error"),
            )

    def _get_employee_doc(self):
        """
        Retrieves the complete Employee document for the current salary slip.
        Uses cache if available.

        Returns:
            frappe.Document: The employee document

        Raises:
            frappe.ValidationError: If employee cannot be found or retrieved
        """
        if not hasattr(self, "employee") or not self.employee:
            frappe.throw(
                _("Salary Slip must have an employee assigned"), title=_("Missing Employee")
            )

        try:
            # Check cache first
            cache_key = f"employee_doc:{self.employee}"
            employee_doc = get_cached_value(cache_key)

            if employee_doc is None:
                employee_doc = frappe.get_doc("Employee", self.employee)
                # Cache for 1 hour
                cache_value(cache_key, employee_doc, CACHE_MEDIUM)

            return employee_doc
        except Exception as e:
            # Critical error - can't continue without employee
            frappe.log_error(
                f"Error retrieving employee {self.employee} for salary slip {self.name if hasattr(self, 'name') else 'New'}: {str(e)}",
                "Employee Retrieval Error",
            )
            frappe.throw(
                _("Could not retrieve Employee {0}: {1}").format(self.employee, str(e)),
                title=_("Employee Not Found"),
            )

    def _calculate_bpjs(self, employee):
        """
        Calculate BPJS (Social Security) components using the external calculation module.
        Uses the centralized BPJS calculator module.

        Args:
            employee (frappe.Document): Employee document for BPJS calculation
        """
        try:
            # Get base salary for BPJS calculation
            base_salary = self._get_base_salary_for_bpjs()

            # Use the bpjs_calculator to calculate and update components
            calculate_bpjs_components(self, employee, base_salary)
        except Exception as e:
            # Critical error - BPJS calculation is required
            frappe.log_error(
                f"Error calculating BPJS for {self.employee}: {str(e)}",
                "BPJS Calculation Error",
            )
            frappe.throw(
                _("Failed to calculate BPJS components: {0}").format(str(e)),
                title=_("BPJS Calculation Failed"),
            )

    def _get_base_salary_for_bpjs(self):
        """
        Get the base salary amount to use for BPJS calculations.
        Uses gross pay or falls back to a configured default.

        Returns:
            float: Salary amount to use for BPJS calculations
        """
        try:
            # Use gross pay as the default base for BPJS
            base_salary = self.gross_pay if hasattr(self, "gross_pay") and self.gross_pay else 0

            # If no gross pay, try to calculate from earnings
            if not base_salary and hasattr(self, "earnings"):
                for earning in self.earnings:
                    if earning.salary_component == "Gaji Pokok":
                        base_salary += earning.amount

            # Log the base salary used
            self.add_payroll_note(f"Base salary for BPJS: {base_salary}")

            return base_salary
        except Exception as e:
            # Non-critical error - log and return 0
            frappe.log_error(
                f"Error calculating base salary for BPJS in {self.name if hasattr(self, 'name') else 'New'}: {str(e)}",
                "Base Salary Calculation Error",
            )
            frappe.msgprint(
                _("Warning: Could not determine base salary for BPJS calculation. Using 0."),
                indicator="orange",
            )
            return 0

    def _verify_ter_settings(self):
        """
        Verify TER settings are correctly applied if using TER method.
        """
        try:
            if getattr(self, "is_using_ter", 0):
                # Verify TER category is set - warning only
                if not getattr(self, "ter_category", ""):
                    self.add_payroll_note("WARNING: Using TER but no category set")
                    frappe.msgprint(_("Warning: Using TER but no category set"), indicator="orange")

                # Verify TER rate is set - warning only
                if not getattr(self, "ter_rate", 0):
                    self.add_payroll_note("WARNING: Using TER but no rate set")
                    frappe.msgprint(_("Warning: Using TER but no rate set"), indicator="orange")
        except Exception as e:
            # Non-critical error - log and continue
            frappe.log_error(
                f"Error verifying TER settings for {self.name if hasattr(self, 'name') else 'New'}: {str(e)}",
                "TER Verification Warning",
            )
            frappe.msgprint(_("Warning: Could not verify TER settings."), indicator="orange")

    def _generate_tax_id_data(self, employee):
        """
        Extract and store tax-related IDs from the employee record.

        Args:
            employee (frappe.Document): Employee document
        """
        try:
            # Copy NPWP from employee if available
            if hasattr(employee, "npwp") and employee.npwp:
                self.npwp = employee.npwp

            # Copy KTP from employee if available
            if hasattr(employee, "ktp") and employee.ktp:
                self.ktp = employee.ktp
        except Exception as e:
            # Non-critical error - log and continue
            frappe.log_error(
                f"Error extracting tax IDs from employee {employee.name} for salary slip {self.name if hasattr(self, 'name') else 'New'}: {str(e)}",
                "Tax ID Extraction Warning",
            )
            frappe.msgprint(
                _("Warning: Could not retrieve tax identification from employee record."),
                indicator="orange",
            )

    def _check_or_create_fiscal_year(self):
        """
        Check if a fiscal year exists for the salary slip period
        and create one if missing.
        """
        try:
            if hasattr(self, "start_date"):
                cache_key = f"fiscal_year:{getdate(self.start_date)}"
                fiscal_year = get_cached_value(cache_key)

                if fiscal_year is None:
                    fiscal_year = check_fiscal_year_setup(self.start_date)
                    # Cache for 24 hours - fiscal years don't change often
                    cache_value(cache_key, fiscal_year, CACHE_LONG)

                if fiscal_year.get("status") == "error":
                    # Try to create fiscal year - non-critical operation
                    setup_result = setup_fiscal_year_if_missing(self.start_date)
                    self.add_payroll_note(
                        f"Fiscal year setup: {setup_result.get('status', 'unknown')}"
                    )
                    # Update cache with new fiscal year
                    cache_value(
                        cache_key,
                        {"status": "ok", "fiscal_year": setup_result.get("fiscal_year")},
                        CACHE_LONG,
                    )
        except Exception as e:
            # Non-critical error - log and continue
            frappe.log_error(
                f"Error checking or creating fiscal year for {self.start_date if hasattr(self, 'start_date') else 'unknown date'}: {str(e)}",
                "Fiscal Year Check Warning",
            )
            frappe.msgprint(
                _("Warning: Could not verify or create fiscal year."), indicator="orange"
            )

    def add_payroll_note(self, note, section=None):
        """
        Add note to payroll_note field with optional section header.

        Args:
            note (str): Note text to add
            section (str, optional): Section header for the note
        """
        try:
            if not hasattr(self, "payroll_note"):
                self.payroll_note = ""

            # Add section header if specified
            if section:
                formatted_note = f"\n\n=== {section} ===\n{note}"
            else:
                formatted_note = note

            # Add new note
            if self.payroll_note:
                self.payroll_note += f"\n{formatted_note}"
            else:
                self.payroll_note = formatted_note

            # Use db_set to avoid another full save
            self.db_set("payroll_note", self.payroll_note, update_modified=False)
        except Exception as e:
            # Non-critical error - log and continue
            frappe.log_error(
                f"Error adding payroll note to {self.name if hasattr(self, 'name') else 'New'}: {str(e)}",
                "Payroll Note Warning",
            )
            # No msgprint here since this is a background operation

    def on_submit(self):
        """
        Handle actions when salary slip is submitted.
        Updates related tax and benefit documents.
        """
        try:
            # Call parent handler first
            super().on_submit()

            # Verify TER settings before submit
            self._verify_ter_settings()

            # Create or update dependent documents
            self._update_tax_summary()
        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # Critical error during submission - throw
            frappe.log_error(
                f"Error during salary slip submission for {self.name if hasattr(self, 'name') else 'New'}: {str(e)}",
                "Submission Error",
            )
            frappe.throw(
                _("Error during salary slip submission: {0}").format(str(e)),
                title=_("Submission Failed"),
            )

    def _update_tax_summary(self):
        """
        Update or create employee tax summary document.
        """
        # Implementation for updating tax summary
        # Logic will depend on your specific requirements
        pass

    def _queue_document_creation(self):
        """
        Queue background jobs for document creation after submission.

        TODO: Implement background job creation for dependent documents
        that need to be generated when a salary slip is submitted.
        """
        # This is a placeholder for future implementation
        pass

    def on_cancel(self):
        """
        Handle actions when salary slip is cancelled.
        Updates or reverts related documents.
        """
        try:
            # Call parent handler first
            super().on_cancel()

            # Update or revert dependent documents
            self._revert_tax_summary()
        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # Critical error during cancellation - throw
            frappe.log_error(
                f"Error during salary slip cancellation for {self.name}: {str(e)}",
                "Cancellation Error",
            )
            frappe.throw(
                _("Error during salary slip cancellation: {0}").format(str(e)),
                title=_("Cancellation Failed"),
            )

    def _revert_tax_summary(self):
        """
        Revert changes to employee tax summary when salary slip is cancelled.
        """
        # Implementation for reverting tax summary
        # Logic will depend on your specific requirements
        pass

    def _queue_document_updates_on_cancel(self):
        """
        Queue background jobs for document updates after cancellation.

        TODO: Implement background job creation for dependent documents
        that need to be updated when a salary slip is cancelled.
        """
        # This is a placeholder for future implementation
        pass


# NEW APPROACH: Use hooks and monkey patching instead of full controller override
def extend_salary_slip_functionality():
    """
    Safely extend SalarySlip functionality without replacing the entire controller.
    This approach uses selective monkey patching of specific methods while preserving
    the original controller class.
    """
    try:
        # Get the original SalarySlip class
        original_class = frappe.get_doc_class("Salary Slip")

        # Dictionary mapping original methods to our enhanced methods
        method_mapping = {
            "validate": _enhance_validate,
            "on_submit": _enhance_on_submit,
            "on_cancel": _enhance_on_cancel,
            # Add any other methods you need to enhance
        }

        # Apply the enhancements
        for method_name, enhancement_func in method_mapping.items():
            if hasattr(original_class, method_name):
                original_method = getattr(original_class, method_name)
                enhanced_method = _create_enhanced_method(original_method, enhancement_func)
                setattr(original_class, method_name, enhanced_method)

        # Log successful enhancement
        frappe.log_error(
            "Successfully enhanced SalarySlip controller with Indonesian payroll features",
            "Controller Enhancement",
        )

        return True
    except Exception as e:
        # Non-critical error with monkey patching - log but don't throw
        frappe.log_error(
            f"Error enhancing SalarySlip controller: {str(e)}",
            "Controller Enhancement Error",
        )
        frappe.msgprint(
            _(
                "Warning: Could not enhance SalarySlip controller. Some Indonesian payroll features may not be available."
            ),
            indicator="red",
        )
        return False


def _create_enhanced_method(original_method, enhancement_func):
    """
    Creates an enhanced method that calls the original method and then applies
    our enhancement function.

    Args:
        original_method: The original class method
        enhancement_func: Our enhancement function that will be called after the original

    Returns:
        A new function that combines both behaviors
    """

    def enhanced_method(self, *args, **kwargs):
        # First apply our additional validations if this is the validate method
        if original_method.__name__ == "validate":
            _validate_input_data_standalone(self)
            employee = _get_employee_doc_standalone(self)
            if employee:
                _validate_tax_fields_standalone(self, employee)

        # Call the original method
        result = original_method(self, *args, **kwargs)

        # Then apply our enhancement
        try:
            enhancement_func(self, *args, **kwargs)
        except Exception as e:
            # Log error but don't break the original functionality
            frappe.log_error(
                f"Error in enhancement for {self.name if hasattr(self, 'name') else 'New Document'}: {str(e)}",
                "Enhancement Function Error",
            )
            frappe.msgprint(
                _("Warning: Error in salary slip enhancement: {0}").format(str(e)),
                indicator="orange",
            )

        # Return the original result
        return result

    # Copy the original method's docstring and attributes
    if hasattr(original_method, "__doc__"):
        enhanced_method.__doc__ = original_method.__doc__

    # Add a note that this is an enhanced version
    if enhanced_method.__doc__:
        enhanced_method.__doc__ += "\n\nEnhanced with Indonesian payroll features."
    else:
        enhanced_method.__doc__ = "Enhanced with Indonesian payroll features."

    return enhanced_method


# Standalone validation functions for use with enhanced methods
def _validate_input_data_standalone(doc):
    """
    Validate basic input data for salary slip including:
    - Gross pay is non-negative
    - Posting date is within payroll entry range

    For use with the enhanced validate method.
    """
    # Validate gross pay is non-negative
    if hasattr(doc, "gross_pay") and doc.gross_pay < 0:
        frappe.throw(
            _("Gross pay cannot be negative. Current value: {0}").format(doc.gross_pay),
            title=_("Invalid Gross Pay"),
        )

    # Validate posting date within payroll entry date range if linked to payroll entry
    if hasattr(doc, "payroll_entry") and doc.payroll_entry and hasattr(doc, "posting_date"):
        try:
            payroll_entry_doc = frappe.get_doc("Payroll Entry", doc.payroll_entry)
            start_date = getdate(payroll_entry_doc.start_date)
            end_date = getdate(payroll_entry_doc.end_date)
            posting_date = getdate(doc.posting_date)

            # Check if posting date is within range
            if posting_date < start_date or posting_date > end_date:
                frappe.throw(
                    _("Posting date {0} must be within payroll period {1} to {2}").format(
                        posting_date, start_date, end_date
                    ),
                    title=_("Invalid Posting Date"),
                )

            # Check if the posting date is too far from the period
            days_diff = min(date_diff(posting_date, start_date), date_diff(end_date, posting_date))
            if days_diff > MAX_DATE_DIFF:
                frappe.throw(
                    _("Posting date {0} is too far from the payroll period ({1} to {2})").format(
                        posting_date, start_date, end_date
                    ),
                    title=_("Invalid Posting Date"),
                )
        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            frappe.log_error(
                f"Error validating posting date: {str(e)}", "Posting Date Validation Error"
            )
            frappe.throw(
                _("Error validating posting date: {0}").format(str(e)), title=_("Validation Error")
            )


def _get_employee_doc_standalone(doc):
    """
    Get employee document for standalone validation.

    Returns:
        frappe.Document: The employee document or None if not found
    """
    if hasattr(doc, "employee") and doc.employee:
        try:
            # Check cache first
            cache_key = f"employee_doc:{doc.employee}"
            employee_doc = get_cached_value(cache_key)

            if employee_doc is None:
                employee_doc = frappe.get_doc("Employee", doc.employee)
                # Cache for 1 hour
                cache_value(cache_key, employee_doc, CACHE_MEDIUM)

            return employee_doc
        except Exception as e:
            frappe.log_error(
                f"Error retrieving employee {doc.employee} for standalone validation: {str(e)}",
                "Employee Retrieval Warning",
            )
    return None


def _validate_tax_fields_standalone(doc, employee):
    """
    Validate required tax fields when PPh 21 component is present:
    - NPWP (Tax ID) should be present
    - Status Pajak (Tax Status) should be set

    For use with the enhanced validate method.
    """
    # Check if PPh 21 component exists in deductions
    has_pph21 = False
    if hasattr(doc, "deductions"):
        for deduction in doc.deductions:
            if deduction.salary_component == "PPh 21" and flt(deduction.amount) > 0:
                has_pph21 = True
                break

    # Only validate tax fields if PPh 21 is being calculated
    if has_pph21:
        # Validate NPWP exists
        npwp = getattr(doc, "npwp", "") or getattr(employee, "npwp", "")
        if not npwp:
            frappe.throw(
                _(
                    "NPWP (Tax ID) is required for PPh 21 calculation. Please update employee record."
                ),
                title=_("Missing NPWP"),
            )

        # Validate status_pajak (Tax Status) exists
        status_pajak = getattr(employee, "status_pajak", "")
        if not status_pajak:
            frappe.throw(
                _(
                    "Tax status (Status Pajak) is required for PPh 21 calculation. Please update employee record."
                ),
                title=_("Missing Tax Status"),
            )

        # Check if status_pajak is valid
        if status_pajak not in VALID_TAX_STATUS:
            frappe.throw(
                _("Invalid tax status: {0}. Should be one of: {1}").format(
                    status_pajak, ", ".join(VALID_TAX_STATUS)
                ),
                title=_("Invalid Tax Status"),
            )


def _enhance_validate(doc, *args, **kwargs):
    """
    Enhancement function for the validate method.
    This will be called after the original validate method.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Only proceed for the correct doctype
        if doc.doctype != "Salary Slip":
            return

        # Create a temporary IndonesiaPayrollSalarySlip to use its methods
        temp = IndonesiaPayrollSalarySlip(doc.as_dict())

        # Initialize additional fields
        temp._initialize_payroll_fields()

        # Get employee document using cache
        cache_key = f"employee_doc:{doc.employee}"
        employee = get_cached_value(cache_key)

        if employee is None:
            employee = temp._get_employee_doc()
            # Cache already handled in _get_employee_doc()

        # Calculate BPJS components
        temp._calculate_bpjs(employee)

        # Calculate tax components using centralized function
        calculate_tax_components(temp, employee)

        # Final verifications
        temp._verify_ter_settings()
        temp._generate_tax_id_data(employee)
        temp._check_or_create_fiscal_year()

        # Copy back all the fields that were calculated
        for field in [
            "biaya_jabatan",
            "netto",
            "total_bpjs",
            "is_using_ter",
            "ter_rate",
            "ter_category",
            "koreksi_pph21",
            "payroll_note",
            "npwp",
            "ktp",
            "is_final_gabung_suami",
        ]:
            if hasattr(temp, field):
                setattr(doc, field, getattr(temp, field))
                # Use db_set for immediate persistence
                doc.db_set(field, getattr(temp, field), update_modified=False)

        # Copy child table changes (earnings and deductions)
        for table_name in ["earnings", "deductions"]:
            if hasattr(temp, table_name) and hasattr(doc, table_name):
                # Get component mappings from temp doc
                temp_components = {d.salary_component: d for d in getattr(temp, table_name)}

                # Update or add components in original doc
                for component_name, temp_row in temp_components.items():
                    # Find if component exists in original doc
                    found = False
                    for row in getattr(doc, table_name):
                        if row.salary_component == component_name:
                            # Update values
                            row.amount = temp_row.amount
                            found = True
                            break

                    # If not found, add it
                    if not found:
                        new_row = frappe.new_doc("Salary Detail")
                        for field in temp_row.as_dict():
                            if field not in ["name", "creation", "modified", "owner"]:
                                setattr(new_row, field, getattr(temp_row, field))
                        getattr(doc, table_name).append(new_row)

        # Add note about successful validation
        if hasattr(doc, "payroll_note"):
            note = "Validasi berhasil: Komponen BPJS dan Pajak dihitung."
            if doc.payroll_note:
                doc.payroll_note += f"\n{note}"
            else:
                doc.payroll_note = note
            doc.db_set("payroll_note", doc.payroll_note, update_modified=False)

    except Exception as e:
        # Non-critical error in enhancement - log and continue
        frappe.log_error(
            f"Error in _enhance_validate for {doc.name if hasattr(doc, 'name') else 'New Salary Slip'}: {str(e)}",
            "Salary Slip Enhancement Error",
        )
        frappe.msgprint(
            _(
                "Warning: Error enhancing salary slip validation. Some features may not be available."
            ),
            indicator="orange",
        )


def _enhance_on_submit(doc, *args, **kwargs):
    """
    Enhancement function for the on_submit method.
    This will be called after the original on_submit method.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Only proceed for the correct doctype
        if doc.doctype != "Salary Slip":
            return

        # Create a temporary IndonesiaPayrollSalarySlip
        temp = IndonesiaPayrollSalarySlip(doc.as_dict())

        # Verify TER settings before submit
        temp._verify_ter_settings()

        # Queue document creation
        temp._queue_document_creation()

        # Copy back any updated fields
        if hasattr(temp, "payroll_note"):
            doc.payroll_note = temp.payroll_note
            doc.db_set("payroll_note", temp.payroll_note, update_modified=False)

    except Exception as e:
        # Non-critical error in enhancement - log and continue
        frappe.log_error(
            f"Error in _enhance_on_submit for {doc.name}: {str(e)}",
            "Submit Enhancement Error",
        )
        frappe.msgprint(
            _(
                "Warning: Error enhancing salary slip submission. Some features may not be available."
            ),
            indicator="orange",
        )


def _enhance_on_cancel(doc, *args, **kwargs):
    """
    Enhancement function for the on_cancel method.
    This will be called after the original on_cancel method.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Only proceed for the correct doctype
        if doc.doctype != "Salary Slip":
            return

        # Create a temporary IndonesiaPayrollSalarySlip
        temp = IndonesiaPayrollSalarySlip(doc.as_dict())

        # Queue document updates on cancel
        temp._queue_document_updates_on_cancel()

        # Copy back any updated fields
        if hasattr(temp, "payroll_note"):
            doc.payroll_note = temp.payroll_note
            doc.db_set("payroll_note", temp.payroll_note, update_modified=False)

    except Exception as e:
        # Non-critical error in enhancement - log and continue
        frappe.log_error(
            f"Error in _enhance_on_cancel for {doc.name}: {str(e)}",
            "Cancel Enhancement Error",
        )
        frappe.msgprint(
            _(
                "Warning: Error enhancing salary slip cancellation. Some features may not be available."
            ),
            indicator="orange",
        )


# Cache management functions
def clear_salary_slip_caches():
    """
    Clear salary slip related caches to prevent memory bloat.

    This function is designed to be called by the scheduler (daily or cron) only.
    It does NOT schedule itself to avoid race conditions.

    If you need to call this function manually, use:

        frappe.enqueue(method="payroll_indonesia.override.salary_slip.clear_salary_slip_caches",
                      queue='long', job_name='clear_payroll_caches')

    The function is configured in hooks.py to run automatically at scheduled intervals.
    """
    try:
        # Clear caches using standardized cache_utils
        prefixes_to_clear = [
            "employee_doc:",
            "fiscal_year:",
            "salary_slip:",
            "ytd_tax:",
            "ter_category:",
            "ter_rate:",
        ]

        # Log the start of cache clearing operation
        frappe.log_error(
            f"Starting cache clearing operation for prefixes: {', '.join(prefixes_to_clear)}",
            "Salary Slip Cache Clearing",
        )

        cleared_count = 0
        for prefix in prefixes_to_clear:
            count = clear_cache(prefix)
            cleared_count += count or 0

        # Log completion
        frappe.log_error(
            f"Cleared {cleared_count} cached items from salary slip caches",
            "Salary Slip Cache Clearing Complete",
        )

        return {"status": "success", "cleared_count": cleared_count, "prefixes": prefixes_to_clear}

    except Exception as e:
        # Non-critical error - log and continue
        frappe.log_error(f"Error clearing salary slip caches: {str(e)}", "Cache Clearing Error")

        return {"status": "error", "message": str(e)}


# Helper function for fiscal year management
def check_fiscal_year_setup(date_str=None):
    """
    Check if fiscal years are properly set up for a given date.

    Args:
        date_str (str, optional): Date string to check fiscal year for. Uses current date if not provided.

    Returns:
        dict: Status and message regarding fiscal year setup
    """
    try:
        test_date = getdate(date_str) if date_str else getdate()

        # Use cache for fiscal year lookup
        cache_key = f"fiscal_year_check:{test_date}"
        cached_result = get_cached_value(cache_key)

        if cached_result is not None:
            return cached_result

        fiscal_year = frappe.db.get_value(
            "Fiscal Year",
            {"year_start_date": ["<=", test_date], "year_end_date": [">=", test_date]},
        )

        if not fiscal_year:
            result = {
                "status": "error",
                "message": f"No active Fiscal Year found for date {test_date}",
                "solution": "Create a Fiscal Year that includes this date in Company settings",
            }
            # Cache negative result for 1 hour
            cache_value(cache_key, result, CACHE_MEDIUM)
            return result

        result = {"status": "ok", "fiscal_year": fiscal_year}
        # Cache positive result for 24 hours
        cache_value(cache_key, result, CACHE_LONG)
        return result
    except Exception as e:
        # Non-critical error - return error status
        frappe.log_error(
            f"Error checking fiscal year setup for date {date_str if date_str else 'current date'}: {str(e)}",
            "Fiscal Year Check Error",
        )
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def setup_fiscal_year_if_missing(date_str=None):
    """
    Automatically set up a fiscal year if missing for a given date.

    Args:
        date_str (str, optional): Date string to create fiscal year for. Uses current date if not provided.

    Returns:
        dict: Status and details of the fiscal year setup operation
    """
    try:
        test_date = getdate(date_str) if date_str else getdate()

        # Check cache first
        cache_key = f"fiscal_year_setup:{test_date}"
        cached_result = get_cached_value(cache_key)

        if cached_result is not None:
            return cached_result

        # Check if fiscal year exists
        fiscal_year = frappe.db.get_value(
            "Fiscal Year",
            {"year_start_date": ["<=", test_date], "year_end_date": [">=", test_date]},
        )

        if fiscal_year:
            result = {"status": "exists", "fiscal_year": fiscal_year}
            # Cache result for 24 hours
            cache_value(cache_key, result, CACHE_LONG)
            return result

        # Create a new fiscal year
        year = test_date.year
        fy_start_month = frappe.db.get_single_value("Accounts Settings", "fy_start_date_is") or 1

        # Create fiscal year based on start month
        if fy_start_month == 1:
            # Calendar year
            start_date = getdate(f"{year}-01-01")
            end_date = getdate(f"{year}-12-31")
        else:
            # Custom fiscal year
            start_date = getdate(f"{year}-{fy_start_month:02d}-01")
            if start_date > test_date:
                start_date = add_to_date(start_date, years=-1)
            end_date = add_to_date(start_date, days=-1, years=1)

        # Create the fiscal year
        new_fy = frappe.new_doc("Fiscal Year")
        new_fy.year = f"{start_date.year}"
        if start_date.year != end_date.year:
            new_fy.year += f"-{end_date.year}"
        new_fy.year_start_date = start_date
        new_fy.year_end_date = end_date
        new_fy.save()

        result = {
            "status": "created",
            "fiscal_year": new_fy.name,
            "year": new_fy.year,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        }

        # Cache result for 24 hours
        cache_value(cache_key, result, CACHE_LONG)
        return result

    except Exception as e:
        # This is a critical operation for payroll - throw if user invoked
        # but just return error if called programmatically
        frappe.log_error(f"Error setting up fiscal year: {str(e)}", "Fiscal Year Setup Error")
        if (
            frappe.local.form_dict.cmd
            == "payroll_indonesia.override.salary_slip.setup_fiscal_year_if_missing"
        ):
            frappe.throw(
                _("Failed to set up fiscal year: {0}").format(str(e)),
                title=_("Fiscal Year Setup Failed"),
            )
        return {"status": "error", "message": str(e)}


# Hook to apply our extensions when the module is loaded
def setup_hooks():
    """Set up our hooks and monkey patches when the module is loaded"""
    try:
        extend_salary_slip_functionality()
        # NOTE: We no longer call clear_salary_slip_caches() here
        # It's now managed by the scheduler in hooks.py
    except Exception as e:
        # Non-critical error during setup - log but continue
        frappe.log_error(f"Error setting up hooks for salary slip: {str(e)}", "Hook Setup Error")


# Apply extensions
setup_hooks()
