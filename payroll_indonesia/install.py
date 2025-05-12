# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and Contributors
# See license.txt

import frappe
import json
import os
from frappe.utils import get_datetime_str, flt
import logging

logger = logging.getLogger(__name__)

# Define DocType schemas for creation if not exist
PAYROLL_INDONESIA_SETTINGS_DOCTYPE = {
    "doctype": "DocType",
    "custom": 0,
    "istable": 0,
    "issingle": 1,
    "module": "Payroll Indonesia",
    "name": "Payroll Indonesia Settings",
    "owner": "Administrator",
    "autoname": "Payroll Indonesia Settings",
    "properties": [],
    "search_fields": "",
    "sort_field": "modified",
    "sort_order": "DESC",
    "track_changes": 1,
    "fields": [
        # App info fields
        {"fieldname": "app_version", "fieldtype": "Data", "label": "App Version"},
        {"fieldname": "app_last_updated", "fieldtype": "Datetime", "label": "Last Updated"},
        {"fieldname": "app_updated_by", "fieldtype": "Data", "label": "Updated By"},
        # BPJS settings section
        {"fieldname": "bpjs_section", "fieldtype": "Section Break", "label": "BPJS Settings"},
        {
            "fieldname": "kesehatan_employee_percent",
            "fieldtype": "Float",
            "label": "BPJS Kesehatan Employee %",
            "precision": 2,
        },
        {
            "fieldname": "kesehatan_employer_percent",
            "fieldtype": "Float",
            "label": "BPJS Kesehatan Employer %",
            "precision": 2,
        },
        {
            "fieldname": "kesehatan_max_salary",
            "fieldtype": "Currency",
            "label": "BPJS Kesehatan Max Salary",
        },
        {"fieldname": "bpjs_col1", "fieldtype": "Column Break"},
        {
            "fieldname": "jht_employee_percent",
            "fieldtype": "Float",
            "label": "BPJS JHT Employee %",
            "precision": 2,
        },
        {
            "fieldname": "jht_employer_percent",
            "fieldtype": "Float",
            "label": "BPJS JHT Employer %",
            "precision": 2,
        },
        {"fieldname": "bpjs_col2", "fieldtype": "Column Break"},
        {
            "fieldname": "jp_employee_percent",
            "fieldtype": "Float",
            "label": "BPJS JP Employee %",
            "precision": 2,
        },
        {
            "fieldname": "jp_employer_percent",
            "fieldtype": "Float",
            "label": "BPJS JP Employer %",
            "precision": 2,
        },
        {"fieldname": "jp_max_salary", "fieldtype": "Currency", "label": "BPJS JP Max Salary"},
        {"fieldname": "bpjs_col3", "fieldtype": "Column Break"},
        {"fieldname": "jkk_percent", "fieldtype": "Float", "label": "BPJS JKK %", "precision": 2},
        {"fieldname": "jkm_percent", "fieldtype": "Float", "label": "BPJS JKM %", "precision": 2},
        # Tax settings section
        {"fieldname": "tax_section", "fieldtype": "Section Break", "label": "Tax Settings"},
        {"fieldname": "umr_default", "fieldtype": "Currency", "label": "Default UMR"},
        {
            "fieldname": "biaya_jabatan_percent",
            "fieldtype": "Float",
            "label": "Biaya Jabatan %",
            "precision": 2,
        },
        {"fieldname": "biaya_jabatan_max", "fieldtype": "Currency", "label": "Biaya Jabatan Max"},
        {"fieldname": "tax_col1", "fieldtype": "Column Break"},
        {"fieldname": "npwp_mandatory", "fieldtype": "Check", "label": "NPWP Mandatory"},
        {
            "fieldname": "tax_calculation_method",
            "fieldtype": "Select",
            "label": "Tax Calculation Method",
            "options": "TER\nProgressive",
        },
        {"fieldname": "use_ter", "fieldtype": "Check", "label": "Use TER"},
        {"fieldname": "use_gross_up", "fieldtype": "Check", "label": "Use Gross Up"},
        # Defaults section
        {
            "fieldname": "defaults_section",
            "fieldtype": "Section Break",
            "label": "Default Settings",
        },
        {
            "fieldname": "default_currency",
            "fieldtype": "Link",
            "label": "Default Currency",
            "options": "Currency",
        },
        {
            "fieldname": "attendance_based_on_timesheet",
            "fieldtype": "Check",
            "label": "Attendance Based on Timesheet",
        },
        {
            "fieldname": "payroll_frequency",
            "fieldtype": "Select",
            "label": "Payroll Frequency",
            "options": "Monthly\nFortnightly\nBimonthly\nWeekly\nDaily",
        },
        {
            "fieldname": "salary_slip_based_on",
            "fieldtype": "Select",
            "label": "Salary Slip Based on",
            "options": "Leave Policy\nWorkday",
        },
        {"fieldname": "defaults_col1", "fieldtype": "Column Break"},
        {
            "fieldname": "max_working_days_per_month",
            "fieldtype": "Int",
            "label": "Max Working Days per Month",
        },
        {
            "fieldname": "include_holidays_in_total_working_days",
            "fieldtype": "Check",
            "label": "Include Holidays in Total Working Days",
        },
        {
            "fieldname": "working_hours_per_day",
            "fieldtype": "Float",
            "label": "Working Hours per Day",
            "precision": 1,
        },
        # Struktur gaji section
        {"fieldname": "struktur_section", "fieldtype": "Section Break", "label": "Struktur Gaji"},
        {
            "fieldname": "basic_salary_percent",
            "fieldtype": "Float",
            "label": "Basic Salary %",
            "precision": 2,
        },
        {"fieldname": "meal_allowance", "fieldtype": "Currency", "label": "Meal Allowance"},
        {
            "fieldname": "transport_allowance",
            "fieldtype": "Currency",
            "label": "Transport Allowance",
        },
        {"fieldname": "struktur_col1", "fieldtype": "Column Break"},
        {
            "fieldname": "struktur_gaji_umr_default",
            "fieldtype": "Currency",
            "label": "Default UMR (Struktur Gaji)",
        },
        {
            "fieldname": "position_allowance_percent",
            "fieldtype": "Float",
            "label": "Position Allowance %",
            "precision": 2,
        },
        {"fieldname": "hari_kerja_default", "fieldtype": "Int", "label": "Default Working Days"},
    ],
    "permissions": [
        {
            "role": "System Manager",
            "permlevel": 0,
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 1,
            "submit": 0,
            "cancel": 0,
            "amend": 0,
            "import": 0,
            "export": 1,
            "report": 1,
            "share": 1,
        },
        {
            "role": "HR Manager",
            "permlevel": 0,
            "read": 1,
            "write": 1,
            "create": 0,
            "delete": 0,
            "submit": 0,
            "cancel": 0,
            "amend": 0,
            "import": 0,
            "export": 1,
            "report": 1,
            "share": 1,
        },
    ],
}

# Child table doctype definitions
CHILD_DOCTYPES = [
    # PTKP Table Entry - for storing PTKP values
    {
        "doctype": "DocType",
        "custom": 0,
        "istable": 1,  # This is a child table
        "module": "Payroll Indonesia",
        "name": "PTKP Table Entry",
        "owner": "Administrator",
        "fields": [
            {
                "fieldname": "status_pajak",
                "fieldtype": "Data",
                "label": "Status Pajak",
                "in_list_view": 1,
            },
            {
                "fieldname": "ptkp_amount",
                "fieldtype": "Currency",
                "label": "PTKP Amount",
                "in_list_view": 1,
            },
        ],
        "permissions": [
            {
                "role": "System Manager",
                "permlevel": 0,
                "read": 1,
                "write": 1,
                "create": 1,
                "delete": 1,
            }
        ],
    },
    # PTKP TER Mapping Entry - for mapping PTKP status to TER categories
    {
        "doctype": "DocType",
        "custom": 0,
        "istable": 1,
        "module": "Payroll Indonesia",
        "name": "PTKP TER Mapping Entry",
        "owner": "Administrator",
        "fields": [
            {
                "fieldname": "ptkp_status",
                "fieldtype": "Data",
                "label": "PTKP Status",
                "in_list_view": 1,
            },
            {
                "fieldname": "ter_category",
                "fieldtype": "Data",
                "label": "TER Category",
                "in_list_view": 1,
            },
        ],
        "permissions": [
            {
                "role": "System Manager",
                "permlevel": 0,
                "read": 1,
                "write": 1,
                "create": 1,
                "delete": 1,
            }
        ],
    },
    # Tax Bracket Entry - for storing tax brackets
    {
        "doctype": "DocType",
        "custom": 0,
        "istable": 1,
        "module": "Payroll Indonesia",
        "name": "Tax Bracket Entry",
        "owner": "Administrator",
        "fields": [
            {
                "fieldname": "income_from",
                "fieldtype": "Currency",
                "label": "Income From",
                "in_list_view": 1,
            },
            {
                "fieldname": "income_to",
                "fieldtype": "Currency",
                "label": "Income To",
                "in_list_view": 1,
            },
            {
                "fieldname": "tax_rate",
                "fieldtype": "Float",
                "label": "Tax Rate (%)",
                "in_list_view": 1,
                "precision": 2,
            },
        ],
        "permissions": [
            {
                "role": "System Manager",
                "permlevel": 0,
                "read": 1,
                "write": 1,
                "create": 1,
                "delete": 1,
            }
        ],
    },
    # Tipe Karyawan Entry - for storing employee types
    {
        "doctype": "DocType",
        "custom": 0,
        "istable": 1,
        "module": "Payroll Indonesia",
        "name": "Tipe Karyawan Entry",
        "owner": "Administrator",
        "fields": [
            {
                "fieldname": "tipe_karyawan",
                "fieldtype": "Data",
                "label": "Tipe Karyawan",
                "in_list_view": 1,
            }
        ],
        "permissions": [
            {
                "role": "System Manager",
                "permlevel": 0,
                "read": 1,
                "write": 1,
                "create": 1,
                "delete": 1,
            }
        ],
    },
]


def before_install():
    """Run before app installation"""
    logger.info("Running pre-installation tasks for Payroll Indonesia")
    ensure_doctypes_exist()


def after_install():
    """Run after app installation"""
    logger.info("Running post-installation tasks for Payroll Indonesia")
    setup_payroll_components()
    migrate_from_json_to_doctype()


def after_update():
    """Run after app update"""
    logger.info("Running post-update tasks for Payroll Indonesia")
    # Apply our salary slip enhancements
    from payroll_indonesia.override.salary_slip import extend_salary_slip_functionality

    extend_salary_slip_functionality()


def after_migrate():
    """Run after app migrations"""
    logger.info("Running post-migration tasks for Payroll Indonesia")
    ensure_doctypes_exist()
    migrate_from_json_to_doctype()


# Add this function to match what's referenced in hooks.py
def create_required_doctypes():
    """Create required DocTypes before migration - called from hooks.py"""
    logger.info("Creating required DocTypes for Payroll Indonesia")
    return ensure_doctypes_exist()


def ensure_doctypes_exist():
    """
    Create necessary DocTypes if they don't exist already

    Returns:
        bool: True if DocTypes were created or already existed, False on error
    """
    try:
        # Create child DocTypes first since they're needed for the main DocType
        for child_doctype in CHILD_DOCTYPES:
            doctype_name = child_doctype["name"]
            if not frappe.db.exists("DocType", doctype_name):
                logger.info(f"Creating child DocType: {doctype_name}")
                doctype = frappe.get_doc(child_doctype)
                doctype.insert(ignore_permissions=True)
                logger.info(f"Successfully created DocType: {doctype_name}")

        # Create Payroll Indonesia Settings DocType if it doesn't exist
        if not frappe.db.exists("DocType", "Payroll Indonesia Settings"):
            logger.info("Creating Payroll Indonesia Settings DocType")

            # Get the main DocType definition
            doctype_def = PAYROLL_INDONESIA_SETTINGS_DOCTYPE

            # Add child table fields (these reference the child DocTypes we created above)
            child_table_fields = [
                {
                    "fieldname": "ptkp_section",
                    "fieldtype": "Section Break",
                    "label": "PTKP Settings",
                },
                {
                    "fieldname": "ptkp_table",
                    "fieldtype": "Table",
                    "label": "PTKP Table",
                    "options": "PTKP Table Entry",
                },
                {
                    "fieldname": "ptkp_ter_mapping_section",
                    "fieldtype": "Section Break",
                    "label": "PTKP to TER Mapping",
                },
                {
                    "fieldname": "ptkp_ter_mapping_table",
                    "fieldtype": "Table",
                    "label": "PTKP to TER Mapping",
                    "options": "PTKP TER Mapping Entry",
                },
                {
                    "fieldname": "tax_brackets_section",
                    "fieldtype": "Section Break",
                    "label": "Tax Brackets",
                },
                {
                    "fieldname": "tax_brackets_table",
                    "fieldtype": "Table",
                    "label": "Tax Brackets",
                    "options": "Tax Bracket Entry",
                },
                {
                    "fieldname": "tipe_karyawan_section",
                    "fieldtype": "Section Break",
                    "label": "Tipe Karyawan",
                },
                {
                    "fieldname": "tipe_karyawan",
                    "fieldtype": "Table",
                    "label": "Tipe Karyawan",
                    "options": "Tipe Karyawan Entry",
                },
            ]

            # Append the child table fields to the main DocType definition
            doctype_def["fields"].extend(child_table_fields)

            # Create the DocType
            doctype = frappe.get_doc(doctype_def)
            doctype.insert(ignore_permissions=True)
            logger.info("Successfully created Payroll Indonesia Settings DocType")

        return True

    except Exception as e:
        logger.exception(f"Error ensuring DocTypes exist: {str(e)}")
        frappe.db.rollback()
        return False


def setup_payroll_components():
    """Set up required payroll components if missing"""
    logger.info("Setting up payroll components")

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

    try:
        for comp in components:
            if not frappe.db.exists("Salary Component", comp["name"]):
                logger.info(f"Creating salary component: {comp['name']}")
                doc = frappe.new_doc("Salary Component")
                doc.salary_component = comp["name"]
                doc.salary_component_abbr = comp["abbr"]
                doc.type = comp["type"]

                # Add optional fields
                for field in ["is_tax_applicable", "variable_based_on_taxable_salary"]:
                    if field in comp:
                        doc.set(field, comp[field])

                doc.insert(ignore_permissions=True)

        frappe.db.commit()
        logger.info("Payroll Indonesia components setup completed")
        return True
    except Exception as e:
        frappe.db.rollback()
        logger.exception(f"Error setting up payroll components: {str(e)}")
        return False


def get_default_config():
    """
    Load the default configuration from defaults.json

    Returns:
        dict: Configuration data or empty dict on error
    """
    try:
        # Try primary path
        config_path = frappe.get_app_path(
            "payroll_indonesia", "payroll_indonesia", "config", "defaults.json"
        )
        if not os.path.exists(config_path):
            # Try alternative path
            config_path = frappe.get_app_path("payroll_indonesia", "config", "defaults.json")
            if not os.path.exists(config_path):
                logger.warning("defaults.json not found at either expected location")
                return {}

        # Load the config
        with open(config_path) as f:
            return json.load(f)
    except Exception as e:
        logger.exception(f"Error loading default config: {str(e)}")
        return {}


def migrate_from_json_to_doctype():
    """
    Migrate settings from defaults.json to the Payroll Indonesia Settings DocType

    Returns:
        bool: True if migration was successful, False otherwise
    """
    try:
        # Make sure the DocType exists - create it if it doesn't
        if not frappe.db.exists("DocType", "Payroll Indonesia Settings"):
            logger.info("Payroll Indonesia Settings DocType not found, creating it now")
            if not ensure_doctypes_exist():
                logger.error(
                    "Failed to create Payroll Indonesia Settings DocType, aborting migration"
                )
                return False

        # Check if already migrated to prevent duplication
        settings_exists = frappe.db.exists(
            "Payroll Indonesia Settings", "Payroll Indonesia Settings"
        )
        if settings_exists:
            settings = frappe.get_doc("Payroll Indonesia Settings", "Payroll Indonesia Settings")
            if (
                settings.app_updated_by
                and settings.app_updated_by == "dannyaudian"
                and settings.app_version == "1.0.0"
            ):
                logger.info("Settings already migrated, skipping")
                return True

        # Load the default configuration
        config = get_default_config()
        if not config:
            logger.warning("No default configuration found, skipping migration")
            return False

        # Create or get settings document
        if settings_exists:
            logger.info("Updating existing Payroll Indonesia Settings")
            settings = frappe.get_doc("Payroll Indonesia Settings", "Payroll Indonesia Settings")
        else:
            logger.info("Creating new Payroll Indonesia Settings")
            settings = frappe.new_doc("Payroll Indonesia Settings")
            settings.name = "Payroll Indonesia Settings"

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
            settings.append(
                "ptkp_ter_mapping_table", {"ptkp_status": status, "ter_category": category}
            )

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
        settings.position_allowance_percent = flt(
            struktur_gaji.get("position_allowance_percent", 7.5)
        )
        settings.hari_kerja_default = struktur_gaji.get("hari_kerja_default", 22)

        # Tipe karyawan
        tipe_karyawan = config.get("tipe_karyawan", [])
        for tipe in tipe_karyawan:
            settings.append("tipe_karyawan", {"tipe_karyawan": tipe})

        # Save the settings with all safety flags
        settings.flags.ignore_validate = True
        settings.flags.ignore_permissions = True
        settings.flags.ignore_mandatory = True

        # Use insert or save as appropriate
        if settings_exists:
            settings.save(ignore_permissions=True)
            logger.info("Updated existing Payroll Indonesia Settings")
        else:
            settings.insert(ignore_permissions=True)
            logger.info("Created new Payroll Indonesia Settings")

        # Migrate TER rates to PPh 21 TER Table
        # This assumes PPh 21 TER Table DocType already exists
        if frappe.db.exists("DocType", "PPh 21 TER Table"):
            migrate_ter_rates(config.get("ter_rates", {}))

        frappe.db.commit()
        logger.info(
            "Successfully migrated settings from defaults.json to Payroll Indonesia Settings"
        )

        # Update BPJS Settings if it exists
        sync_to_bpjs_settings(settings)

        return True

    except Exception as e:
        frappe.db.rollback()
        logger.exception(f"Error migrating settings: {str(e)}")
        return False


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
            logger.info("Syncing settings to BPJS Settings")
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
                bpjs_settings.save(ignore_permissions=True)
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
        logger.info("Clearing existing TER table entries before migration")
        frappe.db.sql("DELETE FROM `tabPPh 21 TER Table`")

        # Process each TER category
        count = 0
        for category, rates in ter_rates.items():
            for rate_data in rates:
                try:
                    # Create TER entry
                    ter_entry = frappe.new_doc("PPh 21 TER Table")
                    ter_entry.status_pajak = category
                    ter_entry.income_from = flt(rate_data.get("income_from", 0))
                    ter_entry.income_to = flt(rate_data.get("income_to", 0))
                    ter_entry.rate = flt(rate_data.get("rate", 0))
                    ter_entry.is_highest_bracket = rate_data.get("is_highest_bracket", 0)

                    # Create description - use string formatting instead of f-strings for better compatibility
                    if rate_data.get("is_highest_bracket", 0) or rate_data.get("income_to", 0) == 0:
                        description = "{0} > {1:,.0f}".format(
                            category, flt(rate_data.get("income_from", 0))
                        )
                    else:
                        description = "{0} {1:,.0f} - {2:,.0f}".format(
                            category,
                            flt(rate_data.get("income_from", 0)),
                            flt(rate_data.get("income_to", 0)),
                        )

                    ter_entry.description = description

                    # Insert with permission bypass
                    ter_entry.flags.ignore_permissions = True
                    ter_entry.flags.ignore_validate = True
                    ter_entry.flags.ignore_mandatory = True
                    ter_entry.insert(ignore_permissions=True)
                    count += 1
                except Exception as entry_error:
                    logger.exception(f"Error creating TER entry for {category}: {str(entry_error)}")
                    continue

        frappe.db.commit()
        logger.info(f"Successfully migrated {count} TER rates from defaults.json")
        return True

    except Exception as e:
        frappe.db.rollback()
        logger.exception(f"Error migrating TER rates: {str(e)}")
        return False
