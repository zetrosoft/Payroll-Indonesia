# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.model.document import Document


class PayrollIndonesiaSettings(Document):
    def validate(self):
        """Validate settings on save"""
        self.validate_tax_settings()
        self.validate_bpjs_settings()
        self.validate_json_fields()
        self.update_timestamp()
        self.sync_to_related_doctypes()

    def update_timestamp(self):
        """Update the timestamp and user info"""
        self.app_last_updated = frappe.utils.now()
        self.app_updated_by = frappe.session.user

    def validate_tax_settings(self):
        """Validate tax-related settings"""
        if not self.ptkp_table:
            frappe.msgprint(
                _("PTKP values must be defined for tax calculation"), indicator="orange"
            )

        if self.use_ter and not self.ptkp_ter_mapping_table:
            frappe.msgprint(
                _("PTKP to TER mappings should be defined when using TER calculation method"),
                indicator="orange",
            )

        # Validate tax brackets
        if not self.tax_brackets_table:
            frappe.msgprint(
                _("Tax brackets should be defined for tax calculation"), indicator="orange"
            )

    def validate_bpjs_settings(self):
        """Validate BPJS-related settings"""
        # Validate BPJS percentages
        if self.kesehatan_employee_percent < 0 or self.kesehatan_employee_percent > 5:
            frappe.msgprint(
                _("BPJS Kesehatan employee percentage must be between 0 and 5%"), indicator="orange"
            )

        if self.kesehatan_employer_percent < 0 or self.kesehatan_employer_percent > 10:
            frappe.msgprint(
                _("BPJS Kesehatan employer percentage must be between 0 and 10%"),
                indicator="orange",
            )

    def validate_json_fields(self):
        """Validate JSON fields have valid content"""
        json_fields = [
            "bpjs_account_mapping_json",
            "expense_accounts_json",
            "payable_accounts_json",
            "parent_accounts_json",
            "ter_rate_ter_a_json",
            "ter_rate_ter_b_json",
            "ter_rate_ter_c_json",
        ]

        for field in json_fields:
            if hasattr(self, field) and self.get(field):
                try:
                    json.loads(self.get(field))
                except Exception:
                    frappe.msgprint(_("Invalid JSON in field {0}").format(field), indicator="red")

    def sync_to_related_doctypes(self):
        """Sync settings to related DocTypes (BPJS Settings, PPh 21 Settings)"""
        try:
            # Sync to BPJS Settings
            if frappe.db.exists("DocType", "BPJS Settings") and frappe.db.exists(
                "BPJS Settings", "BPJS Settings"
            ):
                bpjs_settings = frappe.get_doc("BPJS Settings", "BPJS Settings")
                bpjs_fields = [
                    "kesehatan_employee_percent",
                    "kesehatan_employer_percent",
                    "kesehatan_max_salary",
                    "jht_employee_percent",
                    "jht_employer_percent",
                    "jp_employee_percent",
                    "jp_employer_percent",
                    "jp_max_salary",
                    "jkk_percent",
                    "jkm_percent",
                ]

                needs_update = False
                for field in bpjs_fields:
                    if (
                        hasattr(bpjs_settings, field)
                        and hasattr(self, field)
                        and bpjs_settings.get(field) != self.get(field)
                    ):
                        bpjs_settings.set(field, self.get(field))
                        needs_update = True

                if needs_update:
                    bpjs_settings.flags.ignore_validate = True
                    bpjs_settings.flags.ignore_permissions = True
                    bpjs_settings.save()
                    frappe.msgprint(
                        _("BPJS Settings updated from Payroll Indonesia Settings"),
                        indicator="green",
                    )

            # Sync tax settings to PPh 21 Settings
            if frappe.db.exists("DocType", "PPh 21 Settings") and frappe.db.exists(
                "PPh 21 Settings", "PPh 21 Settings"
            ):
                pph_settings = frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")

                # Update calculation method
                if (
                    hasattr(pph_settings, "calculation_method")
                    and pph_settings.calculation_method != self.tax_calculation_method
                ):
                    pph_settings.calculation_method = self.tax_calculation_method
                    pph_settings.flags.ignore_validate = True
                    pph_settings.flags.ignore_permissions = True
                    pph_settings.save()
                    frappe.msgprint(
                        _("PPh 21 Settings updated from Payroll Indonesia Settings"),
                        indicator="green",
                    )

            # Sync TER rates to PPh 21 TER Table
            self.sync_ter_rates()

        except Exception as e:
            frappe.log_error(f"Error syncing settings: {str(e)}", "Settings Sync Error")

    def sync_ter_rates(self):
        """Sync TER rates from JSON fields to PPh 21 TER Table"""
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            return

        try:
            # Sync TER A rates
            if self.ter_rate_ter_a_json:
                try:
                    ter_a_rates = json.loads(self.ter_rate_ter_a_json)
                    self._sync_ter_category_rates("TER A", ter_a_rates)
                except Exception as e:
                    frappe.log_error(f"Error syncing TER A rates: {str(e)}", "TER Sync Error")

            # Sync TER B rates
            if self.ter_rate_ter_b_json:
                try:
                    ter_b_rates = json.loads(self.ter_rate_ter_b_json)
                    self._sync_ter_category_rates("TER B", ter_b_rates)
                except Exception as e:
                    frappe.log_error(f"Error syncing TER B rates: {str(e)}", "TER Sync Error")

            # Sync TER C rates
            if self.ter_rate_ter_c_json:
                try:
                    ter_c_rates = json.loads(self.ter_rate_ter_c_json)
                    self._sync_ter_category_rates("TER C", ter_c_rates)
                except Exception as e:
                    frappe.log_error(f"Error syncing TER C rates: {str(e)}", "TER Sync Error")

        except Exception as e:
            frappe.log_error(f"Error in sync_ter_rates: {str(e)}", "TER Sync Error")

    def _sync_ter_category_rates(self, category, rates):
        """Sync rates for a specific TER category"""
        if not isinstance(rates, list):
            return

        for rate_data in rates:
            filters = {
                "status_pajak": category,
                "income_from": rate_data.get("income_from", 0),
                "income_to": rate_data.get("income_to", 0),
            }

            if frappe.db.exists("PPh 21 TER Table", filters):
                # Update existing record
                ter_doc = frappe.get_doc("PPh 21 TER Table", filters)
                ter_doc.rate = rate_data.get("rate", 0)
                ter_doc.is_highest_bracket = rate_data.get("is_highest_bracket", 0)
                ter_doc.flags.ignore_permissions = True
                ter_doc.save()
            else:
                # Create new record
                ter_doc = frappe.new_doc("PPh 21 TER Table")
                ter_doc.update(
                    {
                        "status_pajak": category,
                        "income_from": rate_data.get("income_from", 0),
                        "income_to": rate_data.get("income_to", 0),
                        "rate": rate_data.get("rate", 0),
                        "is_highest_bracket": rate_data.get("is_highest_bracket", 0),
                        "description": self._build_ter_description(category, rate_data),
                    }
                )
                ter_doc.flags.ignore_permissions = True
                ter_doc.insert()

    def _build_ter_description(self, status, rate_data):
        """Build description for TER rates"""
        income_from = rate_data.get("income_from", 0)
        income_to = rate_data.get("income_to", 0)

        if rate_data.get("is_highest_bracket") or income_to == 0:
            return f"{status} > {income_from:,.0f}"
        else:
            return f"{status} {income_from:,.0f} – {income_to:,.0f}"

    def get_ptkp_value(self, status_pajak):
        """Get PTKP value for a specific tax status"""
        if not self.ptkp_table:
            return 0

        for row in self.ptkp_table:
            if row.status_pajak == status_pajak:
                return row.ptkp_amount

        return 0

    def get_ptkp_values_dict(self):
        """Return PTKP values as a dictionary"""
        ptkp_dict = {}
        if self.ptkp_table:
            for row in self.ptkp_table:
                ptkp_dict[row.status_pajak] = row.ptkp_amount

        return ptkp_dict

    def get_ptkp_ter_mapping_dict(self):
        """Return PTKP to TER mapping as a dictionary"""
        mapping_dict = {}
        if self.ptkp_ter_mapping_table:
            for row in self.ptkp_ter_mapping_table:
                mapping_dict[row.ptkp_status] = row.ter_category

        return mapping_dict

    def get_tax_brackets_list(self):
        """Return tax brackets as a list of dictionaries"""
        brackets = []
        if self.tax_brackets_table:
            for row in self.tax_brackets_table:
                brackets.append(
                    {
                        "income_from": row.income_from,
                        "income_to": row.income_to,
                        "tax_rate": row.tax_rate,
                    }
                )

        return brackets

    def get_tipe_karyawan_list(self):
        """Return employee types as a list"""
        types = []
        if self.tipe_karyawan:
            for row in self.tipe_karyawan:
                types.append(row.tipe_karyawan)

        return types

    def get_ter_category(self, ptkp_status):
        """Get TER category for a specific PTKP status"""
        if not self.ptkp_ter_mapping_table:
            return "TER A"  # Default

        for row in self.ptkp_ter_mapping_table:
            if row.ptkp_status == ptkp_status:
                return row.ter_category

        return "TER A"  # Default if not found

    def get_ter_rate(self, ter_category, income):
        """Get TER rate based on TER category and income"""
        if not self.use_ter:
            return 0

        # Query the TER Table for matching rates
        ter_entries = frappe.get_all(
            "PPh 21 TER Table",
            filters={"status_pajak": ter_category},
            fields=["income_from", "income_to", "rate", "is_highest_bracket"],
            order_by="income_from",
        )

        for entry in ter_entries:
            # Check if this is the highest bracket (no upper limit)
            if entry.is_highest_bracket and income >= entry.income_from:
                return entry.rate
            # Check if income falls in this range bracket
            elif income >= entry.income_from and (entry.income_to == 0 or income < entry.income_to):
                return entry.rate

        return 0  # Default if no matching bracket found

    def get_gl_account_config(self):
        """Return GL account configurations as a dictionary"""
        config = {}

        # Add BPJS account mapping
        if self.bpjs_account_mapping_json:
            try:
                config["bpjs_account_mapping"] = json.loads(self.bpjs_account_mapping_json)
            except Exception:
                frappe.log_error("Invalid JSON in BPJS account mapping", "GL Config Error")

        # Add expense accounts
        if self.expense_accounts_json:
            try:
                config["expense_accounts"] = json.loads(self.expense_accounts_json)
            except Exception:
                frappe.log_error("Invalid JSON in expense accounts", "GL Config Error")

        # Add payable accounts
        if self.payable_accounts_json:
            try:
                config["payable_accounts"] = json.loads(self.payable_accounts_json)
            except Exception:
                frappe.log_error("Invalid JSON in payable accounts", "GL Config Error")

        # Add parent accounts
        if self.parent_accounts_json:
            try:
                config["parent_accounts"] = json.loads(self.parent_accounts_json)
            except Exception:
                frappe.log_error("Invalid JSON in parent accounts", "GL Config Error")

        # Add parent account candidates
        config["parent_account_candidates"] = {
            "liability": self.get_parent_account_candidates_liability(),
            "expense": self.get_parent_account_candidates_expense(),
        }

        return config

    def get_parent_account_candidates_liability(self):
        """Return parent account candidates for liability accounts"""
        if not self.parent_account_candidates_liability:
            return ["Duties and Taxes", "Current Liabilities", "Accounts Payable"]

        candidates = self.parent_account_candidates_liability.split("\n")
        return [candidate.strip() for candidate in candidates if candidate.strip()]

    def get_parent_account_candidates_expense(self):
        """Return parent account candidates for expense accounts"""
        if not self.parent_account_candidates_expense:
            return ["Direct Expenses", "Indirect Expenses", "Expenses"]

        candidates = self.parent_account_candidates_expense.split("\n")
        return [candidate.strip() for candidate in candidates if candidate.strip()]

    def on_update(self):
        """Perform actions after document is updated"""
        self.populate_default_values()

    def populate_default_values(self):
        """Populate default values from defaults.json if fields are empty"""
        try:
            # Only populated if field values are empty
            defaults_loaded = False

            # Load config/defaults.json
            try:
                from pathlib import Path
                import json

                # Try to get app path
                app_path = frappe.get_app_path("payroll_indonesia")
                defaults_file = Path(app_path) / "config" / "defaults.json"

                if defaults_file.exists():
                    with open(defaults_file, "r") as f:
                        defaults = json.load(f)

                    # Populate TER rates if empty
                    if (
                        not self.ter_rate_ter_a_json
                        and "ter_rates" in defaults
                        and "TER A" in defaults["ter_rates"]
                    ):
                        self.ter_rate_ter_a_json = json.dumps(
                            defaults["ter_rates"]["TER A"], indent=2
                        )
                        defaults_loaded = True

                    if (
                        not self.ter_rate_ter_b_json
                        and "ter_rates" in defaults
                        and "TER B" in defaults["ter_rates"]
                    ):
                        self.ter_rate_ter_b_json = json.dumps(
                            defaults["ter_rates"]["TER B"], indent=2
                        )
                        defaults_loaded = True

                    if (
                        not self.ter_rate_ter_c_json
                        and "ter_rates" in defaults
                        and "TER C" in defaults["ter_rates"]
                    ):
                        self.ter_rate_ter_c_json = json.dumps(
                            defaults["ter_rates"]["TER C"], indent=2
                        )
                        defaults_loaded = True

                    # Populate GL accounts if empty
                    if (
                        not self.bpjs_account_mapping_json
                        and "gl_accounts" in defaults
                        and "bpjs_account_mapping" in defaults["gl_accounts"]
                    ):
                        self.bpjs_account_mapping_json = json.dumps(
                            defaults["gl_accounts"]["bpjs_account_mapping"], indent=2
                        )
                        defaults_loaded = True

                    if (
                        not self.expense_accounts_json
                        and "gl_accounts" in defaults
                        and "expense_accounts" in defaults["gl_accounts"]
                    ):
                        self.expense_accounts_json = json.dumps(
                            defaults["gl_accounts"]["expense_accounts"], indent=2
                        )
                        defaults_loaded = True

                    if (
                        not self.payable_accounts_json
                        and "gl_accounts" in defaults
                        and "payable_accounts" in defaults["gl_accounts"]
                    ):
                        self.payable_accounts_json = json.dumps(
                            defaults["gl_accounts"]["payable_accounts"], indent=2
                        )
                        defaults_loaded = True

                    if (
                        not self.parent_accounts_json
                        and "gl_accounts" in defaults
                        and "parent_accounts" in defaults["gl_accounts"]
                    ):
                        self.parent_accounts_json = json.dumps(
                            defaults["gl_accounts"]["parent_accounts"], indent=2
                        )
                        defaults_loaded = True

                    # Populate parent account candidates if empty
                    if (
                        not self.parent_account_candidates_liability
                        and "gl_accounts" in defaults
                        and "parent_account_candidates" in defaults["gl_accounts"]
                        and "liability" in defaults["gl_accounts"]["parent_account_candidates"]
                    ):
                        self.parent_account_candidates_liability = "\n".join(
                            defaults["gl_accounts"]["parent_account_candidates"]["liability"]
                        )
                        defaults_loaded = True

                    if (
                        not self.parent_account_candidates_expense
                        and "gl_accounts" in defaults
                        and "parent_account_candidates" in defaults["gl_accounts"]
                        and "expense" in defaults["gl_accounts"]["parent_account_candidates"]
                    ):
                        self.parent_account_candidates_expense = "\n".join(
                            defaults["gl_accounts"]["parent_account_candidates"]["expense"]
                        )
                        defaults_loaded = True

                    # If defaults were loaded, save the document
                    if defaults_loaded:
                        self.db_update()
                        frappe.msgprint(
                            _("Default values loaded from config/defaults.json"), indicator="green"
                        )

            except Exception as e:
                frappe.log_error(f"Error loading defaults.json: {str(e)}", "Settings Error")

        except Exception as e:
            frappe.log_error(f"Error populating default values: {str(e)}", "Settings Error")
