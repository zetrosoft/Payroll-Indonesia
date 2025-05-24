import frappe
import logging
from payroll_indonesia.install import get_default_config

logger = logging.getLogger(__name__)

def map_gl_account(company: str, base_account_key: str, category: str) -> str:
    """
    Maps a base account key to a company-specific GL account.
    
    Args:
        company (str): The company name for which to create the account mapping
        base_account_key (str): The key of the base account in defaults.json
        category (str): The category of the account ('expense_accounts', 'bpjs_expense_accounts', 
                        'payable_accounts', 'bpjs_payable_accounts', or 'bpjs_account_mapping')
    
    Returns:
        str: The mapped account name with company suffix
    """
    # Load configuration from defaults.json
    config = get_default_config()
    
    if not config:
        logger.error("Could not load defaults.json configuration")
        return f"Unknown Account - {company}"
    
    # Special handling for bpjs_account_mapping which is a flat mapping
    if category == 'bpjs_account_mapping':
        # Check if bpjs_account_mapping exists in gl_accounts
        bpjs_mapping = config.get("gl_accounts", {}).get("bpjs_account_mapping", {})
        
        if not bpjs_mapping:
            logger.warning("bpjs_account_mapping not found in gl_accounts configuration")
            return f"Unknown Account - {company}"
        
        # Check if the specific key exists in the mapping
        if base_account_key not in bpjs_mapping:
            logger.warning(f"Account key '{base_account_key}' not found in 'bpjs_account_mapping'")
            return f"Unknown Account - {company}"
        
        # Get the account name directly from the mapping
        account_name = bpjs_mapping.get(base_account_key)
        
        # Return the account name with company suffix
        return f"{account_name} - {company}"
    
    # Regular category handling (unchanged)
    if category not in config.get("gl_accounts", {}):
        logger.warning(f"Category '{category}' not found in gl_accounts configuration")
        return f"Unknown Account - {company}"
    
    # Get the account name from the specified category and base_account_key
    category_accounts = config["gl_accounts"].get(category, {})
    
    if base_account_key not in category_accounts:
        logger.warning(f"Account key '{base_account_key}' not found in '{category}' category")
        return f"Unknown Account - {company}"
    
    # Get the base account name
    base_account = category_accounts[base_account_key].get("account_name", "Unknown Account")
    
    # Return the account name with company suffix
    return f"{base_account} - {company}"

def get_gl_account_for_salary_component(company: str, salary_component: str) -> str:
    """
    Maps a salary component to its corresponding GL account for a specific company.
    
    Args:
        company (str): The company name
        salary_component (str): The name of the salary component
    
    Returns:
        str: The mapped GL account with company suffix
    """
    # Define the mapping from salary component to account key and category
    component_mapping = {
        # Earnings
        "Gaji Pokok": ("beban_gaji_pokok", "expense_accounts"),
        "Tunjangan Makan": ("beban_tunjangan_makan", "expense_accounts"),
        "Tunjangan Transport": ("beban_tunjangan_transport", "expense_accounts"),
        "Insentif": ("beban_insentif", "expense_accounts"),
        "Bonus": ("beban_bonus", "expense_accounts"),
        
        # Deductions
        "PPh 21": ("hutang_pph21", "payable_accounts"),
        "BPJS JHT Employee": ("bpjs_jht_payable", "bpjs_payable_accounts"),
        "BPJS JP Employee": ("bpjs_jp_payable", "bpjs_payable_accounts"),
        "BPJS Kesehatan Employee": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
        
        # Employer Contributions (Statistical Components)
        "BPJS JHT Employer": ("bpjs_jht_employer_expense", "bpjs_expense_accounts"),
        "BPJS JP Employer": ("bpjs_jp_employer_expense", "bpjs_expense_accounts"),
        "BPJS JKK": ("bpjs_jkk_employer_expense", "bpjs_expense_accounts"),
        "BPJS JKM": ("bpjs_jkm_employer_expense", "bpjs_expense_accounts"),
        "BPJS Kesehatan Employer": ("bpjs_kesehatan_employer_expense", "bpjs_expense_accounts")
    }
    
    # Check if the salary component exists in the mapping
    if salary_component not in component_mapping:
        logger.warning(f"No GL account mapping found for salary component '{salary_component}'")
        return f"Unknown Account - {company}"
    
    # Get the account key and category
    account_key, category = component_mapping[salary_component]
    
    # Return the mapped GL account
    return map_gl_account(company, account_key, category)
