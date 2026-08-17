# Quarantined legacy model artifacts

The repository-root `*_model_realtime.pkl`, `*_scaler_realtime.pkl`, and
`*_features_realtime.pkl` files are preserved in their original locations for
traceability. They were produced by an older 128-feature pipeline and are
logically quarantined: production inference never scans or loads them.

Only a complete, checksum-validated bundle referenced by
`models/production/manifest.json` can generate a production prediction. Moving
the legacy files would break historical tooling, so quarantine is enforced by
the manifest loader rather than by deleting or relocating them.
