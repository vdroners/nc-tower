# Static analysis / l10n (first App Store cut)

- **Psalm:** intentionally deferred — this app has no Composer `composer.json` /
  `vendor/` tree for app-local PHP tooling. Follow-up: add Composer +
  `psalm.xml` targeting `lib/` at `errorLevel="8"`, then tighten with OCP stubs.
- **Frontend l10n:** `l10n/` already ships many locales. Remaining uncovered Vue
  strings can be wrapped in a later pass; English-only store listing is fine for
  the first cut.

Until Psalm lands, PHP review relies on phpunit (where present) and manual review.
