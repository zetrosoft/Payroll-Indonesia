import frappe
from frappe.utils import flt, getdate, get_first_day, get_last_day, add_months, date_diff, cint
from datetime import datetime
from payroll_indonesia.payroll_indonesia.utils import get_ptkp_settings, get_spt_month

def hitung_pph_tahunan(employee, tahun_pajak):
    """
    Calculate annual progressive income tax (Pasal 17) for December correction
    
    Args:
        employee (str): Employee ID
        tahun_pajak (int): Tax year
        
    Returns:
        dict: Annual tax calculation results
    """
    # Get annual income
    salary_slips = frappe.get_all(
        "Salary Slip",
        filters={
            "employee": employee,
            "docstatus": 1,
            "posting_date": ["between", [f"{tahun_pajak}-01-01", f"{tahun_pajak}-12-31"]]
        },
        fields=["name", "gross_pay", "total_deduction", "total_tax_deducted", "posting_date"]
    )
    
    if not salary_slips:
        return {"annual_income": 0, "annual_tax": 0, "already_paid": 0, "correction": 0}
    
    # Calculate totals
    total_gross = sum(flt(slip.gross_pay) for slip in salary_slips)
    total_deduction = sum(flt(slip.total_deduction) for slip in salary_slips)
    total_tax_paid = sum(flt(slip.total_tax_deducted) for slip in salary_slips)
    
    # Calculate net annual income (PKP)
    net_annual = total_gross - total_deduction
    
    # Get employee details
    emp = frappe.get_doc("Employee", employee)
    status_pajak = emp.get("status_pajak", "TK0")
    
    # Calculate PTKP (Annual non-taxable income)
    ptkp = calculate_ptkp(status_pajak)
    
    # Calculate PKP (taxable income)
    pkp = max(0, net_annual - ptkp)
    
    # Calculate progressive tax (Pasal 17)
    annual_tax = calculate_progressive_tax(pkp)
    
    # Calculate correction needed
    correction = annual_tax - total_tax_paid
    
    return {
        "annual_income": total_gross,
        "annual_tax": annual_tax,
        "already_paid": total_tax_paid,
        "correction": correction
    }
    
def calculate_ptkp(status_pajak):
    """Calculate PTKP based on tax status"""
    # Get PTKP settings
    ptkp_settings = get_ptkp_settings()
    
    # Base PTKP
    base_ptkp = ptkp_settings.get('pribadi', 54000000)
    
    # Additional based on status
    if status_pajak.startswith("TK"):
        # TK0, TK1, TK2, TK3
        dependents = int(status_pajak[-1])
        return base_ptkp + (dependents * ptkp_settings.get('anak', 4500000))
    elif status_pajak.startswith("K"):
        # K0, K1, K2, K3
        dependents = int(status_pajak[-1])
        # K adds for spouse plus dependents
        return (base_ptkp + 
                ptkp_settings.get('kawin', 4500000) + 
                (dependents * ptkp_settings.get('anak', 4500000)))
    
    return base_ptkp

def calculate_progressive_tax(pkp):
    """Calculate progressive tax according to Article 17"""
    tax = 0
    
    # First 60 million: 5%
    if pkp > 0:
        tier1 = min(pkp, 60000000)
        tax += tier1 * 0.05
    
    # 60M to 250M: 15%
    if pkp > 60000000:
        tier2 = min(pkp - 60000000, 190000000)
        tax += tier2 * 0.15
    
    # 250M to 500M: 25%
    if pkp > 250000000:
        tier3 = min(pkp - 250000000, 250000000)
        tax += tier3 * 0.25
    
    # 500M to 5B: 30%
    if pkp > 500000000:
        tier4 = min(pkp - 500000000, 4500000000)
        tax += tier4 * 0.30
    
    # Above 5B: 35%
    if pkp > 5000000000:
        tier5 = pkp - 5000000000
        tax += tier5 * 0.35
    
    return tax