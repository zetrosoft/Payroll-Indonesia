# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-27 10:55:34 by dannyaudian

import frappe
from frappe import _

def on_session_creation(login_manager):
    """Hook that runs when a new session is created"""
    
    # Check if session user is in Indonesia
    user = frappe.session.user
    if not user or user == "Guest":
        return
        
    try:
        # Get the employee linked to this user
        employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
        if not employee:
            return
            
        # Get company of this employee
        company = frappe.db.get_value("Employee", employee, "company")
        if not company:
            return
            
        # Get company country
        country = frappe.db.get_value("Company", company, "country")
        
        # If company is in Indonesia, set regional settings
        # Note: Removing the home_page override which could be causing the 500 error
        if country == "Indonesia":
            # Instead of changing home page directly, we'll add this information to the session
            # This is a safer approach that won't break the response
            if hasattr(frappe.local, "session"):
                frappe.local.session.data.payroll_region = "Indonesia"
                
            # Optional: Log access in a safe way
            try:
                frappe.log_error(
                    f"User {user} (Employee: {employee}) logged in - Region Indonesia",
                    "Region-specific Login"
                )
            except:
                pass  # Ignore logging errors to prevent further issues
                
    except Exception as e:
        try:
            frappe.log_error(
                f"Error in on_session_creation: {str(e)}\nUser: {user}",
                "Auth Hook Error"
            )
        except:
            pass  # Ignore logging errors to prevent further issues