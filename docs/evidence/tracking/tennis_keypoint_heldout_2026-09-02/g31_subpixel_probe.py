"""G31 probe: does sub-pixel heatmap decoding change the 7px verdict? No retraining."""
import json, torch
from torch.utils.data import DataLoader
from pathlib import Path
from scripts.platformkit.tracking import tennis_keypoint_train as T

HEAT_W, HEAT_H = T.HEAT_W, T.HEAT_H

def decode_subpixel(hm, sizes):
    B, K, H, W = hm.shape
    idx = hm.flatten(2).argmax(2)
    x = idx.remainder(W).float()
    y = idx.div(W, rounding_mode="floor").float()
    bi = torch.arange(B)[:, None].expand(B, K)
    ki = torch.arange(K)[None, :].expand(B, K)
    def val(xx, yy):
        return hm[bi, ki, yy.clamp(0, H - 1).long(), xx.clamp(0, W - 1).long()]
    c, xm, xp = val(x, y), val(x - 1, y), val(x + 1, y)
    ym, yp = val(x, y - 1), val(x, y + 1)
    dx = (0.5 * (xp - xm) / (2 * c - xp - xm + 1e-6)).clamp(-0.5, 0.5)
    dy = (0.5 * (yp - ym) / (2 * c - yp - ym + 1e-6)).clamp(-0.5, 0.5)
    pts = torch.stack((x + dx, y + dy), -1)
    return pts * sizes[:, None, :] / pts.new_tensor((W, H))

def run(fold):
    paths = sorted(Path("docs/evidence/tracking/tennis_pseudolabels_2026-09-02").glob("g23_*.jsonl"))
    rows, _ = T.load_rows(paths)
    _, test_rows, held = T.split_fold(rows, fold)
    ds = T.TennisDataset(test_rows, False, True); ds.preload()
    loader = DataLoader(ds, batch_size=16, shuffle=False, num_workers=0)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = T.TennisKeypointNet(True).to(dev)
    model.load_state_dict(torch.load("data/models/tennis_keypoints_fold%d.pt" % fold, map_location=dev)["model"])
    model.eval()
    argm, subp, tgt, vis = [], [], [], []
    done = 0
    with torch.no_grad():
        for image, _, points, mask in loader:
            n = len(image)
            sizes = torch.tensor([[r["width"], r["height"]] for r in ds.rows[done:done + n]], dtype=torch.float32)
            hm = model(image.to(dev)).cpu()
            argm.append(T.decode_heatmaps(hm, sizes))
            subp.append(decode_subpixel(hm, sizes))
            tgt.append(points); vis.append(mask); done += n
    tgt, vis = torch.cat(tgt), torch.cat(vis)
    out = {"fold": fold, "held_out": held, "test_frames": len(test_rows),
           "px_per_heatmap_cell_x": 1920.0 / HEAT_W, "px_per_heatmap_cell_y": 1080.0 / HEAT_H}
    for name, pred in (("argmax", torch.cat(argm)), ("subpixel", torch.cat(subp))):
        m = T.pck_metrics(pred, tgt, vis)
        out[name] = {k: round(v, 6) for k, v in m.items()}
        err = torch.linalg.vector_norm(pred - tgt, dim=-1)[vis]
        out[name]["median_cells"] = round(float(err.median()) / (1920.0 / HEAT_W), 4)
        out[name]["p90_px"] = round(float(err.quantile(0.9)), 3)
    print(json.dumps(out, sort_keys=True), flush=True)

for f in (0, 1):
    run(f)
