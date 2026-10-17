from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.core.text import LabelBase
import random
import copy
import time

# ================== 字体注册 ==================
LabelBase.register(name='ChineseFont', fn_regular='msyh.ttc')

# ================== 设定区域 ==================
X_SIZE = 4
Y_SIZE = 4
MAX_DEPTH = 3   # Expectimax 搜索深度，3 推荐，改 2 更快、改 4 更狠
# ===============================================

# ---------- 基础操作 ----------
def create_board():
    return [[0] * X_SIZE for _ in range(Y_SIZE)]

def merge_line(line):
    non_zero = [v for v in line if v != 0]
    result = []
    i = 0
    while i < len(non_zero):
        if i + 1 < len(non_zero) and non_zero[i] == non_zero[i + 1]:
            result.append(non_zero[i] * 2)
            i += 2
        else:
            result.append(non_zero[i])
            i += 1
    result += [0] * (X_SIZE - len(result))
    return result

def move_left(board):
    for i in range(Y_SIZE):
        board[i] = merge_line(board[i])

def move_right(board):
    for i in range(Y_SIZE):
        board[i] = merge_line(board[i][::-1])[::-1]

def move_up(board):
    for j in range(X_SIZE):
        col = [board[i][j] for i in range(Y_SIZE)]
        new_col = merge_line(col)
        for i in range(Y_SIZE):
            board[i][j] = new_col[i]

def move_down(board):
    for j in range(X_SIZE):
        col = [board[i][j] for i in range(Y_SIZE)][::-1]
        new_col = merge_line(col)[::-1]
        for i in range(Y_SIZE):
            board[i][j] = new_col[i]

MOVE_FUNCS = [move_left, move_right, move_up, move_down]

# ---------- 统计玩家有效移动方向 ----------
def count_valid_moves(board):
    """返回玩家当前所有有效移动方向的数量"""
    valid_dirs = 0
    for move_func in MOVE_FUNCS:
        test_board = [row[:] for row in board]
        move_func(test_board)
        if test_board != board:
            valid_dirs += 1
    return valid_dirs

# ---------- 棋盘评估：从 AI 视角看，分数越高对玩家越不利 ----------
def evaluate_for_ai(board):
    # 1. 压力评估
    valid_count = count_valid_moves(board)
    if valid_count == 0:
        return 999999999  # 玩家死局
    elif valid_count == 1:
        forced_move_bonus = 200000
    elif valid_count == 2:
        forced_move_bonus = 5000
    else:
        forced_move_bonus = 0

    score = forced_move_bonus

    # 2. 空格惩罚
    empty = [(i, j) for i in range(Y_SIZE) for j in range(X_SIZE) if board[i][j] == 0]
    if len(empty) <= 3:
        score -= len(empty) * 500
    else:
        score -= len(empty) * 100

    # 3. 最大值位置
    max_val = 0
    max_pos = (-1, -1)
    for i in range(Y_SIZE):
        for j in range(X_SIZE):
            if board[i][j] > max_val:
                max_val = board[i][j]
                max_pos = (i, j)
    corners = [(0,0), (0,X_SIZE-1), (Y_SIZE-1,0), (Y_SIZE-1,X_SIZE-1)]
    if max_pos not in corners:
        score += 50000
    else:
        neighbors = [board[max_pos[0]+di][max_pos[1]+dj]
                     for di, dj in [(-1,0),(1,0),(0,-1),(0,1)]
                     if 0 <= max_pos[0]+di < Y_SIZE and 0 <= max_pos[1]+dj < X_SIZE]
        if max_val >= 128 and max(neighbors) < max_val // 4:
            score += 3000

    # 4. 合并潜力（指数级惩罚）
    for r in range(Y_SIZE):
        for c in range(X_SIZE):
            if board[r][c] != 0:
                if c + 1 < X_SIZE and board[r][c] == board[r][c+1]:
                    score -= (board[r][c] * 2) ** 2
                if r + 1 < Y_SIZE and board[r][c] == board[r+1][c]:
                    score -= (board[r][c] * 2) ** 2

    # 5. 平滑度（差异大是好事）
    smoothness = 0
    for r in range(Y_SIZE):
        for c in range(X_SIZE):
            if board[r][c] != 0:
                if c + 1 < X_SIZE and board[r][c+1] != 0:
                    smoothness += abs(board[r][c] - board[r][c+1])
                if r + 1 < Y_SIZE and board[r+1][c] != 0:
                    smoothness += abs(board[r][c] - board[r+1][c])
    score += smoothness * 3

    # 6. 单调性（AI 想要低单调性）
    monotonicity = 0
    for r in range(Y_SIZE):
        for c in range(X_SIZE - 1):
            if board[r][c] != 0 and board[r][c+1] != 0:
                monotonicity += 1 if board[r][c] > board[r][c+1] else -1
    for c in range(X_SIZE):
        for r in range(Y_SIZE - 1):
            if board[r][c] != 0 and board[r+1][c] != 0:
                monotonicity += 1 if board[r][c] > board[r+1][c] else -1
    score -= monotonicity * 200

    # 7. 蛇形阵检测
    snake_score = 0
    for r in range(Y_SIZE):
        row = board[r] if r % 2 == 0 else board[r][::-1]
        for c in range(X_SIZE - 1):
            if row[c] != 0 and row[c+1] != 0:
                if row[c] > row[c+1]:
                    snake_score += 1
                elif row[c] < row[c+1]:
                    snake_score -= 1
    score -= snake_score * 300

    return score

# ---------- Expectimax 搜索 ----------
def player_move_max(board, depth):
    """玩家层：玩家会选择让 AI 得分最低的方向"""
    if depth == 0:
        return evaluate_for_ai(board)

    best = float('inf')
    for move_func in MOVE_FUNCS:
        next_board = [row[:] for row in board]
        move_func(next_board)
        if next_board == board:
            continue
        score = ai_place_max(next_board, depth - 1)
        if score < best:
            best = score
    if best == float('inf'):
        return evaluate_for_ai(board)
    return best

def ai_place_max(board, depth):
    """AI 节点：遍历所有（位置，数字）组合，返回最优评分"""
    if depth == 0:
        return evaluate_for_ai(board)

    empty = [(i, j) for i in range(Y_SIZE) for j in range(X_SIZE) if board[i][j] == 0]
    if not empty:
        return evaluate_for_ai(board)

    best = -float('inf')
    for (i, j) in empty:
        for val in [2, 4]:
            new_board = [row[:] for row in board]
            new_board[i][j] = val
            score = player_move_max(new_board, depth - 1)
            if score > best:
                best = score
    return best

def ai_choose_position(board):
    """AI 实际选择：遍历所有（位置，数字）组合，选让玩家最难受的"""
    empty = [(i, j) for i in range(Y_SIZE) for j in range(X_SIZE) if board[i][j] == 0]
    if not empty:
        return None

    best_score = -float('inf')
    best_choice = None

    for (i, j) in empty:
        for val in [2, 4]:
            new_board = [row[:] for row in board]
            new_board[i][j] = val
            exp_score = player_move_max(new_board, MAX_DEPTH - 1)
            # 压力加成
            valid_count = count_valid_moves(new_board)
            if valid_count == 0:
                exp_score += 100000000
            elif valid_count == 1:
                exp_score += 200000
            if exp_score > best_score:
                best_score = exp_score
                best_choice = (i, j, val)

    return best_choice

def add_evil_random(board):
    result = ai_choose_position(board)
    if result:
        i, j, val = result
        board[i][j] = val

# ---------- Kivy UI ----------
COLORS = {
    0:    (0.80, 0.75, 0.71, 1),
    2:    (0.93, 0.89, 0.85, 1),
    4:    (0.93, 0.88, 0.78, 1),
    8:    (0.95, 0.69, 0.47, 1),
    16:   (0.96, 0.58, 0.39, 1),
    32:   (0.96, 0.49, 0.37, 1),
    64:   (0.96, 0.37, 0.23, 1),
    128:  (0.93, 0.81, 0.45, 1),
    256:  (0.93, 0.80, 0.38, 1),
    512:  (0.93, 0.78, 0.31, 1),
    1024: (0.93, 0.77, 0.25, 1),
    2048: (0.93, 0.76, 0.18, 1),
}

class Tile(Label):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.font_name = 'ChineseFont'
        self.font_size = dp(36)
        self.bold = True
        self.color = (0.47, 0.43, 0.40, 1)
        with self.canvas.before:
            self.bg_color = Color(*COLORS[0])
            self.rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def set_value(self, val):
        if val == 0:
            self.text = ""
            self.bg_color.rgba = COLORS[0]
        else:
            self.text = str(val)
            self.bg_color.rgba = COLORS.get(val, (0.15, 0.12, 0.10, 1))
            if val <= 4:
                self.color = (0.47, 0.43, 0.40, 1)
            else:
                self.color = (1, 1, 1, 1)

class Game2048(App):
    def on_stop(self):
        Window.unbind(on_touch_down=self.on_touch_down)
        Window.unbind(on_touch_up=self.on_touch_up)
        Window.unbind(on_key_down=self.on_key_down)
        import os
        os._exit(0)

    def build(self):
        self.board = create_board()
        self.history = []
        self.last_z_time = 0
        self.touch_start = None

        add_evil_random(self.board)
        add_evil_random(self.board)

        self.root_layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(15))
        with self.root_layout.canvas.before:
            self.root_bg = Color(0.73, 0.68, 0.63, 1)
            self.root_rect = Rectangle(pos=self.root_layout.pos, size=self.root_layout.size)
        self.root_layout.bind(pos=self.update_root_rect, size=self.update_root_rect)

        self.title_label = Label(text="幸运_2048", font_size=dp(24), size_hint_y=None, height=dp(50), font_name='ChineseFont')
        self.root_layout.add_widget(self.title_label)

        self.grid_container = FloatLayout()
        self.grid = GridLayout(cols=X_SIZE, spacing=dp(8), size_hint=(None, None))
        self.grid_container.add_widget(self.grid)
        self.root_layout.add_widget(self.grid_container)
        self.grid_container.bind(size=self.update_grid_size)

        self.tiles = []
        for i in range(Y_SIZE):
            row_tiles = []
            for j in range(X_SIZE):
                tile = Tile()
                self.grid.add_widget(tile)
                row_tiles.append(tile)
            self.tiles.append(row_tiles)

        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(60), spacing=dp(20))
        self.undo_btn = Button(text="撤回 (Z)", background_color=(0.5, 0.5, 0.5, 1), font_name='ChineseFont')
        self.undo_btn.bind(on_press=self.do_undo)
        btn_layout.add_widget(self.undo_btn)
        self.restart_btn = Button(text="重开 (R)", background_color=(0.8, 0.3, 0.3, 1), font_name='ChineseFont')
        self.restart_btn.bind(on_press=self.do_restart)
        btn_layout.add_widget(self.restart_btn)
        self.root_layout.add_widget(btn_layout)

        Window.bind(on_touch_down=self.on_touch_down)
        Window.bind(on_touch_up=self.on_touch_up)
        Window.bind(on_key_down=self.on_key_down)

        self.update_grid_size(None, None)
        self.update_ui()
        self.print_board_to_console()
        return self.root_layout

    def on_key_down(self, window, key, *args):
        if key == 273 or key == 119:
            self.move_and_update(move_up)
        elif key == 274 or key == 115:
            self.move_and_update(move_down)
        elif key == 276 or key == 97:
            self.move_and_update(move_left)
        elif key == 275 or key == 100:
            self.move_and_update(move_right)
        return False

    def update_grid_size(self, instance, value):
        avail_w = self.grid_container.width
        avail_h = self.grid_container.height
        side = min(avail_w, avail_h) * 0.95
        self.grid.size = (side, side)
        self.grid.pos = (
            self.grid_container.x + (avail_w - side) / 2,
            self.grid_container.y + (avail_h - side) / 2
        )

    def update_root_rect(self, instance, value):
        self.root_rect.pos = instance.pos
        self.root_rect.size = instance.size

    def update_ui(self):
        for i in range(Y_SIZE):
            for j in range(X_SIZE):
                self.tiles[i][j].set_value(self.board[i][j])

    def print_board_to_console(self):
        print("\n--- 当前棋盘 ---")
        for row in self.board:
            print(" ".join(map(str, row)))
        print("----------------\n")

    def on_touch_down(self, window, touch):
        self.touch_start = (touch.x, touch.y)
        return False

    def on_touch_up(self, window, touch):
        if self.touch_start:
            dx = touch.x - self.touch_start[0]
            dy = touch.y - self.touch_start[1]
            self.touch_start = None
            threshold = dp(40)
            if abs(dx) > abs(dy):
                if abs(dx) > threshold:
                    if dx > 0: self.move_and_update(move_right)
                    else: self.move_and_update(move_left)
            else:
                if abs(dy) > threshold:
                    if dy > 0: self.move_and_update(move_up)
                    else: self.move_and_update(move_down)
        return False

    def move_and_update(self, move_func):
        old_board = copy.deepcopy(self.board)
        move_func(self.board)
        if old_board != self.board:
            self.history.append(old_board)
            add_evil_random(self.board)
            self.update_ui()
            self.print_board_to_console()

    def do_undo(self, instance):
        current_time = time.time()
        if current_time - self.last_z_time < 0.05:
            return
        self.last_z_time = current_time
        if self.history:
            self.board = self.history.pop()
            self.update_ui()
            self.print_board_to_console()
            print("【已撤回上一步】")
            self.root_bg.rgba = (0, 0, 0, 1)
        else:
            print("【已经退回到最开始啦】")

    def do_restart(self, instance):
        self.board = create_board()
        add_evil_random(self.board)
        add_evil_random(self.board)
        self.history.clear()
        self.last_z_time = 0
        self.root_bg.rgba = (0.73, 0.68, 0.63, 1)
        self.update_ui()
        self.print_board_to_console()
        print("【已重开，背景已重置】")

if __name__ == '__main__':
    Game2048().run()
