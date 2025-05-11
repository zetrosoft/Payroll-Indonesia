# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-04 02:05:35 by dannyaudian

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.utils import now_datetime

__all__ = [
    "fix_bpjs_payment_summary",
    "check_bpjs_payment_details",
    "check_child_table_fields",
    "create_custom_child_doctype",
    "fix_employee_tax_summary",
    "fix_all_doctypes",
    "diagnose_doctype_structure",
    "log_error",
]


def fix_bpjs_payment_summary():
    """
    Fix BPJS Payment Summary structure by adding custom fields if needed

    Returns:
        bool: True if successful, False if error occurred
    """
    try:
        frappe.msgprint(_("Checking BPJS Payment Summary DocType structure..."))

        if not frappe.db.exists("DocType", "BPJS Payment Summary"):
            frappe.throw(_("BPJS Payment Summary DocType not found."))
            return False

        # Check required fields using custom field approach
        required_fields = {
            "month": {"fieldtype": "Int", "label": "Month", "insert_after": "company"},
            "year": {"fieldtype": "Int", "label": "Year", "insert_after": "month"},
            "month_year": {"fieldtype": "Data", "label": "Month-Year", "insert_after": "year"},
            "month_name": {
                "fieldtype": "Data",
                "label": "Month Name",
                "insert_after": "month_year",
            },
            "month_year_title": {
                "fieldtype": "Data",
                "label": "Title",
                "insert_after": "month_name",
            },
        }

        # Check if fields exist already
        docfields = frappe.get_meta("BPJS Payment Summary").fields
        existing_fields = [df.fieldname for df in docfields]
        missing_fields = [f for f in required_fields.keys() if f not in existing_fields]

        if missing_fields:
            frappe.msgprint(
                _("Missing fields detected in BPJS Payment Summary: {0}").format(
                    ", ".join(missing_fields)
                )
            )

            # Create custom fields for missing fields
            for field_name in missing_fields:
                field_def = required_fields[field_name]

                try:
                    create_custom_field(
                        "BPJS Payment Summary",
                        {
                            "fieldname": field_name,
                            "fieldtype": field_def["fieldtype"],
                            "label": field_def["label"],
                            "insert_after": field_def["insert_after"],
                        },
                    )
                    frappe.msgprint(f"Added field '{field_name}' to BPJS Payment Summary.")
                except Exception as e:
                    log_error(
                        f"Error creating custom field {field_name}: {str(e)}",
                        "Custom Field Creation Error",
                    )
                    frappe.msgprint(f"Error creating field '{field_name}': {str(e)}")
        else:
            frappe.msgprint(_("BPJS Payment Summary structure is OK."))

        # Check child table
        check_bpjs_payment_details()
        return True

    except Exception as e:
        log_error(f"Error fixing BPJS Payment Summary: {str(e)}", "DocType Fix Error")
        frappe.msgprint(_("Error fixing BPJS Payment Summary structure: {0}").format(str(e)))
        return False


def check_bpjs_payment_details():
    """
    Check and fix the structure of BPJS Payment Details child table

    Returns:
        bool: True if successful, False if error occurred
    """
    try:
        # Find the child table DocType name
        child_table_fieldname = None
        parent_meta = frappe.get_meta("BPJS Payment Summary")

        for field in parent_meta.fields:
            if field.fieldtype == "Table" and (
                "employee_details" in field.fieldname or "details" in field.fieldname
            ):
                child_table_fieldname = field.fieldname
                child_doctype_name = field.options
                break

        if not child_table_fieldname:
            # Create a custom link field for the child table relationship
            frappe.msgprint(_("Creating employee_details table field in BPJS Payment Summary"))

            create_custom_field(
                "BPJS Payment Summary",
                {
                    "fieldname": "employee_details_section",
                    "fieldtype": "Section Break",
                    "label": "Employee Details",
                    "insert_after": "month_year_title",
                },
            )

            # Check if we can find or create a child DocType
            child_doctype_name = "BPJS Payment Details"
            if not frappe.db.exists("DocType", child_doctype_name):
                frappe.msgprint(
                    _(
                        f"Child table DocType {child_doctype_name} not found. Please create it manually."
                    )
                )
                return False

            # Create the table field
            create_custom_field(
                "BPJS Payment Summary",
                {
                    "fieldname": "employee_details",
                    "fieldtype": "Table",
                    "label": "Employee Details",
                    "options": child_doctype_name,
                    "insert_after": "employee_details_section",
                },
            )
            frappe.msgprint(
                _(f"Created employee_details table field linked to {child_doctype_name}")
            )

        # Check fields in the child table
        if child_doctype_name and frappe.db.exists("DocType", child_doctype_name):
            check_child_table_fields(child_doctype_name)
            return True

        return False

    except Exception as e:
        log_error(
            f"Error checking BPJS Payment Details structure: {str(e)}",
            "DocType Structure Check Error",
        )
        frappe.msgprint(_("Error checking BPJS Payment Details structure: {0}").format(str(e)))
        return False


def check_child_table_fields(child_doctype_name):
    """
    Check and add missing fields to child table via custom fields

    Args:
        child_doctype_name (str): Name of child DocType to check and fix

    Returns:
        bool: True if successful, False if error occurred
    """
    try:
        child_meta = frappe.get_meta(child_doctype_name)
        existing_fields = [df.fieldname for df in child_meta.fields]

        required_fields = {
            "employee": {
                "fieldtype": "Link",
                "label": "Employee",
                "options": "Employee",
                "insert_after": "idx",
                "reqd": 1,
            },
            "employee_name": {
                "fieldtype": "Data",
                "label": "Employee Name",
                "insert_after": "employee",
                "fetch_from": "employee.employee_name",
            },
            "salary_slip": {
                "fieldtype": "Link",
                "label": "Salary Slip",
                "options": "Salary Slip",
                "insert_after": "employee_name",
            },
            "jht_employee": {
                "fieldtype": "Currency",
                "label": "JHT Employee",
                "insert_after": "salary_slip",
            },
            "jht_employer": {
                "fieldtype": "Currency",
                "label": "JHT Employer",
                "insert_after": "jht_employee",
            },
            "jp_employee": {
                "fieldtype": "Currency",
                "label": "JP Employee",
                "insert_after": "jht_employer",
            },
            "jp_employer": {
                "fieldtype": "Currency",
                "label": "JP Employer",
                "insert_after": "jp_employee",
            },
            "jkk": {"fieldtype": "Currency", "label": "JKK", "insert_after": "jp_employer"},
            "jkm": {"fieldtype": "Currency", "label": "JKM", "insert_after": "jkk"},
            "kesehatan_employee": {
                "fieldtype": "Currency",
                "label": "Kesehatan Employee",
                "insert_after": "jkm",
            },
            "kesehatan_employer": {
                "fieldtype": "Currency",
                "label": "Kesehatan Employer",
                "insert_after": "kesehatan_employee",
            },
        }

        missing_fields = [f for f in required_fields.keys() if f not in existing_fields]

        if missing_fields:
            frappe.msgprint(
                _("Missing fields detected in {0}: {1}").format(
                    child_doctype_name, ", ".join(missing_fields)
                )
            )

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
                        log_error(
                            f"Error adding field {field_name}: {str(e)}", "Field Addition Error"
                        )
                        frappe.msgprint(f"Error adding field '{field_name}': {str(e)}")
            else:
                # For standard DocTypes, suggest creating a custom child DocType
                frappe.msgprint(
                    _(
                        "Cannot modify standard child table directly. "
                        "Please create a custom child DocType with all required fields."
                    )
                )
        else:
            frappe.msgprint(_("{0} structure is OK.").format(child_doctype_name))

        return True

    except Exception as e:
        log_error(
            f"Error checking child table fields for {child_doctype_name}: {str(e)}",
            "Child Table Check Error",
        )
        frappe.msgprint(_("Error checking child table fields: {0}").format(str(e)))
        return False


def create_custom_child_doctype(doctype_name):
    """
    Create a new custom child DocType with all required fields

    Args:
        doctype_name (str): Name of the child DocType to create

    Returns:
        str: Name of created DocType if successful, None if failed
    """
    try:
        if frappe.db.exists("DocType", doctype_name):
            frappe.msgprint(_(f"{doctype_name} already exists."))
            return doctype_name

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
            {
                "fieldname": "employee",
                "fieldtype": "Link",
                "label": "Employee",
                "options": "Employee",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "employee_name",
                "fieldtype": "Data",
                "label": "Employee Name",
                "fetch_from": "employee.employee_name",
                "in_list_view": 1,
            },
            {
                "fieldname": "salary_slip",
                "fieldtype": "Link",
                "label": "Salary Slip",
                "options": "Salary Slip",
            },
            {
                "fieldname": "jht_employee",
                "fieldtype": "Currency",
                "label": "JHT Employee",
                "in_list_view": 1,
            },
            {
                "fieldname": "jht_employer",
                "fieldtype": "Currency",
                "label": "JHT Employer",
                "in_list_view": 1,
            },
            {"fieldname": "jp_employee", "fieldtype": "Currency", "label": "JP Employee"},
            {"fieldname": "jp_employer", "fieldtype": "Currency", "label": "JP Employer"},
            {"fieldname": "jkk", "fieldtype": "Currency", "label": "JKK"},
            {"fieldname": "jkm", "fieldtype": "Currency", "label": "JKM"},
            {
                "fieldname": "kesehatan_employee",
                "fieldtype": "Currency",
                "label": "Kesehatan Employee",
            },
            {
                "fieldname": "kesehatan_employer",
                "fieldtype": "Currency",
                "label": "Kesehatan Employer",
            },
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
        log_error(f"Error creating {doctype_name} DocType: {str(e)}", "DocType Creation Error")
        frappe.throw(_("Error creating DocType: {0}").format(str(e)))
        return None


def fix_employee_tax_summary():
    """
    Fix Employee Tax Summary structure using Custom Fields

    Returns:
        bool: True if successful, False if error occurred
    """
    try:
        frappe.msgprint(_("Checking Employee Tax Summary DocType structure..."))

        if not frappe.db.exists("DocType", "Employee Tax Summary"):
            frappe.throw(_("Employee Tax Summary DocType not found."))
            return False

        # Check required fields - Note: TER fields are included for PMK-168 compliance
        required_fields = {
            "year": {"fieldtype": "Int", "label": "Year", "insert_after": "employee_name"},
            "ytd_tax": {"fieldtype": "Currency", "label": "YTD Tax", "insert_after": "year"},
            "is_using_ter": {
                "fieldtype": "Check",
                "label": "Is Using TER",
                "insert_after": "ytd_tax",
            },
            "ter_rate": {
                "fieldtype": "Float",
                "label": "TER Rate (%)",
                "insert_after": "is_using_ter",
            },
        }

        # Check if fields exist already
        docfields = frappe.get_meta("Employee Tax Summary").fields
        existing_fields = [df.fieldname for df in docfields]
        missing_fields = [f for f in required_fields.keys() if f not in existing_fields]

        if missing_fields:
            frappe.msgprint(
                _("Missing fields detected in Employee Tax Summary: {0}").format(
                    ", ".join(missing_fields)
                )
            )

            # Create custom fields for missing fields
            for field_name in missing_fields:
                field_def = required_fields[field_name]

                try:
                    create_custom_field(
                        "Employee Tax Summary",
                        {
                            "fieldname": field_name,
                            "fieldtype": field_def["fieldtype"],
                            "label": field_def["label"],
                            "insert_after": field_def["insert_after"],
                        },
                    )
                    frappe.msgprint(f"Added field '{field_name}' to Employee Tax Summary.")
                except Exception as e:
                    log_error(
                        f"Error creating custom field {field_name}: {str(e)}",
                        "Custom Field Creation Error",
                    )
                    frappe.msgprint(f"Error creating field '{field_name}': {str(e)}")
        else:
            frappe.msgprint(_("Employee Tax Summary structure is OK."))

        return True

    except Exception as e:
        log_error(f"Error fixing Employee Tax Summary: {str(e)}", "DocType Fix Error")
        frappe.msgprint(_("Error fixing Employee Tax Summary structure: {0}").format(str(e)))
        return False


def fix_all_doctypes():
    """
    Fix all Payroll Indonesia DocTypes using Custom Fields approach

    Returns:
        dict: Status of fixed DocTypes
    """
    timestamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    results = {
        "timestamp": timestamp,
        "bpjs_payment_summary": False,
        "employee_tax_summary": False,
        "success": False,
    }

    try:
        frappe.msgprint(_("Starting to fix all Payroll Indonesia DocTypes..."))
        frappe.logger().info(f"[{timestamp}] Starting DocType structure fixes")

        # Fix BPJS Payment Summary and related
        results["bpjs_payment_summary"] = fix_bpjs_payment_summary()

        # Fix Employee Tax Summary (with TER fields for PMK-168 compliance)
        results["employee_tax_summary"] = fix_employee_tax_summary()

        # Set overall success
        results["success"] = results["bpjs_payment_summary"] and results["employee_tax_summary"]

        frappe.msgprint(
            _("All Payroll Indonesia DocTypes have been checked and fixed if necessary.")
        )
        frappe.logger().info(f"[{timestamp}] DocType structure fixes completed")

        return results

    except Exception as e:
        log_error(f"Error fixing all DocTypes: {str(e)}", "DocType Fix Error")
        frappe.msgprint(_("Error fixing all DocTypes: {0}").format(str(e)))
        results["error"] = str(e)
        return results


def diagnose_doctype_structure():
    """
    Diagnose structure of key Payroll Indonesia DocTypes

    Returns:
        dict: Diagnostic information about DocType structure
    """
    results = {
        "timestamp": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
        "bpjs_payment_summary": {
            "exists": False,
            "missing_fields": [],
            "child_table_status": "Not Found",
        },
        "employee_tax_summary": {"exists": False, "missing_fields": []},
    }

    try:
        # Check BPJS Payment Summary
        if frappe.db.exists("DocType", "BPJS Payment Summary"):
            results["bpjs_payment_summary"]["exists"] = True

            # Check required fields
            bpjs_required_fields = ["month", "year", "month_year", "month_name", "month_year_title"]
            docfields = frappe.get_meta("BPJS Payment Summary").fields
            existing_fields = [df.fieldname for df in docfields]

            results["bpjs_payment_summary"]["missing_fields"] = [
                f for f in bpjs_required_fields if f not in existing_fields
            ]

            # Check child table
            child_table_found = False
            child_table_name = None

            for field in docfields:
                if field.fieldtype == "Table" and (
                    "employee_details" in field.fieldname or "details" in field.fieldname
                ):
                    child_table_found = True
                    child_table_name = field.options
                    break

            if child_table_found and child_table_name:
                results["bpjs_payment_summary"]["child_table_status"] = {
                    "name": child_table_name,
                    "exists": frappe.db.exists("DocType", child_table_name),
                }
            else:
                results["bpjs_payment_summary"]["child_table_status"] = "Missing"

        # Check Employee Tax Summary
        if frappe.db.exists("DocType", "Employee Tax Summary"):
            results["employee_tax_summary"]["exists"] = True

            # Check required fields
            ter_required_fields = ["year", "ytd_tax", "is_using_ter", "ter_rate"]
            docfields = frappe.get_meta("Employee Tax Summary").fields
            existing_fields = [df.fieldname for df in docfields]

            results["employee_tax_summary"]["missing_fields"] = [
                f for f in ter_required_fields if f not in existing_fields
            ]

        # Output diagnostic info
        print("\nPayroll Indonesia DocType Structure Diagnosis:")
        print("\n1. BPJS Payment Summary:")
        if results["bpjs_payment_summary"]["exists"]:
            print("   - Status: Exists")
            if results["bpjs_payment_summary"]["missing_fields"]:
                print(
                    f"   - Missing fields: {', '.join(results['bpjs_payment_summary']['missing_fields'])}"
                )
            else:
                print("   - All required fields present")

            print(f"   - Child table: {results['bpjs_payment_summary']['child_table_status']}")
        else:
            print("   - Status: Not found")

        print("\n2. Employee Tax Summary:")
        if results["employee_tax_summary"]["exists"]:
            print("   - Status: Exists")
            if results["employee_tax_summary"]["missing_fields"]:
                print(
                    f"   - Missing fields: {', '.join(results['employee_tax_summary']['missing_fields'])}"
                )
            else:
                print("   - All required fields present (including TER fields for PMK-168)")
        else:
            print("   - Status: Not found")

        return results

    except Exception as e:
        error_message = f"Error in diagnose_doctype_structure: {str(e)}"
        log_error(error_message, "DocType Diagnosis Error")
        print(f"Error diagnosing DocType structure: {str(e)}")
        return {"error": str(e), "timestamp": results["timestamp"]}


def log_error(message, title):
    """
    Log error with consistent format and full traceback

    Args:
        message (str): Error message
        title (str): Error title for the log
    """
    full_traceback = f"{message}\n\nTraceback: {frappe.get_traceback()}"
    frappe.log_error(full_traceback, title)
    timestamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    frappe.logger().error(f"[{timestamp}] [{title}] {message}")


# Run from bench console:
# from payroll_indonesia.utilities.fix_doctype_structure import fix_all_doctypes
# fix_all_doctypes()
