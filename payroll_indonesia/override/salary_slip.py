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
    'clear_caches'
]

# Cache variables - moved inside class as class variables
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
    
    # Class-level cache variables
    _ter_rate_cache = {}
    _ytd_tax_cache = {}
    _ptkp_mapping_cache = None  # For PMK 168/2023 TER mapping
    
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
    
    def _get_employee_doc(self):
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
            frappe.throw(_("Error saat mengambil data karyawan {0}: {1}").format(self.employee, str(e)))
    
    def _calculate_bpjs(self, employee):
        """Calculate BPJS components for the salary slip"""
        try:
            from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs, check_bpjs_enrollment
            
            # Get base salary for BPJS calculations
            base_salary = self._get_base_salary_for_bpjs()
            
            # Check if employee is enrolled in BPJS
            bpjs_enrollment = check_bpjs_enrollment(employee)
            
            if not bpjs_enrollment:
                # Employee not enrolled in BPJS, set zeros and return
                self._set_bpjs_components(0, 0, 0)
                return
            
            # Calculate BPJS components
            bpjs_values = hitung_bpjs(employee, base_salary)
            
            # Set component values in salary slip
            self._set_bpjs_components(
                bpjs_values.get("kesehatan_employee", 0),
                bpjs_values.get("jht_employee", 0),
                bpjs_values.get("jp_employee", 0)
            )
            
            # Set total BPJS field
            self.total_bpjs = flt(bpjs_values.get("total_employee", 0))
            self.db_set('total_bpjs', self.total_bpjs, update_modified=False)
            
            # Verify BPJS components
            self._verify_bpjs_components(employee, base_salary)
            
        except ImportError:
            frappe.msgprint(_("BPJS calculation module not found. BPJS components will not be calculated."))
        except Exception as e:
            frappe.msgprint(_("Error calculating BPJS components: {0}").format(str(e)))
    
    def _set_bpjs_components(self, kesehatan, jht, jp):
        """Set BPJS component values in the salary slip"""
        # Helper function to update or add component
        def update_component(component_name, amount, component_type="deductions"):
            components = getattr(self, component_type, [])
            
            # Try to find existing component
            for comp in components:
                if comp.salary_component == component_name:
                    comp.amount = flt(amount)
                    return True
            
            # Component not found, add new one
            try:
                # Get component details
                component_doc = frappe.get_doc("Salary Component", component_name)
                
                # Get abbreviation
                abbr = component_doc.salary_component_abbr if hasattr(component_doc, "salary_component_abbr") else component_name[:3].upper()
                
                # Create new row
                row = frappe.new_doc("Salary Detail")
                row.salary_component = component_name
                row.abbr = abbr
                row.amount = flt(amount)
                row.parentfield = component_type
                row.parenttype = "Salary Slip"
                row.parent = self.name if hasattr(self, 'name') else ""
                
                # Add to components
                components.append(row)
                return True
            except Exception:
                return False
        
        # Update each BPJS component
        update_component("BPJS Kesehatan Employee", kesehatan)
        update_component("BPJS JHT Employee", jht)
        update_component("BPJS JP Employee", jp)
    
    def _verify_bpjs_components(self, employee, base_salary):
        """Verify BPJS components and recalculate if necessary"""
        from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs, check_bpjs_enrollment
        
        # Check if all BPJS components are zero
        all_zero = True
        for component in ["BPJS Kesehatan Employee", "BPJS JHT Employee", "BPJS JP Employee"]:
            amount = self._get_component_amount(component, "deductions")
            if flt(amount) > 0:
                all_zero = False
                break
        
        # If all zero but employee should have BPJS, recalculate
        if all_zero and check_bpjs_enrollment(employee):
            bpjs_values = hitung_bpjs(employee, base_salary)
            if bpjs_values and bpjs_values["total_employee"] > 0:
                # Set components again with recalculated values
                self._set_bpjs_components(
                    bpjs_values.get("kesehatan_employee", 0),
                    bpjs_values.get("jht_employee", 0),
                    bpjs_values.get("jp_employee", 0)
                )
                
                # Update total_bpjs
                self.total_bpjs = flt(bpjs_values["total_employee"])
                self.db_set('total_bpjs', self.total_bpjs, update_modified=False)
    
    def _get_component_amount(self, component_name, component_type):
        """Get amount for a specific component"""
        components = getattr(self, component_type, [])
        for comp in components:
            if comp.salary_component == component_name:
                return flt(comp.amount)
        return 0
    
    def _update_component_amount(self, component_name, amount, component_type):
        """Update or add a component with specified amount"""
        components = getattr(self, component_type, [])
        
        # Find and update existing component
        for comp in components:
            if comp.salary_component == component_name:
                comp.amount = flt(amount)
                return True
        
        # Component not found, add new one if it exists in the system
        try:
            # Check if component exists
            if not frappe.db.exists("Salary Component", component_name):
                return False
                
            # Get component details
            component_doc = frappe.get_doc("Salary Component", component_name)
            
            # Get abbreviation
            abbr = component_doc.salary_component_abbr if hasattr(component_doc, "salary_component_abbr") else component_name[:3].upper()
            
            # Create new row
            row = frappe.new_doc("Salary Detail")
            row.salary_component = component_name
            row.abbr = abbr
            row.amount = flt(amount)
            row.parentfield = component_type
            row.parenttype = "Salary Slip"
            row.parent = self.name if hasattr(self, 'name') else ""
            
            # Add to components
            components.append(row)
            return True
        except Exception:
            return False
    
    def _get_base_salary_for_bpjs(self):
        """Get base salary for BPJS calculation with enhanced validation"""
        base_salary = 0
        
        # Check if earnings exist
        if not hasattr(self, 'earnings') or not self.earnings:
            # No earnings, use gross_pay if available
            if hasattr(self, 'gross_pay') and self.gross_pay > 0:
                return flt(self.gross_pay)
            return 0
        
        # Try to find Gaji Pokok component first    
        for earning in self.earnings:
            if earning.salary_component == "Gaji Pokok":
                base_salary = flt(earning.amount)
                break
        
        # If not found, try Basic
        if base_salary <= 0:
            for earning in self.earnings:
                if earning.salary_component == "Basic":
                    base_salary = flt(earning.amount)
                    break
            
            # If still not found, use first component
            if base_salary <= 0 and self.earnings:
                base_salary = flt(self.earnings[0].amount)
        
        # If still zero, use gross_pay as fallback
        if base_salary <= 0 and hasattr(self, 'gross_pay') and self.gross_pay > 0:
            base_salary = flt(self.gross_pay)
            
        # Final check - if still zero, use UMR as fallback for safe calculation
        if base_salary <= 0:
            default_umr = 4900000  # Jakarta UMR as default
            base_salary = default_umr
            
        return base_salary
    
    def _calculate_tax(self, employee):
        """Calculate tax based on appropriate method (TER or Progressive)"""
        # Store original values to restore after calculation
        original_values = {
            'gross_pay': flt(self.gross_pay),
            'monthly_gross_for_ter': flt(getattr(self, 'monthly_gross_for_ter', 0)),
            'annual_taxable_amount': flt(getattr(self, 'annual_taxable_amount', 0)),
            'ter_rate': flt(getattr(self, 'ter_rate', 0)),
            'ter_category': getattr(self, 'ter_category', '')
        }
        
        try:
            # Determine tax calculation strategy
            strategy = self._determine_tax_strategy(employee)
            
            if strategy == "TER":
                self._apply_ter(employee)
            else:
                self._apply_progressive(employee)
            
            # Verify calculation integrity
            self._verify_tax_calculation(original_values)
            
        except Exception as e:
            self._handle_tax_calculation_error(e)
            
        finally:
            # Ensure TER flags are set correctly for TER strategy
            if strategy == "TER" and not getattr(self, 'is_using_ter', 0):
                self.is_using_ter = 1
                self.db_set('is_using_ter', 1, update_modified=False)
            
            # Verify gross_pay hasn't been modified unexpectedly
            if strategy == "TER" and abs(original_values['gross_pay'] - self.gross_pay) > 1:
                # Restore original gross_pay for TER calculation
                self.gross_pay = original_values['gross_pay']
    
    def _determine_tax_strategy(self, employee):
        """Determine whether to use TER or Progressive method"""
        try:
            from payroll_indonesia.override.salary_slip.ter_calculator import should_use_ter_method
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
    
    def _apply_ter(self, employee):
        """Apply TER calculation method"""
        try:
            from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter, map_ptkp_to_ter_category
            
            # Call TER calculation function
            calculate_monthly_pph_with_ter(self, employee)
            
            # If ter_category is not set, determine it
            if not hasattr(self, 'ter_category') or not self.ter_category:
                ter_category = map_ptkp_to_ter_category(employee)
                if ter_category:
                    self.ter_category = ter_category
                    self.db_set('ter_category', ter_category, update_modified=False)
            
            # Explicitly set and persist TER flags
            self.is_using_ter = 1
            
            # Ensure ter_rate has a valid value
            if not hasattr(self, 'ter_rate') or flt(self.ter_rate) <= 0:
                self.ter_rate = 5.0  # Default to 5% if missing or zero
            
            # Persist values to database with db_set
            self.db_set('is_using_ter', 1, update_modified=False)
            self.db_set('ter_rate', flt(self.ter_rate), update_modified=False)
            
            # Add note to payroll_note
            self.add_payroll_note(f"TER method applied with rate: {self.ter_rate}%")
            
        except ImportError as e:
            frappe.throw(_("TER calculation module not found: {0}").format(str(e)))
        except Exception as e:
            frappe.throw(_("Error in TER calculation: {0}").format(str(e)))
    
    def _apply_progressive(self, employee):
        """Apply Progressive calculation method"""
        try:
            from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components
            
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
            
        except ImportError as e:
            frappe.throw(_("Tax calculation module not found: {0}").format(str(e)))
        except Exception as e:
            frappe.throw(_("Error in progressive tax calculation: {0}").format(str(e)))
    
    def _verify_tax_calculation(self, original_values):
        """Verify tax calculation integrity"""
        try:
            from payroll_indonesia.override.salary_slip.ter_calculator import verify_calculation_integrity
            
            verify_calculation_integrity(
                doc=self,
                original_values=original_values,
                monthly_gross_pay=getattr(self, 'monthly_gross_for_ter', self.gross_pay),
                annual_taxable_amount=getattr(self, 'annual_taxable_amount', 0),
                ter_rate=getattr(self, 'ter_rate', 0) / 100 if hasattr(self, 'ter_rate') else 0,
                ter_category=getattr(self, 'ter_category', ''),
                monthly_tax=self._get_tax_amount()
            )
        except ImportError:
            # Skip verification if module not available
            pass
    
    def _get_tax_amount(self):
        """Get PPh 21 amount from deductions"""
        return next(
            (d.amount for d in self.deductions if d.salary_component == "PPh 21"),
            0
        )
    
    def _verify_ter_settings(self):
        """Verify TER settings consistency"""
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
    
    def _generate_tax_id_data(self, employee):
        """Get tax ID information (NPWP and KTP) from employee data"""
        try:
            if hasattr(employee, 'npwp'):
                self.npwp = employee.npwp
                
            if hasattr(employee, 'ktp'):
                self.ktp = employee.ktp
                
        except Exception as e:
            frappe.log_error(f"Error generating tax ID data: {str(e)}", "Tax ID Data Error")
    
    def _check_or_create_fiscal_year(self):
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
            frappe.log_error(f"Error checking/creating fiscal year: {str(e)}", "Fiscal Year Check Error")
    
    def _handle_validation_error(self, e, employee_info=""):
        """Handle validation errors consistently"""
        frappe.log_error(
            f"Error dalam validasi Salary Slip untuk {self.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Salary Slip Validation Error"
        )
        frappe.throw(_("Error dalam validasi Salary Slip: {0}").format(str(e)))
    
    def _handle_tax_calculation_error(self, e):
        """Handle tax calculation errors consistently"""
        frappe.log_error(
            f"Tax Calculation Error for {self.name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Calculation Error"
        )
        frappe.throw(_("Tax Calculation Error: {0}").format(str(e)))
    
    def on_submit(self):
        """Create related documents on submit and verify BPJS values"""
        try:
            # Verify TER settings before submit
            self._verify_ter_settings()
            
            # Call parent on_submit method
            super(IndonesiaPayrollSalarySlip, self).on_submit()
            
            # Queue document creation
            self._queue_document_creation()
            
        except Exception as e:
            frappe.log_error(
                f"Error in on_submit for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Submit Error"
            )
            frappe.throw(_("Error during salary slip submission: {0}").format(str(e)))

    def _queue_document_creation(self):
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
                frappe.enqueue(
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
            from frappe.utils.background_jobs import get_jobs
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
        try:
            # Call parent on_cancel method
            super(IndonesiaPayrollSalarySlip, self).on_cancel()
            
            # Update related documents
            self._queue_document_updates_on_cancel()
            
        except Exception as e:
            frappe.log_error(
                f"Error dalam on_cancel Salary Slip untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Cancel Error"
            )
            frappe.msgprint(_("Warning: Error saat mengupdate dokumen terkait pada pembatalan: {0}").format(str(e)))
    
    def _queue_document_updates_on_cancel(self):
        """Schedule updates to related documents when canceling salary slip"""
        month = getdate(self.end_date).month
        year = getdate(self.end_date).year
        is_test = bool(getattr(frappe.flags, 'in_test', False))
        
        try:
            # Generate unique job identifiers
            job_prefix = hashlib.md5(f"cancel_{self.name}_{now_datetime()}".encode()).hexdigest()[:8]
            
            # Schedule update for Employee Tax Summary
            job_id = f"tax_cancel_{job_prefix}_{self.name}"
            frappe.enqueue(
                method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.update_on_salary_slip_cancel",
                queue="long",
                timeout=600,
                is_async=True,
                job_name=job_id,
                now=is_test,
                salary_slip=self.name,
                year=year
            )
            
            # Add note about cancellation
            timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
            note = f"[{timestamp}] Cancel berhasil: Pembaruan dokumen terkait telah dijadwalkan."
            self.add_payroll_note(note)
            
            # Add note about BPJS Payment Summary
            self.add_payroll_note("BPJS Payment Summary perlu diupdate secara manual jika sudah dibuat sebelumnya.")
            
        except Exception as e:
            frappe.log_error(
                f"Error dalam queue_document_updates_on_cancel: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Document Update Queue Error"
            )
            frappe.msgprint(_("Error saat menjadwalkan pembaruan dokumen terkait: {0}").format(str(e)))
    
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


# Override SalarySlip controller with enhanced version
try:
    frappe.model.document.get_controller("Salary Slip")._controller = IndonesiaPayrollSalarySlip
except Exception as e:
    frappe.log_error(
        f"Error overriding SalarySlip controller: {str(e)}\n\n"
        f"Traceback: {frappe.get_traceback()}",
        "Controller Override Error"
    )

# Cache management functions
def clear_caches():
    """Clear TER rate and YTD tax caches to prevent memory bloat"""
    IndonesiaPayrollSalarySlip._ter_rate_cache = {}
    IndonesiaPayrollSalarySlip._ytd_tax_cache = {}
    IndonesiaPayrollSalarySlip._ptkp_mapping_cache = None
    
    # Schedule next cleanup in 30 minutes
    frappe.enqueue(clear_caches, queue='long', job_name='clear_payroll_caches', is_async=True, now=False, 
                  enqueue_after=add_to_date(now_datetime(), minutes=30))

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

# Start cache clearing process when module loads
clear_caches()