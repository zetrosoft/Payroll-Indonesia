# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 07:35:26 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, money_in_words

# Fungsi pembantu yang akan digunakan di beberapa file
def get_formatted_currency(value, company=None):
    """Format currency value based on company settings"""
    if company:
        currency = frappe.get_cached_value('Company', company, 'default_currency')
    else:
        currency = frappe.db.get_default("currency")
    return money_in_words(value, currency=currency)

def get_component_amount(doc, component_name, component_type):
    """Get amount for a specific component with validation"""
    try:
        if not component_name or not component_type:
            return 0
            
        components = doc.earnings if component_type == "earnings" else doc.deductions
        
        for component in components:
            if component.salary_component == component_name:
                return flt(component.amount)
        return 0
        
    except Exception as e:
        frappe.log_error(
            f"Error getting component {component_name}: {str(e)}",
            "Component Amount Error"
        )
        return 0

def update_component_amount(doc, component_name, amount, component_type):
    """Update amount for a specific component with validation"""
    try:
        if not component_name or not component_type:
            frappe.throw(_("Component name and type are required"))
            
        # Validate amount is a number
        try:
            amount = flt(amount)
        except Exception:
            amount = 0
            frappe.msgprint(_("Invalid amount for component {0}, using 0").format(component_name))
            
        components = doc.earnings if component_type == "earnings" else doc.deductions

        # Find if component exists
        for component in components:
            if component.salary_component == component_name:
                component.amount = amount
                return

        # If not found, ensure component exists in the system
        if not frappe.db.exists("Salary Component", component_name):
            frappe.throw(_("Salary Component {0} does not exist").format(component_name))
            
        # Get component details
        try:
            component_doc = frappe.get_doc("Salary Component", component_name)
            component_abbr = component_doc.salary_component_abbr
        except Exception:
            component_abbr = component_name[:3].upper()
            
        # Create a new row
        try:
            row = frappe.new_doc("Salary Detail")
            row.salary_component = component_name
            row.abbr = component_abbr
            row.amount = amount
            row.parentfield = component_type
            row.parenttype = "Salary Slip"
            components.append(row)
        except Exception as e:
            frappe.throw(_("Error creating component {0}: {1}").format(component_name, str(e)))
            
    except Exception as e:
        frappe.log_error(
            f"Error updating component {component_name}: {str(e)}",
            "Component Update Error"
        )
        frappe.throw(_("Error updating component {0}: {1}").format(component_name, str(e)))

def get_component_amount_from_doc(doc, component_name):
    """Get component amount from a document"""
    try:
        if hasattr(doc, 'deductions'):
            for component in doc.deductions:
                if component.salary_component == component_name:
                    return flt(component.amount)
        return 0
    except Exception as e:
        frappe.log_error(
            f"Error getting component {component_name} from doc {doc.name}: {str(e)}",
            "Component Retrieval Error"
        )
        return 0