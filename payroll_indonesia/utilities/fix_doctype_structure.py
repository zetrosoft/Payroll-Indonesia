# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 06:17:17 by dannyaudian

import frappe
from frappe import _

def fix_bpjs_payment_summary():
    """
    Fix BPJS Payment Summary structure if it's missing required fields
    """
    frappe.msgprint(_("Checking BPJS Payment Summary DocType structure..."))
    
    if not frappe.db.exists("DocType", "BPJS Payment Summary"):
        frappe.throw(_("BPJS Payment Summary DocType not found."))
        return
        
    # Get DocType
    doctype = frappe.get_doc("DocType", "BPJS Payment Summary")
    
    # Check required fields
    required_fields = {
        "month": {"fieldtype": "Int", "label": "Month"},
        "year": {"fieldtype": "Int", "label": "Year"},
        "month_year": {"fieldtype": "Data", "label": "Month-Year"},
        "month_name": {"fieldtype": "Data", "label": "Month Name"},
        "company": {"fieldtype": "Link", "label": "Company", "options": "Company"},
        "status": {"fieldtype": "Select", "label": "Status", "options": "\nDraft\nSubmitted\nPaid\nCancelled"},
        "month_year_title": {"fieldtype": "Data", "label": "Title"}
    }
    
    missing_fields = []
    for field_name, field_def in required_fields.items():
        if not any(f.fieldname == field_name for f in doctype.fields):
            missing_fields.append({
                "fieldname": field_name,
                "fieldtype": field_def["fieldtype"],
                "label": field_def["label"],
                "options": field_def.get("options", "")
            })
            
    if missing_fields:
        frappe.msgprint(_("Missing fields detected in BPJS Payment Summary: {0}").format(
            ", ".join([f['fieldname'] for f in missing_fields])
        ))
        
        # Add missing fields
        for field_def in missing_fields:
            field = doctype.append("fields", {})
            field.fieldname = field_def["fieldname"]
            field.fieldtype = field_def["fieldtype"]
            field.label = field_def["label"]
            
            if field_def.get("options"):
                field.options = field_def["options"]
            
            if field_def["fieldname"] == "company":
                field.reqd = 1
                
        # Save DocType
        try:
            doctype.save()
            frappe.msgprint(_("BPJS Payment Summary structure has been updated."))
        except Exception as e:
            frappe.log_error(
                f"Error saving DocType changes: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "DocType Update Error"
            )
            frappe.throw(_("Error saving DocType changes: {0}").format(str(e)))
    else:
        frappe.msgprint(_("BPJS Payment Summary structure is OK."))
        
    # Check child table
    check_bpjs_payment_details()
    
def check_bpjs_payment_details():
    """Check the structure of BPJS Payment Details child table"""
    try:
        # Find the child table DocType name
        parent_doctype = frappe.get_doc("DocType", "BPJS Payment Summary")
        
        child_doctype_name = None
        for field in parent_doctype.fields:
            if field.fieldtype == "Table" and ("employee_details" in field.fieldname or "details" in field.fieldname):
                child_doctype_name = field.options
                break
        
        if not child_doctype_name:
            frappe.msgprint(_("Could not find child table for employee details in BPJS Payment Summary."))
            # Look for any child DocType linked to BPJS Payment Summary
            child_doctypes = frappe.db.sql("""
                SELECT distinct options 
                FROM `tabDocField` 
                WHERE parent = 'BPJS Payment Summary' 
                AND fieldtype = 'Table'
            """, as_dict=1)
            
            if child_doctypes:
                child_doctype_name = child_doctypes[0].options
                frappe.msgprint(_(f"Found potential child table: {child_doctype_name}"))
            else:
                frappe.msgprint(_("No child table found, will create one."))
                # Create child table DocType
                child_doctype_name = "BPJS Payment Details"
                create_bpjs_details_doctype(child_doctype_name)
                return
        
        if not frappe.db.exists("DocType", child_doctype_name):
            frappe.msgprint(_(f"{child_doctype_name} DocType not found. Creating a new one."))
            create_bpjs_details_doctype(child_doctype_name)
            return
            
        doctype = frappe.get_doc("DocType", child_doctype_name)
        
        # Check required fields
        required_fields = {
            "employee": {"fieldtype": "Link", "label": "Employee", "options": "Employee"},
            "employee_name": {"fieldtype": "Data", "label": "Employee Name"},
            "salary_slip": {"fieldtype": "Link", "label": "Salary Slip", "options": "Salary Slip"},
            "jht_employee": {"fieldtype": "Currency", "label": "JHT Employee"},
            "jht_employer": {"fieldtype": "Currency", "label": "JHT Employer"},
            "jp_employee": {"fieldtype": "Currency", "label": "JP Employee"},
            "jp_employer": {"fieldtype": "Currency", "label": "JP Employer"},
            "jkk": {"fieldtype": "Currency", "label": "JKK"},
            "jkm": {"fieldtype": "Currency", "label": "JKM"},
            "kesehatan_employee": {"fieldtype": "Currency", "label": "Kesehatan Employee"},
            "kesehatan_employer": {"fieldtype": "Currency", "label": "Kesehatan Employer"}
        }
        
        missing_fields = []
        for field_name, field_def in required_fields.items():
            if not any(f.fieldname == field_name for f in doctype.fields):
                missing_fields.append({
                    "fieldname": field_name,
                    "fieldtype": field_def["fieldtype"],
                    "label": field_def["label"],
                    "options": field_def.get("options", "")
                })
                
        if missing_fields:
            frappe.msgprint(_("Missing fields detected in {0}: {1}").format(
                child_doctype_name, 
                ", ".join([f['fieldname'] for f in missing_fields])
            ))
            
            # Add missing fields
            for field_def in missing_fields:
                field = doctype.append("fields", {})
                field.fieldname = field_def["fieldname"]
                field.fieldtype = field_def["fieldtype"]
                field.label = field_def["label"]
                
                if field_def.get("options"):
                    field.options = field_def["options"]
                
                if field_def["fieldname"] == "employee":
                    field.reqd = 1
                    
            # Save DocType
            try:
                doctype.save()
                frappe.msgprint(_("{0} structure has been updated.").format(child_doctype_name))
            except Exception as e:
                frappe.log_error(
                    f"Error saving DocType changes: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}",
                    "DocType Update Error"
                )
                frappe.throw(_("Error saving DocType changes: {0}").format(str(e)))
        else:
            frappe.msgprint(_("{0} structure is OK.").format(child_doctype_name))
            
    except Exception as e:
        frappe.log_error(
            f"Error checking BPJS Payment Details structure: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "DocType Structure Check Error"
        )
        frappe.throw(_("Error checking BPJS Payment Details structure: {0}").format(str(e)))

def create_bpjs_details_doctype(doctype_name):
    """Create a new BPJS Payment Details DocType"""
    try:
        # Check if already exists
        if frappe.db.exists("DocType", doctype_name):
            frappe.msgprint(_(f"{doctype_name} already exists. Checking structure..."))
            return
        
        # Create child table DocType
        doc = frappe.new_doc("DocType")
        doc.name = doctype_name
        doc.module = "Payroll Indonesia"
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
            
            if field_def.get("options"):
                field.options = field_def["options"]
            
            if field_def.get("reqd"):
                field.reqd = field_def["reqd"]
                
            if field_def.get("in_list_view"):
                field.in_list_view = field_def["in_list_view"]
            
            if field_def.get("fetch_from"):
                field.fetch_from = field_def["fetch_from"]
        
        # Save DocType
        doc.insert()
        frappe.msgprint(_(f"Created new DocType: {doctype_name}"))
        
        # Update parent DocType if needed
        parent_doctype = frappe.get_doc("DocType", "BPJS Payment Summary")
        
        # Check if employee_details field exists
        if not any(f.fieldname == "employee_details" for f in parent_doctype.fields):
            frappe.msgprint(_("Adding employee_details field to BPJS Payment Summary..."))
            
            # Add section break before
            section = parent_doctype.append("fields", {})
            section.fieldtype = "Section Break"
            section.label = "Employee Details"
            
            # Add child table field
            field = parent_doctype.append("fields", {})
            field.fieldname = "employee_details"
            field.fieldtype = "Table"
            field.label = "Employee Details"
            field.options = doctype_name
            
            # Save parent DocType
            parent_doctype.save()
            frappe.msgprint(_("BPJS Payment Summary updated with employee_details table."))
            
    except Exception as e:
        frappe.log_error(
            f"Error creating {doctype_name} DocType: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "DocType Creation Error"
        )
        frappe.throw(_("Error creating DocType: {0}").format(str(e)))

def fix_pph_ter_table():
    """Fix PPh TER Table structure if it's missing required fields"""
    frappe.msgprint(_("Checking PPh TER Table DocType structure..."))
    
    if not frappe.db.exists("DocType", "PPh TER Table"):
        frappe.throw(_("PPh TER Table DocType not found."))
        return
        
    # Get DocType
    doctype = frappe.get_doc("DocType", "PPh TER Table")
    
    # Check required fields
    required_fields = {
        "month": {"fieldtype": "Int", "label": "Month"},
        "year": {"fieldtype": "Int", "label": "Year"},
        "month_year_title": {"fieldtype": "Data", "label": "Title"},
        "company": {"fieldtype": "Link", "label": "Company", "options": "Company"},
        "status": {"fieldtype": "Select", "label": "Status", "options": "\nDraft\nSubmitted\nCancelled"}
    }
    
    missing_fields = []
    for field_name, field_def in required_fields.items():
        if not any(f.fieldname == field_name for f in doctype.fields):
            missing_fields.append({
                "fieldname": field_name,
                "fieldtype": field_def["fieldtype"],
                "label": field_def["label"],
                "options": field_def.get("options", "")
            })
            
    if missing_fields:
        frappe.msgprint(_("Missing fields detected in PPh TER Table: {0}").format(
            ", ".join([f['fieldname'] for f in missing_fields])
        ))
        
        # Add missing fields
        for field_def in missing_fields:
            field = doctype.append("fields", {})
            field.fieldname = field_def["fieldname"]
            field.fieldtype = field_def["fieldtype"]
            field.label = field_def["label"]
            
            if field_def.get("options"):
                field.options = field_def["options"]
            
            if field_def["fieldname"] == "company":
                field.reqd = 1
                
        # Save DocType
        try:
            doctype.save()
            frappe.msgprint(_("PPh TER Table structure has been updated."))
        except Exception as e:
            frappe.log_error(
                f"Error saving DocType changes: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "DocType Update Error"
            )
            frappe.throw(_("Error saving DocType changes: {0}").format(str(e)))
    else:
        frappe.msgprint(_("PPh TER Table structure is OK."))
        
    # Check child table
    check_pph_ter_details()

def check_pph_ter_details():
    """Check the structure of PPh TER Details child table"""
    try:
        # Find the child table DocType name
        parent_doctype = frappe.get_doc("DocType", "PPh TER Table")
        
        child_doctype_name = None
        for field in parent_doctype.fields:
            if field.fieldtype == "Table" and ("employee_details" in field.fieldname or "details" in field.fieldname):
                child_doctype_name = field.options
                break
        
        if not child_doctype_name:
            frappe.msgprint(_("Could not find child table for employee details in PPh TER Table."))
            return
            
        if not frappe.db.exists("DocType", child_doctype_name):
            frappe.msgprint(_(f"{child_doctype_name} DocType not found."))
            return
            
        doctype = frappe.get_doc("DocType", child_doctype_name)
        
        # Check required fields
        required_fields = {
            "employee": {"fieldtype": "Link", "label": "Employee", "options": "Employee"},
            "employee_name": {"fieldtype": "Data", "label": "Employee Name"},
            "status_pajak": {"fieldtype": "Data", "label": "Status Pajak"},
            "salary_slip": {"fieldtype": "Link", "label": "Salary Slip", "options": "Salary Slip"},
            "gross_income": {"fieldtype": "Currency", "label": "Gross Income"},
            "ter_rate": {"fieldtype": "Float", "label": "TER Rate (%)"},
            "pph21_amount": {"fieldtype": "Currency", "label": "PPh 21 Amount"}
        }
        
        missing_fields = []
        for field_name, field_def in required_fields.items():
            if not any(f.fieldname == field_name for f in doctype.fields):
                missing_fields.append({
                    "fieldname": field_name,
                    "fieldtype": field_def["fieldtype"],
                    "label": field_def["label"],
                    "options": field_def.get("options", "")
                })
                
        if missing_fields:
            frappe.msgprint(_("Missing fields detected in {0}: {1}").format(
                child_doctype_name, 
                ", ".join([f['fieldname'] for f in missing_fields])
            ))
            
            # Add missing fields
            for field_def in missing_fields:
                field = doctype.append("fields", {})
                field.fieldname = field_def["fieldname"]
                field.fieldtype = field_def["fieldtype"]
                field.label = field_def["label"]
                
                if field_def.get("options"):
                    field.options = field_def["options"]
                
                if field_def["fieldname"] == "employee":
                    field.reqd = 1
                    
            # Save DocType
            try:
                doctype.save()
                frappe.msgprint(_("{0} structure has been updated.").format(child_doctype_name))
            except Exception as e:
                frappe.log_error(
                    f"Error saving DocType changes: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}",
                    "DocType Update Error"
                )
                frappe.throw(_("Error saving DocType changes: {0}").format(str(e)))
        else:
            frappe.msgprint(_("{0} structure is OK.").format(child_doctype_name))
            
    except Exception as e:
        frappe.log_error(
            f"Error checking PPh TER Details structure: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "DocType Structure Check Error"
        )
        frappe.throw(_("Error checking PPh TER Details structure: {0}").format(str(e)))

def fix_employee_tax_summary():
    """Fix Employee Tax Summary structure if it's missing required fields"""
    frappe.msgprint(_("Checking Employee Tax Summary DocType structure..."))
    
    if not frappe.db.exists("DocType", "Employee Tax Summary"):
        frappe.throw(_("Employee Tax Summary DocType not found."))
        return
        
    # Get DocType
    doctype = frappe.get_doc("DocType", "Employee Tax Summary")
    
    # Check required fields
    required_fields = {
        "employee": {"fieldtype": "Link", "label": "Employee", "options": "Employee"},
        "employee_name": {"fieldtype": "Data", "label": "Employee Name"},
        "year": {"fieldtype": "Int", "label": "Year"},
        "ytd_tax": {"fieldtype": "Currency", "label": "YTD Tax"},
        "is_using_ter": {"fieldtype": "Check", "label": "Is Using TER"},
        "ter_rate": {"fieldtype": "Float", "label": "TER Rate (%)"},
        "title": {"fieldtype": "Data", "label": "Title"}
    }
    
    missing_fields = []
    for field_name, field_def in required_fields.items():
        if not any(f.fieldname == field_name for f in doctype.fields):
            missing_fields.append({
                "fieldname": field_name,
                "fieldtype": field_def["fieldtype"],
                "label": field_def["label"],
                "options": field_def.get("options", "")
            })
            
    if missing_fields:
        frappe.msgprint(_("Missing fields detected in Employee Tax Summary: {0}").format(
            ", ".join([f['fieldname'] for f in missing_fields])
        ))
        
        # Add missing fields
        for field_def in missing_fields:
            field = doctype.append("fields", {})
            field.fieldname = field_def["fieldname"]
            field.fieldtype = field_def["fieldtype"]
            field.label = field_def["label"]
            
            if field_def.get("options"):
                field.options = field_def["options"]
            
            if field_def["fieldname"] in ["employee", "year"]:
                field.reqd = 1
                
        # Save DocType
        try:
            doctype.save()
            frappe.msgprint(_("Employee Tax Summary structure has been updated."))
        except Exception as e:
            frappe.log_error(
                f"Error saving DocType changes: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "DocType Update Error"
            )
            frappe.throw(_("Error saving DocType changes: {0}").format(str(e)))
    else:
        frappe.msgprint(_("Employee Tax Summary structure is OK."))
        
    # Check child table
    check_tax_summary_monthly_details()

def check_tax_summary_monthly_details():
    """Check the structure of Tax Summary Monthly Details child table"""
    try:
        # Find the child table DocType name
        parent_doctype = frappe.get_doc("DocType", "Employee Tax Summary")
        
        child_doctype_name = None
        for field in parent_doctype.fields:
            if field.fieldtype == "Table" and "monthly_details" in field.fieldname:
                child_doctype_name = field.options
                break
        
        if not child_doctype_name:
            frappe.msgprint(_("Could not find monthly_details child table in Employee Tax Summary."))
            return
            
        if not frappe.db.exists("DocType", child_doctype_name):
            frappe.msgprint(_(f"{child_doctype_name} DocType not found."))
            return
            
        doctype = frappe.get_doc("DocType", child_doctype_name)
        
        # Check required fields
        required_fields = {
            "month": {"fieldtype": "Int", "label": "Month"},
            "salary_slip": {"fieldtype": "Link", "label": "Salary Slip", "options": "Salary Slip"},
            "gross_pay": {"fieldtype": "Currency", "label": "Gross Pay"},
            "bpjs_deductions": {"fieldtype": "Currency", "label": "BPJS Deductions"},
            "other_deductions": {"fieldtype": "Currency", "label": "Other Deductions"},
            "tax_amount": {"fieldtype": "Currency", "label": "Tax Amount"},
            "is_using_ter": {"fieldtype": "Check", "label": "Is Using TER"},
            "ter_rate": {"fieldtype": "Float", "label": "TER Rate (%)"}
        }
        
        missing_fields = []
        for field_name, field_def in required_fields.items():
            if not any(f.fieldname == field_name for f in doctype.fields):
                missing_fields.append({
                    "fieldname": field_name,
                    "fieldtype": field_def["fieldtype"],
                    "label": field_def["label"],
                    "options": field_def.get("options", "")
                })
                
        if missing_fields:
            frappe.msgprint(_("Missing fields detected in {0}: {1}").format(
                child_doctype_name, 
                ", ".join([f['fieldname'] for f in missing_fields])
            ))
            
            # Add missing fields
            for field_def in missing_fields:
                field = doctype.append("fields", {})
                field.fieldname = field_def["fieldname"]
                field.fieldtype = field_def["fieldtype"]
                field.label = field_def["label"]
                
                if field_def.get("options"):
                    field.options = field_def["options"]
                
                if field_def["fieldname"] == "month":
                    field.reqd = 1
                    
            # Save DocType
            try:
                doctype.save()
                frappe.msgprint(_("{0} structure has been updated.").format(child_doctype_name))
            except Exception as e:
                frappe.log_error(
                    f"Error saving DocType changes: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}",
                    "DocType Update Error"
                )
                frappe.throw(_("Error saving DocType changes: {0}").format(str(e)))
        else:
            frappe.msgprint(_("{0} structure is OK.").format(child_doctype_name))
            
    except Exception as e:
        frappe.log_error(
            f"Error checking Tax Summary Monthly Details structure: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "DocType Structure Check Error"
        )
        frappe.throw(_("Error checking Tax Summary Monthly Details structure: {0}").format(str(e)))

def fix_all_doctypes():
    """Fix all Payroll Indonesia DocTypes"""
    try:
        frappe.msgprint(_("Starting to fix all Payroll Indonesia DocTypes..."))
        
        # Fix BPJS Payment Summary and related DocTypes
        fix_bpjs_payment_summary()
        
        # Fix PPh TER Table and related DocTypes
        fix_pph_ter_table()
        
        # Fix Employee Tax Summary and related DocTypes
        fix_employee_tax_summary()
        
        frappe.msgprint(_("All Payroll Indonesia DocTypes have been checked and fixed if necessary."))
        
    except Exception as e:
        frappe.log_error(
            f"Error fixing all DocTypes: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "DocType Fix Error"
        )
        frappe.throw(_("Error fixing all DocTypes: {0}").format(str(e)))

# Command to run from bench console:
# from payroll_indonesia.utilities.fix_doctype_structure import fix_all_doctypes
# fix_all_doctypes()