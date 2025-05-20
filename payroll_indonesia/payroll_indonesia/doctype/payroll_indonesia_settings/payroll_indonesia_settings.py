# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last Modified: 2025-05-20 04:45:04 by dannyaudian

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
# Import TER validation and default rates from pph_ter.py
from payroll_indonesia.payroll_indonesia.tax.pph_ter import (
    DEFAULT_TER_RATES,
    validate_ter_data_availability
)


class PayrollIndonesiaSettings(Document):
    def validate(self):
        """Validate settings on save"""
        try:
            self.validate_tax_settings()
            self.validate_ter_settings()  # Updated TER validation
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

    def validate_ter_settings(self):
        """Validate TER-specific settings for completeness"""
        if not self.use_ter:
            # If TER is not enabled, no need to validate TER settings
            return

        # Use the new validation function from pph_ter.py
        issues = validate_ter_data_availability()
        # Store issues in the new field for displaying in the UI
        self.ter_validation_issues = "\n".join(issues) if issues else ""
            
        # Display comprehensive validation results
        if issues:
            issues_text = "\n• " + "\n• ".join(issues)
            frappe.msgprint(
                _("TER Configuration Issues Detected:{0}\n\nPlease complete TER setup before using this method for calculations.").format(issues_text),
                indicator="red"
            )

    def _validate_ter_rate_json(self, json_data, category_name, issues_list):
        """
        Validate TER rate JSON data for a specific category
        
        Args:
            json_data: JSON string with TER rates
            category_name: Name of TER category ("TER A", "TER B", "TER C")
            issues_list: List to collect validation issues
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not json_data:
            issues_list.append(_("{0} rates are missing").format(category_name))
            return False
            
        try:
            # Parse the JSON data
            rate_data = json.loads(json_data)
            
            # Check if it's a list with at least one entry
            if not isinstance(rate_data, list) or not rate_data:
                issues_list.append(_("{0} rates format is invalid (not a list or empty)").format(category_name))
                return False
                
            # Check if there's at least one rate with is_highest_bracket=True
            has_highest_bracket = any(
                item.get("is_highest_bracket", False) for item in rate_data
            )
            if not has_highest_bracket:
                issues_list.append(
                    _("{0} rates missing highest bracket (no unlimited upper bracket defined)").format(category_name)
                )
                return False
                
            # Check that all entries have required fields
            for idx, item in enumerate(rate_data):
                missing_fields = []
                for field in ["income_from", "income_to", "rate"]:
                    if field not in item:
                        missing_fields.append(field)
                
                if missing_fields:
                    issues_list.append(
                        _("{0} rate entry {1} is missing fields: {2}").format(
                            category_name, idx + 1, ", ".join(missing_fields)
                        )
                    )
                    return False
                    
            return True
        except json.JSONDecodeError:
            issues_list.append(_("{0} rates contain invalid JSON").format(category_name))
            return False
        except Exception as e:
            issues_list.append(_("{0} rates validation error: {1}").format(category_name, str(e)))
            return False

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
                except json.JSONDecodeError:
                    frappe.msgprint(_("Invalid JSON format in field {0}").format(field), indicator="red")
                except Exception:
                    frappe.msgprint(_("Error validating field {0}").format(field), indicator="red")

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

                # Update calculation method and TER usage flag
                needs_update = False
                
                if hasattr(pph_settings, "calculation_method") and pph_settings.calculation_method != self.tax_calculation_method:
                    pph_settings.calculation_method = self.tax_calculation_method
                    needs_update = True
                    
                # Sync the use_ter field if it exists in PPh 21 Settings
                if hasattr(pph_settings, "use_ter") and pph_settings.use_ter != self.use_ter:
                    pph_settings.use_ter = self.use_ter
                    needs_update = True
                
                if needs_update:
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

    def sync_ter_rates(self, force_sync=False):
        """
        Sync TER rates from JSON fields to PPh 21 TER Table
        
        Args:
            force_sync (bool): If True, forces sync even if use_ter is not enabled
        """
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            frappe.log_error("PPh 21 TER Table DocType not found - skipping sync", "TER Sync Info")
            return

        # Skip sync if TER is not enabled, unless forced
        if not self.use_ter and not force_sync:
            return
            
        # Check if table is empty and populate with defaults if needed
        if frappe.db.count("PPh 21 TER Table") == 0:
            for category, rate in DEFAULT_TER_RATES.items():
                if not category:
                    continue
                doc = frappe.new_doc("PPh 21 TER Table")
                doc.category = category
                doc.status_pajak = "TK/0"
                doc.min_penghasilan = 0
                doc.max_penghasilan = 1_000_000_000
                doc.rate = rate * 100  # Simpan sebagai persen
                doc.is_highest_bracket = 1
                doc.insert()
            frappe.msgprint("Data default TER berhasil disisipkan.")
            return

        # Proceed with normal sync if table is not empty
        try:
            # Track sync status
            success_count = 0
            error_count = 0
            
            # Sync TER A rates
            if self.ter_rate_ter_a_json:
                try:
                    ter_a_rates = json.loads(self.ter_rate_ter_a_json)
                    success_a = self._sync_ter_category_rates("TER A", ter_a_rates)
                    success_count += success_a
                except Exception as e:
                    error_count += 1
                    frappe.log_error(f"Error syncing TER A rates: {str(e)}", "TER Sync Error")

            # Sync TER B rates
            if self.ter_rate_ter_b_json:
                try:
                    ter_b_rates = json.loads(self.ter_rate_ter_b_json)
                    success_b = self._sync_ter_category_rates("TER B", ter_b_rates)
                    success_count += success_b
                except Exception as e:
                    error_count += 1
                    frappe.log_error(f"Error syncing TER B rates: {str(e)}", "TER Sync Error")

            # Sync TER C rates
            if self.ter_rate_ter_c_json:
                try:
                    ter_c_rates = json.loads(self.ter_rate_ter_c_json)
                    success_c = self._sync_ter_category_rates("TER C", ter_c_rates)
                    success_count += success_c
                except Exception as e:
                    error_count += 1
                    frappe.log_error(f"Error syncing TER C rates: {str(e)}", "TER Sync Error")

            # Log sync results if performed through forced sync
            if force_sync:
                if error_count > 0:
                    frappe.msgprint(
                        _("TER Rates sync completed with some errors. See error log for details."),
                        indicator="orange"
                    )
                else:
                    frappe.msgprint(
                        _("TER Rates successfully synced to database."),
                        indicator="green"
                    )

        except Exception as e:
            frappe.log_error(f"Error in sync_ter_rates: {str(e)}", "TER Sync Error")

    def _sync_ter_category_rates(self, category, rates):
        """
        Sync rates for a specific TER category
        
        Args:
            category: TER category name ("TER A", "TER B", "TER C")
            rates: List of rate dictionaries
            
        Returns:
            int: Number of successfully synced records
        """
        if not isinstance(rates, list):
            return 0
            
        success_count = 0
        for rate_data in rates:
            try:
                # Skip invalid entries
                if not isinstance(rate_data, dict):
                    continue
                    
                income_from = flt(rate_data.get("income_from", 0))
                income_to = flt(rate_data.get("income_to", 0))
                rate = flt(rate_data.get("rate", 0))
                is_highest_bracket = bool(rate_data.get("is_highest_bracket", 0))
                
                filters = {
                    "status_pajak": category,
                    "income_from": income_from,
                    "income_to": income_to,
                }

                if frappe.db.exists("PPh 21 TER Table", filters):
                    # Update existing record
                    ter_doc = frappe.get_doc("PPh 21 TER Table", filters)
                    ter_doc.rate = rate
                    ter_doc.is_highest_bracket = is_highest_bracket
                    ter_doc.flags.ignore_permissions = True
                    ter_doc.save()
                    success_count += 1
                else:
                    # Create new record
                    ter_doc = frappe.new_doc("PPh 21 TER Table")
                    ter_doc.update({
                        "status_pajak": category,
                        "income_from": income_from,
                        "income_to": income_to,
                        "rate": rate,
                        "is_highest_bracket": is_highest_bracket,
                        "description": self._build_ter_description(category, rate_data),
                    })
                    ter_doc.flags.ignore_permissions = True
                    ter_doc.insert()
                    success_count += 1
            except Exception as e:
                frappe.log_error(
                    f"Error syncing TER rate record for {category}: {str(e)}",
                    "TER Rate Sync Error"
                )
                
        return success_count

    def _build_ter_description(self, status, rate_data):
        """Build description for TER rates"""
        income_from = flt(rate_data.get("income_from", 0))
        income_to = flt(rate_data.get("income_to", 0))

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
                return flt(row.ptkp_amount)

        return 0

    def get_ptkp_values_dict(self):
        """Return PTKP values as a dictionary"""
        ptkp_dict = {}
        if hasattr(self, "ptkp_table") and self.ptkp_table:
            for row in self.ptkp_table:
                ptkp_dict[row.status_pajak] = flt(row.ptkp_amount)
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
                        "income_from": flt(row.income_from),
                        "income_to": flt(row.income_to),
                        "tax_rate": flt(row.tax_rate),
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
        """
        Get TER category for a specific PTKP status with improved validation and fallback
        
        Args:
            ptkp_status: PTKP status code (e.g., 'TK0', 'K1')
            
        Returns:
            str: The corresponding TER category ('TER A', 'TER B', or 'TER C')
        """
        # Validate input
        if not ptkp_status:
            return "TER C"  # Default to highest category for safety
            
        # Normalize the status
        try:
            ptkp_status = str(ptkp_status).strip().upper()
        except Exception:
            return "TER C"  # Default on error
            
        # First try to get mapping from settings
        if hasattr(self, "ptkp_ter_mapping_table") and self.ptkp_ter_mapping_table:
            for row in self.ptkp_ter_mapping_table:
                if hasattr(row, "ptkp_status") and row.ptkp_status == ptkp_status:
                    return row.ter_category

        # If no mapping found, use standard logic based on PMK 168/2023
        try:
            # Extract prefix and suffix safely
            prefix = ptkp_status[:2] if len(ptkp_status) >= 2 else ptkp_status
            suffix = ptkp_status[2:] if len(ptkp_status) >= 3 else "0"
            
            # Apply mapping rules
            if ptkp_status == "TK0":
                return "TER A"
            elif prefix == "TK" and suffix in ["1", "2"]:
                return "TER B"
            elif prefix == "TK" and suffix == "3":
                return "TER C"
            elif prefix == "K" and suffix == "0":
                return "TER B"
            elif prefix == "K" and suffix in ["1", "2", "3"]:
                return "TER C"
            elif prefix == "HB":  # Special case for HB (single parent)
                return "TER C"
            else:
                # If unsure, use the highest TER category
                return "TER C"
        except Exception:
            # Return highest category on error for safety
            return "TER C"

    def get_ter_rate(self, ter_category, income, fallback_to_json=True):
        """
        Get TER rate based on TER category and income
        Enhanced with better validation, error handling, and fallback mechanism
        
        Args:
            ter_category: TER category ('TER A', 'TER B', 'TER C')
            income: Monthly income amount
            fallback_to_json: Whether to fallback to JSON data if database lookup fails
            
        Returns:
            float: The TER rate as percentage (e.g., 15.0 for 15%)
        """
        # Early validation
        if not self.use_ter:
            return 0
            
        # Validate inputs
        try:
            income_value = flt(income)
            
            # Normalize ter_category
            if not ter_category or not isinstance(ter_category, str):
                ter_category = "TER C"  # Default to highest category
            else:
                ter_category = ter_category.strip()
                if ter_category not in ["TER A", "TER B", "TER C"]:
                    ter_category = "TER C"  # Default if invalid
        except Exception:
            # On validation error, use safe defaults
            income_value = 0
            ter_category = "TER C"
            
        # If income is zero or negative, return 0 rate
        if income_value <= 0:
            return 0
            
        # Default rates by category - will be used if nothing else works
        default_rates = {
            "TER A": 5.0,   # 5%
            "TER B": 15.0,  # 15%
            "TER C": 25.0,  # 25%
        }

        try:
            # Try to fetch from database first - most reliable source
            rate = self._get_ter_rate_from_database(ter_category, income_value)
            if rate is not None:
                return rate
                
            # If database lookup fails and fallback enabled, try JSON data
            if fallback_to_json:
                rate = self._get_ter_rate_from_json(ter_category, income_value)
                if rate is not None:
                    return rate
        except Exception as e:
            frappe.log_error(
                f"Error getting TER rate for {ter_category}, income {income_value}: {str(e)}",
                "TER Rate Error"
            )
            
        # Ultimate fallback - use conservative default rates
        return default_rates.get(ter_category, 25.0)

    def _get_ter_rate_from_database(self, ter_category, income):
        """
        Get TER rate from PPh 21 TER Table in database
        
        Args:
            ter_category: TER category
            income: Income amount
            
        Returns:
            float: TER rate or None if not found
        """
        try:
            # Query the TER Table for matching rates
            ter_entries = frappe.get_all(
                "PPh 21 TER Table",
                filters={"status_pajak": ter_category},
                fields=["income_from", "income_to", "rate", "is_highest_bracket"],
                order_by="income_from",
            )

            for entry in ter_entries:
                # Check if this is the highest bracket (no upper limit)
                if entry.is_highest_bracket and income >= flt(entry.income_from):
                    return flt(entry.rate)
                    
                # Check if income falls in this range bracket
                if income >= flt(entry.income_from) and (
                    flt(entry.income_to) == 0 or income < flt(entry.income_to)
                ):
                    return flt(entry.rate)
                    
            # No suitable bracket found
            return None
            
        except Exception as e:
            frappe.log_error(f"Error in database TER rate lookup: {str(e)}", "TER Rate DB Error")
            return None

    def _get_ter_rate_from_json(self, ter_category, income):
        """
        Get TER rate from JSON field data
        
        Args:
            ter_category: TER category
            income: Income amount
            
        Returns:
            float: TER rate or None if not found
        """
        try:
            # Select appropriate JSON field
            json_field = None
            if ter_category == "TER A" and self.ter_rate_ter_a_json:
                json_field = self.ter_rate_ter_a_json
            elif ter_category == "TER B" and self.ter_rate_ter_b_json:
                json_field = self.ter_rate_ter_b_json
            elif ter_category == "TER C" and self.ter_rate_ter_c_json:
                json_field = self.ter_rate_ter_c_json
                
            if not json_field:
                return None
                
            # Parse JSON and search for matching rate
            rates = json.loads(json_field)
            if not isinstance(rates, list):
                return None
                
            # Sort rates by income_from to ensure proper ordering
            rates = sorted(rates, key=lambda x: flt(x.get("income_from", 0)))
                
            for rate in rates:
                # Check highest bracket first
                if rate.get("is_highest_bracket") and income >= flt(rate.get("income_from", 0)):
                    return flt(rate.get("rate", 0))
                    
                # Check regular brackets
                if income >= flt(rate.get("income_from", 0)) and (
                    flt(rate.get("income_to", 0)) == 0 or income < flt(rate.get("income_to", 0))
                ):
                    return flt(rate.get("rate", 0))
                    
            # No suitable bracket found
            return None
            
        except Exception as e:
            frappe.log_error(f"Error in JSON TER rate lookup: {str(e)}", "TER Rate JSON Error")
            return None

    def ensure_ter_setup_complete(self):
        """
        Check if TER setup is complete and ready for tax calculations
        
        Returns:
            dict: Status of TER setup with details
        """
        result = {
            "is_complete": False,
            "issues": [],
            "use_ter": self.use_ter,
        }
        
        # First check if TER is even enabled
        if not self.use_ter:
            result["is_complete"] = False
            result["issues"].append("TER calculation method is not enabled")
            return result
            
        # Check if TER rate tables are present for all categories
        if not self.ter_rate_ter_a_json:
            result["issues"].append("TER A rates are missing")
            
        if not self.ter_rate_ter_b_json:
            result["issues"].append("TER B rates are missing")
            
        if not self.ter_rate_ter_c_json:
            result["issues"].append("TER C rates are missing")
            
        # Check if PTKP to TER mapping is complete
        if not self.ptkp_ter_mapping_table or len(self.ptkp_ter_mapping_table) == 0:
            result["issues"].append("PTKP to TER mapping is missing")
            
        # Check if PPh 21 TER Table (database table) has entries
        try:
            ter_table_count = frappe.db.count("PPh 21 TER Table")
            if ter_table_count == 0:
                result["issues"].append("PPh 21 TER Table is empty")
        except Exception:
            result["issues"].append("Could not verify PPh 21 TER Table status")
            
        # Set overall status
        result["is_complete"] = len(result["issues"]) == 0
        
        return result

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

        # Dictionary of DocTypes to check/create with their fields
        child_doctypes = {
            "Tipe Karyawan Entry": [
                {
                    "fieldname": "tipe_karyawan",
                    "fieldtype": "Data",
                    "label": "Tipe Karyawan",
                    "in_list_view": 1,
                    "reqd": 1,
                }
            ],
            "PTKP Table Entry": [
                {
                    "fieldname": "status_pajak",
                    "fieldtype": "Data",
                    "label": "PTKP Status",
                    "in_list_view": 1,
                    "reqd": 1,
                },
                {
                    "fieldname": "ptkp_amount",
                    "fieldtype": "Currency",
                    "label": "PTKP Amount",
                    "in_list_view": 1,
                    "reqd": 1,
                    "default": 0.0,
                },
            ],
            "Tax Bracket Entry": [
                {
                    "fieldname": "income_from",
                    "fieldtype": "Currency",
                    "label": "Income From",
                    "in_list_view": 1,
                    "reqd": 1,
                    "default": 0.0,
                },
                {
                    "fieldname": "income_to",
                    "fieldtype": "Currency",
                    "label": "Income To",
                    "in_list_view": 1,
                    "reqd": 1,
                    "default": 0.0,
                },
                {
                    "fieldname": "tax_rate",
                    "fieldtype": "Float",
                    "label": "Tax Rate (%)",
                    "in_list_view": 1,
                    "reqd": 1,
                    "default": 0.0,
                    "precision": 2,
                },
            ],
            "PTKP TER Mapping Entry": [
                {
                    "fieldname": "ptkp_status",
                    "fieldtype": "Data",
                    "label": "PTKP Status",
                    "in_list_view": 1,
                    "reqd": 1,
                },
                {
                    "fieldname": "ter_category",
                    "fieldtype": "Select",
                    "label": "TER Category",
                    "options": "TER A\nTER B\nTER C",
                    "in_list_view": 1,
                    "reqd": 1,
                },
            ],
        }

        # Check and create each missing DocType
        for doctype_name, fields in child_doctypes.items():
            if not frappe.db.exists("DocType", doctype_name):
                try:
                    # Create new DocType
                    doctype = frappe.new_doc("DocType")
                    doctype.name = doctype_name
                    doctype.module = "Payroll Indonesia"
                    doctype.istable = 1
                    doctype.editable_grid = 1

                    # Add all fields to the DocType
                    for field_def in fields:
                        doctype.append("fields", field_def)

                    # Insert with admin privileges
                    doctype.flags.ignore_permissions = True
                    doctype.insert(ignore_permissions=True)
                    frappe.db.commit()

                    # Log successful creation
                    frappe.log_error(
                        message=f"Successfully created missing DocType: {doctype_name}",
                        title="Setup Info",
                    )

                except Exception as e:
                    # Log detailed error information
                    frappe.log_error(
                        message=f"Failed to create DocType {doctype_name}: {str(e)}",
                        title="Setup Error",
                    )
