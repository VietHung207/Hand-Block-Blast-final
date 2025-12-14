import cv2
import mediapipe as mp
import math
import random
import os

# --- CẤU HÌNH (CONSTANTS) ---
WIDTH, HEIGHT = 1080, 720
CELL_SIZE = 60
GRID_SIZE = 8

# Tính toán vị trí cơ bản
GRID_OFFSET_X = 50
GRID_OFFSET_Y = (HEIGHT - GRID_SIZE*CELL_SIZE) // 2 + 30
UI_START_X = GRID_OFFSET_X + GRID_SIZE*CELL_SIZE + 50

# Màu sắc
COLORS = [(200, 200, 200), (231, 76, 60), (241, 196, 15), (46, 204, 113), (52, 152, 219), (155, 89, 182)] 
SHAPES = [ [(0,0)], [(0,0),(1,0)], [(0,0),(0,1),(1,0),(1,1)], [(0,0),(1,0),(2,0)], 
           [(0,0),(1,0),(2,0),(1,1)], [(0,0),(0,1),(0,2),(1,2)] ]

class HandTracker:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        # [TỐI ƯU 1] model_complexity=0 (Lite model) chạy siêu nhanh
        self.hands = self.mp_hands.Hands(
            min_detection_confidence=0.5, 
            min_tracking_confidence=0.5,
            max_num_hands=1,
            model_complexity=0 
        )
        self.cap = cv2.VideoCapture(0)
        
        # [TỐI ƯU 2] Giảm độ phân giải đầu vào xuống 640x480 để xử lý nhanh hơn
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # Biến cho thuật toán làm mượt (Smoothing)
        self.prev_px, self.prev_py = 0, 0
        self.smooth_factor = 0.5 # 0.1 (mượt nhưng chậm) -> 0.9 (nhanh nhưng rung)

        # Biến Frame Skipping
        self.frame_count = 0
        self.skip_rate = 2 # Chỉ xử lý AI mỗi 2 frame
        self.last_result = None

    def get_hand_pos(self):
        ret, frame = self.cap.read()
        if not ret: return {"detected": False, "px":0, "py":0, "tx":0, "ty":0, "pinching":False}
        
        # [TỐI ƯU 3] Frame Skipping: Chỉ xử lý AI nếu frame_count chia hết cho 2
        self.frame_count += 1
        process_this_frame = (self.frame_count % self.skip_rate == 0)

        data = {"detected": False, "px": self.prev_px, "py": self.prev_py, "tx": 0, "ty": 0, "pinching": False}

        if process_this_frame:
            # Lật ảnh và xử lý
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.last_result = self.hands.process(rgb)
        
        # Dùng kết quả (hoặc kết quả cũ nếu skip frame)
        if self.last_result and self.last_result.multi_hand_landmarks:
            data["detected"] = True
            lm = self.last_result.multi_hand_landmarks[0].landmark
            
            # Lấy tọa độ thô (Raw)
            raw_px = int(lm[8].x * WIDTH)
            raw_py = int(lm[8].y * HEIGHT)
            tx = int(lm[4].x * WIDTH)
            ty = int(lm[4].y * HEIGHT)

            # [TỐI ƯU 4] Smoothing: Công thức trung bình động để con trỏ không bị rung
            # Vị trí mới = (Vị trí cũ * 0.5) + (Vị trí thô * 0.5)
            px = int(self.prev_px * self.smooth_factor + raw_px * (1 - self.smooth_factor))
            py = int(self.prev_py * self.smooth_factor + raw_py * (1 - self.smooth_factor))
            
            self.prev_px, self.prev_py = px, py

            data["px"], data["py"] = px, py
            data["tx"], data["ty"] = tx, ty
            
            # Logic Pinch (Gắp)
            # Vì giảm độ phân giải, khoảng cách pixel thực tế sẽ nhỏ hơn, nên giảm ngưỡng từ 40 -> 30 hoặc giữ nguyên tùy cảm giác
            if math.hypot(px-tx, py-ty) < 50: 
                data["pinching"] = True
        
        return data

    def release(self):
        self.cap.release()

class GameLogic:
    def __init__(self):
        self.grid = [[0]*GRID_SIZE for _ in range(GRID_SIZE)]
        self.tray = self.new_tray()
        self.score = 0
        self.high_score = self.load_high_score()
        self.state = "MENU"
        self.game_started = False
        self.holding = False
        self.held_idx = -1

    def load_high_score(self):
        if os.path.exists("score.txt"): 
            try: return int(open("score.txt").read())
            except: return 0
        return 0

    def new_tray(self):
        return [{"shape": random.choice(SHAPES), "color": random.randint(1, 5)} for _ in range(3)]

    def reset_game(self):
        self.grid = [[0]*GRID_SIZE for _ in range(GRID_SIZE)]
        self.tray = self.new_tray()
        self.score = 0
        self.game_started = True
        self.state = "PLAYING"

    def can_place(self, blk, gx, gy):
        for dx, dy in blk["shape"]:
            nx, ny = gx + dx, gy + dy
            if nx < 0 or ny < 0 or nx >= GRID_SIZE or ny >= GRID_SIZE or self.grid[ny][nx]: 
                return False
        return True

    def place_block(self, blk, gx, gy):
        for dx, dy in blk["shape"]: 
            self.grid[gy+dy][gx+dx] = blk["color"]
        self.score += len(blk["shape"])
        
        rows = [r for r in range(GRID_SIZE) if all(self.grid[r])]
        cols = [c for c in range(GRID_SIZE) if all(self.grid[r][c] for r in range(GRID_SIZE))]
        
        for r in rows: self.grid[r] = [0]*GRID_SIZE
        for c in cols: 
            for r in range(GRID_SIZE): self.grid[r][c] = 0
            
        if (len(rows) + len(cols)) > 0: self.score += (len(rows) + len(cols)) * 10
        if self.score > self.high_score:
            self.high_score = self.score
            with open("score.txt", "w") as f: f.write(str(self.high_score))

    def check_game_over(self):
        if not self.holding:
            moves_left = False
            for blk in self.tray:
                if blk:
                    for r in range(GRID_SIZE):
                        for c in range(GRID_SIZE):
                            if self.can_place(blk, c, r):
                                moves_left = True
                                break
            if not moves_left: self.state = "GAMEOVER"

# -----------------------------------------------------------
# PHẦN CHẠY ĐỘC LẬP (DEBUG MODE - SIÊU ĐƠN GIẢN)
# -----------------------------------------------------------
if __name__ == "__main__":
    import pygame
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Backend Debug View (Optimized)")
    clock = pygame.time.Clock()
    
    logic = GameLogic()
    logic.reset_game()
    tracker = HandTracker()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
        
        hand = tracker.get_hand_pos()
        px, py = hand["px"], hand["py"]
        
        if hand["pinching"] and not logic.holding:
            for i, blk in enumerate(logic.tray):
                if blk and UI_START_X < px < WIDTH and 300 + i*140 < py < 430 + i*140:
                    logic.holding, logic.held_idx = True, i
        elif not hand["pinching"] and logic.holding:
            gx, gy = (px - GRID_OFFSET_X) // CELL_SIZE, (py - GRID_OFFSET_Y) // CELL_SIZE
            blk = logic.tray[logic.held_idx]
            if logic.can_place(blk, gx, gy):
                logic.place_block(blk, gx, gy)
                logic.tray[logic.held_idx] = None
                if all(b is None for b in logic.tray): logic.tray = logic.new_tray()
            logic.holding, logic.held_idx = False, -1

        screen.fill((0, 0, 0))
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                x, y = GRID_OFFSET_X + c*CELL_SIZE, GRID_OFFSET_Y + r*CELL_SIZE
                pygame.draw.rect(screen, (50, 50, 50), (x, y, CELL_SIZE, CELL_SIZE), 1)
                if logic.grid[r][c]:
                    pygame.draw.rect(screen, COLORS[logic.grid[r][c]], (x+2, y+2, CELL_SIZE-4, CELL_SIZE-4))

        for i, blk in enumerate(logic.tray):
            if blk and not (logic.holding and logic.held_idx == i):
                cx, cy = UI_START_X + 50, 300 + i*140
                for dx, dy in blk["shape"]:
                    pygame.draw.rect(screen, COLORS[blk["color"]], (cx + dx*30, cy + dy*30, 25, 25))

        if logic.holding:
            blk = logic.tray[logic.held_idx]
            for dx, dy in blk["shape"]:
                pygame.draw.rect(screen, COLORS[blk["color"]], (px + dx*30, py + dy*30, 25, 25))

        if hand["detected"]:
            col = (0, 255, 0) if hand["pinching"] else (255, 0, 0)
            pygame.draw.circle(screen, col, (px, py), 10)

        pygame.display.flip()
        # [QUAN TRỌNG] Giới hạn FPS ở 60 để game không ngốn 100% CPU
        clock.tick(60)