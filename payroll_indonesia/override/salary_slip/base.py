# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 08:26:15 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, money_in_words


# Fungsi pembantu yang akan digunakan di beberapa file
def get_formatted_currency(value, company=None):
    """Format currency value based on company settings"""
    try:
        if company:
            currency = frappe.get_cached_value("Company", company, "default_currency")
        else:
            currency = frappe.db.get_default("currency")

        return money_in_words(value, currency=currency)
    except Exception as e:
        # Non-critical formatting error - log and return simple numeric format
        frappe.log_error(
            "Error formatting currency value {0} for company {1}: {2}".format(
                value, company, str(e)
            ),
            "Currency Formatting Error",
        )
        return str(value)


def get_component_amount(doc, component_name, component_type):
    """Get amount for a specific component with validation"""
    try:
        if not component_name or not component_type:
            return 0

        if component_type not in ["earnings", "deductions"]:
            frappe.log_error(
                "Invalid component type {0} for component {1}".format(
                    component_type, component_name
                ),
                "Invalid Component Type",
            )
            return 0

        components = doc.earnings if component_type == "earnings" else doc.deductions

        if not hasattr(doc, component_type) or not components:
            return 0

        for component in components:
            if component.salary_component == component_name:
                return flt(component.amount)
        return 0

    except Exception as e:
        # Non-critical error - log and return 0
        frappe.log_error(
            "Error getting component {0} from {1} in {2}: {3}".format(
                component_name,
                component_type,
                doc.name if hasattr(doc, "name") else "unknown",
                str(e),
            ),
            "Component Amount Error",
        )
        return 0


def update_component_amount(doc, component_name, amount, component_type):
    """Update amount for a specific component with validation"""
    try:
        # Validate input parameters
        if not component_name:
            frappe.throw(_("Component name is required"), title=_("Missing Component Name"))

        if not component_type:
            frappe.throw(_("Component type is required"), title=_("Missing Component Type"))

        if component_type not in ["earnings", "deductions"]:
            frappe.throw(
                _("Component type must be either 'earnings' or 'deductions', got '{0}'").format(
                    component_type
                ),
                title=_("Invalid Component Type"),
            )

        # Validate amount is a number
        try:
            amount = flt(amount)
        except Exception as e:
            frappe.log_error(
                "Invalid amount '{0}' for component {1}: {2}".format(
                    amount, component_name, str(e)
                ),
                "Amount Validation Error",
            )
            frappe.msgprint(
                _("Invalid amount for component {0}, using 0").format(component_name),
                indicator="orange",
            )
            amount = 0

        # Get component collection
        if not hasattr(doc, component_type):
            frappe.throw(
                _("Document does not have {0} field").format(component_type),
                title=_("Missing Component Collection"),
            )

        components = doc.earnings if component_type == "earnings" else doc.deductions

        # Find if component exists
        for component in components:
            if component.salary_component == component_name:
                component.amount = amount
                return

        # If not found, ensure component exists in the system
        if not frappe.db.exists("Salary Component", component_name):
            frappe.throw(
                _("Salary Component {0} does not exist").format(component_name),
                title=_("Invalid Component"),
            )

        # Get component details
        try:
            component_doc = frappe.get_doc("Salary Component", component_name)
            component_abbr = component_doc.salary_component_abbr
        except Exception as e:
            # Non-critical error - use fallback abbreviation
            frappe.log_error(
                "Error retrieving component details for {0}: {1}".format(component_name, str(e)),
                "Component Retrieval Warning",
            )
            component_abbr = component_name[:3].upper()

        # Create a new row
        row = frappe.new_doc("Salary Detail")
        row.salary_component = component_name
        row.abbr = component_abbr
        row.amount = amount
        row.parentfield = component_type
        row.parenttype = "Salary Slip"
        components.append(row)

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Critical error - component update failure
        frappe.log_error(
            "Error updating component {0} to {1} in {2}: {3}".format(
                component_name, amount, doc.name if hasattr(doc, "name") else "unknown", str(e)
            ),
            "Component Update Error",
        )
        frappe.throw(
            _("Error updating component {0}: {1}").format(component_name, str(e)),
            title=_("Component Update Failed"),
        )


def get_component_amount_from_doc(doc, component_name):
    """Get component amount from a document"""
    try:
        if not hasattr(doc, "earnings") and not hasattr(doc, "deductions"):
            return 0

        # Check earnings
        if hasattr(doc, "earnings"):
            for component in doc.earnings:
                if component.salary_component == component_name:
                    return flt(component.amount)

        # Check deductions
        if hasattr(doc, "deductions"):
            for component in doc.deductions:
                if component.salary_component == component_name:
                    return flt(component.amount)

        return 0
    except Exception as e:
        # Non-critical error - log and return 0
        frappe.log_error(
            "Error retrieving component {0} from doc {1}: {2}".format(
                component_name, doc.name if hasattr(doc, "name") else "unknown", str(e)
            ),
            "Component Retrieval Error",
        )
        return 0
