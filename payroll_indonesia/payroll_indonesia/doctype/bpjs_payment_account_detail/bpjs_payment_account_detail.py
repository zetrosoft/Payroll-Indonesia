# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa
# For license information, please see license.txt
# Last modified: 2025-05-08 11:25:49 by dannyaudian

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class BPJSPaymentAccountDetail(Document):
    def validate(self):
        """Validate account detail"""
        # Validasi jumlah harus positif
        if self.amount and self.amount <= 0:
            frappe.throw(_("Amount must be greater than 0"))

        # Validasi tipe akun sesuai dengan nama akun yang dipilih
        self.validate_account_type_match()

        # Update timestamp sinkronisasi terakhir
        if hasattr(self, "auto_generated") and self.auto_generated:
            self.last_synced = now_datetime()

    def validate_account_type_match(self):
        """Validate that the account selected is appropriate for the account type"""
        if not self.account or not self.account_type:
            return

        try:
            # Get account name
            account_name = frappe.db.get_value("Account", self.account, "account_name")
            if not account_name:
                return

            # Check if account name contains the account type
            account_name_lower = account_name.lower()
            expected_terms = {
                "Kesehatan": ["kesehatan", "health"],
                "JHT": ["jht"],
                "JP": ["jp", "pensiun", "pension"],
                "JKK": ["jkk", "kecelakaan", "accident"],
                "JKM": ["jkm", "kematian", "death"],
            }

            # Get expected terms for this account type
            expected = expected_terms.get(self.account_type, [])

            # Check if account name contains any expected term
            matches = [term for term in expected if term.lower() in account_name_lower]

            # If no match found and the account doesn't have a generic BPJS name
            if not matches and "bpjs" in account_name_lower and "payable" in account_name_lower:
                # This is a generic BPJS account, so we'll allow it
                return

            # If no match found and this is not a generic BPJS account, show a warning
            if not matches and not ("bpjs payable" in account_name_lower):
                frappe.msgprint(
                    _(
                        "Warning: The selected account '{0}' may not be appropriate for BPJS {1}. Expected account should contain: {2}"
                    ).format(account_name, self.account_type, ", ".join(expected)),
                    indicator="orange",
                )
        except Exception as e:
            frappe.log_error(
                f"Error validating account type match: {str(e)}\n"
                f"Account: {self.account}, Type: {self.account_type}",
                "BPJS Account Detail Validation Error",
            )
            # Don't throw error, just log it

    def before_save(self):
        """Actions before saving the document"""
        # Automatically set description if empty
        if not self.description and self.account_type:
            self.description = f"BPJS {self.account_type} Payment"

        # Generate reference number if empty
        if not self.reference_number and self.account_type:
            parent_doc = None
            try:
                # Try to get parent document if this is a child table
                parent_doc_name = self.get("parent")
                if parent_doc_name:
                    parent_doc = frappe.get_doc(self.get("parenttype"), parent_doc_name)
            except:
                pass

            # Generate reference number using parent info if available
            if parent_doc and hasattr(parent_doc, "month") and hasattr(parent_doc, "year"):
                month = getattr(parent_doc, "month", "")
                year = getattr(parent_doc, "year", "")
                self.reference_number = f"BPJS-{self.account_type}-{month}-{year}"
            else:
                # Fallback to simple reference
                self.reference_number = (
                    f"BPJS-{self.account_type}-{frappe.utils.today().replace('-', '')}"
                )

    @staticmethod
    def sync_with_defaults_json(parent_doc=None):
        """
        Sync account details with defaults.json configured accounts

        Args:
            parent_doc (obj, optional): Parent document to update
        """
        if not parent_doc or not hasattr(parent_doc, "company") or not parent_doc.company:
            return

        try:
            # Get company abbreviation
            company_abbr = frappe.get_cached_value("Company", parent_doc.company, "abbr")
            if not company_abbr:
                return

            # Get mapping from defaults.json
            mapping_config = frappe.get_file_json(
                frappe.get_app_path("payroll_indonesia", "config", "defaults.json")
            )
            bpjs_mapping = mapping_config.get("gl_accounts", {}).get("bpjs_account_mapping", {})

            # Map account types to mapping fields
            type_to_field_map = {
                "JHT": "jht_employee_account",
                "JP": "jp_employee_account",
                "Kesehatan": "kesehatan_employee_account",
                "JKK": "jkk_employer_credit_account",
                "JKM": "jkm_employer_credit_account",
            }

            # Calculate totals if parent has employee_details
            bpjs_totals = {"JHT": 0, "JP": 0, "Kesehatan": 0, "JKK": 0, "JKM": 0}

            # Try to calculate totals from employee_details
            if hasattr(parent_doc, "employee_details") and parent_doc.employee_details:
                for emp in parent_doc.employee_details:
                    bpjs_totals["JHT"] += frappe.utils.flt(emp.jht_employee) + frappe.utils.flt(
                        emp.jht_employer
                    )
                    bpjs_totals["JP"] += frappe.utils.flt(emp.jp_employee) + frappe.utils.flt(
                        emp.jp_employer
                    )
                    bpjs_totals["Kesehatan"] += frappe.utils.flt(
                        emp.kesehatan_employee
                    ) + frappe.utils.flt(emp.kesehatan_employer)
                    bpjs_totals["JKK"] += frappe.utils.flt(emp.jkk)
                    bpjs_totals["JKM"] += frappe.utils.flt(emp.jkm)

            # Generate account entries
            accounts_added = 0
            for bpjs_type, mapping_field in type_to_field_map.items():
                # Get account name from mapping
                account_name = bpjs_mapping.get(mapping_field)
                if not account_name:
                    continue

                # Add company abbreviation
                account = f"{account_name} - {company_abbr}"

                # Check if account exists
                if not frappe.db.exists("Account", account):
                    continue

                # Get amount from totals
                amount = bpjs_totals.get(bpjs_type, 0)
                if amount <= 0:
                    # Skip if no amount
                    continue

                # Add to parent's account_details table
                parent_doc.append(
                    "account_details",
                    {
                        "account_type": bpjs_type,
                        "account": account,
                        "amount": amount,
                        "mapped_from": "defaults.json",
                        "auto_generated": 1,
                        "last_synced": now_datetime(),
                        "description": f"BPJS {bpjs_type} Payment",
                    },
                )
                accounts_added += 1

            return accounts_added

        except Exception as e:
            frappe.log_error(
                f"Error syncing account details with defaults.json: {str(e)}\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Account Detail Sync Error",
            )
            return 0
