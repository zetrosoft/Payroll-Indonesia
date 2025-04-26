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
        // Can be commented out if not needed
        calculate_employee_totals(frm);
    }
    
    frm.set_value('total', total);
    frm.refresh_field('total');
}

/**
 * Calculate totals from employee details
 * @param {Object} frm - The form object
 */
function calculate_employee_totals(frm) {
    if(frm.doc.employee_details && frm.meta.fields.find(field => field.fieldname === "employee_details")) {
        // Calculate component subtotals
        let total_kesehatan = 0;
        let total_jht = 0;
        let total_jp = 0;
        let total_jkk = 0;
        let total_jkm = 0;
        
        frm.doc.employee_details.forEach(function(d) {
            total_kesehatan += flt(d.bpjs_kesehatan);
            total_jht += flt(d.bpjs_jht);
            total_jp += flt(d.bpjs_jp);
            total_jkk += flt(d.bpjs_jkk);
            total_jkm += flt(d.bpjs_jkm);
        });
        
        // Optional: Update component rows if they exist
        if(frm.doc.komponen) {
            // Helper function to find or create component row
            function update_component_row(component_name, amount) {
                let found = false;
                for(let i=0; i<frm.doc.komponen.length; i++) {
                    if(frm.doc.komponen[i].component === component_name) {
                        frappe.model.set_value(
                            'BPJS Payment Component', 
                            frm.doc.komponen[i].name, 
                            'amount', 
                            amount
                        );
                        found = true;
                        break;
                    }
                }
                
                if(!found && amount > 0) {
                    let d = frm.add_child('komponen');
                    d.component = component_name;
                    d.description = component_name + " Monthly Payment";
                    d.amount = amount;
                    frm.refresh_field('komponen');
                }
            }
            
            // Update component rows
            update_component_row("BPJS Kesehatan", total_kesehatan);
            update_component_row("BPJS JHT", total_jht);
            update_component_row("BPJS JP", total_jp);
            update_component_row("BPJS JKK", total_jkk);
            update_component_row("BPJS JKM", total_jkm);
        }
    }
}