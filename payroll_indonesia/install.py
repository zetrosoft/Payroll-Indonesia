# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and Contributors
# See license.txt

import frappe
import json
import os
from frappe import _
from frappe.utils import getdate


def before_install():
    """Run before app installation"""
    pass


def after_install():
    """Run after app installation"""
    setup_payroll_components()


def after_update():
    """Run after app update"""
    # Apply our salary slip enhancements
    from payroll_indonesia.override.salary_slip import extend_salary_slip_functionality

    extend_salary_slip_functionality()


def after_migrate():
    """Run after app migrations"""
    migrate_from_json_to_doctype()


def setup_payroll_components():
    """Set up required payroll components if missing"""
    # Create required salary components if they don't exist
    components = [
        # Earnings
        {"name": "Gaji Pokok", "type": "Earning", "abbr": "GP"},
        # Deductions
        {"name": "BPJS Kesehatan Employee", "type": "Deduction", "abbr": "BKE"},
        {"name": "BPJS JHT Employee", "type": "Deduction", "abbr": "BJE"},
        {"name": "BPJS JP Employee", "type": "Deduction", "abbr": "BPE"},
        {"name": "PPh 21", "type": "Deduction", "abbr": "PPh"},
    ]

    for comp in components:
        if not frappe.db.exists("Salary Component", comp["name"]):
            doc = frappe.new_doc("Salary Component")
            doc.salary_component = comp["name"]
            doc.salary_component_abbr = comp["abbr"]
            doc.type = comp["type"]
            doc.insert()

    frappe.db.commit()

    # Log completion
    frappe.log_error("Payroll Indonesia components setup completed", "Install")


def migrate_from_json_to_doctype():
    """
    Migrate settings from defaults.json to the Payroll Indonesia Settings DocType
    """
    try:
        # Check if DocType exists
        if not frappe.db.exists("DocType", "Payroll Indonesia Settings"):
            frappe.msgprint("Payroll Indonesia Settings DocType not found, skipping migration")
            return

        # Check if already migrated to prevent duplication
        if frappe.db.exists("Payroll Indonesia Settings"):
            settings = frappe.get_doc("Payroll Indonesia Settings")
            if settings.app_updated_by == "dannyaudian" and settings.app_version == "1.0.0":
                frappe.msgprint("Settings already migrated, skipping")
                return

        # Get path to defaults.json
        config_path = frappe.get_app_path("payroll_indonesia", "config", "defaults.json")
        if not os.path.exists(config_path):
            frappe.msgprint("defaults.json not found, skipping migration")
            return

        # Load the config
        with open(config_path) as f:
            config = json.load(f)

        # Create new settings
        settings = frappe.new_doc("Payroll Indonesia Settings")

        # App info
        app_info = config.get("app_info", {})
        settings.app_version = app_info.get("version", "1.0.0")
        settings.app_last_updated = app_info.get(
            "last_updated", getdate().strftime("%Y-%m-%d %H:%M:%S")
        )
        settings.app_updated_by = app_info.get("updated_by", "dannyaudian")

        # BPJS settings
        bpjs = config.get("bpjs", {})
        settings.kesehatan_employee_percent = bpjs.get("kesehatan_employee_percent", 1.0)
        settings.kesehatan_employer_percent = bpjs.get("kesehatan_employer_percent", 4.0)
        settings.kesehatan_max_salary = bpjs.get("kesehatan_max_salary", 12000000.0)
        settings.jht_employee_percent = bpjs.get("jht_employee_percent", 2.0)
        settings.jht_employer_percent = bpjs.get("jht_employer_percent", 3.7)
        settings.jp_employee_percent = bpjs.get("jp_employee_percent", 1.0)
        settings.jp_employer_percent = bpjs.get("jp_employer_percent", 2.0)
        settings.jp_max_salary = bpjs.get("jp_max_salary", 9077600.0)
        settings.jkk_percent = bpjs.get("jkk_percent", 0.24)
        settings.jkm_percent = bpjs.get("jkm_percent", 0.3)

        # Tax settings
        tax = config.get("tax", {})
        settings.umr_default = tax.get("umr_default", 4900000.0)
        settings.biaya_jabatan_percent = tax.get("biaya_jabatan_percent", 5.0)
        settings.biaya_jabatan_max = tax.get("biaya_jabatan_max", 500000.0)
        settings.npwp_mandatory = tax.get("npwp_mandatory", 0)
        settings.tax_calculation_method = tax.get("tax_calculation_method", "TER")
        settings.use_ter = tax.get("use_ter", 1)
        settings.use_gross_up = tax.get("use_gross_up", 0)

        # PTKP values
        ptkp = config.get("ptkp", {})
        for status, amount in ptkp.items():
            settings.append("ptkp_table", {"status_pajak": status, "ptkp_amount": amount})

        # PTKP to TER mapping
        ptkp_ter_mapping = config.get("ptkp_to_ter_mapping", {})
        for status, category in ptkp_ter_mapping.items():
            settings.append(
                "ptkp_ter_mapping_table", {"ptkp_status": status, "ter_category": category}
            )

        # Tax brackets
        tax_brackets = config.get("tax_brackets", [])
        for bracket in tax_brackets:
            settings.append(
                "tax_brackets_table",
                {
                    "income_from": bracket.get("income_from", 0),
                    "income_to": bracket.get("income_to", 0),
                    "tax_rate": bracket.get("tax_rate", 0),
                },
            )

        # Defaults
        defaults = config.get("defaults", {})
        settings.default_currency = defaults.get("currency", "IDR")
        settings.attendance_based_on_timesheet = defaults.get("attendance_based_on_timesheet", 0)
        settings.payroll_frequency = defaults.get("payroll_frequency", "Monthly")
        settings.salary_slip_based_on = defaults.get("salary_slip_based_on", "Leave Policy")
        settings.max_working_days_per_month = defaults.get("max_working_days_per_month", 22)
        settings.include_holidays_in_total_working_days = defaults.get(
            "include_holidays_in_total_working_days", 0
        )
        settings.working_hours_per_day = defaults.get("working_hours_per_day", 8)

        # Struktur gaji
        struktur_gaji = config.get("struktur_gaji", {})
        settings.basic_salary_percent = struktur_gaji.get("basic_salary_percent", 75)
        settings.meal_allowance = struktur_gaji.get("meal_allowance", 750000.0)
        settings.transport_allowance = struktur_gaji.get("transport_allowance", 900000.0)
        settings.struktur_gaji_umr_default = struktur_gaji.get("umr_default", 4900000.0)
        settings.position_allowance_percent = struktur_gaji.get("position_allowance_percent", 7.5)
        settings.hari_kerja_default = struktur_gaji.get("hari_kerja_default", 22)

        # Tipe karyawan
        tipe_karyawan = config.get("tipe_karyawan", [])
        for tipe in tipe_karyawan:
            settings.append("tipe_karyawan", {"tipe_karyawan": tipe})

        # Save the settings
        settings.flags.ignore_permissions = True
        settings.insert()

        # Migrate TER rates to PPh 21 TER Table
        # This assumes PPh 21 TER Table DocType already exists
        if frappe.db.exists("DocType", "PPh 21 TER Table"):
            migrate_ter_rates(config.get("ter_rates", {}))

        frappe.db.commit()
        frappe.msgprint(
            "Successfully migrated settings from defaults.json to Payroll Indonesia Settings DocType"
        )

        # Log the success
        frappe.log_error(
            "Settings migration from defaults.json to Payroll Indonesia Settings completed successfully",
            "Settings Migration",
        )

    except Exception as e:
        frappe.log_error(f"Error migrating settings: {str(e)}", "Migration Error")
        frappe.msgprint(f"Error migrating settings: {str(e)}")


def migrate_ter_rates(ter_rates):
    """
    Migrate TER rates from defaults.json to PPh 21 TER Table entries

    Args:
        ter_rates (dict): Dictionary containing TER rates from defaults.json
    """
    try:
        # Get PPh 21 Settings
        if not frappe.db.exists("DocType", "PPh 21 Settings"):
            frappe.msgprint("PPh 21 Settings DocType not found, skipping TER rates migration")
            return

        # Check if PPh 21 Settings exists
        pph21_settings_list = frappe.db.get_all("PPh 21 Settings")
        if not pph21_settings_list:
            frappe.msgprint("PPh 21 Settings not found, skipping TER rates migration")
            return

        # Get PPh 21 Settings document
        pph21_settings = frappe.get_doc("PPh 21 Settings")

        # Check if we already have TER entries
        existing_entries = frappe.db.count("PPh 21 TER Table", {"parent": "PPh 21 Settings"})
        if existing_entries > 0:
            frappe.msgprint(
                f"Found {existing_entries} existing TER entries, skipping TER rates migration"
            )
            return

        # Process each TER category
        for category, rates in ter_rates.items():
            for rate_data in rates:
                # Create child table entry
                child_doc = frappe.new_doc("PPh 21 TER Table")
                child_doc.status_pajak = category
                child_doc.income_from = rate_data.get("income_from", 0)
                child_doc.income_to = rate_data.get("income_to", 0)
                child_doc.rate = rate_data.get("rate", 0)
                child_doc.is_highest_bracket = rate_data.get("is_highest_bracket", 0)
                child_doc.description = f"{category} {rate_data.get('income_from', 0):,.0f}" + (
                    f" - {rate_data.get('income_to', 0):,.0f}"
                    if rate_data.get("income_to", 0) > 0
                    else " onwards"
                )
                child_doc.parent = "PPh 21 Settings"
                child_doc.parenttype = "PPh 21 Settings"
                child_doc.parentfield = "ter_table"

                # Add to parent
                pph21_settings.append("ter_table", child_doc)

        # Save the settings
        pph21_settings.flags.ignore_permissions = True
        pph21_settings.save()
        frappe.msgprint(f"Successfully migrated TER rates from defaults.json to PPh 21 TER Table")

    except Exception as e:
        frappe.log_error(f"Error migrating TER rates: {str(e)}", "Migration Error")
        frappe.msgprint(f"Error migrating TER rates: {str(e)}")
