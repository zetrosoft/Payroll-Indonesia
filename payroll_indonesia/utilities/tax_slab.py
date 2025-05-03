# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, cstr, add_days, today

def create_default_tax_slab():
    """
    Function for compatibility - calls create_income_tax_slab()
    """
    return create_income_tax_slab()

def create_income_tax_slab():
    """Buat Income Tax Slab untuk Indonesia"""
    try:
        # Check if already exists
        existing_slabs = frappe.get_all(
            "Income Tax Slab", 
            filters={"currency": "IDR"},
            fields=["name"]
        )
        if existing_slabs:
            frappe.logger().info(f"Income Tax Slab untuk IDR sudah ada: {existing_slabs[0].name}")
            return existing_slabs[0].name
            
        # Get company
        company = frappe.defaults.get_defaults().get("company")
        if not company:
            companies = frappe.get_all("Company", fields=["name"])
            if companies:
                company = companies[0].name
            else:
                frappe.logger().error("No company found, cannot create Income Tax Slab")
                return None
                
        # Create slab with unique title
        current_year = getdate(today()).year
        title = f"Indonesia Tax Slab {current_year}"
        
        # Get DocField properties
        meta = frappe.get_meta("Income Tax Slab")
        has_title = meta.get_field("title") is not None
        has_name = meta.get_field("name") is not None
        has_is_default = meta.get_field("is_default") is not None
        has_disabled = meta.get_field("disabled") is not None
        
        # Create doc with necessary fields
        tax_slab = frappe.new_doc("Income Tax Slab")
        
        # Check field existence before setting
        if has_title:
            tax_slab.title = title
        
        # Set effective date to beginning of current year
        tax_slab.effective_from = f"{current_year}-01-01"
        tax_slab.company = company
        tax_slab.currency = "IDR"
        
        if has_is_default:
            tax_slab.is_default = 1
            
        if has_disabled:
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
        
        # Save doc
        tax_slab.insert(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.logger().info(f"Successfully created Income Tax Slab: {tax_slab.name}")
        return tax_slab.name
        
    except Exception as e:
        frappe.db.rollback()
        frappe.logger().error(f"Error membuat Income Tax Slab: {str(e)}")
        frappe.log_error(f"Error membuat Income Tax Slab: {str(e)}", "Tax Slab Error")
        return None

def get_default_tax_slab():
    """Mendapatkan nama Income Tax Slab default"""
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
    """Update semua Salary Structure untuk bypass validasi Income Tax Slab"""
    success_count = 0
    error_count = 0
    
    try:
        # Get default tax slab
        default_tax_slab = get_default_tax_slab()
        if not default_tax_slab:
            frappe.logger().error("Failed to get default tax slab")
            return 0
            
        # Get active salary structures
        structures = frappe.get_all(
            "Salary Structure", 
            filters={"is_active": 1},
            fields=["name"]
        )
        
        # Update each structure
        for structure in structures:
            try:
                doc = frappe.get_doc("Salary Structure", structure.name)
                doc.income_tax_slab = default_tax_slab
                doc.tax_calculation_method = "Manual"
                doc.save(ignore_permissions=True)
                success_count += 1
            except Exception as e:
                error_count += 1
                frappe.logger().error(f"Error updating structure {structure.name}: {str(e)}")
                
        frappe.db.commit()
        
        # Log result
        frappe.logger().info(f"Updated {success_count} salary structures, {error_count} errors")
        return success_count
        
    except Exception as e:
        frappe.log_error(f"Error updating salary structures: {str(e)}", "Tax Slab Error")
        return 0

def update_existing_assignments():
    """Update existing Salary Structure Assignments with default Income Tax Slab"""
    success_count = 0
    error_count = 0
    
    try:
        # Get default tax slab
        default_tax_slab = get_default_tax_slab()
        if not default_tax_slab:
            frappe.logger().error("Failed to get default tax slab")
            return 0
            
        # Get assignments needing update
        assignments = frappe.get_all(
            "Salary Structure Assignment",
            filters=[
                ["income_tax_slab", "in", ["", None]],
                ["docstatus", "=", 1]
            ],
            fields=["name"]
        )
        
        # Update each assignment
        for assignment in assignments:
            try:
                frappe.db.set_value(
                    "Salary Structure Assignment",
                    assignment.name,
                    "income_tax_slab",
                    default_tax_slab,
                    update_modified=False
                )
                success_count += 1
            except Exception as e:
                error_count += 1
                frappe.logger().error(f"Error updating assignment {assignment.name}: {str(e)}")
                
        frappe.db.commit()
        
        # Log result
        frappe.logger().info(f"Updated {success_count} salary structure assignments, {error_count} errors")
        return success_count
        
    except Exception as e:
        frappe.log_error(f"Error updating salary structure assignments: {str(e)}", "Tax Slab Error")
        return 0