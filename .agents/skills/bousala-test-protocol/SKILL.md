---
name: bousala-test-protocol
description: Testing governance for the Bousala project. Load when adding, modifying, or running tests in dev_test_runner.py, or when determining whether a change requires regression validation. Enforces test-count rules, mandatory reporting, and test category conventions.
---

# Bousala Test Protocol

## Purpose

This skill governs all testing activity in Bousala.

No implementation is considered complete until validation and regression testing are performed.

────────────────────────────

## Core Rule

Test coverage must never decrease.

If functionality is added:

* Existing tests must still pass
* New tests should be added when appropriate

────────────────────────────

## Mandatory Reporting

After every implementation provide:

* Files modified
* Functions modified
* New files added
* Tests executed
* Tests passed
* Tests failed
* Remaining risks

────────────────────────────

## Critical Test Areas

Any change affecting:

* Holdings
* Accounts
* Transactions
* Cash
* FX
* Valuation
* Allocation
* Performance
* Risk

requires regression validation.

────────────────────────────

## Regression Rule

When modifying an existing feature:

Verify:

1. Existing behavior still works
2. Related features still work
3. No unintended side effects exist

────────────────────────────

## Test Categories

HLD = Holdings

ACC = Accounts

TXN = Transactions

CASH = Cash

FX = Currency

VAL = Valuation

ALLOC = Allocation

PERF = Performance

RISK = Risk

SEC = SEC Research

SAHMK = Saudi Market Layer

────────────────────────────

## Developer Test Runner Rule

When a new feature is implemented:

1. Determine whether a new regression test category is required.
2. If required:
    * Add the test category to dev_test_runner.py
    * Register it in run_all_tests()
    * Include it in test reporting output
3. Existing test categories must never be removed without explicit approval.

Test count must be maintained or increased.

────────────────────────────

## Completion Rule

Implementation is not complete until:

1. Code is implemented
2. Validation performed
3. Regression checks performed
4. Results reported

────────────────────────────

## Failure Rule

If any blocker defect is discovered:

Do not mark task complete.

Report:

* defect
* impact
* affected files
* recommended fix

before continuing.
