# G340 Local Measurement Environment

Until a repair is applied, local measurements that import the production detector route must use
`conda run -n basketball_ai python` with `prepare_route_imports()` first. Verify with:
`conda run -n basketball_ai python -c "from scripts.platformkit.env_shim import prepare_route_imports; prepare_route_imports(); from ultralytics import YOLO; import src.tracking.osnet_reid"`.

The system `python` is not approved for route measurements until the G340 finisher records a clean
after-shim row. This note does not apply to the pod, which is separate and untouched. The shim is a
workaround; the proposed package changes in `environment_fix_2026-09-08.md` are not applied here.
