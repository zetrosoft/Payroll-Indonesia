import frappe
from frappe.utils import flt

def hitung_biaya_jabatan(penghasilan_bruto):
    """
    Calculate Job Expense (Biaya Jabatan) - 5% of gross income, max 500k per month
    
    Args:
        penghasilan_bruto (float): Gross income
        
    Returns:
        float: Job expense amount
    """
    biaya_jabatan = flt(penghasilan_bruto) * 0.05
    return min(biaya_jabatan, 500000)

def hitung_pph_ter(penghasilan_bersih, status_pajak):
    """
    Calculate PPh 21 using TER method based on net income and tax status
    
    Args:
        penghasilan_bersih (float): Net income (after deductions)
        status_pajak (str): Tax status (TK0-TK3, K0-K3)
        
    Returns:
        float: PPh 21 amount
    """
    if not penghasilan_bersih or not status_pajak:
        return 0
        
    # Get tax rates from PPh TER Table
    ter_rates = frappe.get_all(
        "PPh TER Table",
        filters={"status_pajak": status_pajak},
        fields=["from_income", "to_income", "ter_percent"]
    )
    
    if not ter_rates:
        frappe.msgprint(f"No TER rates found for status {status_pajak}")
        return 0
    
    # Find applicable rate
    pph_rate = 0
    for rate in ter_rates:
        if (not rate.from_income or penghasilan_bersih >= rate.from_income) and \
           (not rate.to_income or penghasilan_bersih <= rate.to_income):
            pph_rate = rate.ter_percent
            break
    
    # Calculate PPh
    return flt(penghasilan_bersih) * flt(pph_rate) / 100