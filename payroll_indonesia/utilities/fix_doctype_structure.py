# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 06:17:17 by dannyaudian

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

def fix_bpjs_payment_summary():
    """
    Fix BPJS Payment Summary structure by adding custom fields if needed
    """
    frappe.msgprint(_("Checking BPJS Payment Summary DocType structure..."))
    
    if not frappe.db.exists("DocType", "BPJS Payment Summary"):
        frappe.throw(_("BPJS Payment Summary DocType not found."))
        return
        
    # Check required fields using custom field approach
    required_fields = {
        "month": {"fieldtype": "Int", "label": "Month", "insert_after": "company"},
        "year": {"fieldtype": "Int", "label": "Year", "insert_after": "month"},
        "month_year": {"fieldtype": "Data", "label": "Month-Year", "insert_after": "year"},
        "month_name": {"fieldtype": "Data", "label": "Month Name", "insert_after": "month_year"},
        "month_year_title": {"fieldtype": "Data", "label": "Title", "insert_after": "month_name"}
    }
    
    # Check if fields exist already
    docfields = frappe.get_meta("BPJS Payment Summary").fields
    existing_fields = [df.fieldname for df in docfields]
    missing_fields = [f for f in required_fields.keys() if f not in existing_fields]
    
    if missing_fields:
        frappe.msgprint(_("Missing fields detected in BPJS Payment Summary: {0}").format(
            ", ".join(missing_fields)
        ))
        
        # Create custom fields for missing fields
        for field_name in missing_fields:
            field_def = required_fields[field_name]
            
            try:
                create_custom_field("BPJS Payment Summary", {
                    "fieldname": field_name,
                    "fieldtype": field_def["fieldtype"],
                    "label": field_def["label"],
                    "insert_after": field_def["insert_after"]
                })
                frappe.msgprint(f"Added field '{field_name}' to BPJS Payment Summary.")
            except Exception as e:
                frappe.log_error(
                    f"Error creating custom field {field_name}: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}",
                    "Custom Field Creation Error"
                )
                frappe.msgprint(f"Error creating field '{field_name}': {str(e)}")
    else:
        frappe.msgprint(_("BPJS Payment Summary structure is OK."))
        
    # Check child table
    check_bpjs_payment_details()

def check_bpjs_payment_details():
    """Check and fix the structure of BPJS Payment Details child table"""
    try:
        # Find the child table DocType name
        child_table_fieldname = None
        parent_meta = frappe.get_meta("BPJS Payment Summary")
        
        for field in parent_meta.fields:
            if field.fieldtype == "Table" and ("employee_details" in field.fieldname or "details" in field.fieldname):
                child_table_fieldname = field.fieldname
                child_doctype_name = field.options
                break
        
        if not child_table_fieldname:
            # Create a custom link field for the child table relationship
            frappe.msgprint(_("Creating employee_details table field in BPJS Payment Summary"))
            
            create_custom_field("BPJS Payment Summary", {
                "fieldname": "employee_details_section",
                "fieldtype": "Section Break",
                "label": "Employee Details",
                "insert_after": "month_year_title"
            })
            
            # Check if we can find or create a child DocType
            child_doctype_name = "BPJS Payment Details"
            if not frappe.db.exists("DocType", child_doctype_name):
                frappe.msgprint(_(f"Child table DocType {child_doctype_name} not found. Please create it manually."))
                return
            
            # Create the table field
            create_custom_field("BPJS Payment Summary", {
                "fieldname": "employee_details",
                "fieldtype": "Table",
                "label": "Employee Details",
                "options": child_doctype_name,
                "insert_after": "employee_details_section"
            })
            frappe.msgprint(_(f"Created employee_details table field linked to {child_doctype_name}"))
            
        # Check fields in the child table
        if child_doctype_name and frappe.db.exists("DocType", child_doctype_name):
            check_child_table_fields(child_doctype_name)
        
    except Exception as e:
        frappe.log_error(
            f"Error checking BPJS Payment Details structure: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "DocType Structure Check Error"
        )
        frappe.msgprint(_("Error checking BPJS Payment Details structure: {0}").format(str(e)))

def check_child_table_fields(child_doctype_name):
    """Check and add missing fields to child table via custom fields"""
    child_meta = frappe.get_meta(child_doctype_name)
    existing_fields = [df.fieldname for df in child_meta.fields]
    
    required_fields = {
        "employee": {"fieldtype": "Link", "label": "Employee", "options": "Employee", 
                     "insert_after": "idx", "reqd": 1},
        "employee_name": {"fieldtype": "Data", "label": "Employee Name", 
                          "insert_after": "employee", "fetch_from": "employee.employee_name"},
        "salary_slip": {"fieldtype": "Link", "label": "Salary Slip", "options": "Salary Slip", 
                        "insert_after": "employee_name"},
        "jht_employee": {"fieldtype": "Currency", "label": "JHT Employee", 
                         "insert_after": "salary_slip"},
        "jht_employer": {"fieldtype": "Currency", "label": "JHT Employer", 
                         "insert_after": "jht_employee"},
        "jp_employee": {"fieldtype": "Currency", "label": "JP Employee", 
                        "insert_after": "jht_employer"},
        "jp_employer": {"fieldtype": "Currency", "label": "JP Employer", 
                        "insert_after": "jp_employee"},
        "jkk": {"fieldtype": "Currency", "label": "JKK", "insert_after": "jp_employer"},
        "jkm": {"fieldtype": "Currency", "label": "JKM", "insert_after": "jkk"},
        "kesehatan_employee": {"fieldtype": "Currency", "label": "Kesehatan Employee", 
                              "insert_after": "jkm"},
        "kesehatan_employer": {"fieldtype": "Currency", "label": "Kesehatan Employer", 
                              "insert_after": "kesehatan_employee"}
    }
    
    missing_fields = [f for f in required_fields.keys() if f not in existing_fields]
    
    if missing_fields:
        frappe.msgprint(_("Missing fields detected in {0}: {1}").format(
            child_doctype_name, 
            ", ".join(missing_fields)
        ))
        
        # For child table, if it's a custom DocType, we can directly add the fields
        is_custom = frappe.db.get_value("DocType", child_doctype_name, "custom")
        
        if is_custom:
            # Add fields directly to the custom DocType
            for field_name in missing_fields:
                field_def = required_fields[field_name]
                
                try:
                    # Get DocType and add field
                    doc = frappe.get_doc("DocType", child_doctype_name)
                    field = doc.append("fields", {})
                    field.fieldname = field_name
                    field.fieldtype = field_def["fieldtype"]
                    field.label = field_def["label"]
                    
                    if "options" in field_def:
                        field.options = field_def["options"]
                    if "reqd" in field_def:
                        field.reqd = field_def["reqd"]
                    if "fetch_from" in field_def:
                        field.fetch_from = field_def["fetch_from"]
                    
                    doc.save()
                    frappe.msgprint(f"Added field '{field_name}' to {child_doctype_name}")
                    
                except Exception as e:
                    frappe.log_error(
                        f"Error adding field {field_name}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}",
                        "Field Addition Error"
                    )
                    frappe.msgprint(f"Error adding field '{field_name}': {str(e)}")
        else:
            # For standard DocTypes, suggest creating a custom child DocType
            frappe.msgprint(_(
                "Cannot modify standard child table directly. "
                "Please create a custom child DocType with all required fields."
            ))
    else:
        frappe.msgprint(_("{0} structure is OK.").format(child_doctype_name))

def create_custom_child_doctype(doctype_name):
    """Create a new custom child DocType with all required fields"""
    try:
        if frappe.db.exists("DocType", doctype_name):
            frappe.msgprint(_(f"{doctype_name} already exists."))
            return
        
        # Create custom DocType
        doc = frappe.new_doc("DocType")
        doc.name = doctype_name
        doc.module = "Payroll Indonesia"
        doc.custom = 1  # Mark as custom
        doc.istable = 1
        doc.editable_grid = 1
        doc.track_changes = 0
        
        # Add fields
        fields = [
            {"fieldname": "employee", "fieldtype": "Link", "label": "Employee", "options": "Employee", "reqd": 1, "in_list_view": 1},
            {"fieldname": "employee_name", "fieldtype": "Data", "label": "Employee Name", "fetch_from": "employee.employee_name", "in_list_view": 1},
            {"fieldname": "salary_slip", "fieldtype": "Link", "label": "Salary Slip", "options": "Salary Slip"},
            {"fieldname": "jht_employee", "fieldtype": "Currency", "label": "JHT Employee", "in_list_view": 1},
            {"fieldname": "jht_employer", "fieldtype": "Currency", "label": "JHT Employer", "in_list_view": 1},
            {"fieldname": "jp_employee", "fieldtype": "Currency", "label": "JP Employee"},
            {"fieldname": "jp_employer", "fieldtype": "Currency", "label": "JP Employer"},
            {"fieldname": "jkk", "fieldtype": "Currency", "label": "JKK"},
            {"fieldname": "jkm", "fieldtype": "Currency", "label": "JKM"},
            {"fieldname": "kesehatan_employee", "fieldtype": "Currency", "label": "Kesehatan Employee"},
            {"fieldname": "kesehatan_employer", "fieldtype": "Currency", "label": "Kesehatan Employer"},
        ]
        
        for field_def in fields:
            field = doc.append("fields", {})
            field.fieldname = field_def["fieldname"]
            field.fieldtype = field_def["fieldtype"]
            field.label = field_def["label"]
            
            if "options" in field_def:
                field.options = field_def["options"]
            
            if "reqd" in field_def:
                field.reqd = field_def["reqd"]
                
            if "in_list_view" in field_def:
                field.in_list_view = field_def["in_list_view"]
            
            if "fetch_from" in field_def:
                field.fetch_from = field_def["fetch_from"]
        
        # Save DocType
        doc.insert()
        frappe.msgprint(_(f"Created new custom DocType: {doctype_name}"))
        return doctype_name
        
    except Exception as e:
        frappe.log_error(
            f"Error creating {doctype_name} DocType: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "DocType Creation Error"
        )
        frappe.throw(_("Error creating DocType: {0}").format(str(e)))

def fix_pph_ter_table():
    """Fix PPh TER Table structure using Custom Fields"""
    frappe.msgprint(_("Checking PPh TER Table DocType structure..."))
    
    if not frappe.db.exists("DocType", "PPh TER Table"):
        frappe.throw(_("PPh TER Table DocType not found."))
        return
    
    # Check required fields
    required_fields = {
        "month": {"fieldtype": "Int", "label": "Month", "insert_after": "company"},
        "year": {"fieldtype": "Int", "label": "Year", "insert_after": "month"},
        "month_year_title": {"fieldtype": "Data", "label": "Title", "insert_after": "year"}
    }
    
    # Check if fields exist already
    docfields = frappe.get_meta("PPh TER Table").fields
    existing_fields = [df.fieldname for df in docfields]
    missing_fields = [f for f in required_fields.keys() if f not in existing_fields]
    
    if missing_fields:
        frappe.msgprint(_("Missing fields detected in PPh TER Table: {0}").format(
            ", ".join(missing_fields)
        ))
        
        # Create custom fields for missing fields
        for field_name in missing_fields:
            field_def = required_fields[field_name]
            
            try:
                create_custom_field("PPh TER Table", {
                    "fieldname": field_name,
                    "fieldtype": field_def["fieldtype"],
                    "label": field_def["label"],
                    "insert_after": field_def["insert_after"]
                })
                frappe.msgprint(f"Added field '{field_name}' to PPh TER Table.")
            except Exception as e:
                frappe.log_error(
                    f"Error creating custom field {field_name}: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}",
                    "Custom Field Creation Error"
                )
                frappe.msgprint(f"Error creating field '{field_name}': {str(e)}")
    else:
        frappe.msgprint(_("PPh TER Table structure is OK."))

def fix_employee_tax_summary():
    """Fix Employee Tax Summary structure using Custom Fields"""
    frappe.msgprint(_("Checking Employee Tax Summary DocType structure..."))
    
    if not frappe.db.exists("DocType", "Employee Tax Summary"):
        frappe.throw(_("Employee Tax Summary DocType not found."))
        return
    
    # Check required fields
    required_fields = {
        "year": {"fieldtype": "Int", "label": "Year", "insert_after": "employee_name"},
        "ytd_tax": {"fieldtype": "Currency", "label": "YTD Tax", "insert_after": "year"},
        "is_using_ter": {"fieldtype": "Check", "label": "Is Using TER", "insert_after": "ytd_tax"},
        "ter_rate": {"fieldtype": "Float", "label": "TER Rate (%)", "insert_after": "is_using_ter"}
    }
    
    # Check if fields exist already
    docfields = frappe.get_meta("Employee Tax Summary").fields
    existing_fields = [df.fieldname for df in docfields]
    missing_fields = [f for f in required_fields.keys() if f not in existing_fields]
    
    if missing_fields:
        frappe.msgprint(_("Missing fields detected in Employee Tax Summary: {0}").format(
            ", ".join(missing_fields)
        ))
        
        # Create custom fields for missing fields
        for field_name in missing_fields:
            field_def = required_fields[field_name]
            
            try:
                create_custom_field("Employee Tax Summary", {
                    "fieldname": field_name,
                    "fieldtype": field_def["fieldtype"],
                    "label": field_def["label"],
                    "insert_after": field_def["insert_after"]
                })
                frappe.msgprint(f"Added field '{field_name}' to Employee Tax Summary.")
            except Exception as e:
                frappe.log_error(
                    f"Error creating custom field {field_name}: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}",
                    "Custom Field Creation Error"
                )
                frappe.msgprint(f"Error creating field '{field_name}': {str(e)}")
    else:
        frappe.msgprint(_("Employee Tax Summary structure is OK."))

def fix_all_doctypes():
    """Fix all Payroll Indonesia DocTypes using Custom Fields approach"""
    try:
        frappe.msgprint(_("Starting to fix all Payroll Indonesia DocTypes..."))
        
        # Fix BPJS Payment Summary and related
        fix_bpjs_payment_summary()
        
        # Fix PPh TER Table
        fix_pph_ter_table()
        
        # Fix Employee Tax Summary
        fix_employee_tax_summary()
        
        frappe.msgprint(_("All Payroll Indonesia DocTypes have been checked and fixed if necessary."))
        
    except Exception as e:
        frappe.log_error(
            f"Error fixing all DocTypes: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "DocType Fix Error"
        )
        frappe.msgprint(_("Error fixing all DocTypes: {0}").format(str(e)))

# Run from bench console:
# from payroll_indonesia.utilities.fix_doctype_structure import fix_all_doctypes
# fix_all_doctypes()