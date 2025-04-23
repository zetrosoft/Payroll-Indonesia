frappe.ui.form.on('PPh TER Table', {
    refresh: function(frm) {
        // Add Generate Payment Entry button
        if(frm.doc.docstatus === 1 && !frm.doc.payment_entry) {
            frm.add_custom_button(__('Generate Payment Entry'), function() {
                frappe.confirm(
                    __('Are you sure you want to create Payment Entry for PPh 21 payment?'),
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
        
        // Add buttons to generate reports
        if(frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Generate PPh 21 Report'), function() {
                // Generate PPh 21 report logic
                frappe.msgprint(__('PPh 21 Report will be generated shortly'));
            }, __('Reports'));
            
            frm.add_custom_button(__('Generate CSV Export'), function() {
                // Generate CSV export logic
                frappe.msgprint(__('CSV Export will be processed shortly'));
            }, __('Reports'));
        }
    },
    
    onload: function(frm) {
        if(frm.is_new()) {
            // Set default values for new document
            frm.set_value('posting_date', frappe.datetime.get_today());
            
            // Set period and year
            let today = frappe.datetime.get_today();
            let month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                             'July', 'August', 'September', 'October', 'November', 'December'];
            let current_month_index = new Date().getMonth();
            let current_year = new Date().getFullYear();
            
            frm.set_value('period', month_names[current_month_index]);
            frm.set_value('year', current_year);
        }
        
        // Set month year title
        if(frm.doc.period && frm.doc.year) {
            frm.set_value('month_year_title', frm.doc.period + ' ' + frm.doc.year);
        }
    },
    
    period: function(frm) {
        if(frm.doc.period && frm.doc.year) {
            frm.set_value('month_year_title', frm.doc.period + ' ' + frm.doc.year);
        }
    },
    
    year: function(frm) {
        if(frm.doc.period && frm.doc.year) {
            frm.set_value('month_year_title', frm.doc.period + ' ' + frm.doc.year);
        }
    },
    
    validate: function(frm) {
        calculate_total(frm);
    }
});

// Employee tax details calculations
frappe.ui.form.on('PPh TER Detail', {
    details_add: function(frm) {
        calculate_total(frm);
    },
    
    amount: function(frm) {
        calculate_total(frm);
    },
    
    details_remove: function(frm) {
        calculate_total(frm);
    }
});

// Account calculations
frappe.ui.form.on('PPh TER Account Detail', {
    account_details_add: function(frm) {
        calculate_total(frm);
    },
    
    amount: function(frm) {
        calculate_total(frm);
    },
    
    account_details_remove: function(frm) {
        calculate_total(frm);
    }
});

function calculate_total(frm) {
    let total = 0;
    if(frm.doc.details) {
        frm.doc.details.forEach(function(d) {
            total += flt(d.amount);
        });
    }
    frm.set_value('total', total);
    frm.refresh_field('total');
}