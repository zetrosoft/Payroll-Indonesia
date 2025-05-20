# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last updated: 2025-05-20 09:53:57 by dannyaudian

from functools import lru_cache
from typing import Dict, Union, Optional, Any, TypedDict, cast
import logging

import frappe
from frappe import _
from frappe.utils import flt, cint

from payroll_indonesia.payroll_indonesia.utils import get_bpjs_settings

# Import constants
from payroll_indonesia.constants import (
    DEFAULT_UMR,
    DEFAULT_BPJS_RATES,
    BPJS_KESEHATAN_EMPLOYEE_PERCENT,
    BPJS_KESEHATAN_EMPLOYER_PERCENT,
    BPJS_KESEHATAN_MAX_SALARY,
    BPJS_JHT_EMPLOYEE_PERCENT,
    BPJS_JHT_EMPLOYER_PERCENT,
    BPJS_JP_EMPLOYEE_PERCENT,
    BPJS_JP_EMPLOYER_PERCENT,
    BPJS_JP_MAX_SALARY,
    BPJS_JKK_PERCENT,
    BPJS_JKM_PERCENT,
)

# Define exports for proper importing by other modules
__all__ = ["hitung_bpjs", "get_bpjs_enrollment_status", "check_bpjs_enrollment"]

# Define types for type hinting
EmployeeDoc = Any  # frappe.model.document.Document type for Employee
SalarySlipDoc = Any  # frappe.model.document.Document type for Salary Slip

# Define CURRENCY_PRECISION constant
# Using standard Indonesian Rupiah precision (0 decimal places)
CURRENCY_PRECISION = 0

# Try to import from constants.py if available
try:
    from payroll_indonesia.constants import CURRENCY_PRECISION as IMPORTED_PRECISION

    CURRENCY_PRECISION = IMPORTED_PRECISION
except ImportError:
    # Keep default value if import fails
    pass


class BPJSResult(TypedDict):
    """Type definition for BPJS calculation result."""

    kesehatan_employee: float
    kesehatan_employer: float
    jht_employee: float
    jht_employer: float
    jp_employee: float
    jp_employer: float
    jkk_employer: float
    jkm_employer: float
    total_employee: float
    total_employer: float


def get_logger() -> logging.Logger:
    """Get properly configured logger for BPJS module."""
    return frappe.logger("bpjs", with_more_info=True)


@lru_cache(maxsize=128)
def check_bpjs_enrollment(employee_doc: Union[str, Dict, EmployeeDoc]) -> Dict[str, Any]:
    """
    Check if employee is enrolled in BPJS programs.

    Args:
        employee_doc: Employee document, dictionary, or employee ID

    Returns:
        dict: Configuration dictionary based on enrollment status

    Note:
        This is the authoritative implementation of check_bpjs_enrollment.
        Other files should use this function directly to ensure consistency.
    """
    logger = get_logger()

    # Get BPJS settings with safe defaults
    settings = get_bpjs_settings() or DEFAULT_BPJS_RATES
    config: Dict[str, Any] = {}

    try:
        # Handle different input types safely
        is_dict = isinstance(employee_doc, dict)
        emp_doc = employee_doc

        # If employee_doc is a string (employee ID), convert to document
        if isinstance(employee_doc, str):
            try:
                emp_doc = frappe.get_doc("Employee", employee_doc)
                is_dict = False
            except Exception as e:
                logger.exception(f"Error getting employee document for ID {employee_doc}: {e}")
                # Continue with empty employee_doc, will use defaults

        # Get enrollment status with safe defaults (default to enrolled if fields missing)
        if is_dict:
            emp_dict = cast(Dict[str, Any], emp_doc)
            kesehatan_enrolled = cint(emp_dict.get("ikut_bpjs_kesehatan", 1))
            ketenagakerjaan_enrolled = cint(emp_dict.get("ikut_bpjs_ketenagakerjaan", 1))

            # Check if BPJS IDs are present
            kesehatan_id = emp_dict.get("bpjs_kesehatan_id", "")
            ketenagakerjaan_id = emp_dict.get("bpjs_ketenagakerjaan_id", "")
            employee_name = emp_dict.get("name", "unknown")
        else:
            emp_obj = cast(EmployeeDoc, emp_doc)
            kesehatan_enrolled = cint(getattr(emp_obj, "ikut_bpjs_kesehatan", 1))
            ketenagakerjaan_enrolled = cint(getattr(emp_obj, "ikut_bpjs_ketenagakerjaan", 1))

            # Check if BPJS IDs are present
            kesehatan_id = getattr(emp_obj, "bpjs_kesehatan_id", "")
            ketenagakerjaan_id = getattr(emp_obj, "bpjs_ketenagakerjaan_id", "")
            employee_name = getattr(emp_obj, "name", str(emp_obj))

        # Log enrollment status for debugging
        logger.info(
            f"BPJS enrollment status for {employee_name}: "
            f"Kesehatan={kesehatan_enrolled}, Ketenagakerjaan={ketenagakerjaan_enrolled}"
        )

        # Warn if enrolled but missing ID
        if kesehatan_enrolled and not kesehatan_id:
            logger.info(f"Employee {employee_name} enrolled in BPJS Kesehatan but missing ID")

        if ketenagakerjaan_enrolled and not ketenagakerjaan_id:
            logger.info(f"Employee {employee_name} enrolled in BPJS Ketenagakerjaan but missing ID")

        # Configure BPJS Kesehatan if enrolled
        if kesehatan_enrolled:
            config["kesehatan"] = {
                "employee_percent": settings.get(
                    "kesehatan_employee_percent", BPJS_KESEHATAN_EMPLOYEE_PERCENT
                ),
                "employer_percent": settings.get(
                    "kesehatan_employer_percent", BPJS_KESEHATAN_EMPLOYER_PERCENT
                ),
                "max_salary": settings.get("kesehatan_max_salary", BPJS_KESEHATAN_MAX_SALARY),
                "id": kesehatan_id,
            }
            logger.info(f"Added BPJS Kesehatan config for {employee_name}")

        # Configure BPJS Ketenagakerjaan components if enrolled
        if ketenagakerjaan_enrolled:
            config["jht"] = {
                "employee_percent": settings.get("jht_employee_percent", BPJS_JHT_EMPLOYEE_PERCENT),
                "employer_percent": settings.get("jht_employer_percent", BPJS_JHT_EMPLOYER_PERCENT),
                "id": ketenagakerjaan_id,
            }
            logger.info(f"Added BPJS JHT config for {employee_name}")

            config["jp"] = {
                "employee_percent": settings.get("jp_employee_percent", BPJS_JP_EMPLOYEE_PERCENT),
                "employer_percent": settings.get("jp_employer_percent", BPJS_JP_EMPLOYER_PERCENT),
                "max_salary": settings.get("jp_max_salary", BPJS_JP_MAX_SALARY),
                "id": ketenagakerjaan_id,
            }
            logger.info(f"Added BPJS JP config for {employee_name}")

            config["jkk"] = {
                "percent": settings.get("jkk_percent", BPJS_JKK_PERCENT),
                "id": ketenagakerjaan_id,
            }
            config["jkm"] = {
                "percent": settings.get("jkm_percent", BPJS_JKM_PERCENT),
                "id": ketenagakerjaan_id,
            }
            logger.info(f"Added BPJS JKK and JKM config for {employee_name}")

        # Log final enrollment status
        is_enrolled = bool(config)
        logger.info(
            f"Final enrollment status for {employee_name}: "
            f"{is_enrolled} with {len(config)} programs"
        )

    except Exception as e:
        logger.exception(f"Error checking BPJS enrollment: {e}")
        # In case of error, return empty config which means not enrolled

    return config


def get_bpjs_enrollment_status(employee: Union[str, Dict, EmployeeDoc]) -> bool:
    """
    Get simple boolean enrollment status for an employee.

    Args:
        employee: Employee document, dict or ID

    Returns:
        bool: True if enrolled in any BPJS program, False otherwise
    """
    config = check_bpjs_enrollment(employee)
    is_enrolled = bool(config and len(config) > 0)

    # Get employee name for logging
    if isinstance(employee, str):
        employee_name = employee
    elif isinstance(employee, dict) and "name" in employee:
        employee_name = employee["name"]
    elif hasattr(employee, "name"):
        employee_name = employee.name
    else:
        employee_name = "unknown"

    logger = get_logger()
    logger.info(
        f"Employee {employee_name} BPJS enrollment status: "
        f"{is_enrolled}, enrolled in {len(config) if config else 0} programs"
    )

    return is_enrolled


@lru_cache(maxsize=128)
def _get_bpjs_settings() -> Dict[str, Any]:
    """
    Get BPJS settings with caching for performance.

    Returns:
        Dict[str, Any]: BPJS settings or default rates
    """
    try:
        settings = frappe.get_cached_doc("BPJS Settings", "BPJS Settings")
        if not settings:
            get_logger().info("BPJS Settings not found, using defaults")
            return DEFAULT_BPJS_RATES
        return settings
    except Exception as e:
        get_logger().exception(f"Error getting BPJS Settings: {e}. Using defaults.")
        return DEFAULT_BPJS_RATES


def _update_doc_fields(doc: SalarySlipDoc, bpjs_values: BPJSResult) -> None:
    """
    Update BPJS-related fields in salary slip document.

    Args:
        doc: Salary slip document
        bpjs_values: BPJS calculation results
    """
    fields_to_update = ["kesehatan_employee", "jht_employee", "jp_employee", "total_bpjs"]

    # Set values using both direct attribute and db_set for persistence
    for field in fields_to_update:
        if hasattr(doc, field) and field in bpjs_values:
            setattr(doc, field, bpjs_values[field])
            try:
                doc.db_set(field, bpjs_values[field], update_modified=False)
            except Exception as e:
                get_logger().exception(f"Error updating field {field} via db_set: {e}")


def hitung_bpjs(
    employee: Union[str, Dict, EmployeeDoc],
    base_salary: float = 0,
    *,
    doc: Optional[SalarySlipDoc] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> BPJSResult:
    """
    Calculate BPJS contributions for given employee and salary.

    If a doc (Salary Slip) is provided, updates its fields with the calculated values.

    Args:
        employee: Employee ID or document
        base_salary: Base salary amount for calculation
        doc: Optional Salary Slip document to update with calculated values
        settings: Optional BPJS Settings doc (for custom processing)

    Returns:
        Dict[str, float]: Dictionary with calculated BPJS amounts
    """
    logger = get_logger()

    # Initialize result with zeros to avoid None values
    result: BPJSResult = {
        "kesehatan_employee": 0,
        "kesehatan_employer": 0,
        "jht_employee": 0,
        "jht_employer": 0,
        "jp_employee": 0,
        "jp_employer": 0,
        "jkk_employer": 0,
        "jkm_employer": 0,
        "total_employee": 0,
        "total_employer": 0,
    }

    try:
        # Extract employee info for logging
        employee_info = ""
        if isinstance(employee, str):
            employee_info = employee
        elif isinstance(employee, dict) and "name" in employee:
            employee_info = employee["name"]
        elif hasattr(employee, "name"):
            employee_info = employee.name

        # Validate inputs with enhanced flexibility
        if isinstance(employee, str):
            try:
                # If employee is an ID, get employee document
                emp_doc = frappe.get_doc("Employee", employee)
                if not emp_doc:
                    logger.info(f"Employee {employee} not found")
                    return result
            except Exception as e:
                logger.exception(f"Error getting employee {employee}: {e}")
                return result
        elif isinstance(employee, dict) or hasattr(employee, "name"):
            # If employee is already a document or dict, use it
            emp_doc = employee
        else:
            logger.exception(f"Invalid employee parameter type: {type(employee)}")
            return result

        # Basic salary validation with a fallback mechanism
        if not base_salary or base_salary <= 0:
            logger.info(
                f"Invalid base salary: {base_salary} for employee {employee_info}. "
                f"Attempting to use gross_pay or default UMR."
            )

            # Try to get salary from employee document if available
            if hasattr(emp_doc, "gross_salary") and emp_doc.gross_salary > 0:
                base_salary = flt(emp_doc.gross_salary)
                logger.info(f"Using employee gross salary as base: {base_salary}")
            else:
                # Use default UMR (minimum wage as safe default)
                base_salary = DEFAULT_UMR
                logger.info(f"Using default UMR as base salary: {base_salary}")

        logger.info(f"Using final base salary: {base_salary}")

        # Get BPJS settings if not provided, with caching
        if not settings:
            settings = _get_bpjs_settings()

        # Get configuration based on enrollment status
        config = check_bpjs_enrollment(emp_doc)

        # If no config (not enrolled in any program), return zeros
        if not config:
            logger.info(f"Employee {employee_info} not participating in any BPJS program")
            return result

        # Calculate BPJS Kesehatan if enrolled
        if "kesehatan" in config:
            # Apply salary cap
            max_kesehatan = flt(config["kesehatan"].get("max_salary", base_salary))
            kesehatan_salary = min(base_salary, max_kesehatan)

            # Calculate contributions
            result["kesehatan_employee"] = flt(
                kesehatan_salary * config["kesehatan"]["employee_percent"] / 100
            )
            result["kesehatan_employer"] = flt(
                kesehatan_salary * config["kesehatan"]["employer_percent"] / 100
            )

            logger.info(
                f"Calculated BPJS Kesehatan: Employee={result['kesehatan_employee']}, "
                f"Employer={result['kesehatan_employer']}"
            )

        # Calculate BPJS JHT if enrolled
        if "jht" in config:
            result["jht_employee"] = flt(base_salary * config["jht"]["employee_percent"] / 100)
            result["jht_employer"] = flt(base_salary * config["jht"]["employer_percent"] / 100)

            logger.info(
                f"Calculated BPJS JHT: Employee={result['jht_employee']}, "
                f"Employer={result['jht_employer']}"
            )

        # Calculate BPJS JP if enrolled with salary cap
        if "jp" in config:
            max_jp = flt(config["jp"].get("max_salary", base_salary))
            jp_salary = min(base_salary, max_jp)

            result["jp_employee"] = flt(jp_salary * config["jp"]["employee_percent"] / 100)
            result["jp_employer"] = flt(jp_salary * config["jp"]["employer_percent"] / 100)

            logger.info(
                f"Calculated BPJS JP: Employee={result['jp_employee']}, "
                f"Employer={result['jp_employer']}"
            )

        # Calculate BPJS JKK if enrolled
        if "jkk" in config:
            result["jkk_employer"] = flt(base_salary * config["jkk"]["percent"] / 100)
            logger.info(f"Calculated BPJS JKK: Employer={result['jkk_employer']}")

        # Calculate BPJS JKM if enrolled
        if "jkm" in config:
            result["jkm_employer"] = flt(base_salary * config["jkm"]["percent"] / 100)
            logger.info(f"Calculated BPJS JKM: Employer={result['jkm_employer']}")

        # Calculate totals with explicit conversion to float
        result["total_employee"] = flt(
            result["kesehatan_employee"] + result["jht_employee"] + result["jp_employee"]
        )
        result["total_employer"] = flt(
            result["kesehatan_employer"]
            + result["jht_employer"]
            + result["jp_employer"]
            + result["jkk_employer"]
            + result["jkm_employer"]
        )

        # Log result safely
        logger.info(
            f"BPJS calculation successful. Total employee={result['total_employee']}, "
            f"total employer={result['total_employer']}"
        )

        # Apply rounding to all result values for consistent calculation
        # Make sure we have a fallback value for CURRENCY_PRECISION if it's somehow not defined
        currency_precision = getattr(
            frappe.utils, "get_currency_precision", lambda: CURRENCY_PRECISION
        )()
        if currency_precision is None:
            currency_precision = 0  # Default to integer precision (Rupiah standard)

        for key in result:
            result[key] = round(flt(result[key], currency_precision), currency_precision)

        # If doc is provided, update its fields
        if doc:
            _update_doc_fields(doc, result)
            logger.info(f"Updated document fields for {getattr(doc, 'name', 'New document')}")

        return result

    except Exception as e:
        # Log error but don't raise exception unless specifically handling critical scenarios
        logger.exception(f"Error calculating BPJS: {e}")
        return result


@frappe.whitelist()
def update_all_bpjs_components() -> Dict[str, str]:
    """
    Update all BPJS components for active salary structures.

    Returns:
        Dict[str, str]: Status of the operation
    """
    try:
        # Get BPJS Settings
        bpjs_settings = frappe.get_doc("BPJS Settings", "BPJS Settings")
        if not bpjs_settings:
            frappe.msgprint(_("Please configure BPJS Settings first"))
            return {"status": "error", "message": "BPJS Settings not found"}

        # Update salary structures
        bpjs_settings.update_salary_structures()
        frappe.msgprint(_("BPJS components updated successfully"))
        return {"status": "success", "message": "Components updated"}

    except Exception as e:
        get_logger().exception(f"Error updating BPJS components: {e}")
        frappe.throw(_("Failed to update BPJS components. Please check error log."))
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def debug_bpjs_for_employee(
    employee: Optional[str] = None, salary: Optional[Union[str, float]] = None
) -> Dict[str, Any]:
    """
    Debug function to test BPJS calculation for a specific employee.

    Args:
        employee: Employee ID
        salary: Base salary to use for calculation

    Returns:
        Dict[str, Any]: BPJS calculation results with additional debug info
    """
    if not employee:
        frappe.throw(_("Employee ID is required"))

    try:
        # Convert salary to float if provided
        base_salary = 0.0
        if salary:
            base_salary = flt(salary)
        else:
            # Try to get salary from employee document
            emp_doc = frappe.get_doc("Employee", employee)
            if hasattr(emp_doc, "gross_salary") and emp_doc.gross_salary:
                base_salary = flt(emp_doc.gross_salary)
            else:
                # Use default UMR
                base_salary = DEFAULT_UMR

        # Log debug information
        get_logger().info(
            f"Debug BPJS calculation for employee {employee} with salary {base_salary}"
        )

        # Calculate BPJS
        result = hitung_bpjs(employee, base_salary)

        # Add enrollment status and other debug info
        debug_result = dict(result)
        debug_result["is_enrolled"] = get_bpjs_enrollment_status(employee)
        debug_result["base_salary_used"] = base_salary
        debug_result["employee_id"] = employee

        # Get employee details for debugging
        emp_doc = frappe.get_doc("Employee", employee)
        debug_result["bpjs_kesehatan_id"] = getattr(emp_doc, "bpjs_kesehatan_id", "")
        debug_result["bpjs_ketenagakerjaan_id"] = getattr(emp_doc, "bpjs_ketenagakerjaan_id", "")

        # Return result
        return debug_result

    except Exception as e:
        get_logger().exception(f"Error in debug_bpjs_for_employee: {e}")
        frappe.throw(_("Error debugging BPJS: {0}").format(str(e)))
        return {"error": str(e)}
