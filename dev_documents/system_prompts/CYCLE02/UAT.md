# CYCLE02 User Acceptance Testing (UAT)

## 1. Test Scenarios

This document details the User Acceptance Testing (UAT) scenarios for the advanced features developed in CYCLE02 of the Zenith Wallet application. The focus is on ensuring these new capabilities are intuitive, provide genuine value, and function correctly from a user's perspective. The UAT will be facilitated by an interactive Jupyter Notebook, which will guide the tester through each scenario, allowing them to see the direct impact of their actions on the system's data.

| Scenario ID | Scenario Description                               | Priority |
|-------------|----------------------------------------------------|----------|
| UAT-006     | Creating and Managing a Monthly Budget             | High     |
| UAT-007     | Real-time Tracking of Spending Against a Budget    | High     |
| UAT-008     | Generating a "Spending by Category" Report         | High     |
| UAT-009     | Generating a "Net Worth" Statement                 | High     |
| UAT-010     | Basic Management of Investment Accounts & Assets   | Medium   |

---

### **UAT-006: Creating and Managing a Monthly Budget** (Min 300 words)

This scenario tests the user's ability to set up and manage a budget, a core feature for proactive financial planning. A logged-in user, who has already set up transaction categories in CYCLE01, will be guided to create their first budget. The example in the Jupyter Notebook will be to create a "$500 budget for Groceries for the current month." The user will need to specify the category, the budget amount, and the time period. The system must validate this input; for instance, it should not be possible to create a budget with a negative amount. Upon successful creation, the system should confirm that the budget is active. The scenario will then guide the user to view their list of active budgets, which should now include the new "Groceries" budget. To test the management aspect, the user will then be instructed to update the budget, for example, by increasing the amount from $500 to $600. The system should reflect this change instantly. Finally, the user will test the deletion of the budget. Upon deletion, the budget should no longer appear in their list of budgets. This scenario verifies the complete CRUD lifecycle for the budgeting feature and ensures the user has full control over their financial planning parameters. The Jupyter notebook will make this interactive, with cells to create, view, update, and finally delete the budget, with clear output at each stage confirming the success of the operation.

---

### **UAT-007: Real-time Tracking of Spending Against a Budget** (Min 300 words)

This scenario is the crucial follow-up to creating a budget and tests the core value proposition of the feature: seeing how actual spending tracks against the plan. The user will start with the "$600 Groceries" budget created in the previous scenario. Initially, the notebook will guide them to query the budget's status, and the system should report that "$0 has been spent" and "$600 is remaining." Next, the user will be instructed to record a new transaction: a $75 grocery purchase. Immediately after, they will query the budget status again. The system must now show that "$75 has been spent" and "$525 is remaining." To test this further, the user will add another grocery transaction of $120. A subsequent check of the budget status should show the totals updated to "$195 spent" and "$405 remaining." The scenario will also test edge cases. The user will edit the first transaction from $75 to $80. The budget's totals should update to reflect this change ($200 spent, $400 remaining). Finally, the user will delete the second transaction ($120). The budget should revert to showing only $80 spent. This UAT case is vital for building user trust, as it proves that the system's calculations are accurate, dynamic, and reliable. The interactive nature of the notebook will make these changes and their effects immediate and obvious to the tester.

---

### **UAT-008: Generating a "Spending by Category" Report** (Min 300 words)

This scenario tests the primary reporting feature, which allows users to gain insight into their spending habits. The user will be working with a pre-populated set of transactions (created via the notebook) spanning multiple categories like "Groceries," "Transport," and "Entertainment" over the last calendar month. The user will then request a "Spending by Category" report for that specific month. The system should process this request and return a clear, structured summary of the data. This data should show the total amount spent in each category. For example, the report might show: Groceries - $480.50, Transport - $120.00, Entertainment - $215.75. The Jupyter Notebook will not only display this raw data but will also use a Python library (like Matplotlib or Plotly) to generate a visual pie chart, demonstrating how the API's data can be used to create the rich visualizations intended for the final user interface. The scenario will also test the date filtering by requesting the same report for "last week" and verifying that the totals are updated to reflect only the transactions from that shorter period. This confirms the reporting engine is both accurate and responsive to user-defined parameters. The visualization is key to demonstrating the user-facing value of this feature.

---

### **UAT-009: Generating a "Net Worth" Statement** (Min 300 words)

This scenario tests the high-level financial summary feature: the Net Worth statement. For this test, the notebook will first guide the user to create a set of accounts representing both assets and liabilities. For example, they will create a 'Savings Account' (Asset) with a balance of $10,000, a 'Checking Account' (Asset) with $5,000, and a 'Credit Card' (Liability) with a balance of -$2,000. After setting up this financial landscape, the user will request the "Net Worth" report. The system should calculate the total assets ($15,000) and total liabilities ($2,000) and return the final net worth of $13,000. The notebook will display this calculation clearly. To verify the dynamic nature of this report, the user will then be instructed to record a new transaction: a $500 payment from their 'Checking Account' to their 'Credit Card'. This action will decrease the checking balance to $4,500 and the credit card balance to -$1,500. The user will then request the Net Worth report again. The system must show the updated totals: Assets of $14,500, Liabilities of $1,500, and a recalculated Net Worth of $13,000. This proves that the report is a live, accurate snapshot of the user's financial position.

---

### **UAT-010: Basic Management of Investment Accounts & Assets** (Min 300 words)

This scenario validates the foundational features for investment tracking. As this is a new module, the focus is on the user's ability to manually record and manage their investment holdings. The user will first be guided to create a new 'Investment Account', for example, naming it "My Brokerage Account" with the provider "Fidelity". Once the account is created, the user will add assets to it. The notebook will instruct them to add their first asset: "10 shares of Apple Inc. (AAPL)". They will need to provide the name, ticker symbol, the quantity, and the purchase price. The system should confirm that the asset has been added to their brokerage account. The user will then add a second asset, such as "5 units of a Vanguard S&P 500 ETF (VOO)". After adding the assets, the user will request a view of their investment account, and the system should return a list of all the assets held within it, showing the details for both AAPL and VOO. The scenario will also test updating an asset, for instance, by changing the quantity of AAPL shares from 10 to 15, and finally deleting the VOO asset. This confirms the full CRUD lifecycle for manually managed investments, laying the groundwork for more advanced tracking in the future.

## 2. Behavior Definitions

This section provides the Gherkin-style definitions for the advanced features, ensuring unambiguous requirements for testing.

**GIVEN** a logged-in user with a "Groceries" category
**WHEN** the user creates a new budget of $500 for the "Groceries" category for the current month
**THEN** the system should save a new budget record associated with the user
**AND** return a confirmation with the details of the created budget.

**GIVEN** a user has a $500 budget for "Groceries"
**AND** the user has spent $100 on groceries so far this month
**WHEN** the user records a new grocery transaction of $50
**THEN** the system should update the budget's status
**AND** a request for the budget's details should show that the total spent is now $150 and the remaining amount is $350.

**GIVEN** a user has a transaction of $50 that is part of a budget
**WHEN** the user deletes that transaction
**THEN** the system should recalculate the budget's status
**AND** the total spent for that budget should decrease by $50.

**GIVEN** a user has made several expense transactions in different categories over the past month
**WHEN** the user requests a "Spending by Category" report for the last month
**THEN** the system should return a list of categories
**AND** each category in the list should have the correct sum of all expenses for that period.

**GIVEN** a user has two asset accounts with balances of $5000 and $10000
**AND** one liability account with a balance of $2000
**WHEN** the user requests a "Net Worth" report
**THEN** the system should return a total net worth of $13000, calculated as (5000 + 10000) - 2000.

**GIVEN** a logged-in user
**WHEN** the user adds a new investment account for their "Fidelity Brokerage"
**THEN** the system should create a new investment account record linked to the user.

**GIVEN** a user has an investment account
**WHEN** the user adds a new asset to that account, such as "10 shares of AAPL"
**THEN** the system should create a new asset record and associate it with the specified investment account. This comprehensive UAT plan ensures that the advanced features of CYCLE02 are not only technically functional but also deliver a user experience that is intuitive, accurate, and empowering.
