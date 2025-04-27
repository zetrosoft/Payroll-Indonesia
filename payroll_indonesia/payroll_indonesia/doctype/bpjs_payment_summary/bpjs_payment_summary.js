// Import required functions
const flt = frappe.utils.flt;

frappe.ui.form.on('BPJS Payment Summary', {
    refresh: function(frm) {
        // Add Generate Payment Entry button
        if(frm.doc.docstatus === 1 && !frm.doc.payment_entry) {
            frm.add_custom_button(__('Generate Payment Entry'), function() {
                frappe.confirm(
                    __('Are you sure you want to create Payment Entry for BPJS payment?'),
                    function() {
                        frm.call({
                            doc: frm.doc,
                            method: 'generate_payment_entry',
                            freeze: true,
                            freeze_message: __('Generating Payment Entry...'),
                            callback: function(r) {
                                if(r.message) {
                                    frappe.show_alert({
                                        message: __('Payment Entry {0} created', [r.message]),
                                        indicator: 'green'
                                    });
                                    frappe.set_route('Form', 'Payment Entry', r.message);
                                }
                            }
                        });
                    }
                );
            }).addClass('btn-primary');
        }
        
        // Add view button if payment entry exists
        if(frm.doc.payment_entry) {
            frm.add_custom_button(__('View Payment Entry'), function() {
                frappe.set_route('Form', 'Payment Entry', frm.doc.payment_entry);
            }, __('Actions'));
        }
        
        // Add button to generate employee details if detail table exists
        if(frm.doc.docstatus === 0 && frm.meta.fields.find(field => field.fieldname === "employee_details")) {
            if(!frm.doc.employee_details || frm.doc.employee_details.length === 0) {
                frm.add_custom_button(__('Generate Employee Details'), function() {
                    frappe.confirm(
                        __('This will add all active employees with BPJS participation. Continue?'),
                        function() {
                            frm.call({
                                doc: frm.doc,
                                method: 'populate_employee_details',
                                freeze: true,
                                freeze_message: __('Fetching employee details...'),
                                callback: function(r) {
                                    frm.refresh();
                                }
                            });
                        }
                    );
                }, __('Actions'));
            }
        }
    },
    
    onload: function(frm) {
        if (frm.is_new()) {
            frm.set_value('posting_date', frappe.datetime.get_today());
        }
    },
    
    validate: function(frm) {
        if (!frm.doc.month || !frm.doc.year) {
            frappe.msgprint(__('Month and Year are mandatory fields.'));
            frappe.validated = false;
        }
        calculate_total(frm);
    }
});

// Component child table calculations
frappe.ui.form.on('BPJS Payment Component', {
    komponen_add: function(frm) {
        calculate_total(frm);
    },
    
    component: function(frm, cdt, cdn) {
        // Set description automatically based on component
        const row = locals[cdt][cdn];
        if (row.component) {
            const descriptions = {
                "BPJS Kesehatan": "BPJS Kesehatan Monthly Payment",
                "BPJS JHT": "BPJS JHT Monthly Payment",
                "BPJS JP": "BPJS JP Monthly Payment",
                "BPJS JKK": "BPJS JKK Monthly Payment",
                "BPJS JKM": "BPJS JKM Monthly Payment"
            };
            
            if (descriptions[row.component] && !row.description) {
                frappe.model.set_value(cdt, cdn, 'description', descriptions[row.component]);
            }
        }
    },
    
    amount: function(frm) {
        calculate_total(frm);
    },
    
    komponen_remove: function(frm) {
        calculate_total(frm);
    }
});

// Employee detail calculations if applicable
frappe.ui.form.on('BPJS Payment Summary Detail', {
    employee_details_add: function(frm) {
        calculate_employee_totals(frm);
    },
    
    amount: function(frm) {
        calculate_employee_totals(frm);
    },
    
    employee_details_remove: function(frm) {
        calculate_employee_totals(frm);
    }
});

/**
 * Calculate total from all BPJS components
 * @param {Object} frm - The form object
 */
function calculate_total(frm) {
    let total = 0;
    
    // Calculate from components table
    if(frm.doc.komponen) {
        frm.doc.komponen.forEach(function(d) {
            total += flt(d.amount);
        });
    }
    
    // Add employee details total if applicable
    if(frm.doc.employee_details && frm.meta.fields.find(field => field.fieldname === "employee_details")) {
        total += calculate_employee_totals(frm);
    }
    
    frm.set_value('total', total);
    frm.refresh_field('total');
}

/**
 * Calculate totals from employee details
 * @param {Object} frm - The form object
 */
function calculate_employee_totals(frm) {
    let total = 0;
    
    if(frm.doc.employee_details && frm.meta.fields.find(field => field.fieldname === "employee_details")) {
        frm.doc.employee_details.forEach(function(d) {
            total += flt(d.amount);
        });
    }
    
    return total;
}