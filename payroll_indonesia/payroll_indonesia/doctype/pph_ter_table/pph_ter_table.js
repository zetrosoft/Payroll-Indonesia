frappe.ui.form.on('PPh TER Table', {
    refresh: function(frm) {
        frm.set_df_property('to_income', 'description', 
            __('Set to 0 for unlimited upper range'));
    },
    
    validate: function(frm) {
        if (frm.doc.to_income && frm.doc.from_income >= frm.doc.to_income) {
            frappe.throw(__('From Income must be less than To Income'));
            frappe.validated = false;
            return;
        }
    },
    
    from_income: function(frm) {
        if (frm.doc.to_income && frm.doc.from_income >= frm.doc.to_income) {
            frappe.msgprint(__('From Income must be less than To Income'));
        }
    },
    
    to_income: function(frm) {
        if (frm.doc.to_income && frm.doc.from_income >= frm.doc.to_income) {
            frappe.msgprint(__('From Income must be less than To Income'));
        }
    }
});
