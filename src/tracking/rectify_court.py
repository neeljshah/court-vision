import os

import cv2
import numpy as np

from .utils.plot_tools import plt_plot

_RESOURCES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resources")

FLANN_INDEX_KDTREE = 1
flann = cv2.FlannBasedMatcher(
    dict(algorithm=FLANN_INDEX_KDTREE, trees=5),
    dict(checks=50),
)


def collage(frames, direction=1, plot=False):
    sift = cv2.xfeatures2d.SIFT_create()
    current_mosaic = frames[0] if direction == 1 else frames[-1]

    for i in range(len(frames) - 1):
        kp1, des1 = sift.compute(current_mosaic, sift.detect(current_mosaic))
        next_frame = frames[i * direction + direction]
        kp2, des2 = sift.compute(next_frame, sift.detect(next_frame))

        good = [m for m, n in flann.knnMatch(des1, des2, k=2)
                if m.distance < 0.7 * n.distance]

        src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        M, _ = cv2.findHomography(dst_pts, src_pts, cv2.RANSAC, 5.0)

        result = cv2.warpPerspective(
            next_frame, M,
            (current_mosaic.shape[1] + next_frame.shape[1], next_frame.shape[0] + 50)
        )
        result[:current_mosaic.shape[0], :current_mosaic.shape[1]] = current_mosaic
        current_mosaic = result

        for j in range(len(current_mosaic[0])):
            if np.sum(current_mosaic[:, j]) == 0:
                current_mosaic = current_mosaic[:, :j - 50]
                break

        if plot:
            plt_plot(current_mosaic)

    return current_mosaic


def add_frame(frame, pano, pano_enhanced, plot=False):
    sift = cv2.xfeatures2d.SIFT_create()
    kp1, des1 = sift.compute(pano, sift.detect(pano))
    kp2, des2 = sift.compute(frame, sift.detect(frame))

    good = [m for m, n in flann.knnMatch(des1, des2, k=2)
            if m.distance < 0.7 * n.distance]

    print(f"Number of good correspondences: {len(good)}")
    if len(good) < 70:
        return pano_enhanced

    src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, _ = cv2.findHomography(dst_pts, src_pts, cv2.RANSAC, 5.0)
    result = cv2.warpPerspective(frame, M, (pano.shape[1], pano.shape[0]))

    if plot:
        plt_plot(result, "Warped new image")

    avg_pano = np.where(
        result < 100, pano_enhanced,
        np.uint8(np.average([pano_enhanced, result], axis=0, weights=[1, 0.7]))
    )
    if plot:
        plt_plot(avg_pano, "AVG new image")
    return avg_pano


def binarize_erode_dilate(img, plot=False):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, img_otsu = cv2.threshold(gray, 100, 255, cv2.THRESH_OTSU)
    kernel = np.array([[0, 0, 0], [1, 1, 1], [0, 0, 0]], np.uint8)
    img_otsu = cv2.erode(img_otsu, kernel, iterations=20)
    img_otsu = cv2.dilate(img_otsu, kernel, iterations=20)
    if plot:
        plt_plot(img_otsu, "After Erosion-Dilation", cmap="gray")
    return img_otsu


def rectangularize_court(pano, plot=False):
    pano[-4:-1] = pano[0:3] = 0
    pano[:, 0:3] = pano[:, -4:-1] = 0

    mask = np.zeros(pano.shape, dtype=np.uint8)
    cnts = cv2.findContours(pano, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if len(cnts) == 2 else cnts[1]

    contours_court = []
    for c in cnts:
        if cv2.contourArea(c) > 100000:
            cv2.drawContours(mask, [c], -1, (36, 255, 12), -1)
            contours_court.append(c)

    # Fallback: if no large contour found, use the largest available
    if not contours_court:
        if not cnts:
            raise RuntimeError(
                "rectangularize_court: no contours found in binarized panorama. "
                "Check that the panorama contains visible court markings."
            )
        largest = max(cnts, key=cv2.contourArea)
        cv2.drawContours(mask, [largest], -1, (36, 255, 12), -1)
        contours_court = [largest]

    pano = mask
    contours_court = contours_court[0]
    simple_court = np.zeros(pano.shape)

    hull = cv2.convexHull(contours_court)
    cv2.drawContours(pano, [hull], 0, 100, 2)

    epsilon = 0.01 * cv2.arcLength(hull, True)
    approx = cv2.approxPolyDP(hull, epsilon, True)
    corners = approx.reshape(-1, 2)

    # Reduce to exactly 4 corners ordered as [bl, tl, tr, br] for homography()
    # s = x+y: min→TL, max→BR   |   d = x-y: min→BL, max→TR
    if len(corners) != 4:
        s = corners.sum(axis=1)
        d = np.diff(corners, axis=1).reshape(-1)
        corners = np.array([
            corners[np.argmin(d)],   # bottom-left  (min x-y)
            corners[np.argmin(s)],   # top-left     (min x+y)
            corners[np.argmax(d)],   # top-right    (max x-y)
            corners[np.argmax(s)],   # bottom-right (max x+y)
        ])

    cv2.drawContours(simple_court, [approx], 0, 255, 3)

    if plot:
        plt_plot(simple_court, "Rectangularized Court", cmap="gray")

    return simple_court, corners


def homography(rect, image, plot=False):
    bl, tl, tr, br = rect
    rect = np.array([tl, tr, br, bl], dtype="float32")

    widthA  = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
    widthB  = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
    maxWidth = max(int(widthA), int(widthB))

    heightA  = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
    heightB  = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
    maxHeight = max(int(heightA), int(heightB)) + 700

    dst = np.array([[0, 0], [maxWidth - 1, 0],
                    [maxWidth - 1, maxHeight - 1], [0, maxHeight - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))

    if plot:
        plt_plot(warped)
    return warped, M


def rectify(pano_enhanced, corners, plot=False):
    """Compute full-court homography, save Rectify1.npy, return warped court."""
    rectified, M = homography(corners, pano_enhanced)
    np.save(os.path.join(_RESOURCES_DIR, "Rectify1.npy"), M)

    if plot:
        plt_plot(rectified)
    return rectified
