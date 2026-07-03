"""sell -- Milestone-12 productization / sell layer.

Multi-tenant access control for the calibrated predictor product. Provides:
  * sell.authz     -- HMAC-signed API key issuance and verification
  * sell.entitlements -- plan->feature map and feature gating
  * sell.tenancy   -- per-tenant filesystem isolation
  * sell.usage_meter -- atomic per-tenant call counters and quota helpers

The product makes NO dollar-edge claims. edge_claimed=False is a hard constant
on every API surface in this layer (see predict_service.contracts).

INVARIANTS: <=300 LOC/file; ASCII only; no secrets in code; no $-edge field;
build only under sell/; never writes data/registry/; never pushes origin.
"""
