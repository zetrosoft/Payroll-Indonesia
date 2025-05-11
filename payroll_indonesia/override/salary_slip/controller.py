# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 08:28:29 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime, add_to_date
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from frappe.utils.background_jobs import get_jobs, enqueue
import json
import hashlib

class IndonesiaPayrollSalarySlip(SalarySlip):
    """Custom Salary Slip class for Indonesia Payroll"""

    def get_component(self, component_name):
        """Get amount of a salary component"""
        try:
            if not component_name:
                return 0
                
            for d in self.earnings + self.deductions:
                if d.salary_component == component_name:
                    return flt(d.amount)
            return 0
        except Exception as e:
            # Non-critical error - log and return 0
            frappe.log_error(
                "Error getting component {0} from salary slip {1}: {2}".format(
                    component_name, self.name if hasattr(self, 'name') else 'unknown', str(e)
                ),
                "Component Retrieval Error"
            )
            return 0

    def set_component(self, component_name, amount, is_deduction=False):
        """Set or update a component in earnings or deductions"""
        try:
            if not component_name:
                frappe.throw(
                    _("Component name is required"),
                    title=_("Missing Component Name")
                )
                
            # Validate amount is a number
            try:
                amount = flt(amount)
            except Exception as e:
                frappe.log_error(
                    "Invalid amount '{0}' for component {1}: {2}".format(
                        amount, component_name, str(e)
                    ),
                    "Amount Validation Error"
                )
                frappe.msgprint(
                    _("Invalid amount for component {0}, using 0").format(component_name),
                    indicator="orange"
                )
                amount = 0
                
            # Select target collection
            target = self.deductions if is_deduction else self.earnings
            if not target:
                frappe.throw(
                    _("Target collection {0} is not initialized").format(
                        "deductions" if is_deduction else "earnings"
                    ),
                    title=_("Invalid Document State")
                )
                
            found = False
            for d in target:
                if d.salary_component == component_name:
                    d.amount = amount
                    found = True
                    break
                    
            if not found:
                # Verify component exists
                if not frappe.db.exists("Salary Component", component_name):
                    frappe.throw(
                        _("Salary Component {0} does not exist").format(component_name),
                        title=_("Invalid Component")
                    )
                    
                target.append({
                    "salary_component": component_name,
                    "amount": amount
                })
        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
                
            # Critical component update error - throw
            frappe.log_error(
                "Error setting component {0} to {1} in salary slip {2}: {3}".format(
                    component_name, amount, 
                    self.name if hasattr(self, 'name') else 'unknown', str(e)
                ),
                "Component Update Error"
            )
            frappe.throw(
                _("Error updating component {0}: {1}").format(component_name, str(e)),
                title=_("Component Update Failed")
            )

    def initialize_payroll_fields(self):
        """
        Initialize additional payroll fields for Indonesian Payroll.
        """
        try:
            defaults = {
                'biaya_jabatan': 0,
                'netto': 0,
                'total_bpjs': 0,
                'is_using_ter': 0,
                'ter_rate': 0,
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
                    
            return defaults  # Return defaults for external callers who might need them
        except Exception as e:
            # Critical initialization error - throw
            frappe.log_error(
                "Error initializing payroll fields for {0}: {1}".format(
                    self.name if hasattr(self, 'name') else 'New Salary Slip', str(e)
                ),
                "Field Initialization Error"
            )
            frappe.throw(
                _("Could not initialize payroll fields: {0}").format(str(e)),
                title=_("Initialization Failed")
            )

    def queue_document_updates_on_cancel(self):
        """
        Schedule updates to related documents when canceling salary slip.
        This is a stub function that will be implemented in the full version.
        """
        # This will be implemented in the full version
        # For now, it's just a placeholder to ensure import works
        pass

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
        except Exception as e:
            # Non-critical error - log and return None
            frappe.log_error(
                "Error estimating memory usage for {0}: {1}".format(
                    self.name if hasattr(self, 'name') else 'unknown', str(e)
                ),
                "Memory Estimation Error"
            )
            return None

# Module-level functions that need to be exported

def setup_fiscal_year_if_missing(date_str=None):
    """
    Automatically set up a fiscal year if missing
    Returns:
        dict: Result of the fiscal year creation
    """
    try:
        from frappe.utils import getdate, add_days, add_to_date
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
        # This is a critical operation for payroll if called by user - log error
        frappe.log_error(
            "Error setting up fiscal year: {0}".format(str(e)),
            "Fiscal Year Setup Error"
        )
        
        # If directly called by user, throw; otherwise return error
        if frappe.local.form_dict.cmd == "payroll_indonesia.override.salary_slip.controller.setup_fiscal_year_if_missing":
            frappe.throw(
                _("Failed to set up fiscal year: {0}").format(str(e)),
                title=_("Fiscal Year Setup Failed")
            )
            
        return {
            "status": "error",
            "message": str(e)
        }

@frappe.whitelist()
def process_salary_slips_batch(salary_slips=None, slip_ids=None, batch_size=50):
    """
    Process multiple salary slips in batches to manage memory usage
    Args:
        salary_slips: List of salary slip objects (optional)
        slip_ids: List of salary slip IDs to process (optional)
        batch_size: Number of slips to process in each batch
    Returns:
        dict: Results of the batch processing
    """
    start_time = now_datetime()
    
    # Log start of batch process
    frappe.log_error(
        "Starting batch processing of salary slips. Batch size: {0}".format(batch_size),
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
        
        # If neither provided, raise error - this is a validation failure
        if not slip_ids:
            frappe.throw(
                _("No salary slips provided for batch processing"),
                title=_("Missing Input")
            )
            
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
                "Processing batch {0}: {1} salary slips".format(batch_count, len(batch_ids)),
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
                    # Get slip - use cached lookup if available
                    slip = frappe.get_doc("Salary Slip", slip_id)
                    
                    # Only process if docstatus=0 (Draft)
                    if slip.docstatus != 0:
                        batch_results["slip_results"].append({
                            "slip": slip_id,
                            "status": "skipped",
                            "message": "Salary slip not in draft status (docstatus={0})".format(slip.docstatus)
                        })
                        continue
                        
                    # Estimate memory before
                    if hasattr(slip, '_estimate_memory_usage'):
                        mem_before = slip._estimate_memory_usage()
                    else:
                        mem_before = None
                    
                    # Submit the salary slip
                    slip.submit()
                    
                    # Estimate memory after
                    if hasattr(slip, '_estimate_memory_usage'):
                        mem_after = slip._estimate_memory_usage()
                    else:
                        mem_after = None
                        
                    # Record success
                    batch_results["successful"] += 1
                    results["successful"] += 1
                    
                    batch_results["slip_results"].append({
                        "slip": slip_id,
                        "status": "success",
                        "memory_before": mem_before,
                        "memory_after": mem_after
                    })
                    
                except Exception as e:
                    # Non-critical error - individual slip failed but batch can continue
                    batch_results["failed"] += 1
                    results["failed"] += 1
                    results["errors"].append({
                        "slip": slip_id,
                        "error": str(e)
                    })
                    
                    batch_results["slip_results"].append({
                        "slip": slip_id,
                        "status": "error",
                        "message": str(e)
                    })
                    
                    frappe.log_error(
                        "Error processing slip {0} in batch {1}: {2}".format(
                            slip_id, batch_count, str(e)
                        ),
                        "Batch Process - Slip Error"
                    )
            
            # Complete batch
            batch_end = now_datetime()
            batch_time = (batch_end - batch_start).total_seconds()
            batch_results["execution_time"] = batch_time
            
            # Get memory after batch
            batch_results["memory_after"] = diagnose_system_resources()["memory_usage"]
            
            # Add batch results
            results["batches"].append(batch_results)
            
            # Log batch completion
            frappe.log_error(
                "Completed batch {0}: Success: {1}, Failed: {2}, Time: {3:.2f}s".format(
                    batch_count, batch_results['successful'], batch_results['failed'], batch_time
                ),
                "Batch Process - Batch Complete"
            )
            
            # Force garbage collection between batches
            import gc
            gc.collect()
            
            # Add small delay between batches to allow background jobs to start
            frappe.db.commit()
            frappe.db.set_value(
                "Background Job Settings", 
                None, 
                {"last_batch_processed_timestamp": now_datetime()}
            )
            frappe.db.commit()
            
        # Calculate total time
        end_time = now_datetime()
        total_time = (end_time - start_time).total_seconds()
        results["execution_time"] = total_time
        
        # Log completion
        frappe.log_error(
            "Batch processing complete. Total: {0}, Success: {1}, Failed: {2}, Time: {3:.2f}s".format(
                results['total'], results['successful'], results['failed'], total_time
            ),
            "Batch Process - Complete"
        )
        
        # Show summary to user
        frappe.msgprint(
            _("Processed {0} salary slips: {1} successful, {2} failed. See error log for details.").format(
                results['total'], results['successful'], results['failed']
            ),
            indicator="green" if results['failed'] == 0 else "orange"
        )
        
        return results
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Critical error in batch processing - log and throw
        frappe.log_error(
            "Error in batch processing: {0}".format(str(e)),
            "Batch Process - Error"
        )
        
        # Add error to results, but also throw since this is user-initiated
        results["errors"].append({
            "global_error": str(e)
        })
        
        frappe.throw(
            _("Batch processing failed: {0}").format(str(e)),
            title=_("Batch Processing Failed")
        )
        
        return results

def check_fiscal_year_setup(date_str=None):
    """
    Check if fiscal years are properly set up
    
    Args:
        date_str: Date string to check (optional)
    Returns:
        dict: Status of fiscal year setup
    """
    try:
        from frappe.utils import getdate
        test_date = getdate(date_str) if date_str else getdate()
        
        # Query fiscal year
        fiscal_year = frappe.db.get_value("Fiscal Year", {
            "year_start_date": ["<=", test_date],
            "year_end_date": [">=", test_date]
        })
        
        if not fiscal_year:
            return {
                "status": "error",
                "message": "No active Fiscal Year found for date {0}".format(test_date),
                "solution": "Create a Fiscal Year that includes this date in Company settings"
            }
        
        return {
            "status": "ok",
            "fiscal_year": fiscal_year
        }
    except Exception as e:
        # Non-critical check error - log and return error status
        frappe.log_error(
            "Error checking fiscal year setup for date {0}: {1}".format(
                date_str if date_str else 'current date', str(e)
            ),
            "Fiscal Year Check Error"
        )
        return {
            "status": "error",
            "message": str(e)
        }

def clear_caches():
    """Clear TER rate and YTD tax caches to prevent memory bloat"""
    try:
        global _ter_rate_cache, _ytd_tax_cache
        
        # Define these to prevent NameError if they're not defined earlier
        if '_ter_rate_cache' not in globals():
            global _ter_rate_cache
            _ter_rate_cache = {}
            
        if '_ytd_tax_cache' not in globals():
            global _ytd_tax_cache
            _ytd_tax_cache = {}
        
        _ter_rate_cache = {}
        _ytd_tax_cache = {}
        
        # Log cache clearing
        frappe.log_error(
            "TER rate and YTD tax caches cleared",
            "Cache Clearing"
        )
        
        # Schedule next cleanup in 30 minutes
        frappe.enqueue(
            clear_caches, 
            queue='long', 
            job_name='clear_payroll_caches', 
            is_async=True, 
            now=False, 
            enqueue_after=add_to_date(now_datetime(), minutes=30)
        )
    except Exception as e:
        # Non-critical error - log but don't interrupt processing
        frappe.log_error(
            "Error clearing caches: {0}".format(str(e)),
            "Cache Clearing Error"
        )
        # No msgprint here as this is typically run as background task

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
        # Non-critical error - just return status
        return {
            "memory_usage": {
                "status": "psutil not installed"
            }
        }
    except Exception as e:
        # Non-critical error - log and return status
        frappe.log_error(
            "Error diagnosing system resources: {0}".format(str(e)),
            "Resource Diagnosis Error"
        )
        return {
            "memory_usage": {
                "status": "error",
                "message": str(e)
            }
        }

# Export these functions at the module level so they can be imported directly
get_component = IndonesiaPayrollSalarySlip.get_component
set_component = IndonesiaPayrollSalarySlip.set_component