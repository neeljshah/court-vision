# Detector weight provenance

Only the following ONNX artifact is approved for the non-AGPL detector path.
The hash is checked during the 2026-09-01 comparison run; a different file is
not covered by this record.

| Artifact | SHA-256 | Upstream source | Licence |
| --- | --- | --- | --- |
| `yolox_s.onnx` | `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063` | Megvii YOLOX v0.1.1rc0 official release | Apache-2.0 |

`yolov8n.pt` is not approved for commercial use.  It was used only as the
baseline comparison model from the local Ultralytics installation and is
licensed AGPL-3.0 by Ultralytics.  Fine-tuning that artifact does not alter
its licence.

The runtime receives a model path explicitly.  Before deploying a replacement
or a fine-tuned weight, record its exact upstream licence and SHA-256 here;
do not infer a weight licence merely from a similarly named architecture.
