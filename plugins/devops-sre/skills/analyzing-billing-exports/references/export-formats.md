# Billing export formats

Column names differ by export version. The script normalizes names (lowercase, alphanumerics only), so
`lineItem/UnblendedCost` and `line_item_unblended_cost` both match.

## AWS Cost and Usage Report (CUR 1.0 CSV, CUR 2.0 / Data Exports)
- Cost: `lineItem/UnblendedCost` (rate before EDP-style discounts), `lineItem/NetUnblendedCost` (after discounts, only if the export includes it), `reservation/EffectiveCost` and `savingsPlan/SavingsPlanEffectiveCost` (amortized). Pick one and say which.
- `lineItem/LineItemType`: `Usage`, `Fee`, `Tax`, `Credit`, `Refund`, `RIFee`, `DiscountedUsage`, `SavingsPlanCoveredUsage`, `SavingsPlanNegation`, `SavingsPlanRecurringFee`, `SavingsPlanUpfrontFee`, `EdpDiscount`, `PrivateRateDiscount`, `BundledDiscount`.
- Period: `lineItem/UsageStartDate` (hourly or daily), `bill/BillingPeriodStartDate`. Granularity is set when the export is created.
- Dimensions: `lineItem/ProductCode`, `lineItem/UsageType` (for example `NatGateway-Bytes`, `BoxUsage:m5.large`, `PublicIPv4:IdleAddress`, `DataTransfer-Out-Bytes`, `EBS:VolumeUsage.gp2`), `lineItem/ResourceId` (only if resource IDs were enabled), `lineItem/UsageAccountId`, `product/region`.
- Tags appear as columns `resourceTags/user:<Key>` only for activated cost allocation tags; untagged rows have empty values, and tags added later are not applied retroactively.
- Amortization: reservation and Savings Plan fees are billed up front or monthly; an amortized view spreads them over usage, so monthly totals differ from the invoice view.

## GCP billing export to BigQuery (CSV/JSONL from a query or export)
- `cost` (before credits), `credits` (array of `{name, amount}` with negative amounts), `currency`, `usage_start_time`, `service.description`, `sku.description`, `project.id`, `location.region`, `labels`, `usage.amount`.
- Net cost = `cost + SUM(credits.amount)`. Committed use and sustained use discounts appear as credits.
- The export has no backfill: data starts the day it was enabled. The detailed export adds `resource.name`.
- Invoice month (`invoice.month`) can differ from usage month; check which one you group by.

## Azure Cost Management export
- Cost: `CostInBillingCurrency` (actual) or `PreTaxCost` / `Cost` in older exports; `BillingCurrency`.
- Period: `Date` (US `MM/DD/YYYY` in some exports) or `UsageDateTime`; `BillingPeriodStartDate`.
- Dimensions: `MeterCategory`, `MeterSubCategory`, `MeterName`, `ResourceId`, `ResourceGroup`, `SubscriptionId`, `ResourceLocation`, `Tags` (JSON text), `ChargeType` (`Usage`, `Purchase`, `Refund`), `PricingModel` (`OnDemand`, `Reservation`, `SavingsPlan`, `Spot`).
- Reservation purchases are charged when billed; use the amortized export to spread them.

## Generic mapping
A file with a date column and a cost column works. Rename columns like the above, or use `--json` and post-process.

## Sanity checks before trusting a total
- Row count and date range match expectations; the first and last day are complete.
- Compare the month total with the invoice or the console: a mismatch means missing line types, missing accounts, a different cost column, or timing.
- One currency only.
