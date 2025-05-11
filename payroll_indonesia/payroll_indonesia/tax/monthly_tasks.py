# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 10:15:05 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, get_first_day, get_last_day, flt, today
from datetime import datetime
from collections import Counter

# Import constants
from payroll_indonesia.constants import (
    CACHE_MEDIUM,
    CACHE_SHORT,
    CACHE_LONG,
    TER_CATEGORIES,
)

# Import from pph_ter.py instead of ter_calculator.py
from payroll_indonesia.payroll_indonesia.tax.pph_ter import map_ptkp_to_ter_category

# Import cache utils
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value, clear_cache

# Import shared utilities
from payroll_indonesia.payroll_indonesia.utils import get_employee_details


def update_tax_summaries(month=None, year=None, company=None):
    """
    Update employee tax summaries at the end of each month

    This function is meant to be called by a scheduled job,
    or can be manually triggered to update all employee tax
    summaries for the current or previous month

    Args:
        month (int, optional): Month to process (1-12). Defaults to previous month.
        year (int, optional): Year to process. Defaults to current year.
        company (str, optional): Company to process. If not provided, all companies are processed.

    Returns:
        dict: Summary of updated summaries
    """
    try:
        # Validate parameters
        current_date = getdate(today())

        if not month:
            # Default to previous month
            if current_date.month == 1:
                month = 12
                year = current_date.year - 1 if not year else year
            else:
                month = current_date.month - 1
                year = current_date.year if not year else year

        if not year:
            year = current_date.year

        # Convert to integer if they are strings
        try:
            month = int(month)
            year = int(year)
        except (ValueError, TypeError):
            frappe.throw(_("Month and year must be valid numbers"), title=_("Invalid Parameters"))

        # Validate month and year
        if month < 1 or month > 12:
            frappe.throw(
                _("Invalid month: {0}. Must be between 1 and 12").format(month),
                title=_("Invalid Month"),
            )

        if year < 2000 or year > current_date.year + 1:
            frappe.throw(
                _("Invalid year: {0}. Must be between 2000 and {1}").format(
                    year, current_date.year + 1
                ),
                title=_("Invalid Year"),
            )

        # Check if company exists if provided
        if company and not frappe.db.exists("Company", company):
            frappe.throw(_("Company {0} not found").format(company), title=_("Invalid Company"))

        # Calculate date range for the month
        start_date = get_first_day(datetime(year, month, 1))
        end_date = get_last_day(datetime(year, month, 1))

        # Log the update
        frappe.log_error(
            "Tax summary update started for {0:02d}-{1}, range: {2} to {3}, company: {4}".format(
                month, year, start_date, end_date, company or "All"
            ),
            "Tax Summary Update",
        )

        # Statistics
        summary = {
            "period": f"{month:02d}-{year}",
            "company": company or "All Companies",
            "total_employees": 0,
            "updated": 0,
            "created": 0,
            "errors": 0,
            "details": [],
        }

        # Get all submitted salary slips in the specified month - using cache for efficiency
        cache_key = f"monthly_slips:{year}:{month}:{company or 'all'}"
        salary_slips = get_cached_value(cache_key)

        if salary_slips is None:
            # Use parameterized query for better security and performance
            query_filters = [
                ["start_date", ">=", start_date],
                ["end_date", "<=", end_date],
                ["docstatus", "=", 1],
            ]

            if company:
                query_filters.append(["company", "=", company])

            salary_slips = frappe.get_all(
                "Salary Slip",
                filters=query_filters,
                fields=["name", "employee", "employee_name", "company", "gross_pay", "start_date"],
            )

            # Cache the results for efficiency
            cache_value(cache_key, salary_slips, CACHE_MEDIUM)

        if not salary_slips:
            frappe.msgprint(
                _("No approved salary slips found for {0}-{1}").format(month, year),
                indicator="orange",
            )
            return summary

        # Get unique employees - Optimize by creating a lookup dictionary to avoid redundant processing
        employees = {}
        employee_ids = set()

        for slip in salary_slips:
            if slip.employee not in employees:
                employees[slip.employee] = {
                    "name": slip.employee,
                    "employee_name": slip.employee_name,
                    "company": slip.company,
                    "slips": [],
                }
                employee_ids.add(slip.employee)
            employees[slip.employee]["slips"].append(slip.name)

        summary["total_employees"] = len(employees)

        # Pre-fetch employee tax summaries for all employees in a single query to reduce DB calls
        existing_summaries = {}
        tax_summary_records = frappe.get_all(
            "Employee Tax Summary",
            filters={"employee": ["in", list(employee_ids)], "year": year},
            fields=["name", "employee"],
        )

        # Create lookup dictionary for efficient access
        for record in tax_summary_records:
            existing_summaries[record.employee] = record.name
            # Also cache individual values
            cache_key = f"tax_summary:{record.employee}:{year}"
            cache_value(cache_key, record.name, CACHE_MEDIUM)

        # Process each employee
        for emp_id, emp_data in employees.items():
            try:
                # Check if Employee Tax Summary DocType exists
                if not frappe.db.exists("DocType", "Employee Tax Summary"):
                    frappe.throw(
                        _("Employee Tax Summary DocType not found. Cannot update tax information."),
                        title=_("Missing DocType"),
                    )

                # Check if employee tax summary already exists (from pre-fetched data)
                existing_summary = existing_summaries.get(emp_id)

                # If not in pre-fetched data, check cache and then database
                if existing_summary is None:
                    cache_key = f"tax_summary:{emp_id}:{year}"
                    existing_summary = get_cached_value(cache_key)

                    if existing_summary is None:
                        existing_summary = frappe.db.get_value(
                            "Employee Tax Summary", {"employee": emp_id, "year": year}, "name"
                        )
                        # Cache result
                        cache_value(cache_key, existing_summary or False, CACHE_MEDIUM)

                if existing_summary:
                    # Update existing summary
                    result = update_existing_summary(
                        existing_summary, emp_id, month, year, emp_data["slips"]
                    )

                    if result:
                        summary["updated"] += 1
                        summary["details"].append(
                            {
                                "employee": emp_id,
                                "employee_name": emp_data["employee_name"],
                                "status": "Updated",
                                "message": "Updated with {0} slips".format(len(emp_data["slips"])),
                            }
                        )
                else:
                    # Create new summary
                    result = create_new_summary(
                        emp_id, emp_data["employee_name"], year, month, emp_data["slips"]
                    )

                    if result:
                        # Update cache with the new summary name
                        cache_key = f"tax_summary:{emp_id}:{year}"
                        cache_value(cache_key, result, CACHE_MEDIUM)

                        summary["created"] += 1
                        summary["details"].append(
                            {
                                "employee": emp_id,
                                "employee_name": emp_data["employee_name"],
                                "status": "Created",
                                "message": "Created with {0} slips".format(len(emp_data["slips"])),
                            }
                        )

            except Exception as e:
                # Non-critical error - can continue with other employees
                frappe.log_error(
                    "Error updating tax summary for employee {0}: {1}".format(emp_id, str(e)),
                    "Monthly Tax Update Error",
                )
                summary["errors"] += 1
                summary["details"].append(
                    {
                        "employee": emp_id,
                        "employee_name": emp_data["employee_name"],
                        "status": "Error",
                        "message": str(e)[:100],
                    }
                )
                continue

        # Log summary
        log_message = (
            "Tax summary update completed for {0:02d}-{1}. "
            "Updated: {2}, Created: {3}, "
            "Errors: {4}, Total: {5}".format(
                month,
                year,
                summary["updated"],
                summary["created"],
                summary["errors"],
                summary["total_employees"],
            )
        )

        if summary["errors"] > 0:
            frappe.log_error(log_message, "Monthly Tax Update Summary")
            frappe.msgprint(log_message, indicator="orange")
        else:
            frappe.log_error(log_message, "Monthly Tax Update Success")
            frappe.msgprint(log_message, indicator="green")

        return summary

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Critical error - log and throw
        frappe.log_error(
            "Error updating tax summaries: {0}".format(str(e)), "Monthly Tax Update Error"
        )
        frappe.throw(
            _("Error updating tax summaries: {0}").format(str(e)), title=_("Update Failed")
        )


def update_existing_summary(summary_name, employee, month, year, slip_names):
    """
    Update an existing tax summary for an employee

    Args:
        summary_name (str): Name of the existing tax summary document
        employee (str): Employee ID
        month (int): Month to update (1-12)
        year (int): Year to update
        slip_names (list): List of salary slip names to include

    Returns:
        bool: True if update was successful
    """
    try:
        # Use cache for summary document
        cache_key = f"tax_summary_doc:{summary_name}"
        summary = get_cached_value(cache_key)

        if summary is None:
            # Get the summary document
            summary = frappe.get_doc("Employee Tax Summary", summary_name)
            # Cache for efficiency
            cache_value(cache_key, summary, CACHE_SHORT)

        # Check for monthly_details table
        if not hasattr(summary, "monthly_details"):
            frappe.throw(
                _("Employee Tax Summary structure is invalid: missing monthly_details child table"),
                title=_("Invalid Document Structure"),
            )

        # Filter out existing monthly detail for this month if it exists
        # This approach avoids issues with directly modifying child tables
        existing_details = []
        for d in summary.get("monthly_details"):  # Use get() to safely access child table
            if getattr(d, "month", 0) != month:
                existing_details.append(d)

        # Replace monthly_details with filtered list
        summary.set("monthly_details", existing_details)

        # Calculate monthly totals from salary slips - using cached results when possible
        monthly_data = calculate_monthly_totals(slip_names)

        if not monthly_data:
            frappe.throw(
                _("Failed to calculate totals from salary slips"), title=_("Calculation Failed")
            )

        # Add new monthly detail - using standard append pattern
        try:
            row = summary.append("monthly_details", {})
            row.month = month
            row.gross_pay = monthly_data["gross_pay"]
            row.bpjs_deductions = monthly_data["bpjs_deductions"]
            row.tax_amount = monthly_data["tax_amount"]
            row.salary_slip = monthly_data["latest_slip"]
            row.is_using_ter = 1 if monthly_data["is_using_ter"] else 0
            row.ter_rate = monthly_data["ter_rate"]

            # Set TER category if available
            if monthly_data["ter_category"] and hasattr(row, "ter_category"):
                row.ter_category = monthly_data["ter_category"]
        except Exception as e:
            # Critical error - cannot update without details
            frappe.log_error(
                "Error adding monthly detail row: {0}".format(str(e)), "Monthly Detail Error"
            )
            frappe.throw(
                _("Error adding monthly detail: {0}").format(str(e)),
                title=_("Detail Update Failed"),
            )

        # Update TER information on parent if applicable
        if monthly_data["is_using_ter"]:
            if hasattr(summary, "is_using_ter"):
                summary.is_using_ter = 1

            if hasattr(summary, "ter_rate") and monthly_data["ter_rate"] > 0:
                summary.ter_rate = monthly_data["ter_rate"]

            if hasattr(summary, "ter_category") and monthly_data["ter_category"]:
                summary.ter_category = monthly_data["ter_category"]

        # Recalculate YTD tax
        total_tax = 0
        for detail in summary.get("monthly_details"):
            total_tax += flt(getattr(detail, "tax_amount", 0))

        if hasattr(summary, "ytd_tax"):
            summary.ytd_tax = total_tax

        # Save the summary
        summary.flags.ignore_validate_update_after_submit = True
        summary.save(ignore_permissions=True)

        # Clear cache for this document
        clear_cache(cache_key)

        # Also clear the YTD cache for this employee/year
        clear_cache(f"ytd:{employee}:{year}:")

        return True

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Critical error - log and re-raise
        frappe.log_error(
            "Error updating tax summary {0} for employee {1}: {2}".format(
                summary_name, employee, str(e)
            ),
            "Summary Update Error",
        )
        raise


def create_new_summary(employee, employee_name, year, month, slip_names):
    """
    Create a new tax summary for an employee

    Args:
        employee (str): Employee ID
        employee_name (str): Employee name
        year (int): Year for the summary
        month (int): Current month being processed (1-12)
        slip_names (list): List of salary slip names to include

    Returns:
        str: Name of the created summary document
    """
    try:
        # Calculate monthly totals from salary slips - using cached results when possible
        monthly_data = calculate_monthly_totals(slip_names)

        if not monthly_data:
            # Non-critical error - log and return None
            frappe.log_error(
                "No valid salary data found for employee {0} in {1}-{2}".format(
                    employee, month, year
                ),
                "Summary Creation Info",
            )
            frappe.msgprint(
                _("No valid salary data found for employee {0} in {1}-{2}").format(
                    employee, month, year
                ),
                indicator="orange",
            )
            return None

        # Create new summary document
        summary = frappe.new_doc("Employee Tax Summary")

        # Set main fields
        summary.employee = employee
        summary.employee_name = employee_name
        summary.year = year

        # Set title if field exists
        if hasattr(summary, "title"):
            summary.title = "{0} - {1}".format(employee_name, year)

        # Set initial tax amount
        if hasattr(summary, "ytd_tax"):
            summary.ytd_tax = monthly_data["tax_amount"]

        # Set TER information if applicable
        if monthly_data["is_using_ter"]:
            if hasattr(summary, "is_using_ter"):
                summary.is_using_ter = 1

            if hasattr(summary, "ter_rate") and monthly_data["ter_rate"] > 0:
                summary.ter_rate = monthly_data["ter_rate"]

            if hasattr(summary, "ter_category") and monthly_data["ter_category"]:
                summary.ter_category = monthly_data["ter_category"]

        # Add first monthly detail - using try/except for safety
        try:
            row = summary.append("monthly_details", {})
            row.month = month
            row.gross_pay = monthly_data["gross_pay"]
            row.bpjs_deductions = monthly_data["bpjs_deductions"]
            row.tax_amount = monthly_data["tax_amount"]
            row.salary_slip = monthly_data["latest_slip"]
            row.is_using_ter = 1 if monthly_data["is_using_ter"] else 0
            row.ter_rate = monthly_data["ter_rate"]

            # Set TER category if available and field exists
            if monthly_data["ter_category"] and hasattr(row, "ter_category"):
                row.ter_category = monthly_data["ter_category"]
        except Exception as e:
            # Critical error - cannot create without details
            frappe.log_error(
                "Error adding monthly detail row for new summary: {0}".format(str(e)),
                "New Summary Error",
            )
            frappe.throw(
                _("Error adding monthly detail to new summary: {0}").format(str(e)),
                title=_("Summary Creation Failed"),
            )

        # Insert the document
        summary.insert(ignore_permissions=True)

        return summary.name

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Critical error - log and re-raise
        frappe.log_error(
            "Error creating tax summary for {0} ({1}): {2}".format(employee, employee_name, str(e)),
            "Summary Creation Error",
        )
        raise


def calculate_monthly_totals(slip_names):
    """
    Calculate monthly totals from a list of salary slips with PMK 168/2023 support

    Args:
        slip_names (list): List of salary slip names

    Returns:
        dict: Monthly totals
    """
    try:
        if not slip_names:
            return None

        # Try to get cached results for efficiency
        cache_key = f"monthly_totals:{','.join(sorted(slip_names))}"
        cached_result = get_cached_value(cache_key)

        if cached_result is not None:
            return cached_result

        result = {
            "gross_pay": 0,
            "bpjs_deductions": 0,
            "tax_amount": 0,
            "is_using_ter": False,
            "ter_rate": 0,
            "ter_category": "",
            "latest_slip": slip_names[0] if slip_names else None,  # Default to first slip
        }

        # Check if we have valid slip names
        if not result["latest_slip"]:
            frappe.throw(_("No valid salary slip names provided"), title=_("Missing Data"))

        # Track which TER category to use
        ter_categories_found = []

        # Pre-fetch all salary component details for these slips in a single query to reduce DB calls
        all_components = {}

        # Use parameterized query to get all relevant components at once
        component_query = """
            SELECT parent, salary_component, amount 
            FROM `tabSalary Detail`
            WHERE parent IN %s
              AND parentfield = 'deductions'
              AND (salary_component IN ('BPJS JHT Employee', 'BPJS JP Employee', 'BPJS Kesehatan Employee', 'PPh 21'))
        """
        components_list = frappe.db.sql(component_query, [tuple(slip_names)], as_dict=True)

        # Organize components by slip
        for comp in components_list:
            if comp.parent not in all_components:
                all_components[comp.parent] = []
            all_components[comp.parent].append(comp)

        for slip_name in slip_names:
            try:
                # Try to get cached salary slip
                slip_cache_key = f"salary_slip:{slip_name}"
                slip = get_cached_value(slip_cache_key)

                if slip is None:
                    # Use safe get_doc approach with error handling
                    try:
                        slip = frappe.get_doc("Salary Slip", slip_name)
                        # Cache for efficiency
                        cache_value(slip_cache_key, slip, CACHE_MEDIUM)
                    except Exception as doc_error:
                        # Non-critical error - can continue with other slips
                        frappe.log_error(
                            "Error retrieving salary slip {0}: {1}".format(
                                slip_name, str(doc_error)
                            ),
                            "Slip Retrieval Warning",
                        )
                        continue

                # Add gross pay - safely access attributes
                result["gross_pay"] += flt(getattr(slip, "gross_pay", 0))

                # Check for TER usage - safely access attributes
                if getattr(slip, "is_using_ter", 0):
                    result["is_using_ter"] = True

                    if flt(getattr(slip, "ter_rate", 0)) > flt(result["ter_rate"]):
                        result["ter_rate"] = flt(getattr(slip, "ter_rate", 0))

                    # Get TER category if available
                    ter_category = getattr(slip, "ter_category", "")
                    if ter_category and ter_category in TER_CATEGORIES:
                        ter_categories_found.append(ter_category)

                # Process components from pre-fetched data
                components = all_components.get(slip_name, [])

                for component in components:
                    if component.salary_component in [
                        "BPJS JHT Employee",
                        "BPJS JP Employee",
                        "BPJS Kesehatan Employee",
                    ]:
                        result["bpjs_deductions"] += flt(component.amount)

                    # Get PPh 21
                    if component.salary_component == "PPh 21":
                        result["tax_amount"] += flt(component.amount)

                # Update latest slip based on posting date
                posting_date = getattr(slip, "posting_date", None)
                if posting_date:
                    # Get current latest slip
                    current_latest_cache_key = f"salary_slip:{result['latest_slip']}"
                    current_latest = get_cached_value(current_latest_cache_key)

                    if current_latest is None:
                        try:
                            current_latest = frappe.get_doc("Salary Slip", result["latest_slip"])
                            cache_value(current_latest_cache_key, current_latest, CACHE_MEDIUM)
                        except Exception:
                            # If error getting current latest, use this slip
                            result["latest_slip"] = slip_name
                            continue

                    current_latest_date = getattr(current_latest, "posting_date", None)

                    if not current_latest_date or getdate(posting_date) > getdate(
                        current_latest_date
                    ):
                        result["latest_slip"] = slip_name

            except Exception as e:
                # Non-critical error - can continue with other slips
                frappe.log_error(
                    "Error processing salary slip {0}: {1}".format(slip_name, str(e)),
                    "Slip Processing Warning",
                )
                continue

        # Determine TER category - efficiently use pre-fetched data when possible
        if result["is_using_ter"]:
            if ter_categories_found:
                # Use most common category
                category_counts = Counter(ter_categories_found)
                result["ter_category"] = category_counts.most_common(1)[0][0]
            else:
                # If no category found but TER is used, get from employee status
                try:
                    # Get employee from latest slip
                    employee_data = get_employee_details(None, result["latest_slip"])
                    if employee_data and employee_data.get("status_pajak"):
                        status_pajak = employee_data.get("status_pajak")

                        # Get TER category mapping
                        ter_category_cache_key = f"ter_category:{status_pajak}"
                        ter_category = get_cached_value(ter_category_cache_key)

                        if ter_category is None:
                            # Use map_ptkp_to_ter_category imported from pph_ter.py
                            ter_category = map_ptkp_to_ter_category(status_pajak)
                            cache_value(ter_category_cache_key, ter_category, CACHE_LONG)

                        result["ter_category"] = ter_category
                except Exception as emp_error:
                    # Non-critical error - can continue without category
                    frappe.log_error(
                        "Error getting TER category from employee: {0}".format(str(emp_error)),
                        "TER Category Warning",
                    )
                    # If error, leave category empty
                    pass

        # Cache the result for efficiency
        cache_value(cache_key, result, CACHE_SHORT)

        return result

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Critical error - log and re-raise
        frappe.log_error(
            "Error calculating monthly totals: {0}".format(str(e)), "Monthly Totals Error"
        )
        raise


def validate_monthly_entries():
    """
    Validate monthly entries in tax summaries and fix any inconsistencies

    This function is meant to be run periodically to ensure that all
    employee tax summaries are accurate and complete

    Returns:
        dict: Summary of validation results
    """
    try:
        # Get current year
        current_year = datetime.now().year

        # Statistics
        summary = {
            "year": current_year,
            "total_summaries": 0,
            "validated": 0,
            "fixed": 0,
            "errors": 0,
            "details": [],
        }

        # Get all tax summaries for the current year - using cache for efficiency
        cache_key = f"tax_summaries:{current_year}"
        tax_summaries = get_cached_value(cache_key)

        if tax_summaries is None:
            tax_summaries = frappe.get_all(
                "Employee Tax Summary",
                filters={"year": current_year},
                fields=["name", "employee", "employee_name", "ytd_tax"],
            )
            # Cache for efficiency
            cache_value(cache_key, tax_summaries, CACHE_MEDIUM)

        if not tax_summaries:
            frappe.msgprint(
                _("No tax summaries found for {0}").format(current_year), indicator="blue"
            )
            return summary

        summary["total_summaries"] = len(tax_summaries)

        # Process each summary
        for tax_summary in tax_summaries:
            try:
                # Get the document with cache
                doc_cache_key = f"tax_summary_doc:{tax_summary.name}"
                summary_doc = get_cached_value(doc_cache_key)

                if summary_doc is None:
                    summary_doc = frappe.get_doc("Employee Tax Summary", tax_summary.name)
                    # Cache for efficiency
                    cache_value(doc_cache_key, summary_doc, CACHE_SHORT)

                # Safely get monthly details
                monthly_details = summary_doc.get("monthly_details", [])

                # Check monthly details
                if not monthly_details:
                    # Non-critical error - log and continue
                    frappe.log_error(
                        "Missing monthly details for tax summary {0} (Employee: {1})".format(
                            tax_summary.name, tax_summary.employee
                        ),
                        "Monthly Details Warning",
                    )
                    summary["errors"] += 1
                    summary["details"].append(
                        {
                            "employee": tax_summary.employee,
                            "employee_name": tax_summary.employee_name,
                            "status": "Error",
                            "message": "Missing monthly details",
                        }
                    )
                    continue

                # Calculate YTD tax from monthly details
                calculated_ytd = 0
                for detail in monthly_details:
                    calculated_ytd += flt(getattr(detail, "tax_amount", 0))

                # Compare with stored value
                current_ytd = flt(tax_summary.ytd_tax)
                if abs(calculated_ytd - current_ytd) > 0.01:  # Allow for small rounding differences
                    # Fix YTD tax
                    summary_doc.ytd_tax = calculated_ytd
                    summary_doc.flags.ignore_validate_update_after_submit = True
                    summary_doc.save(ignore_permissions=True)

                    # Clear cache for this document
                    clear_cache(doc_cache_key)

                    # Also clear the YTD cache for this employee
                    clear_cache(f"ytd:{tax_summary.employee}:{current_year}:")

                    summary["fixed"] += 1
                    summary["details"].append(
                        {
                            "employee": tax_summary.employee,
                            "employee_name": tax_summary.employee_name,
                            "status": "Fixed",
                            "message": "YTD tax updated from {0} to {1}".format(
                                current_ytd, calculated_ytd
                            ),
                        }
                    )
                else:
                    summary["validated"] += 1
                    summary["details"].append(
                        {
                            "employee": tax_summary.employee,
                            "employee_name": tax_summary.employee_name,
                            "status": "Valid",
                            "message": "All values are consistent",
                        }
                    )

            except Exception as e:
                # Non-critical error - can continue with other employees
                frappe.log_error(
                    "Error validating tax summary {0}: {1}".format(tax_summary.name, str(e)),
                    "Tax Summary Validation Warning",
                )
                summary["errors"] += 1
                summary["details"].append(
                    {
                        "employee": tax_summary.employee,
                        "employee_name": tax_summary.employee_name,
                        "status": "Error",
                        "message": str(e)[:100],
                    }
                )
                continue

        # Log summary
        log_message = (
            "Tax summary validation completed for {0}. "
            "Validated: {1}, Fixed: {2}, "
            "Errors: {3}, Total: {4}".format(
                current_year,
                summary["validated"],
                summary["fixed"],
                summary["errors"],
                summary["total_summaries"],
            )
        )

        if summary["errors"] > 0 or summary["fixed"] > 0:
            frappe.log_error(log_message, "Tax Summary Validation Summary")
            frappe.msgprint(log_message, indicator="orange")
        else:
            frappe.log_error(log_message, "Tax Summary Validation Success")
            frappe.msgprint(log_message, indicator="green")

        return summary

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Critical error - log and throw
        frappe.log_error(
            "Error validating monthly entries: {0}".format(str(e)), "Monthly Validation Error"
        )
        frappe.throw(
            _("Error validating monthly entries: {0}").format(str(e)), title=_("Validation Failed")
        )


# Define public exports
__all__ = ["update_tax_summaries", "validate_monthly_entries"]
