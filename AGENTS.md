# Omarchy Aurora

**Rulebook:** follow the Aurora Silicon rulebook, https://github.com/aurora-silicon/agent-guidelines/blob/main/AGENTS.md. It applies to every agent and contributor, whoever runs them. This file adds the repo specifics.

- Preserve the immutable ALARM source/snapshot and every hardware package version when extending an image.
- Build only desktop/platform packages here; reuse the signed ALARM hardware repository.
- Keep Aurora's boot, firmware, encryption and account lifecycle. No second firstboot or Limine stack.
- Verify signatures and artifact identities before use. Never commit private keys or device firmware.
- Run pure tests locally. Build large images and run VM qualification in CI; preserve logs and failing images.
- A VM result is not Apple hardware qualification. Publish the exact image candidate whose tests passed.
