# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-19 08:17:45 by dannyaudian

import frappe
from payroll_indonesia.constants import (
    TER_CATEGORY_A, TER_CATEGORY_B, TER_CATEGORY_C, TER_CATEGORIES
)

# Default rates (in decimal)
DEFAULT_TER_RATES = {
    TER_CATEGORY_A: 0.05,
    TER_CATEGORY_B: 0.15,
    TER_CATEGORY_C: 0.25,
    "": 0.25,
}

def get_ter_rate(category: str, status_pajak: str = None) -> float:
    category = (category or "").strip().upper()
    if category in ["A", "B", "C"]:
        category = f"TER {category}"
    elif not category.startswith("TER "):
        category = TER_CATEGORY_C

    if category not in TER_CATEGORIES:
        category = TER_CATEGORY_C

    try:
        rate = frappe.db.get_value(
            "PPh 21 TER Table",
            filters={
                "category": category,
                "status_pajak": status_pajak,
                "is_highest_bracket": 1
            },
            fieldname="rate"
        )
        if rate is not None:
            return float(rate) / 100.0
    except Exception:
        pass

    return DEFAULT_TER_RATES.get(category, 0.25)

def validate_ter_data_availability() -> list:
    if not frappe.db.table_exists("PPh 21 TER Table"):
        return ["Tabel 'PPh 21 TER Table' tidak ditemukan."]

    issues = []
    for category in TER_CATEGORIES:
        total = frappe.db.count("PPh 21 TER Table", {"category": category})
        if total == 0:
            issues.append(f"Tidak ada entri untuk kategori {category}.")

        highest = frappe.db.count("PPh 21 TER Table", {
            "category": category,
            "is_highest_bracket": 1
        })
        if highest == 0:
            issues.append(f"Tidak ada bracket tertinggi (is_highest_bracket=1) untuk {category}.")

    return issues
