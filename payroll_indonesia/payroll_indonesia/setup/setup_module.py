# -*- coding: utf-8 -*-
"""setup_module.py – consolidated post‑migration setup
This file contains utilities for PPh 21 / TER setup.
It is hooked via **after_migrate** in hooks.py.
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
# PPh 21 / TER setup helpers
# ---------------------------------------------------------------------------


def after_sync():
    """Public hook called after app sync/migrate. Currently a placeholder."""
    debug_log("after_sync called (placeholder)", "Setup")
    # Placeholder for future implementation if needed
    pass


def after_install():
    """Hook called after app installation."""
    debug_log("Running after_install setup for Payroll Indonesia", "Setup")
    _run_pph21_setup()


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
            debug_log("TER rates missing in default config", "PPh 21 Setup")
            # Use fallback rates if default config doesn't have them
            ter_rates = {
                "TER A": [
                    {"income_from": 0, "income_to": 5000000, "rate": 5.0},
                    {"income_from": 5000000, "income_to": 0, "rate": 15.0, "is_highest_bracket": 1},
                ],
                "TER B": [
                    {"income_from": 0, "income_to": 5000000, "rate": 10.0},
                    {"income_from": 5000000, "income_to": 0, "rate": 20.0, "is_highest_bracket": 1},
                ],
                "TER C": [
                    {"income_from": 0, "income_to": 5000000, "rate": 15.0},
                    {"income_from": 5000000, "income_to": 0, "rate": 25.0, "is_highest_bracket": 1},
                ],
            }
            debug_log("Using fallback TER rates", "PPh 21 Setup")

        _create_ter_rates(ter_rates)
        frappe.db.commit()
        return True

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error during TER setup: {str(e)}", "PPh 21 Setup")
        debug_log(f"Error during TER setup: {str(e)}", "PPh 21 Setup", trace=True)
        return False


def _create_ter_rates(ter_rates: dict) -> None:
    """Create TER rate entries in the PPh 21 TER Table."""
    for status, rates in ter_rates.items():
        for row in rates:
            # Check if rate already exists to maintain idempotence
            if frappe.db.exists(
                "PPh 21 TER Table",
                {
                    "status_pajak": status,
                    "income_from": row.get("income_from", 0),
                    "income_to": row.get("income_to", 0),
                },
            ):
                debug_log(
                    f"TER rate for {status} ({row.get('income_from', 0)}-{row.get('income_to', 0)}) already exists",
                    "PPh 21 Setup",
                )
                continue

            # Create new TER rate entry
            try:
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
                debug_log(
                    f"Created TER rate for {status}: {row.get('income_from', 0)}-{row.get('income_to', 0)} at {row.get('rate', 0)}%",
                    "PPh 21 Setup",
                )
            except Exception as e:
                debug_log(f"Error creating TER rate for {status}: {str(e)}", "PPh 21 Setup Error")
                frappe.log_error(
                    f"Error creating TER rate for {status}: {str(e)}", "PPh 21 Setup Error"
                )


def _build_description(status: str, row: dict) -> str:
    """Build a descriptive label for TER rate entries."""
    inc_from = flt(row.get("income_from", 0))
    inc_to = flt(row.get("income_to", 0))
    if row.get("is_highest_bracket") or inc_to == 0:
        return "{} > {:,.0f}".format(status, inc_from)
    return "{} {:,.0f} – {:,.0f}".format(status, inc_from, inc_to)
