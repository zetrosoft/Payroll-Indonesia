# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-04 01:41:20 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

# Import functions from tax_slab.py to avoid duplication
from payroll_indonesia.utilities.tax_slab import (
    create_income_tax_slab,
    get_default_tax_slab,
    update_salary_structures as update_structures,
    update_existing_assignments as update_assignments,
)

__all__ = [
    "update_salary_structures",
    "update_existing_assignments",
    "check_salary_structure_tax_method",
    "check_salary_structure_assignments",
    "fix_all_salary_structures_and_assignments",
    "diagnose_salary_structures",
]


def update_salary_structures():
    """
    Update all Salary Structures to bypass Income Tax Slab validation

    Uses the implementation from tax_slab.py with console output for interactive use.

    Returns:
        int: Number of successfully updated structures
    """
    # Use the function from tax_slab.py that has better logging and error handling
    count = update_structures()

    # Additional console output for interactive use
    if count:
        print(f"Successfully updated {count} Salary Structures")
    else:
        print("No Salary Structures were updated")

    return count


def update_existing_assignments():
    """
    Update existing Salary Structure Assignments with default Income Tax Slab

    Uses the implementation from tax_slab.py with console output for interactive use.

    Returns:
        int: Number of successfully updated assignments
    """
    # Use the function from tax_slab.py that has better logging and error handling
    count = update_assignments()

    # Additional console output for interactive use
    if count:
        print(f"Successfully updated {count} Salary Structure Assignments")
    else:
        print("No Salary Structure Assignments were updated")

    return count


def check_salary_structure_tax_method():
    """
    Check tax calculation method in Salary Structures

    Returns:
        list: List of Salary Structures with their tax methods
    """
    structures = frappe.get_all(
        "Salary Structure",
        filters={"is_active": "Yes"},
        fields=["name", "tax_calculation_method", "income_tax_slab"],
    )

    print(f"\nFound {len(structures)} active Salary Structures:")
    for idx, ss in enumerate(structures, 1):
        print(f"{idx}. {ss.name}")
        print(f"   - Tax Calculation Method: {ss.tax_calculation_method or 'None'}")
        print(f"   - Income Tax Slab: {ss.income_tax_slab or 'None'}")
        print()

    return structures


def check_salary_structure_assignments():
    """
    Check all Salary Structure Assignments

    Returns:
        list: List of Salary Structure Assignments
    """
    assignments = frappe.get_all(
        "Salary Structure Assignment",
        filters={"docstatus": 1},
        fields=["name", "employee", "employee_name", "salary_structure", "income_tax_slab"],
    )

    print(f"\nFound {len(assignments)} Salary Structure Assignments:")
    for idx, ssa in enumerate(assignments, 1):
        print(f"{idx}. {ssa.name}")
        print(f"   - Employee: {ssa.employee} ({ssa.employee_name})")
        print(f"   - Salary Structure: {ssa.salary_structure}")
        print(f"   - Income Tax Slab: {ssa.income_tax_slab or 'None'}")
        print()

    return assignments


def fix_all_salary_structures_and_assignments():
    """
    Fix all Salary Structures and Assignments at once

    This function:
    1. Creates a default Income Tax Slab if none exists
    2. Updates all Salary Structures with the default slab
    3. Updates all Salary Structure Assignments with the default slab

    Returns:
        bool: True if successful, False otherwise
    """
    timestamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Starting comprehensive fix for Salary Structures and Assignments...")

    # Step 1: Create or get default Income Tax Slab
    tax_slab_name = get_default_tax_slab()
    if not tax_slab_name:
        print("Failed to get or create default Income Tax Slab.")
        return False

    print(f"[{timestamp}] Using Income Tax Slab: {tax_slab_name}")

    # Step 2: Update all Salary Structures
    print(f"[{timestamp}] Updating Salary Structures...")
    ss_count = update_salary_structures()

    # Step 3: Update all Salary Structure Assignments
    print(f"[{timestamp}] Updating Salary Structure Assignments...")
    ssa_count = update_existing_assignments()

    # Summary
    print(f"\n[{timestamp}] Fix process completed:")
    print(f"- Income Tax Slab: {tax_slab_name}")
    print(f"- Salary Structures updated: {ss_count}")
    print(f"- Salary Structure Assignments updated: {ssa_count}")

    return True


def diagnose_salary_structures():
    """
    Diagnose issues with Salary Structures and Assignments

    Returns:
        dict: Diagnostic information
    """
    try:
        results = {
            "tax_slab_exists": False,
            "structures": {"total": 0, "with_tax_slab": 0, "with_manual_method": 0, "issues": []},
            "assignments": {"total": 0, "with_tax_slab": 0, "issues": []},
        }

        # Check for default tax slab
        default_slab = get_default_tax_slab()
        if default_slab:
            results["tax_slab_exists"] = True
            results["default_tax_slab"] = default_slab
        else:
            results["issues"] = ["No default Income Tax Slab found"]

        # Check Salary Structures
        structures = frappe.get_all(
            "Salary Structure",
            filters={"is_active": "Yes"},
            fields=["name", "tax_calculation_method", "income_tax_slab"],
        )

        results["structures"]["total"] = len(structures)

        for ss in structures:
            if ss.income_tax_slab:
                results["structures"]["with_tax_slab"] += 1

            if ss.tax_calculation_method == "Manual":
                results["structures"]["with_manual_method"] += 1

            if not ss.income_tax_slab or ss.tax_calculation_method != "Manual":
                results["structures"]["issues"].append(
                    {
                        "name": ss.name,
                        "tax_calculation_method": ss.tax_calculation_method,
                        "income_tax_slab": ss.income_tax_slab,
                    }
                )

        # Check Salary Structure Assignments
        assignments = frappe.get_all(
            "Salary Structure Assignment",
            filters={"docstatus": 1},
            fields=["name", "employee", "employee_name", "income_tax_slab"],
        )

        results["assignments"]["total"] = len(assignments)

        for ssa in assignments:
            if ssa.income_tax_slab:
                results["assignments"]["with_tax_slab"] += 1
            else:
                results["assignments"]["issues"].append(
                    {"name": ssa.name, "employee": ssa.employee, "employee_name": ssa.employee_name}
                )

        # Print summary
        print("\nSalary Structure Diagnosis:")
        print(f"- Default Tax Slab: {default_slab or 'None'}")
        print(
            f"- Salary Structures: {results['structures']['total']} total, {results['structures']['with_tax_slab']} with tax slab, {results['structures']['with_manual_method']} with manual method"
        )
        print(
            f"- Assignments: {results['assignments']['total']} total, {results['assignments']['with_tax_slab']} with tax slab"
        )

        if results["structures"]["issues"]:
            print(f"- {len(results['structures']['issues'])} structures with issues")

        if results["assignments"]["issues"]:
            print(f"- {len(results['assignments']['issues'])} assignments with issues")

        return results

    except Exception as e:
        frappe.log_error(f"Error diagnosing salary structures: {str(e)}", "Maintenance Error")
        print(f"Error diagnosing salary structures: {str(e)}")
        return {"error": str(e)}
