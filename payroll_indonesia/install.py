# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and Contributors
# See license.txt

import frappe
import json
import os
from frappe.utils import get_datetime_str, flt
import logging

logger = logging.getLogger(__name__)


def before_install():
    """Run before app installation"""
    pass


def after_install():
    """Run after app installation"""
    setup_payroll_components()
    migrate_from_json_to_doctype()


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
        {"name": "Gaji Pokok", "type": "Earning", "abbr": "GP", "is_tax_applicable": 1},
        {"name": "Tunjangan Makan", "type": "Earning", "abbr": "TM", "is_tax_applicable": 1},
        {"name": "Tunjangan Transport", "type": "Earning", "abbr": "TT", "is_tax_applicable": 1},
        {"name": "Insentif", "type": "Earning", "abbr": "INS", "is_tax_applicable": 1},
        {"name": "Bonus", "type": "Earning", "abbr": "BON", "is_tax_applicable": 1},
        # Deductions
        {"name": "BPJS Kesehatan Employee", "type": "Deduction", "abbr": "BKE"},
        {"name": "BPJS JHT Employee", "type": "Deduction", "abbr": "BJE"},
        {"name": "BPJS JP Employee", "type": "Deduction", "abbr": "BPE"},
        {
            "name": "PPh 21",
            "type": "Deduction",
            "abbr": "PPH",
            "variable_based_on_taxable_salary": 1,
        },
    ]

    for comp in components:
        if not frappe.db.exists("Salary Component", comp["name"]):
            doc = frappe.new_doc("Salary Component")
            doc.salary_component = comp["name"]
            doc.salary_component_abbr = comp["abbr"]
            doc.type = comp["type"]

            # Add optional fields
            for field in ["is_tax_applicable", "variable_based_on_taxable_salary"]:
                if field in comp:
                    doc.set(field, comp[field])

            doc.insert()

    frappe.db.commit()

    logger.info("Payroll Indonesia components setup completed")


def migrate_from_json_to_doctype():
    """
    Migrate settings from defaults.json to the Payroll Indonesia Settings DocType

    This function is idempotent and will:
    - Skip if DocType doesn't exist (with warning)
    - Skip if settings already exist with the same version
    - Create settings if DocType exists but settings don't
    - Update settings if they exist but have a different version

    Returns:
        bool: True if migration was successful, False otherwise
    """
    try:
        # Check if DocType exists
        if not frappe.db.exists("DocType", "Payroll Indonesia Settings"):
            logger.warning("Payroll Indonesia Settings DocType not found, skipping migration")
            return False

        # Check if settings document already exists
        settings_exists = frappe.db.exists(
            "Payroll Indonesia Settings", "Payroll Indonesia Settings"
        )

        # Get config data regardless of whether we'll use it
        config = get_default_config()
        if not config:
            logger.warning("Could not load defaults.json, skipping migration")
            return False

        # If settings already exist, check version
        if settings_exists:
            settings = frappe.get_doc("Payroll Indonesia Settings", "Payroll Indonesia Settings")
            app_info = config.get("app_info", {})
            config_version = app_info.get("version", "1.0.0")

            # Skip if version matches
            if settings.app_version == config_version and settings.app_updated_by == app_info.get(
                "updated_by", "dannyaudian"
            ):
                logger.info("Settings already exist with matching version, skipping migration")
                return True

            logger.info(
                f"Updating existing settings from version {settings.app_version} to {config_version}"
            )
        else:
            logger.info("Creating new Payroll Indonesia Settings")
            settings = frappe.new_doc("Payroll Indonesia Settings")

        # Update settings with values from config
        update_settings_from_config(settings, config)

        # Save with safe flags
        settings.flags.ignore_validate = True
        settings.flags.ignore_permissions = True
        settings.flags.ignore_mandatory = True

        if settings_exists:
            settings.save(ignore_permissions=True)
            logger.info("Updated existing Payroll Indonesia Settings")
        else:
            settings.insert(ignore_permissions=True)
            logger.info("Created new Payroll Indonesia Settings")

        # Migrate TER rates to PPh 21 TER Table if that DocType exists
        if frappe.db.exists("DocType", "PPh 21 TER Table"):
            migrate_ter_rates(config.get("ter_rates", {}))

        frappe.db.commit()

        # Update BPJS Settings if it exists
        sync_to_bpjs_settings(settings)

        return True

    except Exception as e:
        frappe.db.rollback()
        logger.exception(f"Error in migrate_from_json_to_doctype: {str(e)}")
        return False


def get_default_config():
    """
    Load the defaults.json configuration file

    Returns:
        dict: Configuration data or None if file not found
    """
    try:
        # Try primary location
        config_path = frappe.get_app_path(
            "payroll_indonesia", "payroll_indonesia", "config", "defaults.json"
        )

        if not os.path.exists(config_path):
            # Try alternative location
            config_path = frappe.get_app_path("payroll_indonesia", "config", "defaults.json")

            if not os.path.exists(config_path):
                logger.warning("defaults.json not found in expected locations")
                return None

        # Load and return config
        with open(config_path) as f:
            return json.load(f)

    except Exception as e:
        logger.exception(f"Error loading defaults.json: {str(e)}")
        return None


def update_settings_from_config(settings, config):
    """
    Update settings document with values from config

    Args:
        settings: Payroll Indonesia Settings document
        config: Configuration data from defaults.json
    """
    # App info
    app_info = config.get("app_info", {})
    settings.app_version = app_info.get("version", "1.0.0")
    settings.app_last_updated = app_info.get("last_updated", get_datetime_str())
    settings.app_updated_by = app_info.get("updated_by", "dannyaudian")

    # BPJS settings
    bpjs = config.get("bpjs", {})
    settings.kesehatan_employee_percent = flt(bpjs.get("kesehatan_employee_percent", 1.0))
    settings.kesehatan_employer_percent = flt(bpjs.get("kesehatan_employer_percent", 4.0))
    settings.kesehatan_max_salary = flt(bpjs.get("kesehatan_max_salary", 12000000.0))
    settings.jht_employee_percent = flt(bpjs.get("jht_employee_percent", 2.0))
    settings.jht_employer_percent = flt(bpjs.get("jht_employer_percent", 3.7))
    settings.jp_employee_percent = flt(bpjs.get("jp_employee_percent", 1.0))
    settings.jp_employer_percent = flt(bpjs.get("jp_employer_percent", 2.0))
    settings.jp_max_salary = flt(bpjs.get("jp_max_salary", 9077600.0))
    settings.jkk_percent = flt(bpjs.get("jkk_percent", 0.24))
    settings.jkm_percent = flt(bpjs.get("jkm_percent", 0.3))

    # Tax settings
    tax = config.get("tax", {})
    settings.umr_default = flt(tax.get("umr_default", 4900000.0))
    settings.biaya_jabatan_percent = flt(tax.get("biaya_jabatan_percent", 5.0))
    settings.biaya_jabatan_max = flt(tax.get("biaya_jabatan_max", 500000.0))
    settings.npwp_mandatory = tax.get("npwp_mandatory", 0)
    settings.tax_calculation_method = tax.get("tax_calculation_method", "TER")
    settings.use_ter = tax.get("use_ter", 1)
    settings.use_gross_up = tax.get("use_gross_up", 0)

    # Clear existing tables to prevent duplicates
    settings.ptkp_table = []
    settings.ptkp_ter_mapping_table = []
    settings.tax_brackets_table = []
    settings.tipe_karyawan = []

    # PTKP values
    ptkp = config.get("ptkp", {})
    for status, amount in ptkp.items():
        settings.append("ptkp_table", {"status_pajak": status, "ptkp_amount": flt(amount)})

    # PTKP to TER mapping
    ptkp_ter_mapping = config.get("ptkp_to_ter_mapping", {})
    for status, category in ptkp_ter_mapping.items():
        settings.append("ptkp_ter_mapping_table", {"ptkp_status": status, "ter_category": category})

    # Tax brackets
    tax_brackets = config.get("tax_brackets", [])
    for bracket in tax_brackets:
        settings.append(
            "tax_brackets_table",
            {
                "income_from": flt(bracket.get("income_from", 0)),
                "income_to": flt(bracket.get("income_to", 0)),
                "tax_rate": flt(bracket.get("tax_rate", 0)),
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
    settings.working_hours_per_day = flt(defaults.get("working_hours_per_day", 8))

    # Struktur gaji
    struktur_gaji = config.get("struktur_gaji", {})
    settings.basic_salary_percent = flt(struktur_gaji.get("basic_salary_percent", 75))
    settings.meal_allowance = flt(struktur_gaji.get("meal_allowance", 750000.0))
    settings.transport_allowance = flt(struktur_gaji.get("transport_allowance", 900000.0))
    settings.struktur_gaji_umr_default = flt(struktur_gaji.get("umr_default", 4900000.0))
    settings.position_allowance_percent = flt(struktur_gaji.get("position_allowance_percent", 7.5))
    settings.hari_kerja_default = struktur_gaji.get("hari_kerja_default", 22)

    # Tipe karyawan
    tipe_karyawan = config.get("tipe_karyawan", [])
    for tipe in tipe_karyawan:
        settings.append("tipe_karyawan", {"tipe_karyawan": tipe})


def sync_to_bpjs_settings(pi_settings):
    """
    Sync Payroll Indonesia Settings to BPJS Settings

    Args:
        pi_settings: Payroll Indonesia Settings document
    """
    try:
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
                if hasattr(bpjs_settings, field) and hasattr(pi_settings, field):
                    bpjs_settings.set(field, pi_settings.get(field))
                    needs_update = True

            if needs_update:
                bpjs_settings.flags.ignore_validate = True
                bpjs_settings.flags.ignore_permissions = True
                bpjs_settings.save()
                logger.info("BPJS Settings updated from Payroll Indonesia Settings")
    except Exception as e:
        logger.exception(f"Error syncing to BPJS Settings: {str(e)}")


def migrate_ter_rates(ter_rates):
    """
    Migrate TER rates from defaults.json to PPh 21 TER Table entries

    Args:
        ter_rates (dict): Dictionary containing TER rates from defaults.json

    Returns:
        bool: True if migration was successful, False otherwise
    """
    try:
        # Check if PPh 21 TER Table exists
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            logger.warning("PPh 21 TER Table DocType not found, skipping TER rates migration")
            return False

        # Get PPh 21 Settings
        if not frappe.db.exists("DocType", "PPh 21 Settings"):
            logger.warning("PPh 21 Settings DocType not found, skipping TER rates migration")
            return False

        # Check if PPh 21 Settings exists
        pph21_settings_list = frappe.db.get_all("PPh 21 Settings")
        if not pph21_settings_list:
            logger.warning("PPh 21 Settings not found, skipping TER rates migration")
            return False

        # Count existing entries
        existing_entries = frappe.db.count("PPh 21 TER Table")
        if existing_entries > 10:  # Arbitrary threshold to check if migration is needed
            logger.info(
                f"Found {existing_entries} existing TER entries, skipping TER rates migration"
            )
            return True

        # Clear existing TER entries to prevent duplicates
        frappe.db.sql("DELETE FROM `tabPPh 21 TER Table`")

        # Process each TER category
        count = 0
        for category, rates in ter_rates.items():
            for rate_data in rates:
                # Create TER entry
                ter_entry = frappe.new_doc("PPh 21 TER Table")
                ter_entry.status_pajak = category
                ter_entry.income_from = flt(rate_data.get("income_from", 0))
                ter_entry.income_to = flt(rate_data.get("income_to", 0))
                ter_entry.rate = flt(rate_data.get("rate", 0))
                ter_entry.is_highest_bracket = rate_data.get("is_highest_bracket", 0)

                # Create description
                if rate_data.get("is_highest_bracket", 0) or rate_data.get("income_to", 0) == 0:
                    description = f"{category} > {flt(rate_data.get('income_from', 0)):,.0f}"
                else:
                    description = f"{category} {flt(rate_data.get('income_from', 0)):,.0f} - {flt(rate_data.get('income_to', 0)):,.0f}"

                ter_entry.description = description

                # Insert with permission bypass
                ter_entry.flags.ignore_permissions = True
                ter_entry.flags.ignore_validate = True
                ter_entry.flags.ignore_mandatory = True
                ter_entry.insert(ignore_permissions=True)

                count += 1

        frappe.db.commit()
        logger.info(f"Successfully migrated {count} TER rates from defaults.json")
        return True

    except Exception as e:
        frappe.db.rollback()
        logger.exception(f"Error migrating TER rates: {str(e)}")
        return False
