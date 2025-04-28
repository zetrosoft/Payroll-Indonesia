# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-28 02:30:00 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, cint, now_datetime

# Debug function for error tracking
def debug_log(message, module_name="Employee Tax Summary"):
    """Log debug message with timestamp and additional info"""
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    frappe.log_error(f"[{timestamp}] {message}", module_name)

class EmployeeTaxSummary(Document):
    def validate(self):
        """Validate the employee tax summary with improved error handling"""
        try:
            # Validate required fields
            self.validate_required_fields()
            
            # Check for duplicates
            self.validate_duplicate()
            
            # Set document title
            self.set_title()
            
            # Calculate YTD from monthly entries
            self.calculate_ytd_from_monthly()
            
            # Validate monthly details
            self.validate_monthly_details()
            
        except Exception as e:
            frappe.log_error(
                f"Error validating Employee Tax Summary {self.name}: {str(e)}",
                "Employee Tax Summary Validation Error"
            )
            # Re-throw with user-friendly message
            frappe.throw(_("Error validating tax summary: {0}").format(str(e)))
    
    def validate_required_fields(self):
        """Validate that all required fields are present"""
        # Check employee is specified
        if not self.employee:
            frappe.throw(_("Employee is mandatory for Employee Tax Summary"))
            
        # Check year is specified
        if not self.year:
            frappe.throw(_("Tax year is mandatory for Employee Tax Summary"))
            
        # Validate year is a reasonable value
        current_year = getdate().year
        if self.year < 2000 or self.year > current_year + 1:
            frappe.throw(_("Invalid tax year: {0}. Must be between 2000 and {1}").format(
                self.year, current_year + 1
            ))
    
    def validate_duplicate(self):
        """Check if another record exists for the same employee and year"""
        try:
            # Skip check for new records
            if self.is_new():
                return
                
            existing = frappe.db.exists(
                "Employee Tax Summary", 
                {
                    "name": ["!=", self.name],
                    "employee": self.employee,
                    "year": self.year
                }
            )
            
            if existing:
                frappe.throw(_(
                    "Tax summary for employee {0} for year {1} already exists (ID: {2})"
                ).format(self.employee_name, self.year, existing))
                
        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            frappe.log_error(
                f"Error checking for duplicate tax summaries: {str(e)}",
                "Employee Tax Summary Duplicate Check Error"
            )
            frappe.throw(_("Error checking for duplicate records: {0}").format(str(e)))
    
    def set_title(self):
        """Set the document title"""
        try:
            if not self.employee_name:
                # Try to get employee name if not set
                self.employee_name = frappe.db.get_value("Employee", self.employee, "employee_name")
                if not self.employee_name:
                    self.employee_name = self.employee
                    
            self.title = f"{self.employee_name} - {self.year}"
        except Exception as e:
            frappe.log_error(
                f"Error setting title for Employee Tax Summary {self.name}: {str(e)}",
                "Title Setting Error"
            )
            # Don't throw here, just set a default title
            self.title = f"{self.employee} - {self.year}"
    
    def validate_monthly_details(self):
        """Validate monthly details are consistent"""
        if not self.monthly_details:
            return
            
        try:
            # Check for duplicate months
            months = {}
            for d in self.monthly_details:
                if not d.month:
                    frappe.throw(_("Month is required in row {0}").format(d.idx))
                    
                if d.month < 1 or d.month > 12:
                    frappe.throw(_("Invalid month {0} in row {1}").format(d.month, d.idx))
                    
                if d.month in months:
                    frappe.throw(_("Duplicate month {0} in rows {1} and {2}").format(
                        d.month, months[d.month], d.idx
                    ))
                    
                months[d.month] = d.idx
                
            # Validate monthly data
            for d in self.monthly_details:
                # Ensure gross pay is non-negative
                if flt(d.gross_pay) < 0:
                    frappe.msgprint(_("Negative gross pay {0} in month {1}, setting to 0").format(
                        d.gross_pay, d.month
                    ))
                    d.gross_pay = 0
                
                # Ensure tax amount is non-negative
                if flt(d.tax_amount) < 0:
                    frappe.msgprint(_("Negative tax amount {0} in month {1}, setting to 0").format(
                        d.tax_amount, d.month
                    ))
                    d.tax_amount = 0
                    
                # Validate TER rate if using TER
                if cint(d.is_using_ter) and (flt(d.ter_rate) <= 0 or flt(d.ter_rate) > 50):
                    frappe.msgprint(_(
                        "Invalid TER rate {0}% in month {1}, should be between 0-50%"
                    ).format(d.ter_rate, d.month))
                
        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            frappe.log_error(
                f"Error validating monthly details for Employee Tax Summary {self.name}: {str(e)}",
                "Monthly Details Validation Error"
            )
            frappe.throw(_("Error validating monthly details: {0}").format(str(e)))
    
    def calculate_ytd_from_monthly(self):
        """Calculate YTD tax amount from monthly details"""
        try:
            if not self.monthly_details:
                self.ytd_tax = 0
                return
                
            total_tax = 0
            for monthly in self.monthly_details:
                if hasattr(monthly, 'tax_amount'):
                    total_tax += flt(monthly.tax_amount)
            
            self.ytd_tax = total_tax
            
        except Exception as e:
            frappe.log_error(
                f"Error calculating YTD from monthly for {self.name}: {str(e)}",
                "YTD Calculation Error"
            )
            frappe.throw(_("Error calculating year-to-date tax amount: {0}").format(str(e)))

    def add_monthly_data(self, salary_slip):
        """
        Add or update monthly tax data from salary slip with improved error handling
        
        Args:
            salary_slip: The salary slip document to get tax data from
        """
        try:
            # Validate salary slip
            if not salary_slip or not hasattr(salary_slip, 'start_date'):
                frappe.throw(_("Invalid salary slip provided"))
                
            month = getdate(salary_slip.start_date).month
            year = getdate(salary_slip.start_date).year
            
            # Validate year matches
            if year != self.year:
                frappe.throw(_(
                    "Salary slip year ({0}) doesn't match tax summary year ({1})"
                ).format(year, self.year))
            
            # Initialize values
            pph21_amount = 0
            bpjs_deductions = 0
            other_deductions = 0
            
            # Get tax amount from salary slip
            if hasattr(salary_slip, 'deductions'):
                for deduction in salary_slip.deductions:
                    if deduction.salary_component == "PPh 21":
                        pph21_amount = flt(deduction.amount)
                    elif deduction.salary_component in ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]:
                        bpjs_deductions += flt(deduction.amount)
                    else:
                        other_deductions += flt(deduction.amount)
            
            # Check if month already exists in monthly details
            existing_month = None
            for i, d in enumerate(self.monthly_details):
                if hasattr(d, 'month') and d.month == month:
                    existing_month = i
                    break
            
            # Get gross pay from salary slip, with validation
            gross_pay = 0
            if hasattr(salary_slip, 'gross_pay'):
                gross_pay = flt(salary_slip.gross_pay)
            
            # Get TER information from salary slip
            is_using_ter = 0
            ter_rate = 0
            
            if hasattr(salary_slip, 'is_using_ter') and salary_slip.is_using_ter:
                is_using_ter = 1
                if hasattr(salary_slip, 'ter_rate'):
                    ter_rate = flt(salary_slip.ter_rate)
            
            if existing_month is not None:
                # Update existing month
                self.monthly_details[existing_month].salary_slip = salary_slip.name
                self.monthly_details[existing_month].gross_pay = gross_pay
                self.monthly_details[existing_month].bpjs_deductions = bpjs_deductions
                self.monthly_details[existing_month].other_deductions = other_deductions
                self.monthly_details[existing_month].tax_amount = pph21_amount
                self.monthly_details[existing_month].is_using_ter = is_using_ter
                self.monthly_details[existing_month].ter_rate = ter_rate
            else:
                # Add new month
                self.append("monthly_details", {
                    "month": month,
                    "salary_slip": salary_slip.name,
                    "gross_pay": gross_pay,
                    "bpjs_deductions": bpjs_deductions,
                    "other_deductions": other_deductions,
                    "tax_amount": pph21_amount,
                    "is_using_ter": is_using_ter,
                    "ter_rate": ter_rate
                })
            
            # Recalculate YTD
            self.calculate_ytd_from_monthly()
            
            # Save document with error handling
            try:
                self.flags.ignore_validate_update_after_submit = True
                self.save(ignore_permissions=True)
            except Exception as e:
                frappe.log_error(
                    f"Error saving tax summary after adding monthly data: {str(e)}",
                    "Tax Summary Save Error"
                )
                frappe.throw(_("Error saving tax summary: {0}").format(str(e)))
                
        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            frappe.log_error(
                f"Error adding monthly data to tax summary {self.name} from salary slip {getattr(salary_slip, 'name', 'unknown')}: {str(e)}",
                "Monthly Data Addition Error"
            )
            frappe.throw(_("Error adding monthly data to tax summary: {0}").format(str(e)))
    
    def get_ytd_data_until_month(self, month):
        """
        Get YTD data until specified month with improved error handling
        
        Args:
            month: Month to get data until (1-12)
            
        Returns:
            dict: Dictionary containing YTD data with keys:
                - gross: Total gross pay
                - bpjs: Total BPJS deductions
                - pph21: Total PPh 21 paid
        """
        result = {"gross": 0, "bpjs": 0, "pph21": 0}
        
        try:
            # Validate month parameter
            if not month or not isinstance(month, int) or month < 1 or month > 12:
                frappe.throw(_("Invalid month {0}. Must be between 1-12.").format(month))
            
            if not self.monthly_details:
                return result
            
            for monthly in self.monthly_details:
                if hasattr(monthly, 'month') and monthly.month < month:
                    result["gross"] += flt(monthly.gross_pay)
                    result["bpjs"] += flt(monthly.bpjs_deductions)
                    result["pph21"] += flt(monthly.tax_amount)
            
            return result
            
        except Exception as e:
            frappe.log_error(
                f"Error getting YTD data until month {month} for tax summary {self.name}: {str(e)}",
                "YTD Data Retrieval Error"
            )
            # Instead of throwing, return empty result on error
            return {"gross": 0, "bpjs": 0, "pph21": 0}
            
    def on_update(self):
        """Actions after updating tax summary"""
        try:
            # Update title if not set
            if not self.title:
                self.set_title()
                self.db_set('title', self.title, update_modified=False)
                
            # Update TER indicator at year level if any month uses TER
            has_ter = False
            max_ter_rate = 0
            
            if hasattr(self, 'monthly_details') and self.monthly_details:
                for monthly in self.monthly_details:
                    if cint(monthly.is_using_ter):
                        has_ter = True
                        max_ter_rate = max(max_ter_rate, flt(monthly.ter_rate))
                
            # Update TER fields if they exist
            if hasattr(self, 'is_using_ter'):
                self.db_set('is_using_ter', 1 if has_ter else 0, update_modified=False)
                
            if hasattr(self, 'ter_rate') and has_ter:
                self.db_set('ter_rate', max_ter_rate, update_modified=False)
                
        except Exception as e:
            frappe.log_error(
                f"Error in on_update for Employee Tax Summary {self.name}: {str(e)}",
                "Employee Tax Summary Update Error"
            )

# ----- Fungsi tambahan untuk integrasi dengan Salary Slip -----

@frappe.whitelist()
def create_from_salary_slip(salary_slip):
    """
    Create or update Employee Tax Summary from a Salary Slip
    Called asynchronously from the Salary Slip's on_submit method
    """
    debug_log(f"Starting create_from_salary_slip for {salary_slip}")
    
    try:
        # Get the salary slip document
        slip = frappe.get_doc("Salary Slip", salary_slip)
        if not slip or slip.docstatus != 1:
            debug_log(f"Salary slip {salary_slip} not found or not submitted")
            return None
            
        employee = slip.employee
        year = getdate(slip.end_date).year
        month = getdate(slip.end_date).month
        
        debug_log(f"Processing tax summary for employee={employee}, year={year}, month={month}")
        
        # Check if an Employee Tax Summary already exists for this employee and year
        tax_summary_name = frappe.db.get_value(
            "Employee Tax Summary", 
            {"employee": employee, "year": year}
        )
        
        if tax_summary_name:
            debug_log(f"Found existing Employee Tax Summary: {tax_summary_name}")
            tax_summary = frappe.get_doc("Employee Tax Summary", tax_summary_name)
        else:
            debug_log(f"Creating new Employee Tax Summary for {employee}, {year}")
            # Create a new Employee Tax Summary
            tax_summary = frappe.new_doc("Employee Tax Summary")
            tax_summary.employee = employee
            tax_summary.year = year
            
            # Get employee details
            emp_doc = frappe.get_doc("Employee", employee)
            if emp_doc:
                tax_summary.employee_name = emp_doc.employee_name
                tax_summary.department = emp_doc.department
                tax_summary.designation = emp_doc.designation
                
                # Copy NPWP and other tax-related fields if they exist
                for field in ['npwp', 'ptkp_status', 'ktp']:
                    if hasattr(emp_doc, field):
                        setattr(tax_summary, field, getattr(emp_doc, field))
            
            # Initialize monthly details
            tax_summary.monthly_details = []
            for i in range(1, 13):
                tax_summary.append("monthly_details", {
                    "month": i,
                    "gross_pay": 0,
                    "bpjs_deductions": 0,
                    "tax_amount": 0
                })
                
            # Insert the new document
            tax_summary.insert(ignore_permissions=True)
        
        # Call the add_monthly_data method to update the document with salary slip data
        tax_summary.add_monthly_data(slip)
        
        debug_log(f"Successfully processed Employee Tax Summary: {tax_summary.name}")
        
        return tax_summary.name
        
    except Exception as e:
        debug_log(f"Error in create_from_salary_slip: {str(e)}\nTraceback: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error creating Employee Tax Summary from {salary_slip}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Employee Tax Summary Error"
        )
        return None

@frappe.whitelist()
def update_on_salary_slip_cancel(salary_slip, year):
    """
    Update Employee Tax Summary when a Salary Slip is cancelled
    Called asynchronously from the Salary Slip's on_cancel method
    """
    debug_log(f"Starting update_on_salary_slip_cancel for {salary_slip}, year={year}")
    
    try:
        # Get the salary slip document
        slip = frappe.get_doc("Salary Slip", salary_slip)
        if not slip:
            debug_log(f"Salary slip {salary_slip} not found")
            return False
            
        employee = slip.employee
        month = getdate(slip.end_date).month
        
        # Find the Employee Tax Summary
        tax_summary_name = frappe.db.get_value(
            "Employee Tax Summary", 
            {"employee": employee, "year": year}
        )
        
        if not tax_summary_name:
            debug_log(f"No Employee Tax Summary found for employee={employee}, year={year}")
            return False
            
        # Get the document
        tax_doc = frappe.get_doc("Employee Tax Summary", tax_summary_name)
        
        # Update the monthly entry for this salary slip
        changed = False
        for i, d in enumerate(tax_doc.monthly_details):
            if getattr(d, "month") == month and getattr(d, "salary_slip") == salary_slip:
                debug_log(f"Found entry to update: monthly_details[{i}] with month={month}, salary_slip={salary_slip}")
                # Reset values for this month
                d.gross_pay = 0
                d.bpjs_deductions = 0
                d.other_deductions = 0
                d.tax_amount = 0
                d.salary_slip = None
                d.is_using_ter = 0
                d.ter_rate = 0
                changed = True
                
        # Recalculate YTD if changes were made
        if changed:
            debug_log(f"Recalculating YTD tax for Employee Tax Summary {tax_summary_name}")
            tax_doc.calculate_ytd_from_monthly()
            
            # Save the document
            tax_doc.flags.ignore_validate_update_after_submit = True
            tax_doc.flags.ignore_permissions = True
            tax_doc.save()
            debug_log(f"Successfully updated Employee Tax Summary: {tax_summary_name}")
            
            return True
        else:
            debug_log(f"No changes needed for Employee Tax Summary: {tax_summary_name}")
            return False
            
    except Exception as e:
        debug_log(f"Error in update_on_salary_slip_cancel: {str(e)}\nTraceback: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error updating Employee Tax Summary on cancel for {salary_slip}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Employee Tax Summary Cancel Error"
        )
        return False
    
@frappe.whitelist()
def validate(doc):
    """
    Module-level validate function that delegates to the document's validate method
    This is needed for compatibility with code that calls this function directly
    """
    try:
        if isinstance(doc, str):
            doc = frappe.get_doc("Employee Tax Summary", doc)
        
        # Ensure we have a document instance with a validate method
        if hasattr(doc, "validate") and callable(doc.validate):
            doc.validate()
            return True
        else:
            frappe.log_error(
                "Invalid document passed to validate function",
                "Employee Tax Summary Validation Error"
            )
            return False
    except Exception as e:
        frappe.log_error(
            f"Error in Employee Tax Summary validation: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Employee Tax Summary Validation Error"
        )
        return False
