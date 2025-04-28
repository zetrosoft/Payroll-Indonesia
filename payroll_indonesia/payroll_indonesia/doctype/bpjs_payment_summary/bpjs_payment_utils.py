# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, now_datetime

def debug_log(message, module_name="BPJS Payment Summary"):
    """Log debug message with timestamp and additional info"""
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    frappe.log_error(f"[{timestamp}] {message}", module_name)

def get_formatted_currency(value, company=None):
    """Format currency value based on company settings"""
    if company:
        currency = frappe.get_cached_value('Company', company, 'default_currency')
    else:
        currency = frappe.db.get_default("currency")
    return fmt_money(value, currency=currency)

def add_component_if_positive(bpjs_summary, component, description, amount):
    """Add a component to BPJS summary if amount is positive"""
    if amount > 0:
        bpjs_summary.append("komponen", {
            "component": component,
            "description": description,
            "amount": amount
        })