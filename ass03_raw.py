import sys
import heapq
from itertools import combinations

class Assignment3Solver:
    def __init__(self, tasks, c1, c2):
        self.tasks = tasks  # {id: {'p': prompts, 'deps': [ids], 'm': 0 (ChatGPT) or 1 (Gemini)}}
        self.c1 = c1
        self.c2 = c2

    def is_feasible(self, cap1, cap2):
        """Checks if any single assignment exceeds daily prompt limits."""
        for t in self.tasks.values():
            limit = cap1 if t['m'] == 0 else cap2
            if t['p'] > limit:
                return False
        return True

    def solve_earliest(self, cap1, cap2, case_b):
        """Finds the earliest day to finish all assignments[cite: 16]."""
        if not self.is_feasible(cap1, cap2):
            return None, None

        # State: (day, current_cost, completed_set)
        # Using A* priority: (day + heuristic, day, cost, completed)
        start_node = (0, 1, 0, frozenset())
        pq = [start_node]
        visited = {}

        while pq:
            _, day, cost, completed = heapq.heappop(pq)

            if len(completed) == len(self.tasks):
                return day - 1, cost

            if completed in visited and visited[completed] <= day:
                continue
            visited[completed] = day

            # Available tasks: dependencies met in PREVIOUS days [cite: 13, 35]
            available = [tid for tid, t in self.tasks.items() 
                         if tid not in completed and all(d in completed for d in t['deps'])]

            # Case A: Max 1 assignment per day 
            # Case B: Multiple assignments if prompts allow 
            possible_combos = []
            if not case_b:
                for tid in available:
                    t = self.tasks[tid]
                    if (t['m'] == 0 and cap1 >= t['p']) or (t['m'] == 1 and cap2 >= t['p']):
                        possible_combos.append([tid])
            else:
                # Simple greedy approach for Case B (can be expanded to power sets for exact A*)
                current_combo = []
                r1, r2 = cap1, cap2
                for tid in available:
                    t = self.tasks[tid]
                    if t['m'] == 0 and r1 >= t['p']:
                        r1 -= t['p']; current_combo.append(tid)
                    elif t['m'] == 1 and r2 >= t['p']:
                        r2 -= t['p']; current_combo.append(tid)
                if current_combo: possible_combos.append(current_combo)

            if not possible_combos:
                heapq.heappush(pq, (day + 1, day + 1, cost, completed))
            else:
                for combo in possible_combos:
                    new_completed = completed | frozenset(combo)
                    added_cost = sum((self.c1 if self.tasks[tid]['m'] == 0 else self.c2) * self.tasks[tid]['p'] for tid in combo)
                    heapq.heappush(pq, (day + 1, day + 1, cost + added_cost, new_completed))
        
        return None, None

def parse_input(filename):
    tasks = {}
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(('%', 'N', 'K')): continue
            parts = list(map(int, line.replace('A', '').split()))
            if not parts: continue
            tasks[parts[0]] = {'p': parts[1], 'deps': parts[2:-1], 'm': 0 if parts[0] % 2 == 0 else 1}
    return tasks

if __name__ == "__main__":
    # Args: <file> <c1> <c2> <cap1> <cap2> <m_days>
    if len(sys.argv) < 7:
        print("Usage: python assg03.py <file> <c1> <c2> <cap1> <cap2> <m_days>")
        sys.exit(1)

    fname = sys.argv[1]
    c1, c2, cap1, cap2, m_limit = map(int, sys.argv[2:])
    
    tasks = parse_input(fname)
    solver = Assignment3Solver(tasks, c1, c2)

    for label, mode in [("Case-A", False), ("Case-B", True)]:
        print(f"\n--- {label} ---")
        # Query 1: Earliest finish
        days, cost = solver.solve_earliest(cap1, cap2, mode)
        if days:
            print(f"Earliest Finish: {days} days, Total Cost: {cost}")
        else:
            print("Earliest Finish: Infeasible")

        # Query 2: Best subscription (min cost per day) to finish within m days 
        # We search for the smallest (cap1, cap2) such that days <= m
        best_sub = None
        min_daily_cost = float('inf')
        
        # Heuristic search for subscription:
        for p1 in range(1, 15): 
            for p2 in range(1, 15):
                daily_cost = (p1 * c1) + (p2 * c2)
                if daily_cost < min_daily_cost:
                    d, _ = solver.solve_earliest(p1, p2, mode)
                    if d and d <= m_limit:
                        min_daily_cost = daily_cost
                        best_sub = (p1, p2)
        
        if best_sub:
            print(f"Best Subscription for {m_limit} days: ChatGPT={best_sub[0]}, Gemini={best_sub[1]} (Daily Cost: {min_daily_cost})")
        else:
            print(f"No valid subscription found for {m_limit} days limit.")
