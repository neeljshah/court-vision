# Basketball Computer Vision — Key Concepts

Reference notes for understanding how the tracker works technically.

---

## Detectron2 / Mask R-CNN

- **What it does:** Instance segmentation — detects every person in frame with a pixel mask + bounding box
- **How we use it:** Detect players, then use bounding box centers as foot positions
- **Model:** Pre-trained on COCO dataset, fine-tunable on basketball footage
- **Output:** List of instances, each with: bbox (x1,y1,x2,y2), mask, confidence score, class label

## Homography

- **What it does:** Maps points from one plane (camera view) to another (2D court top-down)
- **How we compute it:** SIFT feature matching between video frame and panoramic court image → findHomography()
- **Stored as:** 3x3 numpy matrix (.npy file)
- **Usage:** `cv2.perspectiveTransform(player_foot_point, H)` → 2D court coordinate

## SIFT (Scale-Invariant Feature Transform)

- **What it does:** Finds stable feature points in images that can be matched across different viewpoints
- **How we use it:** Match each video frame to the panoramic court image to compute per-frame homography
- **Why it works:** Court markings (lines, paint, three-point arc) are stable SIFT features

## CSRT Tracker

- **Full name:** Discriminative Correlation Filter with Channel and Spatial Reliability
- **What it does:** Tracks a bounding box from frame to frame without re-running detection every frame
- **How we use it:** After detecting the ball, CSRT tracks it between Hough circle checks
- **Limitation:** Fails on fast motion or heavy occlusion

## IoU (Intersection over Union)

- **Formula:** `IoU = Area(A ∩ B) / Area(A ∪ B)`
- **How we use it:**
  - Ball possession: ball bounding box IoU with player bounding box > threshold → possession
  - Player matching: match detected bounding boxes to tracked players across frames

## Hough Circle Transform

- **What it does:** Detects circles in a grayscale image
- **How we use it:** Find ball (circular) in frame
- **Parameters:** minRadius, maxRadius, minDist between circles
- **Limitation:** Needs clear circular edge — fails on motion blur

---

## Court Coordinates

The 2D court map (resources/2d_map.png) uses pixel coordinates:
- Origin: top-left corner of image
- Full court: left half + right half stitched together
- Player positions are in these pixel coordinates after homography transform

---

## Pipeline Flow (Detailed)

```
Frame N
  ↓
SIFT match frame → panorama → compute H_frame
  ↓
Detectron2 → player bounding boxes + masks
  ↓
For each player bbox:
  - classify team (HSV color check on mask region)
  - project foot point through H_frame → 2D court position
  - match to existing player via IoU
  ↓
Hough circles → ball candidates
  + template matching → ball confirmation
  → CSRT update
  ↓
Ball IoU with player bboxes → possession assignment
  ↓
Output: tracking_data row per player per frame
```
