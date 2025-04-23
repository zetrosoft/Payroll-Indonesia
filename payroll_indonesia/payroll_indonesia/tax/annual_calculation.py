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
        fields=["name", "gross_pay", "total_deduction", "is_using_ter", "ter_rate", "posting_date"]
    )
    
    if not salary_slips:
        return {"annual_income": 0, "annual_tax": 0, "already_paid": 0, "correction": 0}
    
    # Calculate totals and get slips data
    total_gross = 0
    total_deduction = 0
    total_tax_paid = 0
    slip_details = []
    
    for slip in salary_slips:
        slip_doc = frappe.get_doc("Salary Slip", slip.name)
        total_gross += flt(slip.gross_pay)
        total_deduction += flt(slip.total_deduction)
        
        # Get PPh 21 from deductions
        tax_paid = 0
        for deduction in slip_doc.deductions:
            if deduction.salary_component == "PPh 21":
                tax_paid = flt(deduction.amount)
                break
                
        total_tax_paid += tax_paid
        
        # Store details for reporting
        slip_details.append({
            "name": slip.name,
            "date": slip.posting_date,
            "gross": slip.gross_pay,
            "tax": tax_paid,
            "using_ter": slip.is_using_ter,
            "ter_rate": slip.ter_rate if slip.is_using_ter else 0
        })
    
    # Calculate net annual income (PKP)
    employee_doc = frappe.get_doc("Employee", employee)
    
    # Calculate biaya jabatan (job allowance) - max 6M per year
    biaya_jabatan = min(total_gross * 0.05, 6000000)
    
    # Calculate annual BPJS
    annual_bpjs = 0
    for slip in salary_slips:
        slip_doc = frappe.get_doc("Salary Slip", slip.name)
        bpjs_components = ["BPJS JHT Employee", "BPJS JP Employee", "BPJS Kesehatan Employee"]
        for component in bpjs_components:
            for deduction in slip_doc.deductions:
                if deduction.salary_component == component:
                    annual_bpjs += flt(deduction.amount)
                    break
    
    # Get net annual - for annual calculation we need to deduct biaya jabatan and BPJS
    net_annual = total_gross - biaya_jabatan - annual_bpjs
    
    # Get employee details
    status_pajak = employee_doc.get("status_pajak", "TK0")
    
    # Calculate PTKP (Annual non-taxable income)
    ptkp = calculate_ptkp(status_pajak)
    
    # Calculate PKP (taxable income)
    pkp = max(0, net_annual - ptkp)
    
    # Calculate progressive tax (Pasal 17)
    annual_tax, tax_details = calculate_progressive_tax(pkp)
    
    # Calculate correction needed
    correction = annual_tax - total_tax_paid
    
    return {
        "annual_income": total_gross,
        "annual_net": net_annual,
        "biaya_jabatan": biaya_jabatan,
        "bpjs_total": annual_bpjs,
        "ptkp": ptkp,
        "pkp": pkp,
        "annual_tax": annual_tax,
        "already_paid": total_tax_paid,
        "correction": correction,
        "slip_details": slip_details,
        "tax_details": tax_details
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
    elif status_pajak.startswith("HB"):
        # HB0, HB1, HB2, HB3
        dependents = int(status_pajak[-1])
        # HB adds for spouse plus dependents plus additional for HB status
        return (base_ptkp + 
                ptkp_settings.get('kawin', 4500000) + 
                (dependents * ptkp_settings.get('anak', 4500000)) +
                ptkp_settings.get('hb_additional', 54000000))
    
    return base_ptkp

def calculate_progressive_tax(pkp):
    """Calculate progressive tax according to Article 17"""
    tax = 0
    tax_details = []
    
    # First 60 million: 5%
    if pkp > 0:
        tier1 = min(pkp, 60000000)
        tier1_tax = tier1 * 0.05
        tax += tier1_tax
        tax_details.append({
            "rate": 5,
            "taxable": tier1,
            "tax": tier1_tax
        })
    
    # 60M to 250M: 15%
    if pkp > 60000000:
        tier2 = min(pkp - 60000000, 190000000)
        tier2_tax = tier2 * 0.15
        tax += tier2_tax
        tax_details.append({
            "rate": 15,
            "taxable": tier2,
            "tax": tier2_tax
        })
    
    # 250M to 500M: 25%
    if pkp > 250000000:
        tier3 = min(pkp - 250000000, 250000000)
        tier3_tax = tier3 * 0.25
        tax += tier3_tax
        tax_details.append({
            "rate": 25,
            "taxable": tier3,
            "tax": tier3_tax
        })
    
    # 500M to 5B: 30%
    if pkp > 500000000:
        tier4 = min(pkp - 500000000, 4500000000)
        tier4_tax = tier4 * 0.30
        tax += tier4_tax
        tax_details.append({
            "rate": 30,
            "taxable": tier4,
            "tax": tier4_tax
        })
    
    # Above 5B: 35%
    if pkp > 5000000000:
        tier5 = pkp - 5000000000
        tier5_tax = tier5 * 0.35
        tax += tier5_tax
        tax_details.append({
            "rate": 35,
            "taxable": tier5,
            "tax": tier5_tax
        })
    
    return tax, tax_details

def generate_december_correction_note(calc_result):
    """Generate detailed note for December correction"""
    note = [
        "=== Perhitungan PPh 21 Tahunan ===",
        f"Penghasilan Bruto Setahun: Rp {calc_result['annual_income']:,.0f}",
        f"Biaya Jabatan: Rp {calc_result['biaya_jabatan']:,.0f}",
        f"Total BPJS: Rp {calc_result['bpjs_total']:,.0f}",
        f"Penghasilan Neto: Rp {calc_result['annual_net']:,.0f}",
        f"PTKP: Rp {calc_result['ptkp']:,.0f}",
        f"PKP: Rp {calc_result['pkp']:,.0f}",
        "",
        "Perhitungan Per Lapisan Pajak:"
    ]
    
    for detail in calc_result['tax_details']:
        note.append(
            f"- Lapisan {detail['rate']:.0f}%: "
            f"Rp {detail['taxable']:,.0f} × {detail['rate']:.0f}% = "
            f"Rp {detail['tax']:,.0f}"
        )
    
    note.extend([
        "",
        f"Total PPh 21 Setahun: Rp {calc_result['annual_tax']:,.0f}",
        f"PPh 21 Sudah Dibayar: Rp {calc_result['already_paid']:,.0f}",
        f"Koreksi Desember: Rp {calc_result['correction']:,.0f}",
        f"({'Kurang Bayar' if calc_result['correction'] > 0 else 'Lebih Bayar'})"
    ])
    
    # Tambahkan catatan tentang penggunaan metode progresif untuk koreksi tahunan
    note.append("\nMetode perhitungan Desember menggunakan metode progresif sesuai PMK 168/2023")
    
    # Tambahkan detail slip-slip yang menggunakan TER
    ter_slips = [slip for slip in calc_result['slip_details'] if slip['using_ter']]
    if ter_slips:
        note.append("\nRiwayat Perhitungan Dengan TER:")
        for slip in ter_slips:
            note.append(
                f"- {slip['date']}: Rate {slip['ter_rate']}%, "
                f"PPh 21: Rp {slip['tax']:,.0f}"
            )
    
    return "\n".join(note)