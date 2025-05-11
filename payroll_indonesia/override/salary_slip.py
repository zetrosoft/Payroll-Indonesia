# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime, add_to_date
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from hrms.payroll.doctype.salary_slip.salary_slip import make_salary_slip_from_timesheet as original_make_slip
from frappe.utils.background_jobs import get_jobs, enqueue
import json
import hashlib

# Define exports for proper importing by other modules
__all__ = [
    'IndonesiaPayrollSalarySlip',
    'setup_fiscal_year_if_missing',
    'process_salary_slips_batch',
    'check_fiscal_year_setup',
    'clear_caches'
]

# Import BPJS related functions  
from payroll_indonesia.override.salary_slip.bpjs_calculator import (
    calculate_bpjs_components,
    verify_bpjs_components,
    debug_log,
    check_bpjs_enrollment,
)

# Cache variables
_ter_rate_cache = {}
_ytd_tax_cache = {}
_ptkp_mapping_cache = None  # Added for PMK 168/2023 TER mapping

# Import required modules with proper error handling
try:
    debug_log("Starting imports from payroll_indonesia modules")
    
    from payroll_indonesia.override.salary_slip.base import get_formatted_currency, get_component_amount, update_component_amount
    from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components
    from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter, should_use_ter_method, verify_calculation_integrity
    
    # Direct import for BPJS calculation to ensure it's always available
    from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs
    
    debug_log("Successfully imported all payroll_indonesia modules")
except ImportError as e:
    debug_log(f"Error importing Payroll Indonesia modules: {str(e)}")
    frappe.log_error("Error importing Payroll Indonesia modules", "Salary Slip Import Error")
    
    # Define placeholders to avoid errors when modules not found
    def get_component_amount(doc, name, type_):
        debug_log(f"Using placeholder get_component_amount for {name} in {type_}")
        return 0
        
    def update_component_amount(doc, name, amount, type_):
        debug_log(f"Using placeholder update_component_amount for {name}: {amount} in {type_}")
        return False
        
    def calculate_tax_components(doc, employee):
        debug_log(f"Using placeholder calculate_tax_components for employee {employee.name if hasattr(employee, 'name') else 'unknown'}")
        pass
    
    def verify_calculation_integrity(**kwargs):
        debug_log("Using placeholder verify_calculation_integrity")
        return True


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
        """Validate salary slip and calculate Indonesian components"""
        employee_info = f"{self.employee} ({self.employee_name})" if hasattr(self, 'employee_name') else self.employee
        debug_log(f"Starting validate for salary slip {self.name}", employee=employee_info)
        
        try:
            # Call parent validation first
            super().validate()
            
            # Initialize additional fields
            self.initialize_payroll_fields()
            
            # Get employee document
            employee = self.get_employee_doc()
            
            # Calculate BPJS components
            base_salary = self.get_base_salary_for_bpjs()
            calculate_bpjs_components(self, employee, base_salary)
            
            # Verify BPJS components
            self.handle_bpjs_verification(employee, base_salary)
            
            # Calculate tax
            tax_strategy = self.determine_tax_strategy(employee)
            self.calculate_tax_with_strategy(tax_strategy, employee)
            
            # Final verifications
            self.verify_ter_settings()
            self.generate_tax_id_data(employee)
            self.check_or_create_fiscal_year()
            
            self.add_payroll_note("Validasi berhasil: Komponen BPJS dan Pajak dihitung.")
            
        except Exception as e:
            self.handle_validation_error(e, employee_info)
    
    def handle_bpjs_verification(self, employee, base_salary):
        """Handle BPJS component verification and potential recalculation"""
        employee_info = f"{self.employee} ({self.employee_name})" if hasattr(self, 'employee_name') else self.employee
        verification = verify_bpjs_components(self)
        
        if verification["all_zero"]:
            debug_log(f"Warning: All BPJS components are zero for {employee_info}", employee=employee_info)
            
            # Check if employee should have BPJS
            if check_bpjs_enrollment(employee):
                debug_log(f"Employee is enrolled in BPJS but components are zero. Attempting recalculation.", employee=employee_info)
                self.recalculate_bpjs_components(employee, base_salary)
    
    def recalculate_bpjs_components(self, employee, base_salary):
        """Recalculate BPJS components directly"""
        employee_info = f"{self.employee} ({self.employee_name})" if hasattr(self, 'employee_name') else self.employee
        
        try:
            bpjs_values = hitung_bpjs(employee, base_salary)
            if bpjs_values["total_employee"] > 0:
                # Manually update BPJS components
                for component, value in [
                    ("BPJS Kesehatan Employee", bpjs_values["kesehatan_employee"]), 
                    ("BPJS JHT Employee", bpjs_values["jht_employee"]), 
                    ("BPJS JP Employee", bpjs_values["jp_employee"])
                ]:
                    if value > 0:
                        update_component_amount(self, component, value, "deductions")
                        debug_log(f"Manually updated {component}: {value}", employee=employee_info)
                
                # Update total_bpjs
                self.total_bpjs = flt(bpjs_values["total_employee"])
                self.db_set('total_bpjs', self.total_bpjs, update_modified=False)
        except Exception as bpjs_err:
            debug_log(f"Error in direct BPJS calculation: {str(bpjs_err)}", employee=employee_info, trace=True)
    
    def verify_ter_settings(self):
        """Verify TER settings consistency"""
        debug_log(f"Verifying TER settings for {self.name}")
        
        # If ter_rate > 0, ensure is_using_ter = 1
        if hasattr(self, 'ter_rate') and flt(self.ter_rate) > 0:
            if not hasattr(self, 'is_using_ter') or not self.is_using_ter:
                self.is_using_ter = 1
                self.db_set('is_using_ter', 1, update_modified=False)
        
        # If ter_category exists, ensure is_using_ter = 1
        if hasattr(self, 'ter_category') and self.ter_category:
            if not hasattr(self, 'is_using_ter') or not self.is_using_ter:
                self.is_using_ter = 1
                self.db_set('is_using_ter', 1, update_modified=False)
        
        # If is_using_ter=0, ensure ter_rate=0 and ter_category=""
        if hasattr(self, 'is_using_ter') and not self.is_using_ter:
            if hasattr(self, 'ter_rate') and flt(self.ter_rate) > 0:
                self.ter_rate = 0
                self.db_set('ter_rate', 0, update_modified=False)
            
            if hasattr(self, 'ter_category') and self.ter_category:
                self.ter_category = ""
                self.db_set('ter_category', "", update_modified=False)
    
    def determine_tax_strategy(self, employee):
        """Determine whether to use TER or Progressive method"""
        try:
            return "TER" if should_use_ter_method(employee) else "PROGRESSIVE"
        except Exception:
            # Fall back to simple checks if the import fails
            if hasattr(employee, 'tipe_karyawan') and employee.tipe_karyawan == "Freelance":
                return "PROGRESSIVE"
                
            if hasattr(employee, 'override_tax_method') and employee.override_tax_method == "Progressive":
                return "PROGRESSIVE"
                
            # Per PMK 168/2023, check if December (always use Progressive in December)
            if self.end_date and getdate(self.end_date).month == 12:
                return "PROGRESSIVE"
                
            return "TER"
    
    def calculate_tax_with_strategy(self, strategy, employee):
        """Calculate tax using either TER or Progressive method"""
        # Store original values to restore after calculation
        original_values = {
            'gross_pay': flt(self.gross_pay),
            'monthly_gross_for_ter': flt(getattr(self, 'monthly_gross_for_ter', 0)),
            'annual_taxable_amount': flt(getattr(self, 'annual_taxable_amount', 0)),
            'ter_rate': flt(getattr(self, 'ter_rate', 0)),
            'ter_category': getattr(self, 'ter_category', '')
        }
        
        try:
            if strategy == "TER":
                self.apply_ter_calculation(employee)
            else:
                self.apply_progressive_calculation(employee)
                
            # Verify calculation integrity
            verify_calculation_integrity(
                doc=self,
                original_values=original_values,
                monthly_gross_pay=getattr(self, 'monthly_gross_for_ter', self.gross_pay),
                annual_taxable_amount=getattr(self, 'annual_taxable_amount', 0),
                ter_rate=getattr(self, 'ter_rate', 0) / 100 if hasattr(self, 'ter_rate') else 0,
                ter_category=getattr(self, 'ter_category', ''),
                monthly_tax=self.get_tax_amount()
            )
            
        except Exception as e:
            self.handle_tax_calculation_error(e)
            
        finally:
            # Verify TER flags are set correctly for TER strategy
            if strategy == "TER" and not getattr(self, 'is_using_ter', 0):
                debug_log(f"TER flags not set properly for {self.name}. Setting is_using_ter=1 now.")
                self.is_using_ter = 1
                self.db_set('is_using_ter', 1, update_modified=False)
            
            # Verify values haven't been globally changed
            if strategy == "TER" and abs(original_values['gross_pay'] - self.gross_pay) > 1:
                debug_log(f"gross_pay modified during TER calculation: {original_values['gross_pay']} -> {self.gross_pay}")
                # Restore original gross_pay for TER calculation
                self.gross_pay = original_values['gross_pay']
    
    def apply_ter_calculation(self, employee):
        """Apply TER calculation method"""
        debug_log(f"Using TER calculation method for {self.name}")
        
        # Call TER calculation function
        calculate_monthly_pph_with_ter(self, employee)
        
        # Explicitly set and persist TER flags
        self.is_using_ter = 1
        
        # Ensure ter_rate has a valid value
        if not hasattr(self, 'ter_rate') or flt(self.ter_rate) <= 0:
            self.ter_rate = 5.0  # Default to 5% if missing or zero
            debug_log(f"TER rate was missing or zero for {self.name}, setting default 5%")
        
        # Persist values to database with db_set
        self.db_set('is_using_ter', 1, update_modified=False)
        self.db_set('ter_rate', flt(self.ter_rate), update_modified=False)
        
        # Add note to payroll_note
        self.add_payroll_note(f"TER method applied with rate: {self.ter_rate}%")
    
    def apply_progressive_calculation(self, employee):
        """Apply Progressive calculation method"""
        debug_log(f"Using Progressive calculation method for {self.name}")
        
        # Call progressive calculation function
        calculate_tax_components(self, employee)
        
        # Reset TER values
        self.is_using_ter = 0
        self.ter_rate = 0
        
        # Persist values to database
        self.db_set('is_using_ter', 0, update_modified=False)
        self.db_set('ter_rate', 0, update_modified=False)
        
        # Clear ter_category if it exists
        if hasattr(self, 'ter_category'):
            self.ter_category = ""
            self.db_set('ter_category', "", update_modified=False)
            
        self.add_payroll_note("Progressive tax calculation applied")
    
    def get_tax_amount(self):
        """Get PPh 21 amount from deductions"""
        return next(
            (d.amount for d in self.deductions if d.salary_component == "PPh 21"),
            0
        )
    
    def handle_validation_error(self, e, employee_info=""):
        """Handle validation errors consistently"""
        debug_log(f"Error in validate for {self.name}: {str(e)}", employee=employee_info, trace=True)
        frappe.log_error(
            f"Error dalam validasi Salary Slip untuk {self.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Slip Validation Error"
        )
        frappe.throw(_("Error dalam validasi Salary Slip: {0}").format(str(e)))
    
    def handle_tax_calculation_error(self, e):
        """Handle tax calculation errors consistently"""
        debug_log(f"Tax calculation error for {self.name}: {str(e)}", trace=True)
        frappe.log_error(
            f"Tax Calculation Error for {self.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Calculation Error"
        )
        frappe.throw(_("Tax Calculation Error: {0}").format(str(e)))
    
    def on_submit(self):
        """Create related documents on submit and verify BPJS values"""
        try:
            debug_log(f"Starting on_submit for salary slip {self.name}", 
                      employee=getattr(self, 'employee_name', self.employee))
            
            # Verify TER settings before submit
            self.verify_ter_settings()
            
            # Verify BPJS components before submission
            verify_bpjs_components(self)
            
            # Call parent on_submit method
            super(IndonesiaPayrollSalarySlip, self).on_submit()
            
            # Queue document creation
            self.queue_document_creation()
            
        except Exception as e:
            debug_log(f"Error in on_submit for {self.name}: {str(e)}", trace=True)
            frappe.log_error(
                f"Error in on_submit for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Submit Error"
            )
            frappe.throw(_("Error during salary slip submission: {0}").format(str(e)))

    def queue_document_creation(self):
        """Queue creation of related documents after salary slip submission"""
        try:
            # Generate unique job identifiers
            job_prefix = hashlib.md5(f"{self.name}_{now_datetime()}".encode()).hexdigest()[:8]
            is_test = bool(getattr(frappe.flags, 'in_test', False))
            
            month = getdate(self.end_date).month
            year = getdate(self.end_date).year
            
            # Queue Employee Tax Summary creation (always created)
            job_id = f"tax_summary_{job_prefix}_{self.name}"
            
            if not self._job_exists(job_id):
                enqueue(
                    method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.create_from_salary_slip",
                    queue="long",
                    timeout=600,
                    is_async=True,
                    job_name=job_id,
                    now=is_test,
                    salary_slip=self.name
                )
            
            # Add note about successful submission
            timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
            ter_info = ""
            if hasattr(self, 'is_using_ter') and self.is_using_ter:
                if hasattr(self, 'ter_category') and self.ter_category:
                    ter_info = f" Menggunakan {self.ter_category} sesuai PMK 168/2023."
                else:
                    ter_info = f" Menggunakan metode TER sesuai PMK 168/2023."
            
            note = (
                f"\n[{timestamp}] Submit berhasil: Dokumen dijadwalkan: Employee Tax Summary. "
                f"Periode: {month:02d}/{year}.{ter_info} "
            )
            
            memory_estimate = self._estimate_memory_usage()
            if memory_estimate:
                note += f"Est. memory: {memory_estimate:.2f}MB."
                
            self.add_payroll_note(note)
            
            # Add note about BPJS Payment Summary
            self.add_payroll_note("BPJS Payment Summary harus dibuat secara manual dari doctype BPJS Payment Summary.")
            
        except Exception as e:
            debug_log(f"Error queueing document creation for {self.name}: {str(e)}")
            frappe.log_error(
                f"Error queueing document creation for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip - Document Queue Error"
            )
            # Do not raise exception, just show a message to the user
            frappe.msgprint(_("Warning: Error occurred while queueing related documents: {0}").format(str(e)))
    
    def _job_exists(self, job_name):
        """Check if a job with the given name already exists in the queue"""
        try:
            for queue in ['default', 'long', 'short']:
                jobs = get_jobs(queue, job_name=job_name)
                if jobs:
                    return True
            return False
        except Exception:
            return False
    
    def _estimate_memory_usage(self):
        """Estimate memory usage of this salary slip"""
        try:
            doc_str = json.dumps(self.as_dict())
            return len(doc_str) / (1024 * 1024)
        except Exception:
            return None
    
    def on_cancel(self):
        """Handle document cancellation"""
        employee_info = f"{self.employee} ({self.employee_name})" if hasattr(self, 'employee_name') else self.employee
        debug_log(f"Starting on_cancel for salary slip {self.name}", employee=employee_info)
        
        try:
            # Call parent on_cancel method
            super(IndonesiaPayrollSalarySlip, self).on_cancel()
            
            # Update related documents
            self.queue_document_updates_on_cancel()
            
        except Exception as e:
            debug_log(f"Error in on_cancel for {self.name}: {str(e)}", employee=employee_info, trace=True)
            frappe.log_error(
                f"Error dalam on_cancel Salary Slip untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Cancel Error"
            )
            frappe.msgprint(_("Warning: Error saat mengupdate dokumen terkait pada pembatalan: {0}").format(str(e)))
    
    def queue_document_updates_on_cancel(self):
        """Schedule updates to related documents when canceling salary slip"""
        employee_info = f"{self.employee} ({self.employee_name})" if hasattr(self, 'employee_name') else self.employee
        debug_log(f"Starting queue_document_updates_on_cancel for {self.name}", employee=employee_info)
        
        month = getdate(self.end_date).month
        year = getdate(self.end_date).year
        is_test = bool(getattr(frappe.flags, 'in_test', False))
        
        try:
            # Generate unique job identifiers
            job_prefix = hashlib.md5(f"cancel_{self.name}_{now_datetime()}".encode()).hexdigest()[:8]
            
            # Schedule update for Employee Tax Summary
            job_id = f"tax_cancel_{job_prefix}_{self.name}"
            enqueue(
                method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.update_on_salary_slip_cancel",
                queue="long",
                timeout=600,
                is_async=True,
                job_name=job_id,
                now=is_test,
                **{"salary_slip": self.name, "year": year}
            )
            
            # Add note about cancellation
            timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
            note = f"[{timestamp}] Cancel berhasil: Pembaruan dokumen terkait telah dijadwalkan."
            self.add_payroll_note(note)
            
            # Add note about BPJS Payment Summary
            self.add_payroll_note("BPJS Payment Summary perlu diupdate secara manual jika sudah dibuat sebelumnya.")
            
        except Exception as e:
            debug_log(f"Error in queue_document_updates_on_cancel: {str(e)}", employee=employee_info, trace=True)
            frappe.log_error(
                f"Error dalam queue_document_updates_on_cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Document Update Queue Error"
            )
            frappe.msgprint(_("Error saat menjadwalkan pembaruan dokumen terkait: {0}").format(str(e)))
    
    # Helper methods
    def initialize_payroll_fields(self):
        """Initialize additional payroll fields"""
        debug_log(f"Initializing payroll fields for {self.name if hasattr(self, 'name') else 'unknown'}")
        
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
    
    def get_employee_doc(self):
        """Get employee document with validation and caching"""
        if not hasattr(self, 'employee') or not self.employee:
            frappe.throw(_("Employee harus diisi untuk salary slip"))
            
        # Return cached employee if available
        if hasattr(self, '_cached_employee'):
            return self._cached_employee
            
        try:
            employee_doc = frappe.get_doc("Employee", self.employee)
            self._cached_employee = employee_doc
            return employee_doc
        except Exception as e:
            debug_log(f"Error retrieving employee document for {self.employee}: {str(e)}", trace=True)
            frappe.throw(_("Error saat mengambil data karyawan {0}: {1}").format(self.employee, str(e)))
    
    def get_base_salary_for_bpjs(self):
        """Get base salary for BPJS calculation with enhanced validation"""
        debug_log(f"Getting base salary for BPJS calculation for {self.name}")
        base_salary = 0
        
        # Check if earnings exist
        if not hasattr(self, 'earnings') or not self.earnings:
            debug_log(f"No earnings found in salary slip {self.name}")
            # No earnings, use gross_pay if available
            if hasattr(self, 'gross_pay') and self.gross_pay > 0:
                return flt(self.gross_pay)
            return 0
        
        # Try to find Gaji Pokok component first    
        for earning in self.earnings:
            if earning.salary_component == "Gaji Pokok":
                base_salary = flt(earning.amount)
                debug_log(f"Found Gaji Pokok component: {base_salary}")
                break
        
        # If not found, try Basic
        if base_salary <= 0:
            for earning in self.earnings:
                if earning.salary_component == "Basic":
                    base_salary = flt(earning.amount)
                    debug_log(f"Found Basic component: {base_salary}")
                    break
            
            # If still not found, use first component
            if base_salary <= 0 and self.earnings:
                base_salary = flt(self.earnings[0].amount)
                debug_log(f"Using first component as base salary: {base_salary} ({self.earnings[0].salary_component})")
        
        # If still zero, use gross_pay as fallback
        if base_salary <= 0 and hasattr(self, 'gross_pay') and self.gross_pay > 0:
            base_salary = flt(self.gross_pay)
            debug_log(f"No valid component found, using gross_pay as base salary: {base_salary}")
            
        # Final check - if still zero, use UMR as fallback for safe calculation
        if base_salary <= 0:
            default_umr = 4900000  # Jakarta UMR as default
            debug_log(f"No valid base salary found, using default UMR: {default_umr}")
            base_salary = default_umr
            
        debug_log(f"Final base salary for BPJS calculation: {base_salary}")
        return base_salary
    
    def generate_tax_id_data(self, employee):
        """Get tax ID information (NPWP and KTP) from employee data"""
        try:
            if hasattr(employee, 'npwp'):
                self.npwp = employee.npwp
                
            if hasattr(employee, 'ktp'):
                self.ktp = employee.ktp
                
        except Exception as e:
            debug_log(f"Error generating tax ID data for {self.name}: {str(e)}", trace=True)
            frappe.log_error(f"Error generating tax ID data: {str(e)}", "Tax ID Data Error")
    
    def add_payroll_note(self, note, section=None):
        """Add note to payroll_note field with timestamp and optional section"""
        if not hasattr(self, 'payroll_note'):
            self.payroll_note = ""
        
        # Add timestamp to note
        timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
        formatted_note = f"[{timestamp}] {note}"
    
        if section:
            # Add section header if specified
            formatted_note = f"\n\n=== {section} ===\n{formatted_note}"
    
        # Add new note
        self.payroll_note += f"\n{formatted_note}"
        
        # Use db_set to avoid another full save
        self.db_set('payroll_note', self.payroll_note, update_modified=False)
    
    def check_or_create_fiscal_year(self):
        """Check if fiscal year exists for the posting date, create if missing"""
        try:
            if not hasattr(self, 'posting_date') or not self.posting_date:
                return
                
            fy = frappe.db.get_value("Fiscal Year", 
                                    {"year_start_date": ("<=", self.posting_date),
                                     "year_end_date": (">=", self.posting_date),
                                     "disabled": 0})
            
            if not fy:
                # Use the helper function at module level
                result = setup_fiscal_year_if_missing(self.posting_date)
                if result and result.get('status') == 'created':
                    self.add_payroll_note(f"Fiscal Year {result.get('year')} was created automatically.")
        except Exception as e:
            debug_log(f"Error checking/creating fiscal year: {str(e)}", trace=True)


# Override SalarySlip controller with enhanced version
try:
    debug_log("Attempting to override SalarySlip controller")
    frappe.model.document.get_controller("Salary Slip")._controller = IndonesiaPayrollSalarySlip
    debug_log("Successfully overrode SalarySlip controller")
except Exception as e:
    debug_log(f"Error overriding SalarySlip controller: {str(e)}", trace=True)
    frappe.log_error(
        f"Error overriding SalarySlip controller: {str(e)}\n\n"
        f"Traceback: {frappe.get_traceback()}",
        "Controller Override Error"
    )

# Clear caches periodically
def clear_caches():
    """Clear TER rate and YTD tax caches to prevent memory bloat"""
    global _ter_rate_cache, _ytd_tax_cache, _ptkp_mapping_cache
    _ter_rate_cache = {}
    _ytd_tax_cache = {}
    _ptkp_mapping_cache = None
    
    # Schedule next cleanup in 30 minutes
    frappe.enqueue(clear_caches, queue='long', job_name='clear_payroll_caches', is_async=True, now=False, 
                   enqueue_after=add_to_date(now_datetime(), minutes=30))
    
# Start cache clearing process when module loads
clear_caches()


# Helper function for fiscal year management
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


@frappe.whitelist()
def process_salary_slips_batch(salary_slips=None, slip_ids=None, batch_size=50):
    """Process multiple salary slips in batches to manage memory usage"""
    start_time = now_datetime()
    
    # Log start of batch process
    frappe.log_error(
        f"Starting batch processing of salary slips. Batch size: {batch_size}",
        "Batch Process - Start"
    )
    
    # Initialize results
    results = {
        "total": 0,
        "successful": 0,
        "failed": 0,
        "errors": [],
        "memory_usage": [],
        "batches": [],
        "execution_time": 0
    }
    
    try:
        # Get list of slip IDs if salary_slips provided
        if salary_slips and not slip_ids:
            slip_ids = [slip.name for slip in salary_slips if hasattr(slip, 'name')]
        
        # If neither provided, raise error
        if not slip_ids:
            frappe.throw(_("No salary slips provided for batch processing"))
            
        # Remove duplicates and validate
        slip_ids = list(set(slip_ids))
        results["total"] = len(slip_ids)
        
        # Process in batches
        batch_count = 0
        for i in range(0, len(slip_ids), batch_size):
            batch_start = now_datetime()
            batch_count += 1
            
            # Extract current batch
            batch_ids = slip_ids[i:i+batch_size]
            
            # Log batch start
            frappe.log_error(
                f"Processing batch {batch_count}: {len(batch_ids)} salary slips",
                "Batch Process - Batch Start"
            )
            
            batch_results = {
                "batch_num": batch_count,
                "total": len(batch_ids),
                "successful": 0,
                "failed": 0,
                "slip_results": [],
                "execution_time": 0,
                "memory_before": diagnose_system_resources()["memory_usage"],
            }
            
            # Process each slip in batch
            for slip_id in batch_ids:
                try:
                    # Get slip
                    slip = frappe.get_doc("Salary Slip", slip_id)
                    
                    # Only process if docstatus=0 (Draft)
                    if slip.docstatus != 0:
                        batch_results["slip_results"].append({
                            "slip": slip_id,
                            "status": "skipped",
                            "message": f"Salary slip not in draft status (docstatus={slip.docstatus})"
                        })
                        continue
                        
                    # Submit the salary slip
                    slip.submit()
                    
                    # Record success
                    batch_results["successful"] += 1
                    results["successful"] += 1
                    
                except Exception as e:
                    # Log the error
                    batch_results["failed"] += 1
                    results["failed"] += 1
                    results["errors"].append({
                        "slip": slip_id,
                        "error": str(e)
                    })
                    
                    frappe.log_error(
                        f"Error processing slip {slip_id} in batch {batch_count}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}",
                        f"Batch Process - Slip Error"
                    )
            
            # Complete batch
            batch_end = now_datetime()
            batch_time = (batch_end - batch_start).total_seconds()
            batch_results["execution_time"] = batch_time
            
            # Get memory after batch
            batch_results["memory_after"] = diagnose_system_resources()["memory_usage"]
            
            # Add batch results
            results["batches"].append(batch_results)
            
            # Force garbage collection between batches
            import gc
            gc.collect()
            
            # Commit database changes between batches
            frappe.db.commit()
            
        # Calculate total time
        end_time = now_datetime()
        total_time = (end_time - start_time).total_seconds()
        results["execution_time"] = total_time
        
        # Log completion
        frappe.log_error(
            f"Batch processing complete. "
            f"Total: {results['total']}, "
            f"Success: {results['successful']}, "
            f"Failed: {results['failed']}, "
            f"Time: {total_time:.2f}s",
            "Batch Process - Complete"
        )
        
        return results
        
    except Exception as e:
        frappe.log_error(
            f"Error in batch processing: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Batch Process - Error"
        )
        results["errors"].append({
            "global_error": str(e)
        })
        return results


# Helper function for diagnostics
def diagnose_system_resources():
    """Get system resource information"""
    try:
        import psutil
        memory = psutil.virtual_memory()
        return {
            "memory_usage": {
                "total": memory.total / (1024**3),  # GB
                "available": memory.available / (1024**3),  # GB
                "percent": memory.percent
            }
        }
    except ImportError:
        return {
            "memory_usage": {
                "status": "psutil not installed"
            }
        }