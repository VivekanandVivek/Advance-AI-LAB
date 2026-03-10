import argparse
from collections import defaultdict, deque
# ---------- DATA LOADING ----------

def load_problem_specs(file_path):
    weights = {}
    precedents = defaultdict(list)
    out_edges = defaultdict(list)
    nodes = set()

    with open(file_path) as src:
        for row in src:
            tokens = row.strip().split()
            if not tokens or tokens[0] == "%":
                continue

            if tokens[0] == "A":
                task_id = int(tokens[1])
                weights[task_id] = int(tokens[2])
                nodes.add(task_id)
                

                for dependency in tokens[3:]:
                    if dependency == "0":
                        break
                    dep_id = int(dependency)
                    precedents[task_id].append(dep_id)
                    out_edges[dep_id].append(task_id)
                    nodes.add(dep_id)

    return weights, precedents, out_edges, nodes

# ---------- VALIDATION ----------

def contains_circular_dependency(nodes, out_edges):
    in_degree = {n: 0 for n in nodes}
    for u in out_edges:
        for v in out_edges[u]:
            in_degree[v] += 1

    queue = deque([n for n in nodes if in_degree[n] == 0])
    processed_count = 0

    while queue:
        curr = queue.popleft()
        processed_count += 1
        for neighbor in out_edges[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return processed_count != len(nodes)

# ---------- SCHEDULING ENGINE ----------

class ResourceAllocator:
    def __init__(self, weights, precedents, out_edges, students, capacity, max_days, next_day_mode):
        self.weights = weights
        self.precedents = precedents
        self.out_edges = out_edges
        self.students = students
        self.capacity = capacity
        self.max_days = max_days
        self.next_day_mode = next_day_mode
        
        self.found_configs = set()
        self.task_ids = list(weights.keys())
#Creates a unique hashable signature for the schedule
    def _get_identity(self, current_plan):
        
        transformed = []
        for daily_set in current_plan:
            student_work = []
            for s_idx in range(1, self.students + 1):
                tasks = sorted(tid for sid, tid in daily_set if sid == s_idx)
                student_work.append(tuple(tasks))
            transformed.append(tuple(sorted(student_work)))
        return tuple(transformed)

    def _get_ready_tasks(self, completed, time_map, current_day, in_degree_map):
        ready = []
        for t in self.task_ids:
            if t in completed:
                continue
            
            if self.next_day_mode:
                # Prereqs must be finished in strictly previous days
                if all(p in time_map and time_map[p] < current_day for p in self.precedents[t]):
                    ready.append(t)
            else:
                # Prereqs just need to be done (same-day sharing)
                if in_degree_map[t] == 0:
                    ready.append(t)
        return ready

    def _explore(self, day, daily_caps, completed, in_degree, time_map, plan):
        if len(completed) == len(self.task_ids):
            self.found_configs.add(self._get_identity(plan))
            return

        if day == self.max_days:
            return

        candidates = self._get_ready_tasks(completed, time_map, day, in_degree)

        for t_id in candidates:
            cost = self.weights[t_id]
            used_caps = set()

            for s_idx in range(self.students):
                if daily_caps[s_idx] >= cost and daily_caps[s_idx] not in used_caps:
                    used_caps.add(daily_caps[s_idx])

                    # Apply placement
                    daily_caps[s_idx] -= cost
                    completed.add(t_id)
                    plan[day].append((s_idx + 1, t_id))
                    
                    undo_list = []
                    if self.next_day_mode:
                        time_map[t_id] = day
                    else:
                        for successor in self.out_edges[t_id]:
                            in_degree[successor] -= 1
                            undo_list.append(successor)

                    self._explore(day, daily_caps, completed, in_degree, time_map, plan)

                    # Backtrack placement
                    for s in undo_list: in_degree[s] += 1
                    if self.next_day_mode: del time_map[t_id]
                    plan[day].pop()
                    completed.remove(t_id)
                    daily_caps[s_idx] += cost

        # Jump to next day with refreshed capacities
        self._explore(day + 1, [self.capacity] * self.students, completed, in_degree, time_map, plan)

    def solve(self):
        start_in_degree = {t: len(self.precedents[t]) for t in self.task_ids}
        self._explore(0, [self.capacity] * self.students, set(), start_in_degree, {}, [[] for _ in range(self.max_days)])
        return self.found_configs

# ---------- ENTRY POINT ----------

parser = argparse.ArgumentParser()
parser.add_argument("test_path", type=str)
parser.add_argument("days", type=int)
parser.add_argument("K", type=int)
parser.add_argument("N", type=int)
args = parser.parse_args()

weights, precedents, out_edges, nodes = load_problem_specs(args.test_path)

if contains_circular_dependency(nodes, out_edges):
    print("Dependency graph has a cycle. No valid schedules.")
    exit()

MAX_VAL = 50

for label, mode in [("Current-day sharing:", False), ("\nTommorow sharing:", True)]:
    print(label)
    
    # Optimize Duration
    for d in range(1, MAX_VAL + 1):
        engine = ResourceAllocator(weights, precedents, out_edges, args.N, args.K, d, mode)
        if engine.solve():
            print(f"Minimum days to complete the assignments... {d}" if not mode else f"Minimum days to complete the assignments... {d}")
            break
            
    # Optimize Capacity
    for k in range(1, MAX_VAL + 1):
        engine = ResourceAllocator(weights, precedents, out_edges, args.N, k, args.days, mode)
        if engine.solve():
            print("Minimum prompts Required... ", k)
            break
