# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-08 11:11:10 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, now_datetime, getdate, add_months, date_diff

def debug_log(message, module_name="BPJS Payment Summary"):
    """Log debug message with timestamp and additional info"""
    timestamp = now_datetime().strftime('%Y-%m-%d %H:%M:%S')
    frappe.log_error(f"[{timestamp}] {message}", module_name)

def get_formatted_currency(value, company=None):
    """Format currency value based on company settings"""
    if company:
        currency = frappe.get_cached_value('Company', company, 'default_currency')
    else:
        currency = frappe.db.get_default("currency")
    return fmt_money(value, currency=currency)

def add_component_if_positive(bpjs_summary, component, description, amount):
    """Add a component to BPJS summary if amount is positive"""
    if amount > 0:
        bpjs_summary.append("komponen", {
            "component": component,
            "description": description,
            "amount": amount
        })

@frappe.whitelist()
def get_salary_slip_bpjs_data(salary_slip):
    """
    Extract BPJS data from a specific salary slip
    
    Args:
        salary_slip (str): Name of the salary slip
        
    Returns:
        dict: Dictionary containing BPJS amounts
    """
    if not salary_slip:
        return None
        
    try:
        # Get the salary slip document
        doc = frappe.get_doc("Salary Slip", salary_slip)
        
        bpjs_data = {
            'jht_employee': 0,
            'jp_employee': 0,
            'kesehatan_employee': 0,
            'jht_employer': 0,
            'jp_employer': 0,
            'kesehatan_employer': 0,
            'jkk': 0,
            'jkm': 0
        }
        
        # Extract employee contributions from deductions
        if hasattr(doc, 'deductions') and doc.deductions:
            for d in doc.deductions:
                if "BPJS Kesehatan" in d.salary_component and "Employee" not in d.salary_component:
                    bpjs_data['kesehatan_employee'] += flt(d.amount)
                elif "BPJS JHT" in d.salary_component and "Employee" not in d.salary_component:
                    bpjs_data['jht_employee'] += flt(d.amount)
                elif "BPJS JP" in d.salary_component and "Employee" not in d.salary_component:
                    bpjs_data['jp_employee'] += flt(d.amount)
                # Support alternative naming with "Employee" suffix
                elif "BPJS Kesehatan Employee" in d.salary_component:
                    bpjs_data['kesehatan_employee'] += flt(d.amount)
                elif "BPJS JHT Employee" in d.salary_component:
                    bpjs_data['jht_employee'] += flt(d.amount)
                elif "BPJS JP Employee" in d.salary_component:
                    bpjs_data['jp_employee'] += flt(d.amount)
        
        # Extract employer contributions from earnings
        if hasattr(doc, 'earnings') and doc.earnings:
            for e in doc.earnings:
                if "BPJS Kesehatan Employer" in e.salary_component:
                    bpjs_data['kesehatan_employer'] += flt(e.amount)
                elif "BPJS JHT Employer" in e.salary_component:
                    bpjs_data['jht_employer'] += flt(e.amount)
                elif "BPJS JP Employer" in e.salary_component:
                    bpjs_data['jp_employer'] += flt(e.amount)
                elif "BPJS JKK" in e.salary_component:
                    bpjs_data['jkk'] += flt(e.amount)
                elif "BPJS JKM" in e.salary_component:
                    bpjs_data['jkm'] += flt(e.amount)
        
        return bpjs_data
        
    except Exception as e:
        frappe.log_error(
            f"Error getting BPJS data from salary slip {salary_slip}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Salary Slip Data Error"
        )
        return None

@frappe.whitelist()
def get_salary_slips_for_period(company, month, year, include_all_unpaid=False, from_date=None, to_date=None):
    """
    Get salary slips for a specific period
    
    Args:
        company (str): Company name
        month (int): Month (1-12)
        year (int): Year
        include_all_unpaid (bool): If True, include all unpaid slips
        from_date (str, optional): Custom start date
        to_date (str, optional): Custom end date
        
    Returns:
        list: List of salary slips
    """
    try:
        filters = {"docstatus": 1, "company": company}
        
        if not include_all_unpaid:
            # Use date range based on month and year
            if from_date and to_date:
                filters.update({
                    "start_date": [">=", from_date],
                    "end_date": ["<=", to_date]
                })
            else:
                # Calculate first and last day of month
                first_day = f"{year}-{month:02d}-01"
                last_day = frappe.utils.get_last_day(first_day)
                
                filters.update({
                    "start_date": [
                        "between", 
                        [first_day, last_day]
                    ]
                })
        
        # Get salary slips
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters=filters,
            fields=["name", "employee", "employee_name", "start_date", "end_date", "total_deduction", "gross_pay"]
        )
        
        # If include_all_unpaid is True, filter out slips already linked to BPJS payments
        if include_all_unpaid:
            # Get list of salary slips already linked to BPJS payments
            linked_slips = frappe.get_all(
                "BPJS Payment Summary Detail",
                filters={"docstatus": 1},
                fields=["salary_slip"]
            )
            linked_slip_names = [slip.salary_slip for slip in linked_slips if slip.salary_slip]
            
            # Filter out already linked slips
            salary_slips = [slip for slip in salary_slips if slip.name not in linked_slip_names]
        
        return salary_slips
        
    except Exception as e:
        frappe.log_error(
            f"Error getting salary slips for {month}/{year} in {company}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Salary Slip Query Error"
        )
        return []

@frappe.whitelist()
def check_salary_slips_bpjs_components(salary_slip_list):
    """
    Check if salary slips have BPJS components
    
    Args:
        salary_slip_list (list or str): List of salary slip names or a single slip name
        
    Returns:
        dict: Dictionary with results
    """
    if isinstance(salary_slip_list, str):
        # Convert single slip to list
        salary_slip_list = [salary_slip_list]
        
    results = {
        "total_checked": len(salary_slip_list),
        "with_bpjs": 0,
        "without_bpjs": 0,
        "slips_with_bpjs": [],
        "slips_without_bpjs": []
    }
    
    try:
        for slip_name in salary_slip_list:
            bpjs_data = get_salary_slip_bpjs_data(slip_name)
            
            # Check if any BPJS component has a value
            has_bpjs = False
            if bpjs_data:
                has_bpjs = any(flt(value) > 0 for value in bpjs_data.values())
            
            if has_bpjs:
                results["with_bpjs"] += 1
                results["slips_with_bpjs"].append(slip_name)
            else:
                results["without_bpjs"] += 1
                results["slips_without_bpjs"].append(slip_name)
                
        return results
        
    except Exception as e:
        frappe.log_error(
            f"Error checking BPJS components in salary slips: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Component Check Error"
        )
        return results

@frappe.whitelist()
def calculate_bpjs_rates_for_employee(employee, base_salary=None, structure_salary=None, use_default_rates=True):
    """
    Calculate BPJS rates for an employee based on their salary
    
    Args:
        employee (str): Employee ID
        base_salary (float, optional): Base salary to use for calculation
        structure_salary (float, optional): Structure salary to use for calculation
        use_default_rates (bool): Whether to use default rates if not found in BPJS Settings
        
    Returns:
        dict: Dictionary with calculated BPJS amounts
    """
    try:
        # Get BPJS settings
        bpjs_settings = frappe.get_single("BPJS Settings")
        
        # If no base salary provided, try to determine it
        if not base_salary:
            # First try from structure_salary parameter
            if structure_salary:
                base_salary = flt(structure_salary)
            else:
                # Try to get from the most recent salary slip
                recent_slip = frappe.get_all(
                    "Salary Slip",
                    filters={"employee": employee, "docstatus": 1},
                    fields=["name", "base_salary", "gross_pay"],
                    order_by="start_date desc",
                    limit=1
                )
                
                if recent_slip:
                    base_salary = recent_slip[0].base_salary or recent_slip[0].gross_pay
                else:
                    # Try to get from salary structure assignment
                    assignment = frappe.get_all(
                        "Salary Structure Assignment",
                        filters={"employee": employee, "docstatus": 1},
                        fields=["base"],
                        order_by="from_date desc",
                        limit=1
                    )
                    
                    if assignment:
                        base_salary = assignment[0].base
        
        # If still no base salary, exit
        if not base_salary or flt(base_salary) <= 0:
            return {
                "employee": employee,
                "no_salary_data": True,
                "error": "Tidak dapat menemukan data gaji untuk karyawan ini"
            }
        
        # Calculate BPJS amounts based on settings or default rates
        rates = {
            "jht_employee_rate": 0.02,  # 2%
            "jht_employer_rate": 0.037,  # 3.7%
            "jp_employee_rate": 0.01,  # 1%
            "jp_employer_rate": 0.02,  # 2%
            "kesehatan_employee_rate": 0.01,  # 1%
            "kesehatan_employer_rate": 0.04,  # 4%
            "jkk_rate": 0.0054,  # 0.54%
            "jkm_rate": 0.003  # 0.3%
        }
        
        # Get rates from BPJS settings if available
        for rate_key in rates.keys():
            if hasattr(bpjs_settings, rate_key):
                setting_rate = getattr(bpjs_settings, rate_key)
                if setting_rate is not None:
                    rates[rate_key] = flt(setting_rate) / 100
        
        # Calculate BPJS amounts
        result = {
            "employee": employee,
            "employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
            "base_salary": base_salary,
            "jht_employee": flt(base_salary * rates["jht_employee_rate"]),
            "jp_employee": flt(base_salary * rates["jp_employee_rate"]),
            "kesehatan_employee": flt(base_salary * rates["kesehatan_employee_rate"]),
            "jht_employer": flt(base_salary * rates["jht_employer_rate"]),
            "jp_employer": flt(base_salary * rates["jp_employer_rate"]),
            "kesehatan_employer": flt(base_salary * rates["kesehatan_employer_rate"]),
            "jkk": flt(base_salary * rates["jkk_rate"]),
            "jkm": flt(base_salary * rates["jkm_rate"])
        }
        
        # Calculate total employee and employer contributions
        result["total_employee"] = flt(result["jht_employee"] + result["jp_employee"] + result["kesehatan_employee"])
        result["total_employer"] = flt(result["jht_employer"] + result["jp_employer"] + 
                                     result["kesehatan_employer"] + result["jkk"] + result["jkm"])
        result["grand_total"] = flt(result["total_employee"] + result["total_employer"])
        
        return result
        
    except Exception as e:
        frappe.log_error(
            f"Error calculating BPJS rates for employee {employee}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Rate Calculation Error"
        )
        return {
            "employee": employee,
            "error": f"Error calculating BPJS rates: {str(e)}"
        }