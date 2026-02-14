import argparse
import itertools
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple


@dataclass
class Assignment:
    task_id: int
    effort_needed: int
    prerequisites: List[int] = field(default_factory=list)


@dataclass
class WorkerPool:
    total_workers: int
    daily_capacity: int
    current_availability: List[int] = field(default_factory=list)

    def __post_init__(self):
        self.reset_daily_capacity()

    def reset_daily_capacity(self):
        self.current_availability = [self.daily_capacity] * self.total_workers

    def can_assign(self, worker_idx: int, effort: int) -> bool:
        return self.current_availability[worker_idx] >= effort

    def allocate_work(self, worker_idx: int, effort: int):
        self.current_availability[worker_idx] -= effort

    def release_work(self, worker_idx: int, effort: int):
        self.current_availability[worker_idx] += effort


class DependencyManager:

    def __init__(self, assignments: Dict[int, Assignment]):
        self.task_graph = self._build_graph(assignments)
        self.dependency_count = {tid: len(a.prerequisites) for tid, a in assignments.items()}

    def _build_graph(self, assignments: Dict[int, Assignment]) -> Dict[int, List[int]]:
        graph = {tid: [] for tid in assignments}
        for tid, task in assignments.items():
            for prereq in task.prerequisites:
                graph.setdefault(prereq, []).append(tid)
        return graph

    def has_circular_dependency(self) -> bool:
        incoming = {node: 0 for node in self.task_graph}
        for node in self.task_graph:
            for neighbor in self.task_graph[node]:
                incoming[neighbor] += 1

        processing = [node for node in incoming if incoming[node] == 0]
        processed_count = 0

        while processing:
            current = processing.pop(0)
            processed_count += 1
            for neighbor in self.task_graph[current]:
                incoming[neighbor] -= 1
                if incoming[neighbor] == 0:
                    processing.append(neighbor)

        return processed_count != len(self.task_graph)

    def get_available_tasks(self, completed: Set[int]) -> List[int]:
        return [
            tid for tid, count in self.dependency_count.items()
            if tid not in completed and count == 0
        ]

    def mark_complete(self, task_id: int):
        for dependent in self.task_graph[task_id]:
            self.dependency_count[dependent] -= 1

    def mark_incomplete(self, task_id: int):
        for dependent in self.task_graph[task_id]:
            self.dependency_count[dependent] += 1


class ScheduleBuilder:

    def __init__(self, num_workers: int, max_days: int):
        self.num_workers = num_workers
        self.max_days = max_days
        self.daily_assignments = [[] for _ in range(max_days)]
        self.current_day = 0
        self.completed_tasks = set()

    def add_assignment(self, worker_id: int, task_id: int):
        self.daily_assignments[self.current_day].append((worker_id, task_id))
        self.completed_tasks.add(task_id)

    def remove_last_assignment(self):
        worker_id, task_id = self.daily_assignments[self.current_day].pop()
        self.completed_tasks.remove(task_id)

    def advance_day(self):
        self.current_day += 1

    def revert_day(self):
        self.current_day -= 1

    def is_complete(self, total_tasks: int) -> bool:
        return len(self.completed_tasks) == total_tasks

    def is_time_expired(self) -> bool:
        return self.current_day >= self.max_days

    def get_canonical_signature(self) -> Tuple:
        signature = []
        for day_work in self.daily_assignments:
            worker_allocations = []
            for worker in range(1, self.num_workers + 1):
                tasks = sorted(tid for wid, tid in day_work if wid == worker)
                worker_allocations.append(tuple(tasks))
            worker_allocations.sort()
            signature.append(tuple(worker_allocations))
        return tuple(signature)

    def clone(self):
        copy = ScheduleBuilder(self.num_workers, self.max_days)
        copy.daily_assignments = [day[:] for day in self.daily_assignments]
        copy.current_day = self.current_day
        copy.completed_tasks = self.completed_tasks.copy()
        return copy


class ScheduleSolver:

    def __init__(self, workers: WorkerPool, assignments: Dict[int, Assignment],
                 dependencies: DependencyManager, max_days: int):
        self.workers = workers
        self.assignments = assignments
        self.dependencies = dependencies
        self.max_days = max_days
        self.unique_schedules = []
        self.seen_patterns = set()

    def find_all_schedules(self):
        builder = ScheduleBuilder(self.workers.total_workers, self.max_days)
        self._explore(builder)

    def _explore(self, builder: ScheduleBuilder):
        if builder.is_complete(len(self.assignments)):
            pattern = builder.get_canonical_signature()
            if pattern not in self.seen_patterns:
                self.seen_patterns.add(pattern)
                self.unique_schedules.append(builder.clone())
            return

        if builder.is_time_expired():
            return

        available = self.dependencies.get_available_tasks(builder.completed_tasks)

        for task_id in available:
            task = self.assignments[task_id]
            unique_capacities = set()

            for worker_idx in range(self.workers.total_workers):
                capacity = self.workers.current_availability[worker_idx]

                if (
                    self.workers.can_assign(worker_idx, task.effort_needed)
                    and capacity not in unique_capacities
                ):
                    unique_capacities.add(capacity)

                    self.workers.allocate_work(worker_idx, task.effort_needed)
                    builder.add_assignment(worker_idx + 1, task_id)
                    self.dependencies.mark_complete(task_id)

                    self._explore(builder)

                    self.dependencies.mark_incomplete(task_id)
                    builder.remove_last_assignment()
                    self.workers.release_work(worker_idx, task.effort_needed)

        saved_capacity = self.workers.current_availability[:]
        self.workers.reset_daily_capacity()
        builder.advance_day()

        self._explore(builder)

        builder.revert_day()
        self.workers.current_availability = saved_capacity


class InputParser:

    @staticmethod
    def parse_arguments():
        parser = argparse.ArgumentParser()
        parser.add_argument("test_path", type=str)
        parser.add_argument("days", type=int)
        return parser.parse_args()

    @staticmethod
    def read_input_file(filepath: str) -> Tuple[int, int, Dict[int, Assignment]]:
        num_workers = 0
        max_capacity = 0
        assignments = {}

        with open(filepath, "r") as file:
            for line in file:
                tokens = line.strip().split()
                if not tokens or tokens[0] == '%':
                    continue

                if tokens[0] == 'N':
                    num_workers = int(tokens[1])
                elif tokens[0] == 'K':
                    max_capacity = int(tokens[1])
                elif tokens[0] == 'A':
                    task_id = int(tokens[1])
                    effort = int(tokens[2])
                    prereqs = []
                    for token in tokens[3:]:
                        if token == '0':
                            break
                        prereqs.append(int(token))
                    assignments[task_id] = Assignment(task_id, effort, prereqs)

        return num_workers, max_capacity, assignments


class OutputFormatter:

    @staticmethod
    def display_all_solutions(schedules: List[ScheduleBuilder], num_workers: int):
        solution_num = 1

        for schedule in schedules:
            organized_days = []

            for day_work in schedule.daily_assignments:
                worker_tasks = []
                for worker in range(1, num_workers + 1):
                    tasks = sorted(tid for wid, tid in day_work if wid == worker)
                    worker_tasks.append(tasks)
                organized_days.append(worker_tasks)

            permutation_sets = []
            for day_tasks in organized_days:
                if all(tasks == day_tasks[0] for tasks in day_tasks):
                    permutation_sets.append([tuple(day_tasks)])
                else:
                    permutation_sets.append(set(itertools.permutations(map(tuple, day_tasks))))

            for combination in itertools.product(*permutation_sets):
                print(f"Solution {solution_num}:")
                for day_num, worker_allocation in enumerate(combination, start=1):
                    segments = [
                        f"Worker{w}:{list(t)}"
                        for w, t in enumerate(worker_allocation, start=1)
                    ]
                    print(f"Day {day_num}: " + "|".join(segments))
                print()
                solution_num += 1


class TaskSchedulerApp:

    def __init__(self):
        self.args = InputParser.parse_arguments()
        self.num_workers = 0
        self.max_capacity = 0
        self.assignments = {}
        self.workers = None
        self.dependencies = None
        self.solver = None

    def load_configuration(self):
        self.num_workers, self.max_capacity, self.assignments = (
            InputParser.read_input_file(self.args.test_path)
        )
        self.workers = WorkerPool(self.num_workers, self.max_capacity)
        self.dependencies = DependencyManager(self.assignments)

    def validate_dependencies(self) -> bool:
        if self.dependencies.has_circular_dependency():
            print("Error: Circular dependencies detected. No feasible solution exists.")
            return False
        return True

    def compute_schedules(self):
        self.solver = ScheduleSolver(
            self.workers,
            self.assignments,
            self.dependencies,
            self.args.days,
        )
        self.solver.find_all_schedules()

    def present_results(self):
        total = len(self.solver.unique_schedules)
        print(f"\nTotal unique solutions found: {total}\n")
        OutputFormatter.display_all_solutions(
            self.solver.unique_schedules, self.num_workers
        )

    def run(self):
        self.load_configuration()
        if not self.validate_dependencies():
            return
        self.compute_schedules()
        self.present_results()


if __name__ == "__main__":
    app = TaskSchedulerApp()
    app.run()
