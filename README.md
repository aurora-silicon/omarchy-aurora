# Omarchy Aurora

Omarchy on the shared Aurora ALARM hardware stack for Apple Silicon.

This producer pins the same signed ALARM snapshot and hardware sources as the corresponding Aurora ALARM images, adds Omarchy's desktop and the current Aurora fork of Omarchy Mac support, and retains Aurora's GRUB, per-install firmware and first-boot encryption/account setup.

`sources.lock.json` records every source revision and the ALARM snapshot. `packages/` builds only the desktop and its integration; kernel, Mesa, aura, U-Boot and device services come from the signed Aurora ALARM repository. `omarchy-mac-boot` and its competing Limine/encryption stack are not installed.

CI builds and signs the overlay packages, builds the complete image, runs VM checks on a disposable copy and publishes only passing deliveries. VM evidence distinguishes generic virtual hardware from actual Apple firmware/hardware qualification. Device firmware and calibration are never distributed.

Package validation runs the complete `omarchy-mac` unit suite and the runtime integration tests listed in `sources.lock.json`. Those cover the shipped Mac platform package; Aurora's encryption, owner setup, reboot and desktop are qualified through the complete image's VM test.

Development is in progress. Published downloads and exact validation evidence will be linked here once the first complete delivery passes.

Snapshots can be created with Snapper. Omarchy's Limine snapshot restore and factory reset are unavailable with Aurora boot; use Aurora recovery or the macOS installer for recovery and reinstalling.

To rebuild a pinned release, run `gh workflow run packages.yml --repo aurora-silicon/omarchy-aurora --ref main`. CI builds and tests the packages, signs an immutable snapshot, deploys the package feed, then builds and VM-tests the image before publishing its signed installer payload.

For an image-only change, run `gh workflow run images.yml --repo aurora-silicon/omarchy-aurora --ref main -f overlay-snapshot=testing-YYYYMMDD.N` with a signed snapshot matching the source lock. A successful image run can also be published explicitly with `publish-payload.yml -f image-run=RUN_ID`; the shared workflow authenticates its artifacts and VM results again.

When updating the ALARM base, keep `sources.json`, the locked snapshot manifest and its signed-database package versions aligned. Runtime or Mac package updates also update the matching recipe versions. No local kernel or desktop compilation is required to install an image.
