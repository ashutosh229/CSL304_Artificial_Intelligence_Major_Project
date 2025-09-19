from collections import deque
from fractions import Fraction
import math

class Reservoir:
    def __init__(self, caps, init, target, max_lcm=10**6):
        self.caps_raw = caps
        self.init_raw = init
        self.target_raw = target
        self.max_lcm = max_lcm
        self.caps = [self._to_frac(x) for x in caps]
        self.init = tuple(self._to_frac(x) for x in init)
        self.target = tuple(self._to_frac(x) for x in target)
        self.min_levels = [c * Fraction(1, 5) for c in self.caps]

    def _to_frac(self, x):
        if isinstance(x, Fraction):
            return x
        if isinstance(x, int):
            return Fraction(x)
        return Fraction(str(x))

    def _try_scale_to_ints(self):
        dens = [f.denominator for f in (self.caps + list(self.init) + list(self.target) + self.min_levels)]
        l = 1
        for d in dens:
            l = l * d 
            if l > self.max_lcm:
                return None
        caps_i = [int(f * l) for f in self.caps]
        init_i = tuple(int(f * l) for f in self.init)
        target_i = tuple(int(f * l) for f in self.target)
        min_i = [int(f * l) for f in self.min_levels]
        return l, caps_i, init_i, target_i, min_i

    def _next_states_int(self, state, caps, mins):
        out = []
        for i in range(3):
            for j in range(3):
                if i == j:
                    continue
                src = state[i]; dst = state[j]
                give = src - mins[i]
                take = caps[j] - dst
                if give <= 0 or take <= 0:
                    continue
                transfer = min(give, take)
                new = list(state)
                new[i] -= transfer
                new[j] += transfer
                out.append((tuple(new), (i + 1, j + 1)))
        return out

    def _bfs_int(self, caps, init, target, mins):
        q = deque([init])
        parent = {init: (None, None)}
        while q:
            s = q.popleft()
            if s == target:
                ops = []
                cur = s
                while parent[cur][0] is not None:
                    cur_prev, op = parent[cur]
                    ops.append(op)
                    cur = cur_prev
                return list(reversed(ops))
            for nxt, op in self._next_states_int(s, caps, mins):
                if nxt not in parent:
                    parent[nxt] = (s, op)
                    q.append(nxt)
        return None

    def _next_states_frac(self, state):
        out = []
        for i in range(3):
            for j in range(3):
                if i == j:
                    continue
                src = state[i]; dst = state[j]
                give = src - self.min_levels[i]
                take = self.caps[j] - dst
                if give <= 0 or take <= 0:
                    continue
                transfer = min(give, take)
                new = list(state)
                new[i] -= transfer
                new[j] += transfer
                out.append((tuple(new), (i + 1, j + 1)))
        return out

    def _bfs_frac(self):
        q = deque([self.init])
        parent = {self.init: (None, None)}
        while q:
            s = q.popleft()
            if s == self.target:
                ops = []
                cur = s
                while parent[cur][0] is not None:
                    cur_prev, op = parent[cur]
                    ops.append(op)
                    cur = cur_prev
                return list(reversed(ops))
            for nxt, op in self._next_states_frac(s):
                if nxt not in parent:
                    parent[nxt] = (s, op)
                    q.append(nxt)
        return None

    def solve(self):
        scaled = self._try_scale_to_ints()
        if scaled:
            l, caps_i, init_i, target_i, min_i = scaled
            ops = self._bfs_int(caps_i, init_i, target_i, min_i)
            print("\n--- Problem Results (integer scaled by {}) ---".format(l))
            if ops is None:
                print("No solution found.")
                return None
            for a, b in ops:
                print(f"Open valve ({a}->{b})")
            print("Number of valve operations =", len(ops))
            return ops
        else:
            ops = self._bfs_frac()
            print("\n--- Problem Results (Fraction fallback) ---")
            if ops is None:
                print("No solution found.")
                return None
            for a, b in ops:
                print(f"Open valve ({a}->{b})")
            print("Number of valve operations =", len(ops))
            return ops
