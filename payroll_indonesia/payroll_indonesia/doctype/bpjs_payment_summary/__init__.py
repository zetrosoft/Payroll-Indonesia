# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

# Import fungsi-fungsi dari bpjs_payment_api.py untuk memudahkan akses
from .bpjs_payment_api import (
    get_summary_for_period,
    get_employee_bpjs_details,
    create_payment_entry,
    create_from_salary_slip,
    update_on_salary_slip_cancel
)

# Import fungsi-fungsi dari bpjs_payment_utils.py
from .bpjs_payment_utils import (
    debug_log,
    get_formatted_currency,
    add_component_if_positive
)

# Import fungsi-fungsi lain dari bpjs_payment_integration.py
from .bpjs_payment_integration import (
    extract_bpjs_from_salary_slip,
    get_or_create_bpjs_summary,
    recalculate_bpjs_totals
)

# Fungsi get_bpjs_suppliers dapat diambil dari bpjs_payment_summary.py
# atau bpjs_payment_api.py jika sudah dipindahkan
try:
    from .bpjs_payment_api import get_bpjs_suppliers
except ImportError:
    # Fallback to original location
    from .bpjs_payment_summary import get_bpjs_suppliers