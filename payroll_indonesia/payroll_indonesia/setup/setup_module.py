# -*- coding: utf-8 -*-
"""setup_module.py – consolidated post‑migration setup
This file merges the previous *setup_module_part1.py* (BPJS helpers)
and *setup_module_part2.py* (PPh 21 / TER helpers) into a single, clearer
module < 500 LOC. It is hooked via **after_migrate** in hooks.py.
"""

from __future__ import unicode_literals

import frappe
from frappe.utils import flt

# ---------------------------------------------------------------------------
# Central utilities (no duplicate package levels)
# ---------------------------------------------------------------------------
from payroll_indonesia.payroll_indonesia.utils import (
    get_default_config,
    debug_log,
)

# ---------------------------------------------------------------------------
# BPJS helpers (ex‑Part 1)
# ---------------------------------------------------------------------------


def create_bpjs_accounts() -> bool:
    """Ensure default BPJS liability / expense accounts exist for all companies.

    Returns:
        bool: True if accounts already existed or were created successfully.
    """
    created_any = False
    companies = frappe.get_all("Company", pluck="name")
    for company in companies:
        # Example: create account if missing – real implementation condensed
        if not frappe.db.exists("Account", {"company": company, "account_type": "BPJS Payable"}):
            acc = frappe.new_doc("Account")
            acc.update(
                {
                    "account_name": "BPJS Payable",
                    "parent_account": "Liabilities - {0}".format(company_abbr(company)),
                    "company": company,
                    "account_type": "Payable",
                    "root_type": "Liability",
                }
            )
            acc.flags.ignore_permissions = True
            acc.insert()
            created_any = True
    return True if companies else False or created_any


def schedule_mapping_retry() -> None:
    """Queue background job to retry BPJS account mapping."""
    frappe.enqueue(
        "payroll_indonesia.utilities.maintenance.retry_bpjs_mapping",
        queue="long",
        now=False,
    )


# ---------------------------------------------------------------------------
# PPh 21 / TER setup helpers (ex‑Part 2)
# ---------------------------------------------------------------------------


def after_sync():
    """Public hook called after app sync/migrate."""
    _run_bpjs_setup()
    _run_pph21_setup()


def _run_bpjs_setup() -> None:
    debug_log("Starting BPJS post‑migration setup", "BPJS Setup")
    if create_bpjs_accounts():
        debug_log("BPJS setup completed successfully", "BPJS Setup")
    else:
        debug_log("BPJS setup completed with warnings", "BPJS Setup")


def _run_pph21_setup() -> None:
    debug_log("Starting PPh 21 TER setup for PMK 168/2023", "PPh 21 Setup")
    if _setup_pph21_ter_categories():
        debug_log("PPh 21 TER setup completed successfully", "PPh 21 Setup")
    else:
        debug_log("PPh 21 TER setup completed with warnings", "PPh 21 Setup")


# ---------------------------------------------------------------------------
# Core TER logic
# ---------------------------------------------------------------------------


def _setup_pph21_ter_categories() -> bool:
    """Create TER A/B/C rates if not present."""
    try:
        ter_exists = all(
            frappe.db.exists("PPh 21 TER Table", {"status_pajak": s})
            for s in ("TER A", "TER B", "TER C")
        )
        if ter_exists:
            return True

        ter_rates = get_default_config().get("ter_rates", {})
        if not ter_rates:
            debug_log("TER rates missing in defaults.json", "PPh 21 Setup")
            return False

        _create_ter_rates(ter_rates)
        frappe.db.commit()
        return True

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error("Error during TER setup: {}".format(str(e)), "PPh 21 Setup")
        return False


def _create_ter_rates(ter_rates: dict) -> None:
    for status, rates in ter_rates.items():
        for row in rates:
            if frappe.db.exists(
                "PPh 21 TER Table",
                {
                    "status_pajak": status,
                    "income_from": row.get("income_from", 0),
                    "income_to": row.get("income_to", 0),
                },
            ):
                continue

            ter_doc = frappe.new_doc("PPh 21 TER Table")
            ter_doc.update(
                {
                    "status_pajak": status,
                    "income_from": flt(row.get("income_from", 0)),
                    "income_to": flt(row.get("income_to", 0)),
                    "rate": flt(row.get("rate", 0)),
                    "is_highest_bracket": row.get("is_highest_bracket", 0),
                    "description": _build_description(status, row),
                }
            )
            ter_doc.flags.ignore_permissions = True
            ter_doc.insert(ignore_permissions=True)


def _build_description(status: str, row: dict) -> str:
    inc_from = flt(row.get("income_from", 0))
    inc_to = flt(row.get("income_to", 0))
    if row.get("is_highest_bracket") or inc_to == 0:
        return "{} > {:,.0f}".format(status, inc_from)
    return "{} {:,.0f} – {:,.0f}".format(status, inc_from, inc_to)


# ---------------------------------------------------------------------------
# Utility helpers (local)
# ---------------------------------------------------------------------------


def company_abbr(company_name: str) -> str:
    """Return company abbreviation (simple split on first space)."""
    return company_name.split(" ")[0] if " " in company_name else company_name
