import frappe

def validate_mapping(doc, method=None):
    """Wrapper for BPJSAccountMapping.validate method"""
    # Skip if already being validated
    if getattr(doc, "_validated", False):
        return
        
    # Mark as being validated to prevent recursion
    doc._validated = True
    
    # Call the instance methods
    if not getattr(doc, "flags", {}).get("ignore_validate"):
        doc.validate_duplicate_mapping()
        doc.validate_account_types()
        doc.setup_missing_accounts()
    
    # Clean up flag
    doc._validated = False
    
def on_update_mapping(doc, method=None):
    """Wrapper for BPJSAccountMapping.on_update method"""
    frappe.cache().delete_value(f"bpjs_mapping_{doc.company}")
    frappe.logger().info(f"Cleared cache for BPJS mapping of company {doc.company}")