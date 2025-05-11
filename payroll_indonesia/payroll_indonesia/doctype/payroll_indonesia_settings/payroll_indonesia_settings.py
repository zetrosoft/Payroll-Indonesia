# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PayrollIndonesiaSettings(Document):
    def validate(self):
        """Validate settings on save"""
        self.validate_tax_settings()
        self.validate_bpjs_settings()
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

        except Exception as e:
            frappe.log_error(f"Error syncing settings: {str(e)}", "Settings Sync Error")

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
