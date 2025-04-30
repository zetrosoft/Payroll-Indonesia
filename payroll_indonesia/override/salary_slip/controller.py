# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-30 10:42:45 by dannyaudian

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
        for d in self.earnings + self.deductions:
            if d.salary_component == component_name:
                return d.amount
        return 0

    def set_component(self, component_name, amount, is_deduction=False):
        """Set or update a component in earnings or deductions"""
        target = self.deductions if is_deduction else self.earnings
        found = False
        for d in target:
            if d.salary_component == component_name:
                d.amount = flt(amount)
                found = True
                break
        if not found:
            target.append({
                "salary_component": component_name,
                "amount": flt(amount)
            })

    def initialize_payroll_fields(self):
        """
        Initialize additional payroll fields for Indonesian Payroll.
        """
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
        except Exception:
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
                    # Get slip - use cached lookup if available
                    slip = frappe.get_doc("Salary Slip", slip_id)
                    
                    # Only process if docstatus=0 (Draft)
                    if slip.docstatus != 0:
                        batch_results["slip_results"].append({
                            "slip": slip_id,
                            "status": "skipped",
                            "message": f"Salary slip not in draft status (docstatus={slip.docstatus})"
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
                    # Log the error
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
            
            # Log batch completion
            frappe.log_error(
                f"Completed batch {batch_count}: "
                f"Success: {batch_results['successful']}, "
                f"Failed: {batch_results['failed']}, "
                f"Time: {batch_time:.2f}s",
                "Batch Process - Batch Complete"
            )
            
            # Force garbage collection between batches
            import gc
            gc.collect()
            
            # Add small delay between batches to allow background jobs to start
            frappe.db.commit()
            frappe.db.set_value("Background Job Settings", None, 
                               {"last_batch_processed_timestamp": now_datetime()})
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

def clear_caches():
    """Clear TER rate and YTD tax caches to prevent memory bloat"""
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
    
    # Schedule next cleanup in 30 minutes
    frappe.enqueue(clear_caches, queue='long', job_name='clear_payroll_caches', is_async=True, now=False, 
                   enqueue_after=add_to_date(now_datetime(), minutes=30))

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

# Export these functions at the module level so they can be imported directly
get_component = IndonesiaPayrollSalarySlip.get_component
set_component = IndonesiaPayrollSalarySlip.set_component