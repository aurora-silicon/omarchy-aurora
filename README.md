# Omarchy Aurora

Omarchy on the shared Aurora ALARM hardware stack for Apple Silicon.

This producer pins the same signed ALARM snapshot and hardware sources as the corresponding Aurora ALARM images, adds Omarchy's desktop and the current Aurora fork of Omarchy Mac support, and retains Aurora's GRUB, per-install firmware and first-boot encryption/account setup.

`sources.lock.json` records every source revision and the ALARM snapshot. `packages/` builds only the desktop and its integration; kernel, Mesa, aura, U-Boot and device services come from the signed Aurora ALARM repository. `omarchy-mac-boot` and its competing Limine/encryption stack are not installed.

CI builds and signs the overlay packages, builds the complete image, runs VM checks on a disposable copy and publishes only passing deliveries. VM evidence distinguishes generic virtual hardware from actual Apple firmware/hardware qualification. Device firmware and calibration are never distributed.

Development is in progress. Published downloads and exact validation evidence will be linked here once the first complete delivery passes.

Snapshots can be created with Snapper. Omarchy's Limine snapshot restore and factory reset are unavailable with Aurora boot; use Aurora recovery or the macOS installer for recovery and reinstalling.
