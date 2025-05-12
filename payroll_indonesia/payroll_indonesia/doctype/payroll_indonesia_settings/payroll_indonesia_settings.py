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
        try:
            self.validate_tax_settings()
            self.validate_bpjs_settings()
            self.validate_json_fields()
            self.update_timestamp()
            self.sync_to_related_doctypes()
        except Exception as e:
            frappe.log_error(
                f"Error validating Payroll Indonesia Settings: {str(e)}", "Settings Error"
            )

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
            frappe.log_error("PPh 21 TER Table DocType not found - skipping sync", "TER Sync Info")
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
        if hasattr(self, "ptkp_table") and self.ptkp_table:
            for row in self.ptkp_table:
                ptkp_dict[row.status_pajak] = row.ptkp_amount
        return ptkp_dict

    def get_ptkp_ter_mapping_dict(self):
        """Return PTKP to TER mapping as a dictionary"""
        mapping_dict = {}
        if hasattr(self, "ptkp_ter_mapping_table") and self.ptkp_ter_mapping_table:
            for row in self.ptkp_ter_mapping_table:
                mapping_dict[row.ptkp_status] = row.ter_category
        return mapping_dict

    def get_tax_brackets_list(self):
        """Return tax brackets as a list of dictionaries"""
        brackets = []
        if hasattr(self, "tax_brackets_table") and self.tax_brackets_table:
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
        try:
            if hasattr(self, "tipe_karyawan") and self.tipe_karyawan:
                for row in self.tipe_karyawan:
                    types.append(row.tipe_karyawan)

            # If still empty, try to load from defaults.json
            if not types:
                types = self._get_default_tipe_karyawan()
        except Exception as e:
            frappe.log_error(f"Error getting tipe_karyawan list: {str(e)}", "Settings Error")

        return types

    def _get_default_tipe_karyawan(self):
        """Get default employee types from defaults.json as fallback"""
        try:
            from pathlib import Path
            import json

            defaults = []
            # Try to get app path
            app_path = frappe.get_app_path("payroll_indonesia")
            defaults_file = Path(app_path) / "config" / "defaults.json"

            if defaults_file.exists():
                with open(defaults_file, "r") as f:
                    config = json.load(f)
                if "tipe_karyawan" in config:
                    defaults = config["tipe_karyawan"]

            return defaults
        except Exception:
            return ["Tetap", "Tidak Tetap", "Freelance"]  # Hardcoded fallback

    def get_ter_category(self, ptkp_status):
        """Get TER category for a specific PTKP status"""
        if not self.ptkp_ter_mapping_table:
            # Fallback logic if no mapping exists
            prefix = ptkp_status[:2] if len(ptkp_status) >= 2 else ptkp_status
            suffix = ptkp_status[2:] if len(ptkp_status) >= 3 else "0"

            if ptkp_status == "TK0":
                return "TER A"
            elif prefix == "TK" and suffix in ["1", "2"]:
                return "TER B"
            elif prefix == "K" and suffix in ["0", "1"]:
                return "TER B"
            else:
                return "TER C"

        for row in self.ptkp_ter_mapping_table:
            if row.ptkp_status == ptkp_status:
                return row.ter_category

        return "TER A"  # Default if not found

    def get_ter_rate(self, ter_category, income):
        """Get TER rate based on TER category and income"""
        if not self.use_ter:
            return 0

        # Query the TER Table for matching rates
        try:
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
                elif income >= entry.income_from and (
                    entry.income_to == 0 or income < entry.income_to
                ):
                    return entry.rate
        except Exception as e:
            frappe.log_error(f"Error getting TER rate from database: {str(e)}", "TER Rate Error")

            # Try to get from JSON fields if DB lookup fails
            try:
                json_field = None
                if ter_category == "TER A" and self.ter_rate_ter_a_json:
                    json_field = self.ter_rate_ter_a_json
                elif ter_category == "TER B" and self.ter_rate_ter_b_json:
                    json_field = self.ter_rate_ter_b_json
                elif ter_category == "TER C" and self.ter_rate_ter_c_json:
                    json_field = self.ter_rate_ter_c_json

                if json_field:
                    rates = json.loads(json_field)
                    for rate in rates:
                        if rate.get("is_highest_bracket") and income >= rate.get("income_from", 0):
                            return rate.get("rate", 0)
                        elif income >= rate.get("income_from", 0) and (
                            rate.get("income_to", 0) == 0 or income < rate.get("income_to", 0)
                        ):
                            return rate.get("rate", 0)
            except Exception:
                pass

        # Default rates by category if nothing found
        if ter_category == "TER A":
            return 5.0  # 5%
        elif ter_category == "TER B":
            return 15.0  # 15%
        else:  # TER C
            return 25.0  # 25%

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

        # Ensure we have tipe_karyawan
        if not self.tipe_karyawan or len(self.tipe_karyawan) == 0:
            self.populate_tipe_karyawan()

    def populate_tipe_karyawan(self):
        """Populate tipe karyawan from defaults.json if empty"""
        try:
            if (
                not hasattr(self, "tipe_karyawan")
                or not self.tipe_karyawan
                or len(self.tipe_karyawan) == 0
            ):
                # Get default values
                default_types = self._get_default_tipe_karyawan()

                if default_types:
                    # Create child table entries
                    for tipe in default_types:
                        row = self.append("tipe_karyawan", {})
                        row.tipe_karyawan = tipe

                    # Save changes
                    self.db_update()
                    frappe.log_error("Populated default tipe karyawan", "Settings Info")
        except Exception as e:
            frappe.log_error(f"Error populating tipe karyawan: {str(e)}", "Settings Error")

    def populate_default_values(self):
        """Populate default values from defaults.json if fields are empty"""
        try:
            # Only populated if field values are empty
            defaults_loaded = False

            # Check if Tipe Karyawan Entry DocType exists and try to create if missing
            if not frappe.db.exists("DocType", "Tipe Karyawan Entry"):
                try:
                    self._ensure_child_doctypes_exist()
                except Exception as e:
                    frappe.log_error(
                        f"Error ensuring child DocTypes exist: {str(e)}", "Settings Error"
                    )

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

                    # Populate PTKP table if empty
                    if hasattr(self, "ptkp_table") and (
                        not self.ptkp_table or len(self.ptkp_table) == 0
                    ):
                        if "ptkp" in defaults:
                            # Clear existing rows if any
                            self.set("ptkp_table", [])

                            for status, amount in defaults["ptkp"].items():
                                row = self.append("ptkp_table", {})
                                row.status_pajak = status
                                row.ptkp_amount = amount

                            defaults_loaded = True

                    # Populate PTKP to TER mapping if empty
                    if hasattr(self, "ptkp_ter_mapping_table") and (
                        not self.ptkp_ter_mapping_table or len(self.ptkp_ter_mapping_table) == 0
                    ):
                        if "ptkp_to_ter_mapping" in defaults:
                            # Clear existing rows if any
                            self.set("ptkp_ter_mapping_table", [])

                            for status, category in defaults["ptkp_to_ter_mapping"].items():
                                row = self.append("ptkp_ter_mapping_table", {})
                                row.ptkp_status = status
                                row.ter_category = category

                            defaults_loaded = True

                    # Populate tax brackets if empty
                    if hasattr(self, "tax_brackets_table") and (
                        not self.tax_brackets_table or len(self.tax_brackets_table) == 0
                    ):
                        if "tax_brackets" in defaults:
                            # Clear existing rows if any
                            self.set("tax_brackets_table", [])

                            for bracket in defaults["tax_brackets"]:
                                row = self.append("tax_brackets_table", {})
                                row.income_from = bracket.get("income_from", 0)
                                row.income_to = bracket.get("income_to", 0)
                                row.tax_rate = bracket.get("tax_rate", 0)

                            defaults_loaded = True

                    # Populate tipe karyawan if empty
                    if hasattr(self, "tipe_karyawan") and (
                        not self.tipe_karyawan or len(self.tipe_karyawan) == 0
                    ):
                        if "tipe_karyawan" in defaults:
                            # Clear existing rows if any
                            self.set("tipe_karyawan", [])

                            for tipe in defaults["tipe_karyawan"]:
                                row = self.append("tipe_karyawan", {})
                                row.tipe_karyawan = tipe

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

    def _ensure_child_doctypes_exist(self):
        """Ensure all required child DocTypes exist, try to create them if missing"""
        # Check for Tipe Karyawan Entry
        if not frappe.db.exists("DocType", "Tipe Karyawan Entry"):
            doctype = frappe.new_doc("DocType")
            doctype.name = "Tipe Karyawan Entry"
            doctype.module = "Payroll Indonesia"
            doctype.istable = 1
            doctype.editable_grid = 1

            field = {
                "fieldname": "tipe_karyawan",
                "fieldtype": "Data",
                "label": "Tipe Karyawan",
                "in_list_view": 1,
                "reqd": 1,
            }

            doctype.append("fields", field)
            doctype.flags.ignore_permissions = True
            doctype.insert(ignore_permissions=True)
            frappe.db.commit()

            frappe.log_error("Created missing Tipe Karyawan Entry DocType", "Setup Info")

        # Add code for other child DocTypes if needed
