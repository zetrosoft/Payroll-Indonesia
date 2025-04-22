frappe.ui.form.on('BPJS Payment Summary', {
    refresh: function(frm) {
        // Add Generate Payment Entry button
        if(frm.doc.docstatus === 1 && !frm.doc.payment_entry) {
            frm.add_custom_button(__('Generate Payment Entry'), function() {
                frappe.confirm(
                    __('Are you sure you want to create Payment Entry?'),
                    function() {
                        frm.call({
                            doc: frm.doc,
                            method: 'generate_payment_entry',
                            callback: function(r) {
                                if(r.message) {
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
            });
        }
    },
    
    onload: function(frm) {
        if (frm.is_new()) {
            frm.set_value('posting_date', frappe.datetime.get_today());
        }
    }
});

// Component child table calculations
frappe.ui.form.on('BPJS Payment Component', {
    amount: function(frm, cdt, cdn) {
        calculate_total(frm);
    },
    
    komponen_remove: function(frm) {
        calculate_total(frm);
    }
});

function calculate_total(frm) {
    let total = 0;
    if(frm.doc.komponen) {
        frm.doc.komponen.forEach(function(d) {
            total += flt(d.amount);
        });
    }
    frm.set_value('total', total);
    frm.refresh_field('total');
}