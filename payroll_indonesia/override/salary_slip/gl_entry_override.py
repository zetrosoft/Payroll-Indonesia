import frappe
from frappe import _
from frappe.utils import flt

def override_salary_slip_gl_entries(doc, method=None):
    """
    Override GL entries for BPJS components in Salary Slip
    This function modifies GL entries for BPJS employer components
    to use correct credit account from BPJS Account Mapping
    """
    # Skip if no earnings/deductions
    if not doc.earnings and not doc.deductions:
        return
    
    # Get BPJS account mapping for this company
    bpjs_mapping = get_bpjs_account_mapping(doc.company)
    if not bpjs_mapping:
        frappe.msgprint(_("BPJS Account Mapping not found for company {0}. Using default accounts.").format(doc.company))
        return
    
    # Get existing GL entries that will be created
    gl_entries = get_existing_gl_entries(doc)
    if not gl_entries:
        return
    
    # Modify GL entries for BPJS components
    modified_entries = []
    
    for entry in gl_entries:
        # Skip entries without 'against' field
        if not entry.get('against'):
            modified_entries.append(entry)
            continue
        
        # Check if this is a BPJS component
        component = entry.get('against')
        if "BPJS" not in component:
            modified_entries.append(entry)
            continue
        
        # Handle different BPJS component types
        if "Employer" in component:
            # This is an employer contribution
            if "Kesehatan" in component:
                if entry.get('debit') and bpjs_mapping.kesehatan_employer_debit_account:
                    entry['account'] = bpjs_mapping.kesehatan_employer_debit_account
                elif entry.get('credit') and bpjs_mapping.kesehatan_employer_credit_account:
                    entry['account'] = bpjs_mapping.kesehatan_employer_credit_account
            elif "JHT" in component:
                if entry.get('debit') and bpjs_mapping.jht_employer_debit_account:
                    entry['account'] = bpjs_mapping.jht_employer_debit_account
                elif entry.get('credit') and bpjs_mapping.jht_employer_credit_account:
                    entry['account'] = bpjs_mapping.jht_employer_credit_account
            elif "JP" in component:
                if entry.get('debit') and bpjs_mapping.jp_employer_debit_account:
                    entry['account'] = bpjs_mapping.jp_employer_debit_account
                elif entry.get('credit') and bpjs_mapping.jp_employer_credit_account:
                    entry['account'] = bpjs_mapping.jp_employer_credit_account
            elif "JKK" in component:
                if entry.get('debit') and bpjs_mapping.jkk_employer_debit_account:
                    entry['account'] = bpjs_mapping.jkk_employer_debit_account
                elif entry.get('credit') and bpjs_mapping.jkk_employer_credit_account:
                    entry['account'] = bpjs_mapping.jkk_employer_credit_account
            elif "JKM" in component:
                if entry.get('debit') and bpjs_mapping.jkm_employer_debit_account:
                    entry['account'] = bpjs_mapping.jkm_employer_debit_account
                elif entry.get('credit') and bpjs_mapping.jkm_employer_credit_account:
                    entry['account'] = bpjs_mapping.jkm_employer_credit_account
        else:
            # This is an employee contribution
            if "Kesehatan" in component and bpjs_mapping.kesehatan_employee_account:
                if entry.get('credit'):
                    entry['account'] = bpjs_mapping.kesehatan_employee_account
            elif "JHT" in component and bpjs_mapping.jht_employee_account:
                if entry.get('credit'):
                    entry['account'] = bpjs_mapping.jht_employee_account
            elif "JP" in component and bpjs_mapping.jp_employee_account:
                if entry.get('credit'):
                    entry['account'] = bpjs_mapping.jp_employee_account
        
        modified_entries.append(entry)
    
    # Replace GL entries with our modified entries
    doc.gl_entries = modified_entries

def get_bpjs_account_mapping(company):
    """Get BPJS Account Mapping for this company"""
    mapping = frappe.get_all(
        "BPJS Account Mapping",
        filters={"company": company},
        limit=1
    )
    
    if mapping:
        return frappe.get_doc("BPJS Account Mapping", mapping[0].name)
    
    return None

def get_existing_gl_entries(doc):
    """
    Get GL entries that would be created for this Salary Slip
    This simulates the standard ERPNext GL entry creation process
    """
    gl_entries = []
    
    # Process earnings and statistical components
    for earning in doc.earnings:
        if not earning.salary_component:
            continue
            
        # Get account based on component and type
        account = get_component_account(earning.salary_component, "earnings", doc.company)
        if not account:
            continue
            
        # Create debit entry
        gl_entries.append({
            "account": account,
            "against": earning.salary_component,
            "debit": flt(earning.amount),
            "credit": 0,
            "cost_center": doc.cost_center,
            "project": doc.project
        })
        
        # For statistical components, create balancing credit entry
        if earning.statistical_component == 1:
            default_payable = get_default_payable_account(doc)
            gl_entries.append({
                "account": default_payable,
                "against": earning.salary_component,
                "debit": 0,
                "credit": flt(earning.amount),
                "cost_center": doc.cost_center,
                "project": doc.project
            })
    
    # Process deductions (except loans)
    for deduction in doc.deductions:
        if not deduction.salary_component:
            continue
        
        # Handle loan repayments separately
        if deduction.is_loan_repayment:
            continue
            
        # Get account based on component and type
        account = get_component_account(deduction.salary_component, "deductions", doc.company)
        if not account:
            continue
            
        # Create credit entry
        gl_entries.append({
            "account": account,
            "against": deduction.salary_component,
            "debit": 0,
            "credit": flt(deduction.amount),
            "cost_center": doc.cost_center,
            "project": doc.project
        })
        
        # For statistical components, create balancing debit entry
        if deduction.statistical_component == 1:
            default_payable = get_default_payable_account(doc)
            gl_entries.append({
                "account": default_payable,
                "against": deduction.salary_component,
                "debit": flt(deduction.amount),
                "credit": 0,
                "cost_center": doc.cost_center,
                "project": doc.project
            })
    
    return gl_entries

def get_component_account(salary_component, type_name, company):
    """Get the account for a salary component"""
    account = frappe.db.get_value(
        "Salary Component Account",
        {"parent": salary_component, "company": company},
        "account"
    )
    
    if not account:
        # Try with % wildcard
        account = frappe.db.get_value(
            "Salary Component Account",
            {"parent": salary_component, "company": "%"},
            "account"
        )
        
        if account:
            # Replace % with company name
            account = account.replace("%", company)
    
    return account

def get_default_account(company, account_type=None):
    """
    Get default account for company based on account type
    Fallback implementation untuk menggantikan fungsi yang tidak ada di ERPNext v15
    """
    if account_type:
        return frappe.get_cached_value('Company', company, account_type)
    return None

# Atau gunakan fungsi yang masih tersedia dari journal_entry.py
from erpnext.accounts.doctype.journal_entry.journal_entry import get_default_bank_cash_account