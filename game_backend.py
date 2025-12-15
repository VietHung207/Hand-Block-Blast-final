import cv2
import mediapipe as mp
import math
import random
import os

# --- CẤU HÌNH ---
WIDTH, HEIGHT = 1080, 720
CELL_SIZE = 60
GRID_SIZE = 8
GRID_OFFSET_X = 50
GRID_OFFSET_Y = (HEIGHT - GRID_SIZE*CELL_SIZE) // 2 + 30
UI_START_X = GRID_OFFSET_X + GRID_SIZE*CELL_SIZE + 50

COLORS = [
    (200, 200, 200), (231, 76, 60), (241, 196, 15), 
    (46, 204, 113), (52, 152, 219), (155, 89, 182)
]

SHAPES = [
    [(0,0)], [(0,0), (1,0)], [(0,0), (0,1), (1,0), (1,1)], 
    [(0,0), (1,0), (2,0)], [(0,0), (1,0), (2,0), (1,1)], [(0,0), (0,1), (0,2), (1,2)]
]

class HandTracker:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            max_num_hands=1,              # Chỉ nhận tối đa 1 tay
            min_detection_confidence=0.7, # [QUAN TRỌNG] Phải nhìn rất rõ tay mới bắt đầu nhận
            min_tracking_confidence=0.9   # [QUAN TRỌNG] Đã bắt được rồi thì bám cực chặt (90%)
        )
        self.mp_draw = mp.solutions.drawing_utils 
        
        self.cap = cv2.VideoCapture(0)
        self.cap.set(3, 640)
        self.cap.set(4, 480)
        
        self.prev_px, self.prev_py = 0, 0
        self.smooth_factor = 0.5
        
        # Biến để khóa tay (Chỉ nhận tay trái hoặc phải)
        self.locked_hand_label = None 
        self.loss_frame_count = 0 # Đếm số frame bị mất tay

    def get_hand_pos(self):
        ret, frame = self.cap.read()
        if not ret: return {"detected": False, "px":0, "py":0, "pinching":False}

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)

        data = {"detected": False, "px": self.prev_px, "py": self.prev_py, "tx":0, "ty":0, "pinching": False, "image": frame}

        # Nếu phát hiện tay
        if results.multi_hand_landmarks and results.multi_handedness:
            # Lấy thông tin tay (Trái hay Phải?)
            hand_label = results.multi_handedness[0].classification[0].label
            
            # --- LOGIC KHÓA TAY ---
            # 1. Nếu chưa khóa tay nào -> Khóa tay hiện tại
            if self.locked_hand_label is None:
                self.locked_hand_label = hand_label
            
            # 2. Nếu tay mới KHÔNG PHẢI tay đang khóa -> Bỏ qua (Không xử lý)
            if hand_label == self.locked_hand_label:
                # Reset biến đếm mất tay vì đã tìm thấy đúng tay
                self.loss_frame_count = 0
                
                data["detected"] = True
                hand_lms = results.multi_hand_landmarks[0]
                lm = hand_lms.landmark

                # --- XỬ LÝ TỌA ĐỘ NHƯ CŨ ---
                self.mp_draw.draw_landmarks(frame, hand_lms, self.mp_hands.HAND_CONNECTIONS)

                h, w, c = frame.shape
                cx8, cy8 = int(lm[8].x * w), int(lm[8].y * h)
                cx4, cy4 = int(lm[4].x * w), int(lm[4].y * h)

                cv2.circle(frame, (cx8, cy8), 10, (255, 0, 255), cv2.FILLED)
                cv2.circle(frame, (cx4, cy4), 10, (255, 0, 255), cv2.FILLED)

                raw_px, raw_py = int(lm[8].x * WIDTH), int(lm[8].y * HEIGHT)
                tx, ty = int(lm[4].x * WIDTH), int(lm[4].y * HEIGHT)

                px = int(self.prev_px * self.smooth_factor + raw_px * (1 - self.smooth_factor))
                py = int(self.prev_py * self.smooth_factor + raw_py * (1 - self.smooth_factor))
                self.prev_px, self.prev_py = px, py

                data.update({"px": px, "py": py, "tx": tx, "ty": ty})
                
                if math.hypot(px-tx, py-ty) < 50: 
                    data["pinching"] = True
                    cv2.line(frame, (cx8, cy8), (cx4, cy4), (0, 255, 0), 3)

                # Vẽ chữ báo hiệu đang khóa tay nào
                cv2.putText(frame, f"LOCKED: {hand_label}", (10, 30), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 2)
            else:
                # Nếu sai tay thì hiển thị cảnh báo
                cv2.putText(frame, f"WRONG HAND! USE {self.locked_hand_label}", (10, 30), cv2.FONT_HERSHEY_PLAIN, 1.5, (0, 0, 255), 2)
        else:
            # Nếu không thấy tay, tăng biến đếm
            self.loss_frame_count += 1
            # Nếu mất tay quá 60 frame (khoảng 1-2 giây) -> Reset khóa để cho phép đổi tay
            if self.loss_frame_count > 60:
                self.locked_hand_label = None

        # CHÚ THÍCH 2 DÒNG DƯỚI NẾU MUỐN TẮT CỬA SỔ CAMERA PHỤ
        # cv2.imshow("Camera Feedback", frame)
        # cv2.waitKey(1)

        data["image"] = frame
        return data

    def release(self):
        self.cap.release()
        # cv2.destroyAllWindows()

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