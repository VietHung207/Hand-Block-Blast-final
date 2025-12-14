import cv2                  # thư viện Opencv: lấy cam
import mediapipe as mp      # thư viện của google : nhận diện tay
import math                 # thư viện toán: tính khoảng cách
import random               # thư viện ngẫu nhiên: dùng để lấy hình dạng khối + màu khối ngẫu nhiên
import os

# CẤU HÌNH
WIDTH, HEIGHT = 1080, 720   # kích thước cửa sổ game 1080x720
CELL_SIZE = 60              # kích thước của khối ô vuông
GRID_SIZE = 8               # KÍCH THƯỚC CỦA BÀN CỜ: 8X8

# Tính toán vị trí
GRID_OFFSET_X = 50
GRID_OFFSET_Y = (HEIGHT - GRID_SIZE*CELL_SIZE) // 2 + 30
UI_START_X = GRID_OFFSET_X + GRID_SIZE*CELL_SIZE + 50

# BẢNG MÀU 
# Định dạng: (R, G, B)
COLORS = [
    (200, 200, 200), # 0: Xám nhạt 
    (231, 76, 60),   # 1: Đỏ
    (241, 196, 15),  # 2: Vàng 
    (46, 204, 113),  # 3: Xanh lá 
    (52, 152, 219),  # 4: Xanh dương 
    (155, 89, 182)   # 5: Tím
]

# --- HÌNH DẠNG KHỐI (SHAPES) ---
SHAPES = [
    [(0,0)],                                  # 1. Khối Đơn 
    [(0,0), (1,0)],                           # 2. Thanh Ngang 
    [(0,0), (0,1), (1,0), (1,1)],             # 3. Khối Vuông Lớn 
    [(0,0), (1,0), (2,0)],                    # 4. Thanh Ngang 
    [(0,0), (1,0), (2,0), (1,1)],             # 5. Khối chữ T 
    [(0,0), (0,1), (0,2), (1,2)]              # 6. Khối chữ L 
]

class HandTracker:
    def __init__(self):
        self.mp_hands = mp.solutions.hands      # GỌI NHẬN DIỆN TAY CỦA THƯ VIỆN MEDIAPIPE
        self.hands = self.mp_hands.Hands()      # KHỞI TẠO NHẬN DIỆN NGÓN TAY
        self.cap = cv2.VideoCapture(0)          # KHỞI TẠO MỞ CAMERA
        
        self.prev_px, self.prev_py = 0, 0       # LƯU VỊ TRÍ NGÓN TAY Ở KHUNG HÌNH TRƯỚC
        self.smooth_factor = 0.5                # HỆ SỐ LÀM MƯỢT


    def get_hand_pos(self):
        ret, frame = self.cap.read()               #đọc khung hình từ cam: chupJ 1 tấm ảnh api xử lí
                
        frame = cv2.flip(frame, 1)          #lật ảnh: 1 là trục dọc
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)    # đổi hệ mẩu từ BGR sang RGB cho media pipe xử lí
        results = self.hands.process(rgb)   #gửi ảnh để xử lí
        
        data = {"detected": False, 
                "px": self.prev_px, 
                "py": self.prev_py,
                "pinching": False}

        if results.multi_hand_landmarks:
            data["detected"] = True
            lm = results.multi_hand_landmarks[0].landmark
            
            # Tọa độ thô
            raw_px = int(lm[8].x * WIDTH)
            raw_py = int(lm[8].y * HEIGHT)
            tx = int(lm[4].x * WIDTH)
            ty = int(lm[4].y * HEIGHT)

            # Làm mượt tọa độ
            px = int(self.prev_px * self.smooth_factor + raw_px * (1 - self.smooth_factor))
            py = int(self.prev_py * self.smooth_factor + raw_py * (1 - self.smooth_factor))
            
            self.prev_px, self.prev_py = px, py

            data["px"], data["py"] = px, py
            data["tx"], data["ty"] = tx, ty
            
            # Kiểm tra gắp (khoảng cách giữa ngón cái và ngón trỏ)
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


# TEST LOGIC
if __name__ == "__main__":
    import pygame
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Backend Debug View")
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
        clock.tick(60)