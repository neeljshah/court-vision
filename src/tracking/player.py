class Player:
    def __init__(self, ID: int, team: str, color: tuple):
        self.ID = ID
        self.team = team          # 'green', 'white', 'referee'
        self.color = color        # BGR tuple for visualization
        self.previous_bb = None   # (y1, x1, y2, x2) bounding box for IoU matching
        self.positions = {}       # {timestamp: (x_2d, y_2d)} court coordinates
        self.has_ball = False
        # Pose estimation fields (set by AdvancedFeetDetector each frame)
        self.ankle_x:           float | None = None   # pixel x of ankle midpoint
        self.ankle_y:           float | None = None   # pixel y of ankle midpoint
        self.jump_detected:     bool         = False  # True when hip-y rising > 2px/frame
        self.contest_arm_angle: float        = 0.0    # 0=arm at hip, 1=arm above nose
        self.dribble_hand:      str          = "unknown"  # "left" | "right" | "unknown"
