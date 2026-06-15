# Seed Folders

Use these folders to bootstrap Hub's WAI-Spoke with framework updates.

- **seed/ingest**: Framework drops upgrade-adoption-plan.json here during teach operations
- **seed/reference**: Drop reference docs to be indexed and archived in reference/

After running closeout/update, seed/ingest and seed/reference should be empty.

## Hub-Specific Usage

The hub receives framework updates via `seed/ingest/upgrade-adoption-plan.json` just like any spoke. During closeout, the hub processes these updates using the same SpokeUpdateProcessor logic.
