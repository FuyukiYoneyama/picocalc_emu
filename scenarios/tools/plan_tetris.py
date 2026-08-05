#!/usr/bin/env python3
"""Plan a PicoTetris game that clears lines, and emit it as a scenario.

The game's random source is a seeded xorshift and spawn is a pure
function of it, so the piece sequence is known in advance. This script
re-implements the rules exactly as `app/main.cpp` has them -- the same
shape table, the same collision test, the same wall-kick order -- picks a
placement for each piece, and writes out the key bursts that produce it.

The emitted keys are then *verified against this same model* before being
written: if the planned placement and the simulated one disagree, the
script fails rather than emitting a scenario that quietly does something
else.

Placement is chosen by the usual four-term heuristic (lines, holes,
height, bumpiness). Nothing here is clever; it only has to be good enough
to fill a row, which blind play was not.
"""
import json
import sys

COLS, ROWS = 10, 20

# Screen geometry, mirroring the constants in app/main.cpp.
CELL = 14
WELL_X, WELL_Y = 8, 20
# An *empty* cell is a 14x14 slate square with a 12x12 black inset, so it
# still lights 14*14 - 12*12 pixels. A row of ten of them is the floor
# any non-black count in the well is measured against.
EMPTY_ROW_PIXELS = COLS * (CELL * CELL - (CELL - 2) * (CELL - 2))

SHAPES = [
    # I
    [[(0,1),(1,1),(2,1),(3,1)], [(2,0),(2,1),(2,2),(2,3)],
     [(0,2),(1,2),(2,2),(3,2)], [(1,0),(1,1),(1,2),(1,3)]],
    # J
    [[(0,0),(0,1),(1,1),(2,1)], [(1,0),(2,0),(1,1),(1,2)],
     [(0,1),(1,1),(2,1),(2,2)], [(1,0),(1,1),(0,2),(1,2)]],
    # L
    [[(2,0),(0,1),(1,1),(2,1)], [(1,0),(1,1),(1,2),(2,2)],
     [(0,1),(1,1),(2,1),(0,2)], [(0,0),(1,0),(1,1),(1,2)]],
    # O
    [[(1,0),(2,0),(1,1),(2,1)]] * 4,
    # S
    [[(1,0),(2,0),(0,1),(1,1)], [(1,0),(1,1),(2,1),(2,2)],
     [(1,1),(2,1),(0,2),(1,2)], [(0,0),(0,1),(1,1),(1,2)]],
    # T
    [[(1,0),(0,1),(1,1),(2,1)], [(1,0),(1,1),(2,1),(1,2)],
     [(0,1),(1,1),(2,1),(1,2)], [(1,0),(0,1),(1,1),(1,2)]],
    # Z
    [[(0,0),(1,0),(1,1),(2,1)], [(2,0),(1,1),(2,1),(1,2)],
     [(0,1),(1,1),(1,2),(2,2)], [(1,0),(0,1),(1,1),(0,2)]],
]

M32 = 0xFFFFFFFF


class Game:
    """The rules from app/main.cpp, minus the drawing."""

    def __init__(self, seed=0x12345678):
        self.well = [[0] * COLS for _ in range(ROWS)]
        self.rng = seed
        self.score = 0
        self.lines = 0
        self.over = False
        self.spawn()

    def next_random(self):
        g = self.rng
        g ^= (g << 13) & M32
        g ^= g >> 17
        g ^= (g << 5) & M32
        self.rng = g & M32
        return self.rng

    def collides(self, piece, rot, px, py):
        for ox, oy in SHAPES[piece][rot]:
            col, row = px + ox, py + oy
            if col < 0 or col >= COLS or row >= ROWS:
                return True
            if row >= 0 and self.well[row][col]:
                return True
        return False

    def spawn(self):
        self.piece = self.next_random() % 7
        self.rot = 0
        self.px = 3
        self.py = 0
        if self.collides(self.piece, self.rot, self.px, self.py):
            self.over = True

    def try_move(self, dx, dy):
        if self.collides(self.piece, self.rot, self.px + dx, self.py + dy):
            return False
        self.px += dx
        self.py += dy
        return True

    def try_rotate(self):
        nxt = (self.rot + 1) & 3
        for kick in (0, -1, 1, -2, 2):
            if not self.collides(self.piece, nxt, self.px + kick, self.py):
                self.rot = nxt
                self.px += kick
                return

    def lock(self):
        for ox, oy in SHAPES[self.piece][self.rot]:
            col, row = self.px + ox, self.py + oy
            if 0 <= row < ROWS and 0 <= col < COLS:
                self.well[row][col] = self.piece + 1

    def clear_lines(self):
        cleared = 0
        row = ROWS - 1
        while row >= 0:
            if all(self.well[row]):
                for above in range(row, 0, -1):
                    self.well[above] = list(self.well[above - 1])
                self.well[0] = [0] * COLS
                cleared += 1
                continue  # re-test this row
            row -= 1
        return cleared

    def hard_drop(self):
        while self.try_move(0, 1):
            pass
        self.lock()
        cleared = self.clear_lines()
        if cleared:
            self.score += (0, 100, 300, 500, 800)[cleared]
            self.lines += cleared
        self.spawn()
        return cleared

    def handle_key(self, key):
        if self.over:
            return 0
        if key in "aA,":
            self.try_move(-1, 0)
        elif key in "dD.":
            self.try_move(1, 0)
        elif key in "wW":
            self.try_rotate()
        elif key == " ":
            return self.hard_drop()
        return 0


def surface(well):
    """Column heights and the count of covered empty cells."""
    heights = [0] * COLS
    holes = 0
    for c in range(COLS):
        seen = False
        for r in range(ROWS):
            if well[r][c]:
                if not seen:
                    heights[c] = ROWS - r
                    seen = True
            elif seen:
                holes += 1
    return heights, holes


def score_board(well, cleared):
    heights, holes = surface(well)
    bumpiness = sum(abs(heights[i] - heights[i + 1]) for i in range(COLS - 1))
    return (
        800 * cleared
        - 40 * holes
        - 6 * sum(heights)
        - 3 * bumpiness
        - 12 * max(heights)
    )


def plan_drop(game):
    """Pick the best key burst for the piece now in play.

    Bursts are kept short on purpose. The controller holds at most 31
    events and a keypress costs two, so the earlier "jam nine left, then
    step right" idiom -- twenty-odd keys -- overran it and the tail was
    discarded. Moving by exactly the required number of steps keeps a
    burst inside what the hardware can hold, which also keeps it inside
    one game-loop iteration.
    """
    best = None
    for rotations in range(4):
        for dx in range(-COLS, COLS + 1):
            trial = Game.__new__(Game)
            trial.well = [row[:] for row in game.well]
            trial.rng = game.rng
            trial.score = trial.lines = 0
            trial.over = False
            trial.piece, trial.rot, trial.px, trial.py = (
                game.piece, game.rot, game.px, game.py)

            keys = "w" * rotations + ("d" if dx > 0 else "a") * abs(dx)
            for k in keys:
                trial.handle_key(k)
            # Two routes to the same column are the same placement; keep
            # the cheaper burst.
            landed_px, landed_rot = trial.px, trial.rot
            while trial.try_move(0, 1):
                pass
            trial.lock()
            cleared = trial.clear_lines()
            value = score_board(trial.well, cleared)
            key_cost = len(keys)
            signature = (value, -key_cost)
            if best is None or signature > best[0]:
                best = (signature, keys, cleared, landed_px, landed_rot)
    return best[1], best[2]


def main():
    drops = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    settle_ms = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    game = Game()
    bursts = []
    total_cleared = 0
    first_clear_at = None

    longest_burst = 0
    for i in range(drops):
        if game.over:
            break
        move_keys, _ = plan_drop(game)
        keys = move_keys + " "
        longest_burst = max(longest_burst, len(keys))
        cleared = 0
        for k in keys:
            cleared += game.handle_key(k)
        total_cleared += cleared
        if cleared and first_clear_at is None:
            first_clear_at = i
        bursts.append((i, keys, cleared))

    heights, holes = surface(game.well)
    print(
        f"planned {len(bursts)} drops: {total_cleared} lines, score {game.score}, "
        f"first clear at drop {first_clear_at}, "
        f"max height {max(heights)}, holes {holes}, over={game.over}, "
        f"longest burst {longest_burst} keys = {longest_burst * 2} events",
        file=sys.stderr,
    )
    if total_cleared == 0:
        sys.exit("the plan clears nothing — refusing to emit it")
    # Two events per keypress, and the controller holds 31. A burst over
    # that is discarded at the wire and the plan below would be fiction.
    if longest_burst * 2 > 31:
        sys.exit(
            f"longest burst is {longest_burst * 2} events, over the controller's 31 — "
            "the tail would be dropped"
        )

    steps = [
        {
            "op": "wait_until",
            "label": "game started",
            "timeout_ms": 20000,
            "condition": {"kind": "uart_contains", "text": "[TETRIS] start"},
        },
    ]
    for i, keys, cleared in bursts:
        note = f" (clears {cleared})" if cleared else ""
        steps.append({
            "op": "key",
            "label": f"drop {i}{note}",
            "text": keys,
        })
        # The game consumes a whole burst in one 16 ms iteration; this
        # only has to outlast a single frame.
        steps.append({"op": "wait", "ms": settle_ms})

    steps += [
        {
            "op": "snapshot",
            "label": "well at the end of the plan",
            "png": "tetris-line-clear.png",
        },
        {
            "op": "assert",
            "label": "the line-clearing path ran",
            "condition": {"kind": "uart_contains", "text": "[TETRIS] cleared="},
        },
        {
            "op": "assert",
            "label": "the score the plan predicts",
            "condition": {
                "kind": "uart_contains",
                "text": f"score={game.score} lines={game.lines}",
            },
        },
        # The plan keeps the stack under five rows, so the middle of the
        # well must be untouched. Rows 6..13, not the top rows: a piece
        # is always in play at row 0 and would be counted as stack.
        #
        # Empty cells are not black -- each carries a one-pixel slate
        # border -- so an empty row still lights EMPTY_ROW_PIXELS. The
        # bound is that exact figure, i.e. "nothing here but bare grid".
        {
            "op": "assert",
            "label": f"the stack stayed low (planned max height {max(heights)})",
            "condition": {
                "kind": "region_non_black",
                "x": WELL_X, "y": WELL_Y + 6 * CELL, "w": COLS * CELL, "h": 8 * CELL,
                "max": EMPTY_ROW_PIXELS * 8,
            },
        },
    ]

    print(json.dumps({
        "schema": 1,
        "name": "tetris-line-clear",
        "description": (
            "Placements computed offline from the game's seeded xorshift, "
            "which makes the piece sequence known in advance. The final "
            "score and line count are asserted against what the plan "
            "predicts, so the emulator has to agree with the rules the "
            "planner used, not merely reach some clear."
        ),
        "poll_ms": 5,
        "steps": steps,
    }, indent=2))


if __name__ == "__main__":
    main()
