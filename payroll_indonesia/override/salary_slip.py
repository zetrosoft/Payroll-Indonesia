# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime, add_to_date
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
import json
import hashlib

# Define exports for proper importing by other modules
__all__ = [
    'IndonesiaPayrollSalarySlip',
    'setup_fiscal_year_if_missing',
    'check_fiscal_year_setup',
    'clear_caches',
    'extend_salary_slip_functionality'
]

# Cache variables - encapsulated in a module-level dict to avoid global namespace pollution
_CACHE = {
    'ter_rate_cache': {},
    'ytd_tax_cache': {},
    'ptkp_mapping_cache': None,  # For PMK 168/2023 TER mapping
}

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
    
    # Class methods remain the same as in your original implementation
    def validate(self):
        """Validate salary slip and calculate Indonesian components"""
        employee_info = f"{self.employee} ({self.employee_name})" if hasattr(self, 'employee_name') else self.employee
        
        try:
            # Call parent validation first
            super().validate()
            
            # Initialize additional fields
            self._initialize_payroll_fields()
            
            # Get employee document
            employee = self._get_employee_doc()
            
            # Calculate BPJS components
            self._calculate_bpjs(employee)
            
            # Determine and apply tax calculation strategy
            self._calculate_tax(employee)
            
            # Final verifications
            self._verify_ter_settings()
            self._generate_tax_id_data(employee)
            self._check_or_create_fiscal_year()
            
            self.add_payroll_note("Validasi berhasil: Komponen BPJS dan Pajak dihitung.")
            
        except Exception as e:
            self._handle_validation_error(e, employee_info)
    
    # Keep all your original methods here - I'm showing just a sample
    # for brevity, but your full implementation should include all methods
    
    def _initialize_payroll_fields(self):
        """Initialize additional payroll fields"""
        defaults = {
            'biaya_jabatan': 0,
            'netto': 0,
            'total_bpjs': 0,
            'is_using_ter': 0,
            'ter_rate': 0,
            'ter_category': "",
            'koreksi_pph21': 0,
            'payroll_note': "",
            'npwp': "",
            'ktp': "",
            'is_final_gabung_suami': 0,
        }
        
        # Set defaults for fields that don't exist or are None
        for field, default in defaults.items():
            if not hasattr(self, field) or getattr(self, field) is None:
                setattr(self, field, default)
                
        return defaults
    
    # ... include all your other methods here ...
    
    # Example of one of your methods for illustration:
    def add_payroll_note(self, note, section=None):
        """Add note to payroll_note field with timestamp and optional section"""
        if not hasattr(self, 'payroll_note'):
            self.payroll_note = ""
        
        # Add section header if specified
        if section:
            # Add section header if specified
            formatted_note = f"\n\n=== {section} ===\n{note}"
        else:
            formatted_note = note
    
        # Add new note
        if self.payroll_note:
            self.payroll_note += f"\n{formatted_note}"
        else:
            self.payroll_note = formatted_note
        
        # Use db_set to avoid another full save
        self.db_set('payroll_note', self.payroll_note, update_modified=False)


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
            'validate': _enhance_validate,
            'on_submit': _enhance_on_submit,
            'on_cancel': _enhance_on_cancel,
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
            "Controller Enhancement"
        )
        
        return True
    except Exception as e:
        frappe.log_error(
            f"Error enhancing SalarySlip controller: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Controller Enhancement Error"
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
        # Call the original method first
        result = original_method(self, *args, **kwargs)
        
        # Then apply our enhancement
        enhancement_func(self, *args, **kwargs)
        
        # Return the original result
        return result
        
    # Copy the original method's docstring and attributes
    if hasattr(original_method, '__doc__'):
        enhanced_method.__doc__ = original_method.__doc__
    
    # Add a note that this is an enhanced version
    if enhanced_method.__doc__:
        enhanced_method.__doc__ += "\n\nEnhanced with Indonesian payroll features."
    else:
        enhanced_method.__doc__ = "Enhanced with Indonesian payroll features."
        
    return enhanced_method

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
            
        # Get employee info for logging
        employee_info = f"{doc.employee} ({doc.employee_name})" if hasattr(doc, 'employee_name') else doc.employee
        
        # Create a temporary IndonesiaPayrollSalarySlip to use its methods
        temp = IndonesiaPayrollSalarySlip(doc.as_dict())
        
        # Initialize additional fields
        temp._initialize_payroll_fields()
        
        # Get employee document
        employee = temp._get_employee_doc()
        
        # Calculate BPJS components
        temp._calculate_bpjs(employee)
        
        # Determine and apply tax calculation strategy
        temp._calculate_tax(employee)
        
        # Final verifications
        temp._verify_ter_settings()
        temp._generate_tax_id_data(employee)
        temp._check_or_create_fiscal_year()
        
        # Copy back all the fields that were calculated
        for field in ['biaya_jabatan', 'netto', 'total_bpjs', 'is_using_ter',
                     'ter_rate', 'ter_category', 'koreksi_pph21',
                     'payroll_note', 'npwp', 'ktp', 'is_final_gabung_suami']:
            if hasattr(temp, field):
                setattr(doc, field, getattr(temp, field))
                # Use db_set for immediate persistence
                doc.db_set(field, getattr(temp, field), update_modified=False)
                
        # Copy child table changes (earnings and deductions)
        for table_name in ['earnings', 'deductions']:
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
                            if field not in ['name', 'creation', 'modified', 'owner']:
                                setattr(new_row, field, getattr(temp_row, field))
                        getattr(doc, table_name).append(new_row)
                
        # Add note about successful validation
        if hasattr(doc, 'payroll_note'):
            note = "Validasi berhasil: Komponen BPJS dan Pajak dihitung."
            if doc.payroll_note:
                doc.payroll_note += f"\n{note}"
            else:
                doc.payroll_note = note
            doc.db_set('payroll_note', doc.payroll_note, update_modified=False)
            
    except Exception as e:
        frappe.log_error(
            f"Error in _enhance_validate for {doc.name if hasattr(doc, 'name') else 'New Salary Slip'}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Slip Enhancement Error"
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
        if hasattr(temp, 'payroll_note'):
            doc.payroll_note = temp.payroll_note
            doc.db_set('payroll_note', temp.payroll_note, update_modified=False)
            
    except Exception as e:
        frappe.log_error(
            f"Error in _enhance_on_submit for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Slip Enhancement Error"
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
        if hasattr(temp, 'payroll_note'):
            doc.payroll_note = temp.payroll_note
            doc.db_set('payroll_note', temp.payroll_note, update_modified=False)
            
    except Exception as e:
        frappe.log_error(
            f"Error in _enhance_on_cancel for {doc.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Slip Enhancement Error"
        )

# Cache management functions
def clear_caches():
    """Clear TER rate and YTD tax caches to prevent memory bloat"""
    _CACHE['ter_rate_cache'] = {}
    _CACHE['ytd_tax_cache'] = {}
    _CACHE['ptkp_mapping_cache'] = None
    
    # Schedule next cleanup in 30 minutes
    frappe.enqueue(clear_caches, queue='long', job_name='clear_payroll_caches', is_async=True, now=False, 
                  enqueue_after=add_to_date(now_datetime(), minutes=30))

# Helper function for fiscal year management - keep your original implementation
def check_fiscal_year_setup(date_str=None):
    """Check if fiscal years are properly set up"""
    try:
        from frappe.utils import getdate
        test_date = getdate(date_str) if date_str else getdate()
        
        fiscal_year = frappe.db.get_value("Fiscal Year", {
            "year_start_date": ["<=", test_date],
            "year_end_date": [">=", test_date]
        })
        
        if not fiscal_year:
            return {
                "status": "error",
                "message": f"No active Fiscal Year found for date {test_date}",
                "solution": "Create a Fiscal Year that includes this date in Company settings"
            }
        
        return {
            "status": "ok",
            "fiscal_year": fiscal_year
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@frappe.whitelist()
def setup_fiscal_year_if_missing(date_str=None):
    """Automatically set up a fiscal year if missing"""
    # Keep your original implementation
    try:
        from frappe.utils import getdate, add_to_date
        test_date = getdate(date_str) if date_str else getdate()
        
        # Check if fiscal year exists
        fiscal_year = frappe.db.get_value("Fiscal Year", {
            "year_start_date": ["<=", test_date],
            "year_end_date": [">=", test_date]
        })
        
        if fiscal_year:
            return {
                "status": "exists",
                "fiscal_year": fiscal_year
            }
        
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
        
        return {
            "status": "created",
            "fiscal_year": new_fy.name,
            "year": new_fy.year,
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d')
        }
        
    except Exception as e:
        frappe.log_error(
            f"Error setting up fiscal year: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Fiscal Year Setup Error"
        )
        return {
            "status": "error",
            "message": str(e)
        }

# NEW: Hook to apply our extensions when the module is loaded
def setup_hooks():
    """Set up our hooks and monkey patches when the module is loaded"""
    extend_salary_slip_functionality()
    clear_caches()  # Start cache clearing process

# Apply extensions
setup_hooks()