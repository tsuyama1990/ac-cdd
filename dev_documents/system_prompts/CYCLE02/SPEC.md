# CYCLE02 Specification: Advanced Features

## 1. Summary

This document outlines the technical specifications for the second development cycle of Zenith Wallet. CYCLE02 represents a significant evolution of the platform, building upon the foundational transaction management system established in CYCLE01. The primary objective of this cycle is to introduce a suite of advanced features that empower users with proactive financial insights and control. The core deliverables are a comprehensive budgeting system, a powerful reporting engine with data visualizations, and the foundational framework for investment tracking. This cycle will transition Zenith Wallet from a passive financial record-keeper into an active financial management partner for the user. The budgeting feature will allow users to set monthly spending limits for any category they have defined. The system will then automatically track spending against these budgets in real-time and provide visual feedback on their progress. The reporting engine is the cornerstone of this cycle, designed to provide users with a deep understanding of their financial habits. It will generate key reports, such as a detailed "Spending by Category" analysis and a "Net Worth" statement, presenting the data in easily digestible formats, including charts and graphs. Finally, this cycle will lay the groundwork for investment tracking by allowing users to manually add and monitor their investment accounts and assets. Upon successful completion of CYCLE02, the Zenith Wallet backend will be equipped with a sophisticated set of analytical tools. The API will offer new endpoints for managing budgets, generating complex reports, and tracking investments. The architectural additions will be modular, ensuring that the new capabilities are seamlessly integrated into the existing structure without compromising performance or maintainability. This cycle is critical in delivering the core value proposition of Zenith Wallet: providing users with the clarity and tools they need to take control of their financial future. The specifications laid out in this document provide a detailed roadmap for achieving this goal, ensuring that the implementation is as robust and well-designed as the core system it builds upon.

## 2. System Architecture

The architecture for CYCLE02 expands upon the existing structure by introducing new, dedicated Django apps for each major new feature, ensuring continued modularity and separation of concerns. This approach prevents feature-specific logic from bloating the core apps and maintains a clean, understandable project structure.

**File Structure (CYCLE02):**
The file structure will be extended to include `budgets`, `reports`, and `investments` apps.

```
zenith_wallet/
├── apps/
│   ├── users/
│   │   ├── ... (existing files from CYCLE01)
│   ├── transactions/
│   │   ├── ... (existing files from CYCLE01)
│   ├── **budgets/**
│   │   ├── **__init__.py**
│   │   ├── **models.py**       # Budget model
│   │   ├── **serializers.py**
│   │   ├── **views.py**        # API views for budget management
│   │   ├── **urls.py**
│   │   └── **tests/**
│   │       ├── **__init__.py**
│   │       └── **test_budgets.py**
│   ├── **reports/**
│   │   ├── **__init__.py**
│   │   ├── **services.py**     # Core logic for report generation
│   │   ├── **views.py**        # API endpoints for reports
│   │   ├── **urls.py**
│   │   └── **tests/**
│   │       ├── **__init__.py**
│   │       └── **test_reports.py**
│   └── **investments/**
│       ├── **__init__.py**
│       ├── **models.py**       # Investment and Asset models
│       ├── **serializers.py**
│       ├── **views.py**        # API views for investment tracking
│       ├── **urls.py**
│       └── **tests/**
│           ├── **__init__.py**
│           └── **test_investments.py**
├── zenith_wallet/
│   ├── **settings.py**         # Add new apps
│   ├── **urls.py**             # Include new app URLs
│   └── ...
```

**Code Blueprints:**

-   **`apps/budgets/models.py`**:
    -   **`Budget`**: This model is the core of the budgeting feature. It will have foreign keys to `User` and `Category`, establishing a many-to-one relationship (a user can have many budgets). Key fields will be `amount` (`DecimalField`), `start_date` (`DateField`), and `end_date` (`DateField`). A `period` field (e.g., 'Monthly') could also be added for future flexibility. A crucial part of this app will not be in the model itself, but in the view/service layer, which will be responsible for calculating the current spending against this budget.

-   **`apps/reports/services.py`**:
    This file will contain the heavy lifting for report generation, keeping the `views.py` clean and focused on handling HTTP requests.
    -   `generate_spending_by_category_report(user, start_date, end_date)`: This function will take a user and a date range as input. It will perform a database query that groups the user's expense transactions by category and sums their amounts within the given date range. It will return a data structure (e.g., a list of dictionaries) suitable for serialization, like `[{'category': 'Groceries', 'total_spent': 450.75}, ...]`. This service will use Django's ORM aggregation and annotation features for maximum efficiency.
    -   `generate_net_worth_report(user)`: This function will calculate the user's net worth. It will do this by summing the balances of all their asset-type accounts ('Checking', 'Savings') and subtracting the sum of the balances of all their liability-type accounts ('Credit Card', 'Loan'). This service demonstrates the power of having a well-structured `Account` model.

-   **`apps/reports/views.py`**:
    -   `SpendingByCategoryView`: An `APIView` that accepts `GET` requests with `start_date` and `end_date` as query parameters. It will validate these parameters, call the corresponding service function from `reports/services.py`, and return the report data as a JSON response.
    -   `NetWorthView`: A simple `APIView` that calls the net worth service function for the current user and returns the calculated value.

-   **`apps/investments/models.py`**:
    -   **`InvestmentAccount`**: Represents a user's investment account, like a brokerage account. It will have a foreign key to `User` and fields for `name` and `provider`.
    -   **`Asset`**: Represents a specific asset within an `InvestmentAccount`. It will have a foreign key to `InvestmentAccount` and fields like `name` (e.g., "Apple Inc."), `ticker_symbol` ("AAPL"), `quantity` (`DecimalField`), and `purchase_price` (`DecimalField`). This provides the foundation for future features like portfolio performance tracking.

## 3. Design Architecture

The design for CYCLE02 continues the schema-first approach, ensuring that all new API endpoints are built on a foundation of well-defined data contracts using Pydantic-based schemas. This consistency is key to a maintainable and predictable API.

**Pydantic-based Schema Design:**

-   **`BudgetSchema` (Input/Output):** This schema will define the structure for a budget. For input, it will require `category_id`, `amount`, `start_date`, and `end_date`. It will include custom validators to ensure that `end_date` is after `start_date` and that the amount is a positive number. For output, it will be enhanced to include calculated fields like `total_spent` and `remaining_amount`, which will be computed on-the-fly when the data is serialized. This dynamic calculation is a key part of the design, providing rich data to the client without cluttering the database model.
-   **`ReportParametersSchema` (Input):** A schema used to validate the query parameters for report generation. It will define `start_date` and `end_date` fields and can be used to enforce that the date range is valid (e.g., not longer than one year).
-   **`SpendingReportSchema` (Output):** This will define the structure of the data returned by the spending report endpoint. It will likely be a schema that contains a list of objects, where each object has a `category_name` and a `total_spent` field.
-   **`NetWorthReportSchema` (Output):** A simple schema that defines the fields for the net worth report, such as `total_assets`, `total_liabilities`, and `net_worth`.
-   **`InvestmentAccountSchema` and `AssetSchema` (Input/Output):** These will mirror their corresponding models, providing a clear data contract for creating and managing investment data.

**Data Flow for Budget Status Calculation:**

1.  A user's frontend requests the details for a specific budget.
2.  The `BudgetViewSet` in `apps/budgets/views.py` receives the `GET` request.
3.  The view retrieves the `Budget` model instance from the database.
4.  Before serializing the data with `BudgetSchema`, the view (or a dedicated service) calculates the `total_spent` for that budget's category and period by querying the `Transaction` model. This query will be highly efficient, summing transactions that match the user, category, and date range.
5.  This calculated data (`total_spent` and the derived `remaining_amount`) is passed into the `BudgetSchema` as part of the serialization context.
6.  The schema combines the model data with the calculated fields and returns a complete JSON response to the client, providing a full picture of the budget's status in a single API call. This design ensures that complex business logic is handled on the backend and that the API provides rich, ready-to-use data to the client, simplifying frontend development significantly.

## 4. Implementation Approach

The implementation of CYCLE02 will be structured to build each new feature as a distinct, testable module before integrating it into the main application.

1.  **App Scaffolding:** Create the new Django apps (`budgets`, `reports`, `investments`) using `manage.py startapp`. Add them to `INSTALLED_APPS` in `settings.py`. This initial step ensures the project structure is correctly extended.
2.  **Budget Module Implementation:**
    -   Define the `Budget` model in `apps/budgets/models.py`.
    -   Run `makemigrations` and `migrate`.
    -   Implement the `BudgetSchema` in `apps/budgets/serializers.py`, including the logic for the calculated fields.
    -   Create the `BudgetViewSet` in `apps/budgets/views.py`, ensuring it is properly permissioned so users can only access their own budgets. Implement the logic for calculating spending vs. budget.
    -   Set up URL routing in `apps/budgets/urls.py` and include it in the root `urls.py`. Write extensive tests for this module before moving on.
3.  **Reporting Engine Implementation:**
    -   Create the `apps/reports/services.py` file. Implement the core logic for the `generate_spending_by_category_report` and `generate_net_worth_report` functions, including the necessary database queries and calculations.
    -   Write extensive unit tests for these service functions to ensure their accuracy with a variety of data scenarios. This is critical for financial calculations.
    -   Implement the `SpendingByCategoryView` and `NetWorthView` in `apps/reports/views.py`. These views will primarily act as a thin layer that validates input and calls the service functions.
    -   Configure the URL routing for the new report endpoints.
4.  **Investment Tracking Foundation:**
    -   Define the `InvestmentAccount` and `Asset` models in `apps/investments/models.py`.
    -   Run `makemigrations` and `migrate`.
    -   Implement the corresponding `InvestmentAccountSchema` and `AssetSchema` serializers.
    -   Create the `ModelViewSet`s for these models, again ensuring strict, user-level permissioning.
    -   Set up the URL routing.
5.  **Testing and Integration:**
    -   Write comprehensive integration tests for all new features. For the budget feature, this means creating a budget, creating transactions, and then hitting the API to verify that the `total_spent` and `remaining_amount` fields are calculated correctly. For reports, tests will involve populating the test database with a known set of transactions and asserting that the report endpoints return the expected calculated totals.
    -   Update the OpenAPI/Swagger documentation to include all the new endpoints from CYCLE02. Ensure the documentation is clear and provides examples for the new, more complex endpoints.
    -   Conduct a final round of regression testing on the CYCLE01 features to ensure that the new code has not introduced any unintended side effects.

## 5. Test Strategy

**Unit Testing Approach (Min 300 words):**
The focus of unit testing in CYCLE02 shifts to the complex business logic introduced in the new modules.
-   **Reporting Services:** The `apps/reports/services.py` file will be the most critical area for unit testing. For the `generate_spending_by_category_report` function, we will write a suite of tests that create an in-memory database with a variety of transaction scenarios. This will include: a user with no transactions, a user with only income, a user with expenses in multiple categories, and transactions that fall outside the requested date range. For each scenario, we will call the service function and assert that the returned data structure is exactly as expected. For the `generate_net_worth_report`, we will create a user with a mix of asset and liability accounts and assert that the final calculated net worth is correct. These tests will be data-driven, using parameterized inputs to cover many cases efficiently.
-   **Budget Logic:** While much of the budget logic is in the view/serializer, any helper functions or complex calculations will be extracted into a `budgets/services.py` and unit tested. For example, a function that determines the relevant date range for a "monthly" budget would be tested to ensure it correctly handles different months and leap years. We will also unit test the logic within the `BudgetSchema` that calculates the remaining amount, providing it with different values for `total_spent` and `amount` to verify the calculation.

**Integration Testing Approach (Min 300 words):**
Integration tests in CYCLE02 will validate the end-to-end functionality of the new features, ensuring they work correctly with the existing core system.
-   **Budgeting Lifecycle:** A key test will simulate a user's entire interaction with the budgeting feature. The test will: 1) Authenticate as a user. 2) Create a "Groceries" budget of $500 for the current month. 3) Hit the budget detail endpoint and assert that `total_spent` is $0 and `remaining_amount` is $500. 4) Create a $75 grocery expense transaction. 5) Hit the budget detail endpoint again and assert that `total_spent` is now $75 and `remaining_amount` is $425. 6) Update the transaction to $100. 7) Hit the endpoint again and assert the totals are updated to $100 and $400 respectively. This comprehensive test ensures the entire system, from API view to model to database, is working in concert.
-   **Report Accuracy:** We will write integration tests that validate the accuracy of our reporting endpoints. A test will populate the database with a known, fixed set of transactions for a user across several categories and months. It will then call the `/api/reports/spending-by-category/` endpoint with a specific date range and assert that the JSON response contains the exact, pre-calculated totals for each category. This provides end-to-end confidence in the correctness of our financial calculations.
-   **Performance of Reports:** While not a functional test, we will use the integration testing framework to get an early indication of performance. We will write a test that generates a large number of transactions for a user (e.g., 5,000) and then hits the main reporting endpoints, measuring the execution time of the API call using a tool like `pytest-benchmark`. This can help us catch grossly inefficient database queries early in the development process and provides a baseline for future performance monitoring.
