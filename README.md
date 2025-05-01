# Payroll Indonesia

Payroll module for Indonesian companies, integrated with ERPNext's Human Resource Management system and customized for Indonesian regulations.

## Features

- Integration with native ERPNext payroll modules (Salary Component, Salary Structure, Salary Slip, Payroll Entry)
- BPJS (Health & Employment Insurance) calculations
- PPh 21 TER (Monthly) tax calculation + progressive December rates for SPT
- Support for various tax statuses (TK/K)
- NPWP Spouse Joint processing
- Support for Non-Permanent Employees (PMK 168/2023)
- December tax correction (SPT)
- Ready for VPS or Frappe Cloud deployment

## Installation

### Prerequisites
- ERPNext v15
- Frappe Framework v15

### From GitHub
```bash
# In your bench directory
bench get-app https://github.com/dannyaudian/payroll_indonesia
bench --site yoursite.local install-app payroll_indonesia
bench migrate
```

## Required Configuration

### BPJS Account Setup
This system requires GL accounts (Chart of Accounts) to record BPJS deductions and expenses.

#### 1. Employee Deduction Accounts (Liability)
- BPJS Kesehatan - Employee
- BPJS JHT - Employee
- BPJS JP - Employee

#### 2. Company Expense Accounts (Expense)
- BPJS Kesehatan - Employer
- BPJS JHT - Employer
- BPJS JP - Employer
- BPJS JKK - Employer
- BPJS JKM - Employer

#### 3. Company Liability Accounts (Liability)
- BPJS Kesehatan - Employer
- BPJS JHT - Employer
- BPJS JP - Employer
- BPJS JKK - Employer
- BPJS JKM - Employer

> **Tip:** Place these accounts under Current Liabilities and Payroll Expenses according to your company's internal structure.

#### 4. BPJS Account Mapping Setup
1. Open DocType "BPJS Account Mapping"
2. Select your company
3. Link accounts for each component (employee & employer)
4. Save and activate for Salary Slip

#### 5. BPJS Settings Configuration
- Define contribution percentages (employee & employer) per component
- Set maximum salary thresholds
- Specify GL accounts for BPJS payments when using Payment Entry

### 🧾 Salary Component Account Mapping
This module uses two strategies for determining GL accounts during Salary Slip processing:

#### ✅ Default (Non-BPJS) Components
For regular components such as Basic Salary, Allowances, and Deductions, you must fill in the Default Account field in the Salary Component:

- Ensure that each Salary Component points to the correct account in your Chart of Accounts (e.g., Payroll Expense or Deductions).
- These accounts will be used when generating Journal Entries unless overridden.

#### 🚫 BPJS Components (Auto-Mapped)
For all BPJS-related components, such as:
- BPJS Kesehatan (Employee & Employer)
- BPJS JHT (Employee & Employer)
- BPJS JP (Employee & Employer)
- BPJS JKK / JKM

Do not fill in the Default Account field in Salary Component.

Instead:
- The system will automatically determine the correct accounts using the BPJS Account Mapping document.
- This ensures flexibility and avoids conflicting entries across companies with different account structures.

> ℹ️ This separation ensures that account logic is clean: manual for standard components, and dynamic/centralized for BPJS.

### PPh 21 Settings
This module supports two calculation methods:

- **Progressive** (default, according to tax bracket rates)
- **TER** (Effective Average Rate - per PMK 168/2023)

#### Configuration:
1. Open "PPh 21 Settings"
2. Select method: Progressive or TER
3. Fill in:
   - PTKP Table (PPh 21 PTKP)
   - Tax Bracket Table (PPh 21 Tax Bracket) for Progressive
   - TER Table (PPh 21 TER Table) for TER
4. Enable "Use TER for Monthly Calculation" if using TER method

## Module Structure
- **BPJS Settings** – Configure rates and salary thresholds
- **BPJS Account Mapping** – Account mapping per company
- **PPh 21 Settings** – Tax method configuration
- **Salary Slip** – Override validation & Indonesian components
- **Journal Entry** – Automation of entries based on mapping

## Employee Setup for BPJS
To control BPJS enrollment on an employee-by-employee basis:
1. Open the Employee document
2. Set the following fields:
   - **ikut_bpjs_kesehatan**: Enable/disable BPJS Health Insurance
   - **ikut_bpjs_ketenagakerjaan**: Enable/disable BPJS Employment Insurance

## Memory Optimization
This module includes optimizations to reduce memory usage during salary slip processing:
- Field initialization to prevent NoneType errors
- Truncated error messages to avoid memory bloat
- Garbage collection during batch processing
- Optimized BPJS and tax calculations

## Status
This module is actively being developed and used in production environments. Please report bugs or feature requests in GitHub Issues.