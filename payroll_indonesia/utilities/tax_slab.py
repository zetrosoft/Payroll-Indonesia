# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-04 01:59:00 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, cstr, add_days, today, now_datetime
from payroll_indonesia.fixtures.setup import debug_log

__all__ = [
    'create_default_tax_slab',
    'create_income_tax_slab',
    'get_default_tax_slab',
    'update_salary_structures',
    'update_existing_assignments'
]

def create_default_tax_slab():
    """
    Function for compatibility - calls create_income_tax_slab()
    
    Returns:
        str: Name of the Income Tax Slab or None if creation failed
    """
    return create_income_tax_slab()

def create_income_tax_slab():
    """
    Create Income Tax Slab for Indonesia
    
    Returns:
        str: Name of the created or existing Income Tax Slab, None if failed
    """
    try:
        # Check if already exists
        existing_slabs = frappe.get_all(
            "Income Tax Slab", 
            filters={"currency": "IDR"},
            fields=["name"]
        )
        if existing_slabs:
            debug_log(f"Income Tax Slab for IDR already exists: {existing_slabs[0].name}", "Tax Slab")
            return existing_slabs[0].name
            
        # Get company
        company = frappe.defaults.get_defaults().get("company")
        if not company:
            companies = frappe.get_all("Company", fields=["name"])
            if companies:
                company = companies[0].name
            else:
                debug_log("No company found, cannot create Income Tax Slab", "Tax Slab Error")
                return None
                
        # Create slab with unique title
        current_year = getdate(today()).year
        title = f"Indonesia Tax Slab {current_year}"
        
        # Check the autoname field for Income Tax Slab
        autoname_field = frappe.db.get_value("DocType", "Income Tax Slab", "autoname")
        debug_log(f"Income Tax Slab has autoname field: {autoname_field}", "Tax Slab")
        
        # Create doc with necessary fields
        tax_slab = frappe.new_doc("Income Tax Slab")
        
        # Set effective date to beginning of current year
        tax_slab.effective_from = f"{current_year}-01-01"
        tax_slab.company = company
        tax_slab.currency = "IDR"
        
        # Check field existence before setting
        meta = frappe.get_meta("Income Tax Slab")
        
        if meta.get_field("title"):
            tax_slab.title = title
            
        # Important: Set name by title for prompt autoname
        if autoname_field == "prompt":
            # For prompt autoname, use the title as the document name directly
            tax_slab.name = f"Indonesia-Tax-Slab-{current_year}"
            debug_log(f"Setting document name directly to: {tax_slab.name}", "Tax Slab")
            
        if meta.get_field("is_default"):
            tax_slab.is_default = 1
            
        if meta.get_field("disabled"):
            tax_slab.disabled = 0
        
        # Add tax slabs
        tax_slab.append("slabs", {
            "from_amount": 0,
            "to_amount": 60000000,
            "percent_deduction": 5
        })
        
        tax_slab.append("slabs", {
            "from_amount": 60000000,
            "to_amount": 250000000,
            "percent_deduction": 15
        })
        
        tax_slab.append("slabs", {
            "from_amount": 250000000,
            "to_amount": 500000000,
            "percent_deduction": 25
        })
        
        tax_slab.append("slabs", {
            "from_amount": 500000000,
            "to_amount": 5000000000,
            "percent_deduction": 30
        })
        
        tax_slab.append("slabs", {
            "from_amount": 5000000000,
            "to_amount": 0,
            "percent_deduction": 35
        })
        
        # Save doc with additional flags to bypass validation
        tax_slab.flags.ignore_permissions = True
        tax_slab.flags.ignore_mandatory = True
        
        # Special handling for prompt autoname
        if autoname_field == "prompt":
            # Use direct SQL insert as a last resort if normal insertion fails
            try:
                tax_slab.insert()
            except frappe.exceptions.ValidationError as e:
                if "Please set the document name" in str(e):
                    debug_log("Trying alternative approach for prompt autoname", "Tax Slab")
                    
                    # Try using db_set for name
                    tax_slab.db_set("name", f"Indonesia-Tax-Slab-{current_year}")
                    tax_slab.insert(ignore_mandatory=True)
                else:
                    raise
        else:
            tax_slab.insert()
        
        frappe.db.commit()
        
        debug_log(f"Successfully created Income Tax Slab: {tax_slab.name}", "Tax Slab")
        return tax_slab.name
        
    except Exception as e:
        frappe.db.rollback()
        debug_log(f"Error creating Income Tax Slab: {str(e)}", "Tax Slab Error")
        frappe.log_error(f"Error creating Income Tax Slab: {str(e)}\n\n{frappe.get_traceback()}", "Tax Slab Error")
        
        # If we can't create a tax slab, try setting an existing one as default
        try:
            # Find any existing tax slabs
            any_slabs = frappe.get_all("Income Tax Slab", limit=1)
            if any_slabs:
                debug_log(f"Using existing tax slab as fallback: {any_slabs[0].name}", "Tax Slab")
                return any_slabs[0].name
        except:
            pass
            
        return None

def get_default_tax_slab():
    """
    Get default Income Tax Slab for Indonesia
    
    Returns:
        str: Name of the default Income Tax Slab, None if not found or creation failed
    """
    try:
        # Check if we have a default slab
        default_slab = None
        
        # Check if is_default field exists
        meta = frappe.get_meta("Income Tax Slab")
        has_is_default = meta.get_field("is_default") is not None
        
        if has_is_default:
            # Get default slab
            default_slab = frappe.db.get_value(
                "Income Tax Slab", 
                {"currency": "IDR", "is_default": 1},
                "name"
            )
        
        # If no default slab, get any IDR slab
        if not default_slab:
            slabs = frappe.get_all(
                "Income Tax Slab",
                filters={"currency": "IDR"},
                fields=["name"],
                order_by="effective_from desc",
                limit=1
            )
            
            if slabs:
                default_slab = slabs[0].name
                
        # If still no slab, create one
        if not default_slab:
            default_slab = create_income_tax_slab()
            
        return default_slab
        
    except Exception as e:
        frappe.log_error(f"Error getting default tax slab: {str(e)}", "Tax Slab Error")
        return None

def update_salary_structures():
    """
    Update all Salary Structures to bypass Income Tax Slab validation
    with improved error handling for missing salary details
    
    Returns:
        int: Number of successfully updated Salary Structures
    """
    success_count = 0
    error_count = 0
    skipped_count = 0
    
    try:
        # Get default tax slab
        default_tax_slab = get_default_tax_slab()
        if not default_tax_slab:
            debug_log("Failed to get default tax slab", "Tax Slab Error")
            return 0
            
        # Get active salary structures
        structures = frappe.get_all(
            "Salary Structure", 
            filters={"is_active": 1},
            fields=["name", "docstatus"]
        )
        
        debug_log(f"Found {len(structures)} active salary structures to update", "Tax Slab")
        
        # Update each structure with better error handling
        for structure in structures:
            try:
                # First check if the structure can be opened (has valid references)
                try:
                    doc = frappe.get_doc("Salary Structure", structure.name)
                except Exception as e:
                    if "not found" in str(e).lower():
                        # Log the specific missing reference
                        debug_log(f"Skipping structure {structure.name} - missing reference: {str(e)}", "Tax Slab Error")
                        skipped_count += 1
                        continue
                    else:
                        # Re-raise if it's a different kind of error
                        raise
                
                # Check if the structure has valid earnings and deductions
                has_invalid_details = False
                
                # Check earnings
                for i, earning in enumerate(doc.earnings or []):
                    if not frappe.db.exists("Salary Detail", earning.name):
                        debug_log(f"Structure {structure.name} has invalid earning reference: {earning.name}", "Tax Slab Error")
                        has_invalid_details = True
                        break
                
                # Check deductions
                if not has_invalid_details:
                    for i, deduction in enumerate(doc.deductions or []):
                        if not frappe.db.exists("Salary Detail", deduction.name):
                            debug_log(f"Structure {structure.name} has invalid deduction reference: {deduction.name}", "Tax Slab Error")
                            has_invalid_details = True
                            break
                
                if has_invalid_details:
                    skipped_count += 1
                    continue
                
                # Only update if it's not submitted
                if structure.docstatus == 0:
                    # Update the structure
                    doc.income_tax_slab = default_tax_slab
                    doc.tax_calculation_method = "Manual"
                    doc.flags.ignore_validate = True  # Skip validation
                    doc.save(ignore_permissions=True)
                    success_count += 1
                    debug_log(f"Updated structure {structure.name} with tax slab", "Tax Slab")
                else:
                    # For submitted documents, use direct DB update to avoid validation
                    frappe.db.set_value(
                        "Salary Structure",
                        structure.name,
                        {
                            "income_tax_slab": default_tax_slab,
                            "tax_calculation_method": "Manual"
                        },
                        update_modified=False
                    )
                    success_count += 1
                    debug_log(f"Updated submitted structure {structure.name} with tax slab", "Tax Slab")
            except Exception as e:
                error_count += 1
                debug_log(f"Error updating structure {structure.name}: {str(e)}", "Tax Slab Error")
                frappe.log_error(
                    f"Error updating structure {structure.name}: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}", 
                    "Salary Structure Update Error"
                )
                
        frappe.db.commit()
        
        # Log result
        debug_log(f"Updated {success_count} salary structures, {skipped_count} skipped, {error_count} errors", "Tax Slab")
        return success_count
        
    except Exception as e:
        frappe.db.rollback()
        debug_log(f"Critical error updating salary structures: {str(e)}", "Tax Slab Error")
        frappe.log_error(
            f"Critical error updating salary structures: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}", 
            "Tax Slab Error"
        )
        return 0

def update_existing_assignments():
    """
    Update existing Salary Structure Assignments with default Income Tax Slab
    with improved error handling
    
    Returns:
        int: Number of successfully updated Salary Structure Assignments
    """
    success_count = 0
    error_count = 0
    
    try:
        # Get default tax slab
        default_tax_slab = get_default_tax_slab()
        if not default_tax_slab:
            debug_log("Failed to get default tax slab", "Tax Slab Error")
            return 0
            
        # Get assignments needing update
        assignments = frappe.get_all(
            "Salary Structure Assignment",
            filters=[
                ["income_tax_slab", "in", ["", None]],
                ["docstatus", "=", 1]
            ],
            fields=["name", "employee", "salary_structure"]
        )
        
        debug_log(f"Found {len(assignments)} salary structure assignments to update", "Tax Slab")
        
        # Process in batches to avoid transaction timeouts
        batch_size = 50
        for i in range(0, len(assignments), batch_size):
            batch = assignments[i:i+batch_size]
            updated_in_batch = 0
            
            for assignment in batch:
                try:
                    # Check if the referenced salary structure exists
                    if assignment.salary_structure and not frappe.db.exists("Salary Structure", assignment.salary_structure):
                        debug_log(f"Skipping assignment {assignment.name} - salary structure {assignment.salary_structure} not found", "Tax Slab Warning")
                        continue
                        
                    # Update the assignment
                    frappe.db.set_value(
                        "Salary Structure Assignment",
                        assignment.name,
                        "income_tax_slab",
                        default_tax_slab,
                        update_modified=False
                    )
                    updated_in_batch += 1
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    debug_log(f"Error updating assignment {assignment.name} for employee {assignment.employee}: {str(e)}", "Tax Slab Error")
                    frappe.log_error(
                        f"Error updating assignment {assignment.name}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}", 
                        "Tax Slab Assignment Error"
                    )
            
            # Commit after each batch
            frappe.db.commit()
            debug_log(f"Updated {updated_in_batch} assignments in batch {i//batch_size + 1}", "Tax Slab")
                
        # Log final result
        debug_log(f"Updated {success_count} salary structure assignments, {error_count} errors", "Tax Slab")
        return success_count
        
    except Exception as e:
        frappe.db.rollback()
        debug_log(f"Critical error updating salary structure assignments: {str(e)}", "Tax Slab Error")
        frappe.log_error(
            f"Critical error updating salary structure assignments: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}", 
            "Tax Slab Error"
        )
        return 0
