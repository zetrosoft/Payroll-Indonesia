# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-29 14:30:00 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime, add_to_date
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from hrms.payroll.doctype.salary_slip.salary_slip import make_salary_slip_from_timesheet as original_make_slip
from frappe.utils.background_jobs import get_jobs, enqueue
import json
import hashlib

# Debug function for error tracking with enhanced information
def debug_log(message, module_name="Salary Slip Debug", employee=None, trace=False):
    """Log debug message with timestamp, employee info, and optional traceback"""
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    employee_info = f"[Employee: {employee}] " if employee else ""
    log_message = f"[{timestamp}] {employee_info}{message}"
    
    if trace:
        log_message += f"\nTraceback: {frappe.get_traceback()}"
    
    frappe.log_error(log_message, module_name)

# Import functions from support modules with better error handling and cache TER rates
_ter_rate_cache = {}
_ytd_tax_cache = {}

try:
    debug_log("Starting imports from payroll_indonesia modules")
    
    from payroll_indonesia.override.salary_slip.base import get_formatted_currency, get_component_amount, update_component_amount
    from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components
    from payroll_indonesia.override.salary_slip.bpjs_calculator import calculate_bpjs_components
    from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter, should_use_ter_method, get_ter_rate
    
    # Direct import for BPJS calculation to ensure it's always available
    from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs
    
    debug_log("Successfully imported all payroll_indonesia modules")
except ImportError as e:
    debug_log(f"Error importing Payroll Indonesia modules: {str(e)}", trace=True)
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
        
    def calculate_bpjs_components(doc, employee, base):
        debug_log(f"Using placeholder calculate_bpjs_components: employee={employee.name if hasattr(employee, 'name') else 'unknown'}, base={base}")
        pass
        
    def hitung_bpjs(employee, base_salary):
        debug_log(f"Using placeholder hitung_bpjs: employee={employee}, base_salary={base_salary}")
        # Return default structure to prevent errors
        return {
            "kesehatan_employee": 0,
            "jht_employee": 0,
            "jp_employee": 0,
            "total_employee": 0
        }


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll
    Extends hrms.payroll.doctype.salary_slip.salary_slip.SalarySlip
    
    Key features for Indonesian payroll:
    - BPJS calculations (Kesehatan, JHT, JP, JKK, JKM)
    - PPh 21 tax calculations with gross or gross-up methods
    - TER (Tax Equal Rate) method support
    - Integration with BPJS Payment Summary
    - Integration with Employee Tax Summary
    """
    def validate(self):
        """Validate salary slip and calculate Indonesian components"""
        employee_info = f"{self.employee} ({self.employee_name})" if hasattr(self, 'employee_name') else self.employee
        debug_log(f"Starting validate for salary slip {self.name}", employee=employee_info)
        
        try:
            # Call parent validation first
            debug_log(f"Calling parent validate for {self.name}", employee=employee_info)
            super(IndonesiaPayrollSalarySlip, self).validate()
            
            # Initialize additional fields if not present
            debug_log(f"Initializing payroll fields for {self.name}", employee=employee_info)
            self.initialize_payroll_fields()
            
            # Get employee document with validation
            debug_log(f"Getting employee doc for {self.employee}", employee=employee_info)
            employee = self.get_employee_doc()
            
            # Calculate base salary for BPJS
            debug_log(f"Calculating base salary for {self.name}", employee=employee_info)
            base_salary = self.get_base_salary_for_bpjs()
            debug_log(f"Base salary for BPJS calculation: {base_salary}", employee=employee_info)
            
            # Calculate BPJS components once
            self.calculate_and_set_bpjs_components(employee, base_salary)
            
            # IMPROVED: First determine tax calculation strategy, then calculate
            tax_strategy = self.determine_tax_strategy(employee)
            self.calculate_tax_with_strategy(tax_strategy, employee)
            
            # Generate tax ID data
            self.generate_tax_id_data(employee)

            # Add note to payroll_note
            self.add_payroll_note("Validasi berhasil: Komponen BPJS dan Pajak dihitung.")
            debug_log(f"Validation completed successfully for {self.name}", employee=employee_info)
            
        except Exception as e:
            debug_log(f"Error in validate for {self.name}: {str(e)}", employee=employee_info, trace=True)
            frappe.log_error(
                f"Error dalam validasi Salary Slip untuk {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Validation Error"
            )
            frappe.throw(_("Error dalam validasi Salary Slip: {0}").format(str(e)))
    
    def determine_tax_strategy(self, employee):
        """
        Determine which tax calculation strategy should be used
        Returns: String indicating the strategy ("TER" or "PROGRESSIVE")
        """
        try:
            # Get PPh 21 Settings - only get required fields for better performance
            pph_settings = frappe.get_cached_value(
                "PPh 21 Settings", 
                "PPh 21 Settings",
                ["calculation_method", "use_ter", "default_ter_rate"],
                as_dict=True
            ) or {}
        
            # Check if calculation_method and use_ter fields exist
            if not pph_settings.get('calculation_method'):
                return "PROGRESSIVE"
            
            if not pph_settings.get('use_ter'):
                return "PROGRESSIVE"
        
            # Check if TER method is enabled globally
            if pph_settings.get('calculation_method') == "TER" and pph_settings.get('use_ter'):
                # Check if employee is eligible for TER - using an optimized check
                if self._is_eligible_for_ter(employee):
                    return "TER"
        
            # Default to progressive method
            return "PROGRESSIVE"
        except Exception as e:
            debug_log(f"Error determining tax strategy for {employee.name}: {str(e)}", trace=True)
            return "PROGRESSIVE"

    def _is_eligible_for_ter(self, employee):
        """
        Optimized check if employee is eligible for TER method
        Args:
            employee: Employee document
        Returns:
            bool: True if eligible, False otherwise
        """
        # Quick check for exclusion fields
        if hasattr(employee, 'tipe_karyawan') and employee.tipe_karyawan == "Freelance":
            return False
            
        if hasattr(employee, 'override_tax_method') and employee.override_tax_method == "Progressive":
            return False
            
        return True

    def calculate_tax_with_strategy(self, strategy, employee):
        """
        Calculate tax based on selected strategy
        Args:
            strategy: String indicating strategy ("TER" or "PROGRESSIVE")
            employee: Employee document
        """
        if strategy == "TER":
            from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter
            debug_log(f"Calculating tax with TER for {self.name}")
            calculate_monthly_pph_with_ter(self, employee)
        else:
            from payroll_indonesia.override.salary_slip.tax_calculator import calculate_monthly_pph_progressive
            debug_log(f"Calculating tax with Progressive method for {self.name}")
            calculate_monthly_pph_progressive(self, employee)

    def on_submit(self):
        """Create related documents on submit and verify BPJS values"""
        try:
            # Start time measurement
            start_time = now_datetime()
            debug_log(f"Starting on_submit for salary slip {self.name}", 
                      employee=getattr(self, 'employee_name', self.employee))
            
            # Verify BPJS components before submission
            self.verify_bpjs_components()
        
            # Call parent on_submit method
            super(IndonesiaPayrollSalarySlip, self).on_submit()
        
            # Use optimized queue for document creation
            self.queue_document_creation()
        
            # Calculate and log execution time
            end_time = now_datetime()
            execution_time = (end_time - start_time).total_seconds()
            
            # Add detailed note to payroll_note
            message = (
                f"Submit berhasil: Pembuatan dokumen terkait telah dijadwalkan. "
                f"Waktu proses: {execution_time:.2f} detik."
            )
            self.add_payroll_note(message)
            
            debug_log(f"on_submit completed in {execution_time:.2f} seconds for {self.name}")
            
        except Exception as e:
            debug_log(f"Error in on_submit for {self.name}: {str(e)}", trace=True)
            frappe.log_error(
                f"Error in on_submit for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip Submit Error"
            )
            frappe.throw(_("Error during salary slip submission: {0}").format(str(e)))
               
    def calculate_and_set_bpjs_components(self, employee, base_salary):
        """
        Calculate BPJS components using direct call to hitung_bpjs
        and update salary slip components
        """
        employee_info = f"{employee.name} ({employee.employee_name})" if hasattr(employee, 'employee_name') else employee.name
        
        try:
            # Check if employee is enrolled in BPJS - use fast check
            is_enrolled = self.check_bpjs_enrollment(employee)
            if not is_enrolled:
                debug_log(f"Employee {employee_info} not enrolled in BPJS - skipping calculation")
                return
        
            # Calculate BPJS values using hitung_bpjs
            from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs
            bpjs_values = hitung_bpjs(employee.name, base_salary)
        
            # Set BPJS components in salary slip
            if bpjs_values:
                # BPJS JHT Employee
                jht_amount = flt(bpjs_values.get("jht_employee", 0))
                self.set_component_value("BPJS JHT Employee", jht_amount, is_deduction=True)
            
                # BPJS JP Employee
                jp_amount = flt(bpjs_values.get("jp_employee", 0))
                self.set_component_value("BPJS JP Employee", jp_amount, is_deduction=True)
            
                # BPJS Kesehatan Employee
                kesehatan_amount = flt(bpjs_values.get("kesehatan_employee", 0))
                self.set_component_value("BPJS Kesehatan Employee", kesehatan_amount, is_deduction=True)
            
                # Calculate and store total BPJS deductions
                total_bpjs = jht_amount + jp_amount + kesehatan_amount
            
                # Set total in custom field
                if hasattr(self, 'total_bpjs'):
                    self.total_bpjs = total_bpjs
            
                # Add BPJS details to payroll note
                self.add_bpjs_details_to_note(bpjs_values)
            
        except Exception as e:
            debug_log(f"Error calculating BPJS for {self.name}: {str(e)}", trace=True)
            frappe.log_error(
                f"Error calculating BPJS for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Calculation Error"
            )
            frappe.throw(_("Error calculating BPJS: {0}").format(str(e)))
        
    def add_bpjs_details_to_note(self, bpjs_values):
        """Add BPJS calculation details to the payroll note"""
        try:
            # Get BPJS settings once and cache it
            if not hasattr(self, '_bpjs_settings'):
                from payroll_indonesia.payroll_indonesia.utils import get_bpjs_settings
                self._bpjs_settings = get_bpjs_settings()
            
            settings = self._bpjs_settings
            
            # Get BPJS percentage rates
            kesehatan_percent = flt(settings.get("kesehatan_employee_percent", 1.0))
            jht_percent = flt(settings.get("jht_employee_percent", 2.0))
            jp_percent = flt(settings.get("jp_employee_percent", 1.0))
        
            # BPJS details
            self.payroll_note += "\n\n=== Perhitungan BPJS ==="
        
            # Add component details
            if bpjs_values.get("kesehatan_employee", 0) > 0:
                self.payroll_note += f"\nBPJS Kesehatan ({kesehatan_percent}%): Rp {bpjs_values['kesehatan_employee']:,.0f}"
            
            if bpjs_values.get("jht_employee", 0) > 0:
                self.payroll_note += f"\nBPJS JHT ({jht_percent}%): Rp {bpjs_values['jht_employee']:,.0f}"
            
            if bpjs_values.get("jp_employee", 0) > 0:
                self.payroll_note += f"\nBPJS JP ({jp_percent}%): Rp {bpjs_values['jp_employee']:,.0f}"
        
            # Total
            total_employee = bpjs_values.get("total_employee", 0)
            self.payroll_note += f"\nTotal BPJS: Rp {total_employee:,.0f}"
        
        except Exception as e:
            debug_log(f"Error adding BPJS details to note: {str(e)}")
            # Continue even if there's an error adding details to the note
    
    def verify_bpjs_components(self):
        """
        Verify BPJS component values before submission
        Log detailed information about current values
        """
        employee_info = f"{self.employee} ({self.employee_name})" if hasattr(self, 'employee_name') else self.employee
        debug_log(f"Verifying BPJS components for {self.name}", employee=employee_info)
        
        # Check if components exist and have values - use optimized lookup
        bpjs_components = {
            "BPJS JHT Employee": 0,
            "BPJS JP Employee": 0,
            "BPJS Kesehatan Employee": 0
        }
        
        # Get current values - use direct lookup for better performance
        for deduction in self.deductions:
            if deduction.salary_component in bpjs_components:
                bpjs_components[deduction.salary_component] = flt(deduction.amount)
        
        # Log component values
        debug_log(
            f"BPJS components for {self.name}: "
            f"JHT={bpjs_components['BPJS JHT Employee']}, "
            f"JP={bpjs_components['BPJS JP Employee']}, "
            f"Kesehatan={bpjs_components['BPJS Kesehatan Employee']}, "
            f"Total: {sum(bpjs_components.values())}",
            employee=employee_info
        )
        
        # Check if employee should have BPJS but all values are zero
        if all(value == 0 for value in bpjs_components.values()):
            try:
                # Check enrollment efficiently without loading full employee doc if possible
                if hasattr(self, '_cached_employee'):
                    employee = self._cached_employee
                else:
                    employee = frappe.get_doc("Employee", self.employee)
                    self._cached_employee = employee
                    
                is_enrolled = self.check_bpjs_enrollment(employee)
                
                if is_enrolled:
                    debug_log(
                        f"WARNING: Employee {employee_info} is enrolled in BPJS but all BPJS components are zero. "
                        f"This may indicate a calculation issue.",
                        employee=employee_info
                    )
                    
                    # Re-attempt BPJS calculation as a fallback
                    base_salary = self.get_base_salary_for_bpjs()
                    self.calculate_and_set_bpjs_components(employee, base_salary)
            except Exception as e:
                debug_log(f"Error during BPJS verification: {str(e)}", employee=employee_info, trace=True)
    
    def check_bpjs_enrollment(self, employee=None):
        """
        Check if employee is enrolled in BPJS - optimized version
        Args:
            employee: Employee document (optional)
        Returns:
            bool: True if enrolled, False otherwise
        """
        if not employee:
            if hasattr(self, '_cached_employee'):
                employee = self._cached_employee
            else:
                employee = self.get_employee_doc()
                self._cached_employee = employee
            
        # Use fast-path check with direct attribute access
        is_enrolled = getattr(employee, 'is_bpjs_active', True)
        
        # Only check specific types if main flag is False
        if not is_enrolled:
            kesehatan_enrolled = getattr(employee, 'bpjs_kesehatan_active', False)
            jht_enrolled = getattr(employee, 'bpjs_jht_active', False)
            jp_enrolled = getattr(employee, 'bpjs_jp_active', False)
            
            # Employee is enrolled if at least one type is active
            return kesehatan_enrolled or jht_enrolled or jp_enrolled
            
        return True
    
    def queue_document_creation(self):
        """
        Queue creation of related documents after salary slip submission:
        - Employee Tax Summary
        - BPJS Payment Summary (if BPJS components exist)
        - PPh TER Table (if using TER method)
        
        Optimized version with job_name parameters to avoid duplicates.
        """
        try:
            # Generate unique job identifiers
            job_prefix = hashlib.md5(f"{self.name}_{now_datetime()}".encode()).hexdigest()[:8]
            is_test = bool(getattr(frappe.flags, 'in_test', False))
            
            # Check for BPJS components - optimized version
            bpjs_amounts = self._get_component_amounts(["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"])
            has_bpjs = any(amount > 0 for amount in bpjs_amounts.values())
            
            # Check if using TER
            is_using_ter = getattr(self, 'is_using_ter', 0)
            ter_rate = getattr(self, 'ter_rate', 0)
            
            # Log start of document creation
            start_time = now_datetime()
            month = getdate(self.end_date).month
            year = getdate(self.end_date).year
            
            # Prepare note about queued documents
            queued_docs = ["Employee Tax Summary"]
            
            # 1. Queue Employee Tax Summary creation (always created)
            job_id = f"tax_summary_{job_prefix}_{self.name}"
            
            # Check if job already exists in the queue
            if not self._job_exists(job_id):
                enqueue(
                    method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.create_from_salary_slip",
                    queue="long",  # Changed to long queue for better load balancing
                    timeout=600,   # Increased timeout
                    is_async=True,
                    job_name=job_id,
                    now=is_test,
                    salary_slip=self.name
                )
        
            # 2. Queue BPJS Payment Summary if needed
            if has_bpjs:
                job_id = f"bpjs_summary_{job_prefix}_{self.name}"
                queued_docs.append("BPJS Payment Summary")
                
                if not self._job_exists(job_id):
                    enqueue(
                        method="payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.create_from_salary_slip",
                        queue="long",
                        timeout=600,
                        is_async=True, 
                        job_name=job_id,
                        now=is_test,
                        salary_slip=self.name
                    )
        
            # 3. Queue PPh TER Table creation if using TER
            if is_using_ter:
                job_id = f"pph_ter_{job_prefix}_{self.name}"
                queued_docs.append(f"PPh TER Table (rate: {ter_rate}%)")
                
                if not self._job_exists(job_id):
                    enqueue(
                        method="payroll_indonesia.payroll_indonesia.doctype.pph_ter_table.pph_ter_table.create_from_salary_slip",
                        queue="long",
                        timeout=600,
                        is_async=True,
                        job_name=job_id,
                        now=is_test, 
                        salary_slip=self.name
                    )
            
            # Add note to salary slip's payroll_note field with details
            if hasattr(self, 'payroll_note'):
                timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
                queued_docs_text = ", ".join(queued_docs)
                memory_estimate = self._estimate_memory_usage()
                
                note = (
                    f"\n[{timestamp}] Submit berhasil: Dokumen dijadwalkan: {queued_docs_text}. "
                    f"Periode: {month:02d}/{year}. "
                )
                
                if memory_estimate:
                    note += f"Est. memory: {memory_estimate:.2f}MB."
                    
                self.payroll_note += note
                
                # Use db_set to avoid another full save
                self.db_set('payroll_note', self.payroll_note, update_modified=False)
            
            # Calculate and log execution time for queuing
            end_time = now_datetime()
            execution_time = (end_time - start_time).total_seconds()
            
            debug_log(
                f"Document creation jobs queued in {execution_time:.2f}s for {self.name}: "
                f"{', '.join(queued_docs)}"
            )
            
        except Exception as e:
            debug_log(f"Error queueing document creation for {self.name}: {str(e)}", trace=True)
            frappe.log_error(
                f"Error queueing document creation for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "Salary Slip - Document Queue Error"
            )
            # Do not raise exception, just show a message to the user
            frappe.msgprint(_("Warning: Error occurred while queueing related documents: {0}").format(str(e)))

    def _job_exists(self, job_name):
        """
        Check if a job with the given name already exists in the queue
        Args:
            job_name: Job name to check
        Returns:
            bool: True if job exists, False otherwise
        """
        try:
            # Check all queues for the job
            for queue in ['default', 'long', 'short']:
                jobs = get_jobs(queue, job_name=job_name)
                if jobs:
                    return True
            return False
        except Exception:
            # If error checking queues, assume job doesn't exist
            return False
            
    def _get_component_amounts(self, component_names):
        """
        Get component amounts efficiently
        Args:
            component_names: List of component names to get
        Returns:
            dict: Dictionary of component names and amounts
        """
        result = {name: 0 for name in component_names}
        
        for deduction in self.deductions:
            if deduction.salary_component in result:
                result[deduction.salary_component] = flt(deduction.amount)
                
        return result
        
    def _estimate_memory_usage(self):
        """
        Estimate memory usage of this salary slip
        Returns:
            float: Estimated memory usage in MB or None if error
        """
        try:
            # Convert to string to estimate size - includes child tables
            doc_str = json.dumps(self.as_dict())
            # Convert to MB (approximate)
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
            
            debug_log(f"on_cancel completed successfully for {self.name}", employee=employee_info)
            
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
            
            # Schedule update for BPJS Payment Summary
            job_id = f"bpjs_cancel_{job_prefix}_{self.name}"
            enqueue(
                method="payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.update_on_salary_slip_cancel",
                queue="long",
                timeout=600,
                is_async=True,
                job_name=job_id,
                now=is_test,
                **{"salary_slip": self.name, "month": month, "year": year}
            )
            
            # Schedule update for PPh TER Table if using TER
            if getattr(self, 'is_using_ter', 0) == 1:
                job_id = f"ter_cancel_{job_prefix}_{self.name}"
                enqueue(
                    method="payroll_indonesia.payroll_indonesia.doctype.pph_ter_table.pph_ter_table.update_on_salary_slip_cancel",
                    queue="long",
                    timeout=600,
                    is_async=True,
                    job_name=job_id,
                    now=is_test,
                    **{"salary_slip": self.name, "month": month, "year": year}
                )
            
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
            
            debug_log(f"queue_document_updates_on_cancel completed for {self.name}", employee=employee_info)
            
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
        debug_log(f"Initializing payroll fields for {self.name}")
        # Use single assignment for better performance
        defaults = {
            'biaya_jabatan': 0,
            'netto': 0,
            'total_bpjs': 0,
            'is_using_ter': 0,
            'ter_rate': 0,
            'koreksi_pph21': 0,
            'payroll_note': "",
            'npwp': "",
            'ktp': ""
        }
        
        # Set defaults for fields that don't exist or are None
        for field, default in defaults.items():
            if not hasattr(self, field) or getattr(self, field) is None:
                setattr(self, field, default)
                
        debug_log(f"Payroll fields initialized for {self.name}")
    
    def get_employee_doc(self):
        """Get employee document with validation and caching"""
        if not self.employee:
            frappe.throw(_("Employee harus diisi untuk salary slip"))
            
        # Return cached employee if available
        if hasattr(self, '_cached_employee'):
            return self._cached_employee
            
        try:
            # Get only required fields for better performance
            employee_doc = frappe.get_doc("Employee", self.employee)
            
            # Cache for reuse
            self._cached_employee = employee_doc
            return employee_doc
        except Exception as e:
            debug_log(f"Error retrieving employee document for {self.employee}: {str(e)}", trace=True)
            frappe.throw(_("Error saat mengambil data karyawan {0}: {1}").format(self.employee, str(e)))
    
    def get_base_salary_for_bpjs(self):
        """
        Get base salary for BPJS calculation
        First tries to find Gaji Pokok component, then falls back to Basic or first component
        """
        debug_log(f"Getting base salary for BPJS calculation for {self.name}")
        
        # Optimized component lookup with direct access
        for earning in self.earnings:
            if earning.salary_component == "Gaji Pokok":
                return flt(earning.amount)
        
        # If not found, try Basic
        for earning in self.earnings:
            if earning.salary_component == "Basic":
                return flt(earning.amount)
        
        # If still not found, use first component
        if self.earnings:
            return flt(self.earnings[0].amount)
        
        # If still zero, use gross_pay
        if hasattr(self, 'gross_pay'):
            return flt(self.gross_pay)
            
        # Last resort - return 0
        return 0
    
    def generate_tax_id_data(self, employee):
        """Get tax ID information (NPWP and KTP) from employee data"""
        try:
            # Get NPWP and KTP from employee
            if hasattr(employee, 'npwp'):
                self.npwp = employee.npwp
                
            if hasattr(employee, 'ktp'):
                self.ktp = employee.ktp
                
        except Exception as e:
            debug_log(f"Error generating tax ID data for {self.name}: {str(e)}", trace=True)
            frappe.log_error(f"Error generating tax ID data: {str(e)}", "Tax ID Data Error")
            # Don't throw, since this is non-critical
    
    def add_payroll_note(self, note):
        """Add note to payroll_note field with timestamp"""
        if not hasattr(self, 'payroll_note'):
            self.payroll_note = ""
            
        # Add timestamp to note
        timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
        
        # Add new note
        self.payroll_note += f"\n[{timestamp}] {note}"
    
    def get_component_value(self, component_name, component_type):
        """
        Get component amount with better error handling and caching
        Args:
            component_name: Name of the component
            component_type: Type of component (earnings/deductions)
        Returns:
            float: Component amount or 0 if not found
        """
        # Use cache to avoid repeated lookups
        cache_key = f"{component_type}:{component_name}"
        if not hasattr(self, '_component_cache'):
            self._component_cache = {}
            
        if cache_key in self._component_cache:
            return self._component_cache[cache_key]
            
        # Direct lookup for better performance
        components = getattr(self, component_type, [])
        for comp in components:
            if comp.salary_component == component_name:
                value = flt(comp.amount)
                self._component_cache[cache_key] = value
                return value
                
        # If not found, return 0
        self._component_cache[cache_key] = 0
        return 0
    
    def set_component_value(self, component_name, amount, is_deduction=False):
        """
        Set component value with improved error handling
        Args:
            component_name: Name of the component
            amount: Amount to set
            is_deduction: Whether this is a deduction component
        """
        if amount is None:
            amount = 0
            
        amount = flt(amount)
        component_type = "deductions" if is_deduction else "earnings"
        
        # Use direct component setting for better performance
        component_list = getattr(self, component_type, [])
        
        # Look for existing component
        found = False
        for comp in component_list:
            if comp.salary_component == component_name:
                comp.amount = amount
                found = True
                
                # Update cache if it exists
                if hasattr(self, '_component_cache'):
                    cache_key = f"{component_type}:{component_name}"
                    self._component_cache[cache_key] = amount
                    
                break
                
        if not found and amount > 0:
            # Component doesn't exist, create it if amount > 0
            try:
                # Get component abbr efficiently
                abbr = frappe.get_cached_value("Salary Component", component_name, "salary_component_abbr")
                if not abbr:
                    abbr = component_name[:3].upper()
                
                # Create and add row
                row = frappe.new_doc("Salary Detail")
                row.salary_component = component_name
                row.abbr = abbr
                row.amount = amount
                row.parentfield = component_type
                row.parenttype = "Salary Slip"
                row.parent = self.name
                
                component_list.append(row)
                
                # Update cache if it exists
                if hasattr(self, '_component_cache'):
                    cache_key = f"{component_type}:{component_name}"
                    self._component_cache[cache_key] = amount
                    
            except Exception as e:
                debug_log(f"Error creating new component {component_name}: {str(e)}", trace=True)
        
        # Update totals
        self.update_totals()
    
    def update_totals(self):
        """Update salary slip totals after component changes"""
        # Use optimized sum calculation
        self.gross_pay = sum(flt(e.amount) for e in self.earnings)
        self.total_deduction = sum(flt(d.amount) for d in self.deductions)
        
        # Update net pay
        total_loan = flt(getattr(self, 'total_loan_repayment', 0))
        self.net_pay = self.gross_pay - self.total_deduction - total_loan


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
    global _ter_rate_cache, _ytd_tax_cache
    _ter_rate_cache = {}
    _ytd_tax_cache = {}
    
    # Schedule next cleanup in 30 minutes
    frappe.enqueue(clear_caches, queue='long', job_name='clear_payroll_caches', is_async=True, now=False, 
                   enqueue_after=add_to_date(now_datetime(), minutes=30))
    
# Start cache clearing process when module loads
clear_caches()

# Diagnostic function
@frappe.whitelist()
def diagnose_salary_slip_submission(salary_slip_name):
    """Diagnostic function for salary slip submission issues"""
    debug_log(f"Starting diagnosis for salary slip {salary_slip_name}")
    result = {
        "salary_slip_exists": False,
        "class_override_working": False,
        "custom_fields_exist": {},
        "dependent_doctypes_exist": {},
        "background_jobs_count": 0,
        "memory_estimate": None,
        "recommendations": []
    }
    
    try:
        # Check if salary slip exists
        if not frappe.db.exists("Salary Slip", salary_slip_name):
            result["recommendations"].append(f"Salary slip {salary_slip_name} not found. Please provide a valid salary slip name.")
            return result
            
        result["salary_slip_exists"] = True
        
        # Get the salary slip
        slip = frappe.get_doc("Salary Slip", salary_slip_name)
        
        # Check if class override is working
        result["class_override_working"] = isinstance(slip, IndonesiaPayrollSalarySlip)
        
        # Estimate memory usage
        if result["class_override_working"]:
            result["memory_estimate"] = slip._estimate_memory_usage()
        
        # Check custom fields
        custom_fields = ["biaya_jabatan", "netto", "total_bpjs", "is_using_ter", "ter_rate", "koreksi_pph21", "payroll_note", "npwp", "ktp"]
        for field in custom_fields:
            result["custom_fields_exist"][field] = hasattr(slip, field)
            
        # Check background jobs
        try:
            queues = ['default', 'short', 'long']
            job_counts = {}
            total_jobs = 0
            
            for queue in queues:
                jobs = get_jobs(queue) or {}
                queue_count = len(jobs)
                job_counts[queue] = queue_count
                total_jobs += queue_count
                
            result["background_jobs"] = job_counts
            result["background_jobs_count"] = total_jobs
            
            # Check for job limits
            if total_jobs > 2000:
                result["recommendations"].append(
                    f"High number of background jobs ({total_jobs}). "
                    "Consider clearing the queue or increasing worker count."
                )
        except Exception as e:
            result["recommendations"].append(f"Error checking background jobs: {str(e)}")
        
        # Check Redis memory usage if possible
        try:
            from rq.utils import current_timestamp
            result["rq_timestamp"] = current_timestamp()
        except Exception:
            pass
            
        # Generate recommendations
        if not result["class_override_working"]:
            result["recommendations"].append("SalarySlip class override is not working. Check hooks.py for correct override_doctype_class configuration.")
            
        if result["memory_estimate"] and result["memory_estimate"] > 10:
            result["recommendations"].append(
                f"Salary slip memory usage is high ({result['memory_estimate']:.2f}MB). "
                "Consider reviewing and optimizing attachments and child tables."
            )
            
        missing_fields = [field for field, exists in result["custom_fields_exist"].items() if not exists]
        if missing_fields:
            result["recommendations"].append(f"Missing custom fields: {', '.join(missing_fields)}. Create these fields in Salary Slip doctype.")
            
        # Success case
        if not result["recommendations"]:
            result["recommendations"].append("Diagnostics completed successfully. No issues detected.")
            
        return result
        
    except Exception as e:
        debug_log(f"Error in diagnose_salary_slip_submission: {str(e)}", trace=True)
        result["recommendations"].append(f"Error during diagnosis: {str(e)}")
        return result