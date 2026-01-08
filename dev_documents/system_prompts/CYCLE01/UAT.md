# CYCLE01 User Acceptance Testing (UAT)

## 1. Test Scenarios

This document details the User Acceptance Testing (UAT) scenarios for the foundational features of the Zenith Wallet application developed in CYCLE01. The purpose of this UAT is to validate that the core functionalities are not only working correctly from a technical standpoint but are also logical, intuitive, and meet the real-world needs of an end-user. The scenarios are designed to be executed via an interactive Jupyter Notebook, which will provide a guided, tutorial-like experience. This notebook will allow testers to execute API calls, see the results in real-time, and verify the system's behavior against the definitions below, making the verification process accessible even to non-developers.

| Scenario ID | Scenario Description                               | Priority |
|-------------|----------------------------------------------------|----------|
| UAT-001     | New User Registration & Account Security           | High     |
| UAT-002     | User Login, Session Management, and Logout         | High     |
| UAT-003     | End-to-End Financial Account Management            | High     |
| UAT-004     | Management of Personal Transaction Categories      | High     |
| UAT-005     | Recording and Viewing a New Transaction            | High     |

---

### **UAT-001: New User Registration & Account Security** (Min 300 words)

This scenario is arguably the most critical first impression a user has of the application. Its success is measured not just by the ability to create an account, but by the user's confidence in the security and professionalism of the platform. The user will be guided to a registration endpoint where they must provide a unique username, a valid email address, and a password. The system must provide immediate and clear feedback on the validity of this information. For example, if the chosen username or email is already in use, the error message should be explicit and helpful, such as "Username is already taken." The password field should have clearly stated requirements (e.g., "minimum 8 characters, including one number"), and the system must enforce these rules, rejecting weak passwords with a clear message like "Password does not meet complexity requirements." Upon successful submission, the user's credentials should be securely stored, with the password being hashed and salted using a modern, strong algorithm like Argon2 or PBKDF2, ensuring it is never stored in plain text. The user should receive a clear success message confirming their account has been created. The Jupyter Notebook for this test will include cells for attempting registration with invalid data (e.g., a poorly formatted email, a short password, a duplicate username) to explicitly verify the robustness of the validation rules. A successful test will conclude with the creation of a new user account, which will be used in subsequent test scenarios. This initial handshake between the user and the system is paramount for building trust and ensuring the user feels their sensitive financial data will be handled with the utmost care.

---

### **UAT-002: User Login, Session Management, and Logout** (Min 300 words)

This scenario tests the gateway to the application for a returning user. The user will be directed to a login interface where they will enter their username and password. The primary test is to authenticate with the correct credentials created in UAT-001. A successful login should result in the system returning a secure access token (JWT). This token is the user's key to the application for their session, and the Jupyter Notebook will demonstrate how this token is captured and used in the headers of subsequent API requests to access protected resources. The scenario will also test failure cases: attempting to log in with an incorrect password or a non-existent username should result in a clear, unambiguous "Invalid credentials" error message, without revealing which part of the credential pair was incorrect, which is a key security practice to prevent username enumeration attacks. Furthermore, this scenario covers the logout process. The user will be able to make a request to a logout endpoint which, from a user's perspective, should securely terminate their session. While JWT is stateless on the server, the client-side implementation (simulated by the notebook) will demonstrate the deletion of the token, effectively logging the user out. An attempt to use the same token to access a protected endpoint after logout should result in an authentication error, confirming the session has been properly terminated on the client side. The test will also verify that the JWT has a reasonable expiration time encoded within it.

---

### **UAT-003: End-to-End Financial Account Management** (Min 300 words)

This scenario validates the user's ability to manage the virtual representations of their real-world financial accounts. After logging in (using the token from UAT-002), the user will be guided through the complete lifecycle of a financial account within Zenith Wallet. First, they will create a new account, for example, a 'Chase Checking' account. They will need to provide a name, select an account type from a predefined list (e.g., 'Checking', 'Savings', 'Credit Card'), and set an initial balance. The system should confirm the creation and return the full details of the newly created account. Next, the user will be prompted to view a list of all their accounts, which should now include the one they just created. The scenario will then guide them through updating the account's name, for instance, changing it to 'Primary Checking Account'. The system should reflect this change immediately upon request. Finally, the scenario will test the deletion process. The user will select the account for deletion. The system should ask for confirmation (a standard UX best practice, simulated in the notebook's instructions) and, upon confirmation, permanently remove the account from the user's profile. A subsequent request to list all accounts should show that the account is no longer present, thus verifying the entire CRUD (Create, Read, Update, Delete) lifecycle for financial accounts. This ensures the user has full and intuitive control over their financial landscape within the app.

---

### **UAT-004: Management of Personal Transaction Categories** (Min 300 words)

This scenario focuses on a key aspect of personalization: allowing users to categorize their transactions in a way that makes sense to them. A logged-in user will start with an empty set of custom categories. The Jupyter Notebook will first guide them to request a list of their categories, which should return an empty list. Then, the user will be instructed to create a new category, for instance, "Groceries." The system should confirm the creation and return the new category object, including its unique ID and name. The user will then create a few more categories, such as "Transport" and "Utilities," to simulate a real-world setup. After creating these, they will again request a list of all their categories, and the system should return a list containing all three new categories. The next step is to test the update functionality. The user will choose to rename "Transport" to "Transportation," and the system should confirm the change. Finally, the user will delete the "Utilities" category. A subsequent request to list their categories should show only "Groceries" and "Transportation." This scenario verifies the full CRUD lifecycle for categories, which is essential for empowering users to organize their financial data effectively and is a prerequisite for the budgeting features in the next cycle. The ability to tailor categories is fundamental to making the app feel personal and useful.

---

### **UAT-005: Recording and Viewing a New Transaction** (Min 300 words)

This scenario tests the most frequent and fundamental action a user will perform in the application: recording a transaction. A logged-in user will have already created a "Primary Checking Account" and a "Groceries" category from the previous scenarios. The notebook will guide them to record their first expense. They will need to provide the amount (e.g., $45.50), the date, a description ("Weekly grocery run"), and associate it with their checking account and groceries category. Upon submission, the system should create the transaction record and, crucially, automatically update the balance of the "Primary Checking Account" to reflect the expense. The test will verify this by requesting the account details and asserting that the balance has decreased by exactly $45.50. The scenario will then guide the user to record an income transaction, such as a "$2000 Salary" payment, associated with an "Income" category. The test will again verify that the account balance correctly increases. The final part of the scenario involves viewing the transaction history. The user will request a list of all their transactions, and the system should return a list containing the two transactions they just created, with all the correct details. This confirms the core functionality of the application is working correctly and that data integrity is maintained.

## 2. Behavior Definitions

This section translates the user scenarios into the structured Gherkin format (GIVEN/WHEN/THEN), which is an unambiguous way to describe system behavior. It serves as a clear specification for both testers and developers.

**GIVEN** a user is not registered in the Zenith Wallet system
**AND** the user has a unique username, a valid email address, and a strong password that meets the complexity requirements
**WHEN** the user submits their registration details to the registration endpoint
**THEN** the system should create a new user account
**AND** the user's password must be securely hashed and stored
**AND** the system should return a "201 Created" status with a confirmation message.

**GIVEN** a user is registered but not logged in
**AND** they provide an incorrect password for their username
**WHEN** the user attempts to log in
**THEN** the system should return a "401 Unauthorized" error
**AND** the error message should be a generic "Invalid credentials" to prevent security risks.

**GIVEN** a user is successfully logged into the system and has a valid access token
**WHEN** the user makes a request to a protected endpoint (e.g., to list their accounts) including the access token in the header
**THEN** the system should grant access and return the requested data with a "200 OK" status.

**GIVEN** a user is logged in
**WHEN** the user submits the details for a new financial account (name, type, initial balance)
**THEN** the system should create the new account and associate it with that user
**AND** return the full details of the newly created account.

**GIVEN** a user is logged in and has created a financial account
**WHEN** the user sends a request to delete that specific account
**THEN** the system should remove the account from the user's profile
**AND** a subsequent request to list the user's accounts should not include the deleted account.

**GIVEN** a user is logged in
**WHEN** they create a new custom transaction category named "Freelance Income"
**THEN** the system should save this category and associate it with the user.

**GIVEN** a user is logged in, has at least one account, and at least one category
**WHEN** the user records a new income transaction of $1500 to their "Freelance Income" category
**THEN** the system should create the transaction record
**AND** the balance of the associated account should increase by $1500, which must be verified by a subsequent API call.

**GIVEN** a user has recorded a transaction with the description "Coffee Meeting"
**WHEN** the user sends a request to update the description to "Client Coffee Meeting"
**THEN** the system should update the transaction's description
**AND** the updated transaction details should be returned in the response.

**GIVEN** a user has a transaction of $50 linked to their checking account
**AND** the checking account has a balance of $1000
**WHEN** the user deletes that transaction
**THEN** the system should remove the transaction record
**AND** the balance of the checking account should be correctly recalculated to $1050 (assuming the transaction was an expense). This detailed and structured approach ensures that all core functionalities are tested from a user-centric perspective, confirming that the system is not just technically sound but also practically usable and trustworthy.
