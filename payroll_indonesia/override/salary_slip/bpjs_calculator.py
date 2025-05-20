# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-20 09:58:16 by dannyaudian

from typing import Any, Dict
import logging

import frappe
from frappe import _
from frappe.utils import flt

from .base import update_component_amount

# Import functions from bpjs_calculation.py - centralized BPJS logic
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import (
    hitung_bpjs,
    check_bpjs_enrollment,
)

# Define exports for proper importing by other modules
__all__ = ["calculate_bpjs_components"]

# Type aliases
SalarySlipDoc = Any  # frappe.model.document.Document type for Salary Slip
EmployeeDoc = Any  # frappe.model.document.Document type for Employee


def get_logger() -> logging.Logger:
    """Get properly configured logger for BPJS calculator module."""
    return frappe.logger("bpjs_calculator", with_more_info=True)


def calculate_bpjs_components(slip: SalarySlipDoc) -> None:
    """
    Calculate and update BPJS components in salary slip.

    This function is a wrapper around the centralized BPJS calculation logic
    that handles integration with Salary Slip documents including:
    - Calling the core calculation function
    - Updating salary component deduction entries
    - Adding explanatory notes
    - Verifying components were properly added

    Args:
        slip: Salary slip document to update with BPJS components
    """
    logger = get_logger()

    # Check for required fields
    if not hasattr(slip, "employee") or not slip.employee:
        logger.exception("Salary slip missing employee field")
        frappe.throw(_("Employee field is required to calculate BPJS"))
        return

    # Get employee document
    try:
        employee = frappe.get_doc("Employee", slip.employee)
    except Exception as e:
        logger.exception(f"Error retrieving employee {slip.employee}: {e}")
        frappe.throw(_("Could not retrieve employee data for BPJS calculation"))
        return

    # Get employee info for logging
    employee_info = f"{employee.name}"
    if hasattr(employee, "employee_name") and employee.employee_name:
        employee_info += f" ({employee.employee_name})"

    # Get base salary for BPJS calculation
    base_salary = _get_base_salary_for_bpjs(slip)

    try:
        # Check if employee is enrolled in any BPJS program
        bpjs_config = check_bpjs_enrollment(employee)

        if not bpjs_config:
            # Non-critical information - log but continue
            logger.info(
                f"Employee {employee_info} not enrolled in any BPJS program - skipping calculation"
            )

            # Initialize total_bpjs to 0 to avoid NoneType errors
            if hasattr(slip, "total_bpjs"):
                slip.total_bpjs = 0
                slip.db_set("total_bpjs", 0, update_modified=False)

            return

        # Calculate BPJS values using the centralized function
        # Pass the slip document directly so it can update custom fields
        bpjs_values = hitung_bpjs(employee, base_salary, doc=slip)

        # If no contributions calculated, initialize fields and return
        if bpjs_values["total_employee"] <= 0:
            logger.info(
                f"No BPJS contributions calculated for {employee_info}. Check BPJS settings."
            )

            # Initialize total_bpjs to 0 to avoid NoneType errors
            if hasattr(slip, "total_bpjs"):
                slip.total_bpjs = 0
                slip.db_set("total_bpjs", 0, update_modified=False)

            return

        # Log that we're updating components
        logger.info(
            f"Updating BPJS components in salary slip {slip.name if hasattr(slip, 'name') else 'New'}"
        )

        # Update salary components in deductions table
        _update_deduction_components(slip, bpjs_values)

        # Add BPJS details to payroll note
        add_bpjs_info_to_note(slip, bpjs_values)

        # Verify the components were properly added
        verify_bpjs_components(slip)

        logger.info(
            f"BPJS components calculation completed for {slip.name if hasattr(slip, 'name') else 'New'}"
        )

    except Exception as e:
        # BPJS calculation can continue with default values - log error and show warning
        logger.exception(f"Error calculating BPJS for {employee_info}: {e}")

        # Initialize total_bpjs to 0 to avoid NoneType errors in tax calculations
        if hasattr(slip, "total_bpjs"):
            slip.total_bpjs = 0
            slip.db_set("total_bpjs", 0, update_modified=False)

        # Show warning to user but continue processing
        frappe.msgprint(
            _("Warning: Error in BPJS calculation. Using zero values as fallback."),
            indicator="orange",
        )


def _get_base_salary_for_bpjs(slip: SalarySlipDoc) -> float:
    """
    Get the base salary amount to use for BPJS calculations.

    Uses gross pay or falls back to a configured default.

    Args:
        slip: Salary slip document

    Returns:
        float: Salary amount to use for BPJS calculations
    """
    from payroll_indonesia.constants import DEFAULT_UMR

    try:
        # Use gross pay as the default base for BPJS
        base_salary = slip.gross_pay if hasattr(slip, "gross_pay") and slip.gross_pay else 0

        # If no gross pay, try to calculate from earnings
        if not base_salary and hasattr(slip, "earnings"):
            for earning in slip.earnings:
                if earning.salary_component == "Gaji Pokok":
                    base_salary += earning.amount

        # If still no base salary, use default UMR
        if not base_salary:
            base_salary = DEFAULT_UMR
            get_logger().info(
                f"No base salary found for {slip.name}. Using default UMR: {DEFAULT_UMR}"
            )

        # Log the base salary used
        if hasattr(slip, "add_payroll_note"):
            slip.add_payroll_note(f"Base salary for BPJS: {base_salary}")

        return flt(base_salary)
    except Exception as e:
        # Non-critical error - log and return default UMR
        get_logger().exception(f"Error calculating base salary for BPJS: {e}")
        return DEFAULT_UMR


def _update_deduction_components(slip: SalarySlipDoc, bpjs_values: Dict[str, float]) -> None:
    """
    Update BPJS components in salary slip deductions table.

    Args:
        slip: Salary slip document
        bpjs_values: BPJS calculation results
    """
    # Define component mappings
    components = [
        ("BPJS Kesehatan Employee", "kesehatan_employee"),
        ("BPJS JHT Employee", "jht_employee"),
        ("BPJS JP Employee", "jp_employee"),
    ]

    # Update each component in deductions table
    for component_name, value_key in components:
        if bpjs_values[value_key] > 0:
            update_component_amount(slip, component_name, bpjs_values[value_key], "deductions")


def verify_bpjs_components(slip: SalarySlipDoc) -> Dict[str, Any]:
    """
    Verify that BPJS components in the salary slip are correct.

    Args:
        slip: Salary slip document

    Returns:
        Dict[str, Any]: Verification results
    """
    logger = get_logger()

    # Initialize result
    result = {
        "all_zero": True,
        "kesehatan_found": False,
        "jht_found": False,
        "jp_found": False,
        "total": 0,
    }

    try:
        # Debug log at start of verification
        logger.debug(f"Starting BPJS verification for slip {getattr(slip, 'name', 'unknown')}")

        # Check for BPJS components in deductions
        if not hasattr(slip, "deductions") or not slip.deductions:
            logger.info(f"No deductions found in slip {getattr(slip, 'name', 'unknown')}")
            return result

        # Check each deduction component
        for deduction in slip.deductions:
            if deduction.salary_component == "BPJS Kesehatan Employee":
                result["kesehatan_found"] = True
                if flt(deduction.amount) > 0:
                    result["all_zero"] = False
                result["total"] += flt(deduction.amount)

                # Ensure custom field is consistent with deduction
                if hasattr(slip, "kesehatan_employee"):
                    slip.kesehatan_employee = flt(deduction.amount)
                    slip.db_set("kesehatan_employee", flt(deduction.amount), update_modified=False)

            elif deduction.salary_component == "BPJS JHT Employee":
                result["jht_found"] = True
                if flt(deduction.amount) > 0:
                    result["all_zero"] = False
                result["total"] += flt(deduction.amount)

                # Ensure custom field is consistent with deduction
                if hasattr(slip, "jht_employee"):
                    slip.jht_employee = flt(deduction.amount)
                    slip.db_set("jht_employee", flt(deduction.amount), update_modified=False)

            elif deduction.salary_component == "BPJS JP Employee":
                result["jp_found"] = True
                if flt(deduction.amount) > 0:
                    result["all_zero"] = False
                result["total"] += flt(deduction.amount)

                # Ensure custom field is consistent with deduction
                if hasattr(slip, "jp_employee"):
                    slip.jp_employee = flt(deduction.amount)
                    slip.db_set("jp_employee", flt(deduction.amount), update_modified=False)

        # Update doc.total_bpjs to ensure consistency
        if hasattr(slip, "total_bpjs"):
            slip.total_bpjs = result["total"]
            slip.db_set("total_bpjs", result["total"], update_modified=False)

        # Log verification results
        logger.debug(
            f"BPJS verification complete: kesehatan={result['kesehatan_found']}, "
            f"jht={result['jht_found']}, jp={result['jp_found']}, total={result['total']}"
        )

        return result

    except Exception as e:
        # Non-critical verification error - log and return default result
        logger.exception(f"Error verifying BPJS components: {e}")
        frappe.msgprint(_("Warning: Could not verify BPJS components."), indicator="orange")
        # Return default result on error
        return result


def add_bpjs_info_to_note(slip: SalarySlipDoc, bpjs_values: Dict[str, float]) -> None:
    """
    Add BPJS calculation details to payroll note with duplication check.

    Args:
        slip: Salary slip document
        bpjs_values: BPJS calculation results
    """
    try:
        # Initialize payroll_note if needed
        if not hasattr(slip, "payroll_note"):
            slip.payroll_note = ""
        elif slip.payroll_note is None:
            slip.payroll_note = ""

        # Check if BPJS calculation section already exists
        if "=== BPJS Calculation ===" in slip.payroll_note:
            return

        # Add BPJS calculation details with section markers
        slip.payroll_note += "\n\n<!-- BPJS_CALCULATION_START -->\n"
        slip.payroll_note += "=== BPJS Calculation ===\n"

        # Only add components with values
        if bpjs_values["kesehatan_employee"] > 0:
            slip.payroll_note += (
                f"BPJS Kesehatan: Rp {flt(bpjs_values['kesehatan_employee']):,.0f}\n"
            )

        if bpjs_values["jht_employee"] > 0:
            slip.payroll_note += f"BPJS JHT: Rp {flt(bpjs_values['jht_employee']):,.0f}\n"

        if bpjs_values["jp_employee"] > 0:
            slip.payroll_note += f"BPJS JP: Rp {flt(bpjs_values['jp_employee']):,.0f}\n"

        # Add total
        slip.payroll_note += f"Total BPJS: Rp {flt(bpjs_values['total_employee']):,.0f}\n"
        slip.payroll_note += "<!-- BPJS_CALCULATION_END -->\n"

        # Update payroll_note field
        slip.db_set("payroll_note", slip.payroll_note, update_modified=False)

    except Exception as e:
        # Non-critical error - log and continue
        get_logger().exception(f"Error adding BPJS info to note: {e}")
