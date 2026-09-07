# 02 — Definition of Done

Applies to every feature in `/features`, in addition to that feature's own Acceptance Criteria. A feature isn't complete until all four are true.

## 1. Functional Requirements Covered
Every FR — and lettered sub-requirement, e.g. FR-2a — listed in the feature doc is implemented. A happy path that skips an explicitly stated error case (a broken URL, a provider timeout, a fallback trigger) doesn't count as done.

## 2. Unit Test Coverage
All implemented functionality has unit tests, not just the happy path. At minimum: one test per FR, plus the failure and edge cases the feature doc calls out explicitly.

## 3. No Dead Comments
Remove comments that just restate the code (`# increment i` above `i += 1`), or leftover scaffolding from AI-assisted drafting that was never reviewed. A comment earns its place only by explaining *why* — a non-obvious business rule, a workaround for a specific constraint, a decision that isn't self-evident from the code alone.

## 4. Locally Verified
The feature is exercised manually against a real running `docker-compose up` environment, not just passing unit tests in isolation. This is what catches what unit tests miss: service wiring, environment variables, Docker networking, and integration gaps between features.

---

This checklist doesn't replace a feature's own Acceptance Criteria section — it's the baseline quality bar underneath all of them.
