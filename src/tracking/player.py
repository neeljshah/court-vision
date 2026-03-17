class Player:
    def __init__(self, ID: int, team: str, color: tuple):
        self.ID = ID
        self.team = team          # 'green', 'white', 'referee'
        self.color = color        # BGR tuple for visualization
        self.previous_bb = None   # (y1, x1, y2, x2) bounding box for IoU matching
        self.positions = {}       # {timestamp: (x_2d, y_2d)} court coordinates
        self.has_ball = False
