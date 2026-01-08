# CYCLE01 Specification: Core Functionality

## 1. Summary

This document provides the definitive technical specification for the first development cycle of Zenith Wallet. The singular focus of CYCLE01 is to construct the foundational bedrock of the application. This entails the implementation of a secure and reliable user authentication system, comprehensive management of financial accounts and transaction categories, and the core functionality of tracking individual financial transactions. By the conclusion of this cycle, the system will provide a robust, API-driven backend, enabling a client application to support user registration, login, and the complete lifecycle of transaction management (Create, Read, Update, Delete - CRUD). This initial version, while not feature-complete from a user's perspective, will be technically complete from a foundational standpoint. It will deliver a stable, well-tested, and secure core upon which all subsequent features, such as budgeting and reporting, will be built. The strategic objective of CYCLE01 is risk mitigation. By prioritizing the most critical and central components of the system—user data and financial transactions—we ensure that the core architecture is sound before building more complex, peripheral features. This cycle will see the establishment of key architectural patterns, including the modular Django app structure, the Pydantic-based data serialization and validation layer, and the token-based authentication scheme. The successful completion of this cycle will yield a fully functional, secure RESTful API that serves as the central nervous system for the entire Zenith Wallet application. The API will be self-documenting, rigorously tested, and adhere to best practices for security and performance. This disciplined, foundational approach ensures that future development cycles can proceed with a high degree of confidence, building upon a solid and reliable core. Every decision and specification within this document is geared towards creating a system that is not only functional but also secure, scalable, and maintainable from day one. This initial phase is not merely about building features; it is about establishing a professional development culture, setting up robust CI/CD pipelines, and creating a stable platform that can be iterated upon for years to come. It is the essential, unglamorous work that determines the long-term success and technical integrity of the entire project.

## 2. System Architecture

The architecture for CYCLE01 is intentionally focused and modular, establishing the primary building blocks of the Zenith Wallet backend. We will create two main Django apps, `users` and `transactions`, to ensure a clean separation of concerns. This modularity is a core tenant of our design, preventing the creation of a monolithic "big ball of mud" and instead fostering a codebase where components are independent, testable, and reusable.

**File Structure (CYCLE01):**
The following ASCII tree depicts the exact files to be created and modified during this cycle. This structure is designed for clarity and scalability.

```
zenith_wallet/
├── apps/
│   ├── **users/**
│   │   ├── **__init__.py**
│   │   ├── **admin.py**        # For Django admin integration
│   │   ├── **apps.py**         # App configuration
│   │   ├── **models.py**       # Database models (UserProfile)
│   │   ├── **serializers.py**  # Pydantic-based schemas for API data
│   │   ├── **views.py**        # API endpoint logic (registration, login)
│   │   ├── **urls.py**         # URL routing for the users app
│   │   └── **tests/**
│   │       ├── **__init__.py**
│   │       └── **test_auth.py** # Tests for user authentication
│   ├── **transactions/**
│   │   ├── **__init__.py**
│   │   ├── **admin.py**
│   │   ├── **apps.py**
│   │   ├── **models.py**       # Models for Account, Category, Transaction
│   │   ├── **serializers.py**
│   │   ├── **views.py**        # API views for CRUD operations
│   │   ├── **urls.py**         # URL routing for the transactions app
│   │   └── **tests/**
│   │       ├── **__init__.py**
│   │       └── **test_transactions.py** # Tests for transaction management
├── zenith_wallet/
│   ├── **settings.py**         # Add new apps, DRF, and auth settings
│   ├── **urls.py**             # Include app-level URLs
│   └── ...
└── manage.py
```

**Code Blueprints:**

-   **`apps/users/models.py`**:
    We will create a `UserProfile` model that has a one-to-one relationship with Django's built-in `User` model. This is a standard and highly recommended Django practice for extending the user model without replacing it entirely. This `UserProfile` will initially contain fields like `preferred_currency` (e.g., 'USD', 'GBP') and `created_at`. This design is extensible, allowing us to easily add more profile-specific fields later (e.g., `avatar_url`, `timezone`) without modifying the core authentication model.

-   **`apps/transactions/models.py`**:
    This is the heart of the application's data structure.
    1.  **`Account`**: This model will represent a user's financial account. It will have a foreign key to the `User` model, ensuring each account is owned by a single user. Fields will include `name` (e.g., "Chase Sapphire Preferred"), `account_type` (a choices field with options like 'Checking', 'Savings', 'Credit Card', 'Loan'), and `balance` (a `DecimalField` for high precision).
    2.  **`Category`**: This model allows users to organize their spending. It will also have a foreign key to `User`, allowing users to create their own custom categories. It will simply have a `name` field (e.g., "Groceries").
    3.  **`Transaction`**: The central model. It will have foreign keys to `User`, `Account`, and `Category`. Key fields will be `amount` (`DecimalField`), `transaction_type` ('Income' or 'Expense'), `date`, and a `description` text field. A crucial part of this model will be overriding the `save` method to automatically update the associated `Account`'s balance whenever a transaction is created, updated, or deleted, ensuring data integrity at the model layer.

-   **`apps/users/views.py`**:
    This will contain the API views for authentication, built using Django REST Framework (DRF).
    -   `RegisterView`: An `APIView` that accepts `POST` requests. It will use the `UserSerializer` to validate the incoming data (username, email, password), create a new `User` object, and return a success response.
    -   `LoginView`: An `APIView` that will handle user login. It will take credentials, authenticate the user, and if successful, generate and return a JSON Web Token (JWT) that the client can use for subsequent authenticated requests.

-   **`apps/transactions/views.py`**:
    This will contain `ModelViewSet`s from DRF for `Account`, `Category`, and `Transaction`. Using `ModelViewSet` is highly efficient as it automatically provides the standard CRUD operations (GET, POST, PUT, DELETE). A critical component here will be setting the permissions. We will use DRF's `IsAuthenticated` combined with a custom permission class to ensure that a user can only view and modify their *own* accounts, categories, and transactions. The `get_queryset` method in each `ViewSet` will be overridden to filter the results based on `self.request.user`. This is the most critical security component of the entire application and will be tested rigorously. We will also override the `perform_create` method to automatically associate the logged-in user with any new object they create, preventing the need for the client to send the user ID in the request body. This is both more secure and more convenient.

## 3. Design Architecture

The design of our system is fundamentally centered on the robust and explicit definition of data structures using Pydantic-based schemas, which will be integrated with Django REST Framework. This approach, often referred to as "schema-first," provides a single source of truth for our API's data contracts, ensuring strict validation, clear documentation, and decoupling the API's public shape from the internal database models.

**Pydantic-based Schema Design Philosophy:**
Our entire API will be designed around these schemas. A schema is not just a data container; it is a contract. It defines:
-   **Structure:** The exact fields an API endpoint expects or returns.
-   **Data Types:** The type of each field (e.g., `int`, `str`, `datetime`). Pydantic's strict type enforcement prevents a vast class of common bugs.
-   **Validation Rules:** Sophisticated validation logic beyond simple data types. For example, a password schema can enforce a minimum length and complexity, an email schema can validate the format, and a transaction amount must be a positive number.
-   **Documentation:** These schemas will be used to automatically generate our OpenAPI/Swagger documentation, ensuring that our API documentation is always perfectly in sync with its implementation.

**Key Schema Definitions for CYCLE01:**
-   **`UserRegistrationSchema` (Input):** This schema will define the data required to create a new user. It will include `username` (`str`), `email` (`EmailStr` from Pydantic for format validation), and `password` (`str`). The password field will have a custom validator to enforce a minimum length of 8 characters.
-   **`UserResponseSchema` (Output):** This will define the user data that is safe to return to the client (i.e., without the password hash). It will include `id`, `username`, and `email`.
-   **`TokenSchema` (Output):** A simple schema to standardize the format of the JWT token returned upon successful login, containing an `access_token` field.
-   **`AccountSchema` (Input/Output):** Defines the structure for a financial account. Fields: `id` (output-only), `name` (`str`), `account_type` (`Enum` of allowed types), `balance` (`Decimal`). This ensures that no invalid account types can ever be created.
-   **`CategorySchema` (Input/Output):** Defines a category with `id` and `name` fields.
-   **`TransactionSchema` (Input/Output):** The most critical schema. It will define all the fields of a transaction. For input (creation), it will require `account_id`, `category_id`, `amount`, `transaction_type`, and `date`. The `transaction_type` will be an `Enum` ('Income', 'Expense'). For output, it will be extended to include nested `AccountSchema` and `CategorySchema` objects to provide richer context to the client in a single API call, avoiding the need for follow-up requests. This schema will have a validator that ensures the `amount` is always a positive value.

**Consumers and Producers:**
-   **Producers:** The primary producer of this data will be the Zenith Wallet frontend application, sending JSON data to the API to create and update resources.
-   **Consumers:** The primary consumer is also the frontend, which will receive JSON data from the API to display to the user. Additionally, the auto-generated API documentation will consume these schemas to build an interactive reference for developers.

This schema-centric design is a cornerstone of our strategy for building a reliable and maintainable API. It forces clarity of thought and provides strong guarantees about the data flowing through our system. It makes the API predictable and easy for client-side developers to work with.

## 4. Implementation Approach

The implementation of CYCLE01 will be a methodical, step-by-step process designed to build the foundation of the application in a logical order, with testing integrated at every stage.

1.  **Project Initialization & Configuration:**
    -   Initialize the Django project (`django-admin startproject zenith_wallet`).
    -   Create the `users` and `transactions` apps (`python manage.py startapp users`).
    -   Add `rest_framework` and our new apps to `INSTALLED_APPS` in `settings.py`.
    -   Configure the database connection (PostgreSQL).
    -   Set up Django REST Framework's default settings, specifying JWT as the authentication scheme.

2.  **User Authentication Module:**
    -   Implement the `UserProfile` model in `apps/users/models.py`.
    -   Run `makemigrations` and `migrate` to create the initial database tables.
    -   Define the `UserRegistrationSchema` and `UserResponseSchema` in `apps/users/serializers.py`.
    -   Implement the `RegisterView` and `LoginView` in `apps/users/views.py`. This includes the logic for validating data with the serializer, creating the user, and generating a JWT.
    -   Create `apps/users/urls.py` and wire up the new views. Include this URL file in the main `zenith_wallet/urls.py`.
    -   Write the first tests in `apps/users/tests/test_auth.py` to verify that user registration and login work correctly.

3.  **Transaction Management Core:**
    -   Define the `Account`, `Category`, and `Transaction` models in `apps/transactions/models.py`, including the crucial balance-updating logic in the `Transaction` model's `save` method.
    -   Run `makemigrations` and `migrate` again to add these new tables to the database.
    -   Implement the Pydantic-based schemas (`AccountSchema`, `CategorySchema`, `TransactionSchema`) in `apps/transactions/serializers.py`.

4.  **API Endpoint Implementation:**
    -   In `apps/transactions/views.py`, create `ModelViewSet` classes for `Account`, `Category`, and `Transaction`.
    -   Inside each `ViewSet`, set the `queryset` and `serializer_class` attributes.
    -   **Crucially**, implement the permissioning. Set `permission_classes = [IsAuthenticated]`. Then, override `get_queryset` in each `ViewSet` to return `self.queryset.filter(user=self.request.user)`. This is the key to ensuring data privacy.
    -   Override the `perform_create` method in each `ViewSet` to automatically associate the newly created object with the currently logged-in user (`serializer.save(user=self.request.user)`).
    -   Configure the routing for these `ViewSet`s in `apps/transactions/urls.py` using DRF's `DefaultRouter`. Include this file in the root `urls.py`.

5.  **Testing and Finalization:**
    -   Write extensive tests in `apps/transactions/tests/test_transactions.py`. These tests must cover:
        -   Creating and retrieving accounts, categories, and transactions.
        -   Attempting to access another user's data and asserting that a 403/404 error is returned.
        -   Verifying that creating/updating/deleting a transaction correctly updates the corresponding account balance.
    -   Set up the auto-documentation library (e.g., `drf-spectacular`) to generate an OpenAPI schema.
    -   Manually test all endpoints using a tool like Postman or Insomnia to ensure they behave as expected.

This detailed, test-driven approach ensures that by the end of CYCLE01, we have a highly reliable and secure API foundation.

## 5. Test Strategy

The test strategy for CYCLE01 is comprehensive, focusing on ensuring the correctness, security, and reliability of the application's core. We will adhere to a strict Test-Driven Development (TDD) methodology where practical.

**Unit Testing Approach (Min 300 words):**
Our unit testing philosophy is to test each piece of code in complete isolation. We will use `pytest` and Python's built-in `unittest.mock` library extensively.
-   **Models:** For the models in `transactions/models.py`, the most critical unit test will be for the balance update logic within the `Transaction.save()` method. We will write tests that create an account with an initial balance, then create various transactions (income and expense) linked to it, and assert that the account's balance is updated correctly after each transaction is saved. We will also test the update and delete scenarios. For example, a test will update a transaction's amount and verify the balance reflects this change. Another will delete a transaction and ensure the balance reverts correctly.
-   **Serializers:** The Pydantic-based serializers will have their own suite of unit tests. For the `UserRegistrationSchema`, we will test the password validation logic by attempting to serialize data with passwords that are too short or fail other complexity rules, and assert that a `ValidationError` is raised. For the `TransactionSchema`, we will test the validator that ensures the `amount` is positive, feeding it negative numbers and zero and expecting validation to fail.
-   **Views:** We will unit test the logic within our views where appropriate. For example, in the `LoginView`, we will mock the authentication backend and the token generation utility to test the view's logic of handling successful and failed authentication attempts without needing a real database or user object.

**Integration Testing Approach (Min 300 words):**
Integration tests are designed to verify that the different components of our application work together as a cohesive whole. We will use Django REST Framework's `APITestCase` for this, which provides a test client to make HTTP requests to our API and a test database that is created and destroyed for each test run.
-   **Authentication Flow:** We will write a test that simulates the entire user lifecycle. It will first hit the `/api/users/register/` endpoint with valid data and assert a `201 Created` response. It will then use those same credentials to hit the `/api/users/login/` endpoint, assert a `200 OK` response, and verify that a valid JWT is returned in the response body. Finally, it will use this token in the `Authorization` header to make a request to a protected endpoint (like the user profile endpoint) and assert that it receives a `200 OK` response, proving the token is valid.
-   **Data Isolation and Permissions:** This is the most critical integration test for security. We will create two users in our test database, User A and User B. We will authenticate as User A and create an account. The test will then authenticate as User B and attempt to `GET`, `PUT`, and `DELETE` User A's account using its ID. We will assert that for every one of these attempts, the API returns a `403 Forbidden` or `404 Not Found` status code. This test provides strong confidence that our permissioning system is working correctly and that there is no data leakage between users.
-   **Full Transaction Lifecycle:** We will write a test that covers the end-to-end process of transaction management. It will: 1) Authenticate as a user. 2) Create an account via a `POST` request. 3) Create a category. 4) Create a new transaction linked to that account and category. 5) `GET` the transaction's details and assert the data is correct. 6) `PUT` the transaction to update its amount. 7) Verify that the account's balance in the database has been correctly updated to reflect the change. 8) `DELETE` the transaction and assert it is gone. This single, comprehensive test validates the interaction between our views, serializers, models, and database.
