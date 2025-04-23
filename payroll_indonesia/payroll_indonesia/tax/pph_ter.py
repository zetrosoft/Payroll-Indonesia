import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime

def hitung_biaya_jabatan(penghasilan_bruto, is_annual=False):
    """
    Calculate Job Expense (Biaya Jabatan) - 5% of gross income, max 500k per month or 6M per year
    
    Args:
        penghasilan_bruto (float): Gross income
        is_annual (bool): Whether calculation is for annual income
        
    Returns:
        float: Job expense amount
    """
    biaya_jabatan = flt(penghasilan_bruto) * 0.05
    max_amount = 6000000 if is_annual else 500000
    return min(biaya_jabatan, max_amount)

def get_ter_rate(penghasilan_bruto, status_pajak):
    """
    Get applicable TER rate based on income and tax status from PMK 168/2023
    
    Args:
        penghasilan_bruto (float): Gross income
        status_pajak (str): Tax status (TK0-TK3, K0-K3, HB0-HB3)
        
    Returns:
        float: TER rate (as decimal, e.g. 0.05 for 5%)
    """
    if not penghasilan_bruto or not status_pajak:
        return 0
        
    # Query TER table
    ter = frappe.db.sql("""
        SELECT rate
        FROM `tabPPh 21 TER Table`
        WHERE status_pajak = %s
          AND %s >= income_from
          AND (%s <= income_to OR income_to = 0)
        LIMIT 1
    """, (status_pajak, penghasilan_bruto, penghasilan_bruto), as_dict=1)
    
    if not ter:
        # Try with fallback to status type + 0 (e.g. TK2 -> TK0, K3 -> K0)
        status_prefix = status_pajak[0:2] if len(status_pajak) > 2 else status_pajak[0:1]
        fallback_status = f"{status_prefix}0"
        
        ter = frappe.db.sql("""
            SELECT rate
            FROM `tabPPh 21 TER Table`
            WHERE status_pajak = %s
              AND %s >= income_from
              AND (%s <= income_to OR income_to = 0)
            LIMIT 1
        """, (fallback_status, penghasilan_bruto, penghasilan_bruto), as_dict=1)
        
        if not ter:
            # Ultimate fallback to TK0 (default lowest)
            ter = frappe.db.sql("""
                SELECT rate
                FROM `tabPPh 21 TER Table`
                WHERE status_pajak = 'TK0'
                  AND %s >= income_from
                  AND (%s <= income_to OR income_to = 0)
                LIMIT 1
            """, (penghasilan_bruto, penghasilan_bruto), as_dict=1)
            
            if not ter:
                frappe.log_error(
                    f"No TER rate found for status {status_pajak} or fallbacks with income {penghasilan_bruto}",
                    "PPh 21 TER Error"
                )
                return 0
    
    # Convert percent to decimal
    return flt(ter[0].rate) / 100.0

def hitung_pph_ter(penghasilan_bruto, status_pajak):
    """
    Calculate PPh 21 using TER method based on gross income and tax status
    
    Args:
        penghasilan_bruto (float): Gross income
        status_pajak (str): Tax status (TK0-TK3, K0-K3, HB0-HB3)
        
    Returns:
        dict: PPh 21 calculation result
    """
    if not penghasilan_bruto or penghasilan_bruto <= 0:
        return {
            "tax_amount": 0,
            "ter_rate": 0,
            "status": "No Income"
        }
    
    # Get TER rate for this income and status
    ter_rate = get_ter_rate(penghasilan_bruto, status_pajak)
    
    # Calculate tax
    tax_amount = flt(penghasilan_bruto) * ter_rate
    
    return {
        "tax_amount": tax_amount,
        "ter_rate": ter_rate * 100,  # Convert to percent for display
        "status": "Success",
        "calculation_date": now_datetime()
    }

def generate_ter_calculation_note(penghasilan_bruto, status_pajak, ter_result):
    """
    Generate detailed calculation note for TER method
    
    Args:
        penghasilan_bruto (float): Gross income
        status_pajak (str): Tax status
        ter_result (dict): Result from hitung_pph_ter
    
    Returns:
        str: Formatted calculation note
    """
    note = [
        "=== Perhitungan PPh 21 dengan TER ===",
        f"Status Pajak: {status_pajak}",
        f"Penghasilan Bruto: Rp {penghasilan_bruto:,.0f}",
        f"Tarif Efektif Rata-rata: {ter_result['ter_rate']:.2f}%",
        f"PPh 21: Rp {ter_result['tax_amount']:,.0f}",
        "",
        "Perhitungan sesuai PMK 168/2023 tentang Tarif Efektif Rata-rata"
    ]
    
    return "\n".join(note)

def should_use_ter():
    """Check if TER method should be used based on system settings"""
    pph_settings = frappe.get_single("PPh 21 Settings")
    return (pph_settings.calculation_method == "TER" and pph_settings.use_ter)