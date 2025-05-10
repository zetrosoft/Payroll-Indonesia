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
                
        # Create tax slab
        tax_slab = frappe.new_doc("Income Tax Slab")
        tax_slab.title = "Indonesia Income Tax"
        tax_slab.effective_from = getdate("2023-01-01")
        tax_slab.company = company
        tax_slab.currency = "IDR"
        tax_slab.income_tax_slab_name = "Indonesia Income Tax"
        tax_slab.is_default = 1
        tax_slab.disabled = 0

        # Add tax brackets
        tax_slab.append("slabs", {"from_amount": 0, "to_amount": 60000000, "percent_deduction": 5})
        tax_slab.append("slabs", {"from_amount": 60000000, "to_amount": 250000000, "percent_deduction": 15})
        tax_slab.append("slabs", {"from_amount": 250000000, "to_amount": 500000000, "percent_deduction": 25})
        tax_slab.append("slabs", {"from_amount": 500000000, "to_amount": 5000000000, "percent_deduction": 30})
        tax_slab.append("slabs", {"from_amount": 5000000000, "to_amount": 0, "percent_deduction": 35})
            
        # Save with flags to bypass validation
        tax_slab.flags.ignore_permissions = True
        tax_slab.flags.ignore_mandatory = True
        tax_slab.insert()
        frappe.db.commit()

        debug_log(f"Successfully created Income Tax Slab: {tax_slab.name}", "Tax Slab")
        return tax_slab.name
            
    except Exception as e:
        frappe.db.rollback()
        debug_log(f"Error creating Income Tax Slab: {str(e)}", "Tax Slab Error")
        frappe.log_error(f"Error creating Income Tax Slab: {str(e)}\n\n{frappe.get_traceback()}", "Tax Slab Error")
        
        # Last resort - check if any tax slabs exist already
        try:
            existing_slabs = frappe.get_all("Income Tax Slab", limit=1)
            if existing_slabs:
                debug_log(f"Using existing tax slab as last resort: {existing_slabs[0].name}", "Tax Slab")
                return existing_slabs[0].name
        except:
            pass
            
        return None

def get_default_tax_slab(create_if_missing=True):
    """
    Get default Income Tax Slab for Indonesia
    
    Args:
        create_if_missing: Create tax slab if none exists
        
    Returns:
        str: Name of the default Income Tax Slab, None if not found or creation failed
    """
    try:
        # Check if we have a default slab
        default_slab = None
        
        # Get default slab if is_default field exists
        try:
            default_slab = frappe.db.get_value(
                "Income Tax Slab", 
                {"currency": "IDR", "is_default": 1},
                "name"
            )
        except:
            pass
        
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
                
        # If still no slab and create_if_missing is True, create one
        if not default_slab and create_if_missing:
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
        
        # Update each structure
        for structure in structures:
            try:
                # Only update if it's not submitted
                if structure.docstatus == 0:
                    # Update the structure
                    doc = frappe.get_doc("Salary Structure", structure.name)
                    doc.income_tax_slab = default_tax_slab
                    doc.tax_calculation_method = "Manual"
                    doc.flags.ignore_validate = True  # Skip validation
                    doc.save(ignore_permissions=True)
                    success_count += 1
                else:
                    # For submitted documents, use direct DB update
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
            except Exception as e:
                frappe.log_error(
                    f"Error updating structure {structure.name}: {str(e)}", 
                    "Salary Structure Update Error"
                )
                
        frappe.db.commit()
        debug_log(f"Updated {success_count} salary structures", "Tax Slab")
        return success_count
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            f"Critical error updating salary structures: {str(e)}", 
            "Tax Slab Error"
        )
        return 0

def update_existing_assignments():
    """
    Update existing Salary Structure Assignments with default Income Tax Slab
    to bypass validation errors
    
    Returns:
        int: Number of successfully updated Salary Structure Assignments
    """
    success_count = 0
    
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
            fields=["name", "salary_structure"]
        )
        
        debug_log(f"Found {len(assignments)} salary structure assignments to update", "Tax Slab")
        
        # Find structures with PPh 21 component
        tax_structures = []
        try:
            structures_with_tax = frappe.db.sql("""
                SELECT DISTINCT parent 
                FROM `tabSalary Detail` 
                WHERE salary_component = 'PPh 21'
                AND parenttype = 'Salary Structure'
            """, as_dict=1)
            
            if structures_with_tax:
                tax_structures = [s.parent for s in structures_with_tax]
        except:
            pass
            
        # Process assignments
        batch_size = 50
        for i in range(0, len(assignments), batch_size):
            batch = assignments[i:i+batch_size]
            updated_in_batch = 0
            
            for assignment in batch:
                try:
                    # Only update if the structure has PPh 21 component
                    if assignment.salary_structure in tax_structures:
                        frappe.db.set_value(
                            "Salary Structure Assignment",
                            assignment.name,
                            "income_tax_slab",
                            default_tax_slab,
                            update_modified=False
                        )
                        updated_in_batch += 1
                        success_count += 1
                except Exception:
                    continue
            
            # Commit after each batch
            frappe.db.commit()
                
        debug_log(f"Updated {success_count} salary structure assignments", "Tax Slab")
        return success_count
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            f"Error updating salary structure assignments: {str(e)}", 
            "Tax Slab Error"
        )
        return 0