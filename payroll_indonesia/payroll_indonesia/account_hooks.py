# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe


def account_on_update(doc, method=None):
    """Hook when accounts are updated"""
    try:
        if doc.account_type in ["Payable", "Expense", "Liability"] and ("BPJS" in doc.account_name):
            # Update BPJS mappings
            update_bpjs_mappings(doc)
    except Exception as e:
        frappe.log_error(str(e)[:100], "Account Hook Error")


def update_bpjs_mappings(account_doc):
    """Update BPJS mappings that use this account"""
    try:
        # Get all mappings for this company
        mappings = frappe.get_all(
            "BPJS Account Mapping", filters={"company": account_doc.company}, pluck="name"
        )

        for mapping_name in mappings:
            try:
                mapping = frappe.get_doc("BPJS Account Mapping", mapping_name)

                # Check all account fields for a match
                account_fields = [
                    "kesehatan_employee_account",
                    "jht_employee_account",
                    "jp_employee_account",
                    "kesehatan_employer_debit_account",
                    "jht_employer_debit_account",
                    "jp_employer_debit_account",
                    "jkk_employer_debit_account",
                    "jkm_employer_debit_account",
                    "kesehatan_employer_credit_account",
                    "jht_employer_credit_account",
                    "jp_employer_credit_account",
                    "jkk_employer_credit_account",
                    "jkm_employer_credit_account",
                ]

                updated = False
                for field in account_fields:
                    if hasattr(mapping, field) and getattr(mapping, field) == account_doc.name:
                        # Account is being used in this mapping
                        updated = True

                if updated:
                    # Clear cache for this mapping
                    frappe.cache().delete_value(f"bpjs_mapping_{mapping.company}")
                    frappe.logger().info(
                        f"Cleared cache for BPJS mapping {mapping_name} due to account update"
                    )
            except Exception as e:
                frappe.log_error(
                    f"Error processing mapping {mapping_name}: {str(e)[:100]}",
                    "BPJS Mapping Update Error",
                )
    except Exception as e:
        frappe.log_error(
            f"Error updating BPJS mappings: {str(e)[:100]}", "BPJS Mapping Update Error"
        )
