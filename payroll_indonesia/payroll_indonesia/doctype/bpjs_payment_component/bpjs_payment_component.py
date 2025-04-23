{
    "actions": [],
    "creation": "2025-04-23 11:58:22",
    "doctype": "DocType",
    "editable_grid": 1,
    "engine": "InnoDB",
    "field_order": [
        "component",
        "description",
        "amount"
    ],
    "fields": [
        {
            "fieldname": "component",
            "fieldtype": "Select",
            "in_list_view": 1,
            "label": "Component",
            "options": "BPJS Kesehatan\nBPJS JHT\nBPJS JP\nBPJS JKK\nBPJS JKM\nLainnya",
            "reqd": 1
        },
        {
            "fieldname": "description",
            "fieldtype": "Data",
            "in_list_view": 1,
            "label": "Description"
        },
        {
            "fieldname": "amount",
            "fieldtype": "Currency",
            "in_list_view": 1,
            "label": "Amount",
            "reqd": 1
        }
    ],
    "istable": 1,
    "modified": "2025-04-23 11:58:22",
    "modified_by": "dannyaudian",
    "module": "Payroll Indonesia",
    "name": "BPJS Payment Component",
    "owner": "dannyaudian",
    "permissions": [],
    "sort_field": "modified",
    "sort_order": "DESC",
    "track_changes": 1
}