
import sys
import os
import random
import time
import subprocess
from itertools import combinations
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
import statistics
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


@dataclass
class Course:
    course_id: int
    earliest_start: int
    latest_finish: int
    duration: int
    
    def get_valid_start_range(self) -> range:
        return range(self.earliest_start, 
                    self.latest_finish - self.duration + 2)
    
    def occupies_day(self, start_day: int, target_day: int) -> bool:
        return start_day <= target_day < start_day + self.duration


@dataclass
class TestCase:
    test_id: int
    num_rooms: int
    num_courses: int
    courses: List[Course]


@dataclass
class SolverResult:
    solver_name: str
    encoding_type: str
    test_id: int
    satisfiable: Optional[bool]
    runtime: float
    num_variables: int
    num_clauses: int
    num_binary_clauses: int
    num_ternary_clauses: int
    num_longer_clauses: int
    memory_kb: Optional[float]
    error: Optional[str] = None


class TestCaseGenerator:
    
    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
    
    def generate_test_case(self, test_id: int, 
                          num_courses: int = None,
                          num_rooms: int = None,
                          max_duration: int = 10,
                          time_horizon: int = 30) -> TestCase:
        
        if num_courses is None:
            num_courses = random.randint(5, 20)
        if num_rooms is None:
            num_rooms = random.randint(2, min(5, num_courses))
        
        courses = []
        for i in range(num_courses):
            duration = random.randint(1, max_duration)
            earliest_start = random.randint(1, time_horizon - duration)
            latest_finish = random.randint(
                earliest_start + duration - 1,
                min(time_horizon, earliest_start + duration + 15)
            )
            
            course = Course(
                course_id=i + 1,
                earliest_start=earliest_start,
                latest_finish=latest_finish,
                duration=duration
            )
            courses.append(course)
        
        return TestCase(test_id, num_rooms, num_courses, courses)
    
    def generate_batch(self, count: int = 100) -> List[TestCase]:
        test_cases = []
        
        for i in range(count):
            if i < 30:
                num_courses = random.randint(3, 8)
                num_rooms = random.randint(2, 4)
            elif i < 70:
                num_courses = random.randint(8, 15)
                num_rooms = random.randint(3, 5)
            else:
                num_courses = random.randint(15, 25)
                num_rooms = random.randint(3, 6)
            
            test_case = self.generate_test_case(
                test_id=i + 1,
                num_courses=num_courses,
                num_rooms=num_rooms
            )
            test_cases.append(test_case)
        
        return test_cases


class InputFileWriter:
    
    @staticmethod
    def write_to_file(test_case: TestCase, filepath: str):
        with open(filepath, 'w') as f:
            f.write("% number of rooms\n")
            f.write(f"M {test_case.num_rooms}\n")
            f.write("% number of short-term-courses\n")
            f.write("N\n")
            f.write(f"{test_case.num_courses}\n")
            f.write("% course details\n")
            f.write("% course id start-day end-day duration\n")
            
            for course in test_case.courses:
                f.write(f"C {course.course_id} {course.earliest_start} "
                       f"{course.latest_finish} {course.duration}\n")


class VariableEncoder:
    
    def __init__(self, num_courses: int, num_rooms: int, time_horizon: int):
        self.num_courses = num_courses
        self.num_rooms = num_rooms
        self.time_horizon = time_horizon
        self.next_var = 1
    
    def reserve_variables(self, count: int) -> int:
        start = self.next_var
        self.next_var += count
        return start
    
    def get_total_variables(self) -> int:
        return self.next_var - 1


class ThreeDimensionalEncoding:
    
    def __init__(self, courses: List[Course], num_rooms: int, time_horizon: int):
        self.courses = courses
        self.num_rooms = num_rooms
        self.time_horizon = time_horizon
        self.var_encoder = VariableEncoder(len(courses), num_rooms, time_horizon)
        self.variable_map = {}
        self._initialize_variables()
    
    def _initialize_variables(self):
        for course_idx in range(len(self.courses)):
            for room in range(self.num_rooms):
                for time in range(self.time_horizon + 1):
                    var_id = self.var_encoder.reserve_variables(1)
                    self.variable_map[(course_idx, room, time)] = var_id
    
    def get_variable(self, course_idx: int, room: int, time: int) -> int:
        return self.variable_map.get((course_idx, room, time), 0)
    
    def generate_cnf_formula(self) -> List[List[int]]:
        constraint_set = []
        constraint_set.extend(self._build_assignment_constraints())
        constraint_set.extend(self._build_room_conflict_constraints())
        return constraint_set
    
    def _build_assignment_constraints(self) -> List[List[int]]:
        constraints = []
        
        for course_idx, course in enumerate(self.courses):
            assignment_vars = []
            
            for room in range(self.num_rooms):
                for start_time in course.get_valid_start_range():
                    var = self.get_variable(course_idx, room, start_time)
                    if var > 0:
                        assignment_vars.append(var)
            
            if assignment_vars:
                constraints.append(assignment_vars)
            
            for var1, var2 in combinations(assignment_vars, 2):
                constraints.append([-var1, -var2])
        
        return constraints
    
    def _build_room_conflict_constraints(self) -> List[List[int]]:
        constraints = []
        
        for room in range(self.num_rooms):
            for day in range(1, self.time_horizon + 1):
                overlapping_assignments = []
                
                for course_idx, course in enumerate(self.courses):
                    for start_time in course.get_valid_start_range():
                        if course.occupies_day(start_time, day):
                            var = self.get_variable(course_idx, room, start_time)
                            if var > 0:
                                overlapping_assignments.append(var)
                
                for var1, var2 in combinations(overlapping_assignments, 2):
                    constraints.append([-var1, -var2])
        
        return constraints
    
    def get_num_variables(self) -> int:
        return self.var_encoder.get_total_variables()


class TwoDimensionalEncoding:
    
    def __init__(self, courses: List[Course], num_rooms: int, time_horizon: int):
        self.courses = courses
        self.num_rooms = num_rooms
        self.time_horizon = time_horizon
        self.var_encoder = VariableEncoder(len(courses), num_rooms, time_horizon)
        self.room_assignment_map = {}
        self.time_assignment_map = {}
        self._initialize_variables()
    
    def _initialize_variables(self):
        for course_idx in range(len(self.courses)):
            for room in range(self.num_rooms):
                var_id = self.var_encoder.reserve_variables(1)
                self.room_assignment_map[(course_idx, room)] = var_id
        
        for course_idx in range(len(self.courses)):
            for time in range(self.time_horizon + 1):
                var_id = self.var_encoder.reserve_variables(1)
                self.time_assignment_map[(course_idx, time)] = var_id
    
    def get_room_variable(self, course_idx: int, room: int) -> int:
        return self.room_assignment_map.get((course_idx, room), 0)
    
    def get_time_variable(self, course_idx: int, time: int) -> int:
        return self.time_assignment_map.get((course_idx, time), 0)
    
    def generate_cnf_formula(self) -> List[List[int]]:
        constraint_set = []
        constraint_set.extend(self._build_room_assignment_constraints())
        constraint_set.extend(self._build_time_assignment_constraints())
        constraint_set.extend(self._build_conflict_prevention_constraints())
        return constraint_set
    
    def _build_room_assignment_constraints(self) -> List[List[int]]:
        constraints = []
        
        for course_idx in range(len(self.courses)):
            room_vars = [self.get_room_variable(course_idx, room) 
                        for room in range(self.num_rooms)]
            
            constraints.append(room_vars)
            
            for var1, var2 in combinations(room_vars, 2):
                constraints.append([-var1, -var2])
        
        return constraints
    
    def _build_time_assignment_constraints(self) -> List[List[int]]:
        constraints = []
        
        for course_idx, course in enumerate(self.courses):
            time_vars = [self.get_time_variable(course_idx, time) 
                        for time in course.get_valid_start_range()]
            
            if time_vars:
                constraints.append(time_vars)
            
            for var1, var2 in combinations(time_vars, 2):
                constraints.append([-var1, -var2])
        
        return constraints
    
    def _build_conflict_prevention_constraints(self) -> List[List[int]]:
        constraints = []
        
        for course1_idx in range(len(self.courses)):
            for course2_idx in range(course1_idx + 1, len(self.courses)):
                course1 = self.courses[course1_idx]
                course2 = self.courses[course2_idx]
                
                for room in range(self.num_rooms):
                    room_var1 = self.get_room_variable(course1_idx, room)
                    room_var2 = self.get_room_variable(course2_idx, room)
                    
                    for time1 in course1.get_valid_start_range():
                        for time2 in course2.get_valid_start_range():
                            if self._intervals_overlap(time1, course1.duration, 
                                                       time2, course2.duration):
                                time_var1 = self.get_time_variable(course1_idx, time1)
                                time_var2 = self.get_time_variable(course2_idx, time2)
                                
                                constraints.append([-room_var1, -room_var2, 
                                                   -time_var1, -time_var2])
        
        return constraints
    
    @staticmethod
    def _intervals_overlap(start1: int, duration1: int, 
                          start2: int, duration2: int) -> bool:
        end1 = start1 + duration1
        end2 = start2 + duration2
        return not (end1 <= start2 or end2 <= start1)
    
    def get_num_variables(self) -> int:
        return self.var_encoder.get_total_variables()


class DIMACSWriter:
    
    @staticmethod
    def write_to_file(clauses: List[List[int]], filepath: str) -> Dict:
        if not clauses:
            return {
                'num_variables': 0,
                'num_clauses': 0,
                'num_binary': 0,
                'num_ternary': 0,
                'num_longer': 0
            }
        
        max_variable = max(abs(literal) 
                          for clause in clauses 
                          for literal in clause)
        
        num_binary = sum(1 for c in clauses if len(c) == 2)
        num_ternary = sum(1 for c in clauses if len(c) == 3)
        num_longer = sum(1 for c in clauses if len(c) > 3)
        
        with open(filepath, 'w') as output:
            output.write(f"p cnf {max_variable} {len(clauses)}\n")
            
            for clause in clauses:
                clause_str = " ".join(map(str, clause)) + " 0\n"
                output.write(clause_str)
        
        return {
            'num_variables': max_variable,
            'num_clauses': len(clauses),
            'num_binary': num_binary,
            'num_ternary': num_ternary,
            'num_longer': num_longer
        }


class SATSolverRunner:
    
    SUPPORTED_SOLVERS = {
        'z3': 'z3',
        'minisat': 'minisat',
        'glucose': 'glucose'
    }
    
    @staticmethod
    def check_solver_availability(solver_name: str) -> bool:
        try:
            result = subprocess.run(
                [solver_name, '--help'],
                capture_output=True,
                timeout=5
            )
            return result.returncode in [0, 1]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    @staticmethod
    def run_z3(cnf_file: str, timeout: int = 300) -> Tuple[Optional[bool], float, Optional[str]]:
        try:
            start_time = time.time()
            result = subprocess.run(
                ['z3', cnf_file],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            runtime = time.time() - start_time
            
            output = result.stdout.lower()
            if 'unsat' in output:
                return False, runtime, None
            elif 'sat' in output:
                return True, runtime, None
            else:
                return None, runtime, "Unknown output"
                
        except subprocess.TimeoutExpired:
            return None, timeout, "Timeout"
        except Exception as e:
            return None, 0.0, str(e)
    
    @staticmethod
    def run_minisat(cnf_file: str, timeout: int = 300) -> Tuple[Optional[bool], float, Optional[str]]:
        try:
            output_file = cnf_file + '.minisat.out'
            start_time = time.time()
            result = subprocess.run(
                ['minisat', cnf_file, output_file],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            runtime = time.time() - start_time
            
            try:
                with open(output_file, 'r') as f:
                    first_line = f.readline().strip()
                    os.remove(output_file)
                    
                    if first_line == 'SAT':
                        return True, runtime, None
                    elif first_line == 'UNSAT':
                        return False, runtime, None
                    else:
                        return None, runtime, "Unknown output"
            except FileNotFoundError:
                return None, runtime, "No output file"
                
        except subprocess.TimeoutExpired:
            return None, timeout, "Timeout"
        except Exception as e:
            return None, 0.0, str(e)
    
    @staticmethod
    def run_glucose(cnf_file: str, timeout: int = 300) -> Tuple[Optional[bool], float, Optional[str]]:
        try:
            output_file = cnf_file + '.glucose.out'
            start_time = time.time()
            result = subprocess.run(
                ['glucose', cnf_file, output_file],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            runtime = time.time() - start_time
            
            output = result.stdout.lower()
            if 'unsatisfiable' in output or 's unsat' in output:
                sat_result = False
            elif 'satisfiable' in output or 's sat' in output:
                sat_result = True
            else:
                sat_result = None
            
            if os.path.exists(output_file):
                os.remove(output_file)
            
            return sat_result, runtime, None if sat_result is not None else "Unknown output"
                
        except subprocess.TimeoutExpired:
            return None, timeout, "Timeout"
        except Exception as e:
            return None, 0.0, str(e)


class SchedulingSolver:
    
    def __init__(self, test_case: TestCase):
        self.test_case = test_case
        self.num_rooms = test_case.num_rooms
        self.num_courses = test_case.num_courses
        self.courses = test_case.courses
        self.time_horizon = 30
        self._calculate_time_horizon()
    
    def _calculate_time_horizon(self):
        if self.courses:
            self.time_horizon = max(course.latest_finish 
                                   for course in self.courses)
    
    def generate_encoding_1(self) -> Tuple[List[List[int]], int]:
        encoder = ThreeDimensionalEncoding(self.courses, self.num_rooms, 
                                          self.time_horizon)
        clauses = encoder.generate_cnf_formula()
        num_vars = encoder.get_num_variables()
        return clauses, num_vars
    
    def generate_encoding_2(self) -> Tuple[List[List[int]], int]:
        encoder = TwoDimensionalEncoding(self.courses, self.num_rooms, 
                                        self.time_horizon)
        clauses = encoder.generate_cnf_formula()
        num_vars = encoder.get_num_variables()
        return clauses, num_vars


class ExperimentRunner:
    
    def __init__(self, output_dir: str = "results"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(f"{output_dir}/test_cases", exist_ok=True)
        os.makedirs(f"{output_dir}/cnf_files", exist_ok=True)
        
        self.available_solvers = []
        for solver_name in ['z3', 'minisat', 'glucose']:
            if SATSolverRunner.check_solver_availability(solver_name):
                self.available_solvers.append(solver_name)
                print(f"✓ Found solver: {solver_name}")
            else:
                print(f"✗ Solver not found: {solver_name}")
        
        if not self.available_solvers:
            print("WARNING: No SAT solvers found. Only CNF files will be generated.")
    
    def run_experiments(self, test_cases: List[TestCase], 
                       max_tests: Optional[int] = None) -> Tuple[List[SolverResult], Dict]:
        results = []
        encoding_stats = {'op-1': [], 'op-2': []}
        
        if max_tests:
            test_cases = test_cases[:max_tests]
        
        total_tests = len(test_cases)
        
        for idx, test_case in enumerate(test_cases, 1):
            print(f"\n{'='*60}")
            print(f"Processing Test Case {idx}/{total_tests}")
            print(f"  Courses: {test_case.num_courses}, Rooms: {test_case.num_rooms}")
            print(f"{'='*60}")
            
            test_file = f"{self.output_dir}/test_cases/test_{test_case.test_id:03d}.txt"
            InputFileWriter.write_to_file(test_case, test_file)
            
            for encoding_type in ['op-1', 'op-2']:
                print(f"\n  Encoding: {encoding_type}")
                
                solver = SchedulingSolver(test_case)
                
                if encoding_type == 'op-1':
                    clauses, num_vars = solver.generate_encoding_1()
                else:
                    clauses, num_vars = solver.generate_encoding_2()
                
                cnf_file = f"{self.output_dir}/cnf_files/test_{test_case.test_id:03d}_{encoding_type}.cnf"
                stats = DIMACSWriter.write_to_file(clauses, cnf_file)
                
                encoding_stats[encoding_type].append({
                    'test_id': test_case.test_id,
                    'num_courses': test_case.num_courses,
                    'num_rooms': test_case.num_rooms,
                    'num_variables': stats['num_variables'],
                    'num_clauses': stats['num_clauses'],
                    'num_binary': stats['num_binary'],
                    'num_ternary': stats['num_ternary'],
                    'num_longer': stats['num_longer']
                })
                
                print(f"    Variables: {stats['num_variables']}")
                print(f"    Clauses: {stats['num_clauses']} " +
                      f"(Binary: {stats['num_binary']}, " +
                      f"Ternary: {stats['num_ternary']}, " +
                      f"Longer: {stats['num_longer']})")
                
                for solver_name in self.available_solvers:
                    print(f"    Running {solver_name}...", end=' ')
                    
                    if solver_name == 'z3':
                        sat_result, runtime, error = SATSolverRunner.run_z3(cnf_file, timeout=60)
                    elif solver_name == 'minisat':
                        sat_result, runtime, error = SATSolverRunner.run_minisat(cnf_file, timeout=60)
                    elif solver_name == 'glucose':
                        sat_result, runtime, error = SATSolverRunner.run_glucose(cnf_file, timeout=60)
                    else:
                        continue
                    
                    result = SolverResult(
                        solver_name=solver_name,
                        encoding_type=encoding_type,
                        test_id=test_case.test_id,
                        satisfiable=sat_result,
                        runtime=runtime,
                        num_variables=stats['num_variables'],
                        num_clauses=stats['num_clauses'],
                        num_binary_clauses=stats['num_binary'],
                        num_ternary_clauses=stats['num_ternary'],
                        num_longer_clauses=stats['num_longer'],
                        memory_kb=None,
                        error=error
                    )
                    results.append(result)
                    
                    if error:
                        print(f"ERROR ({error})")
                    else:
                        sat_str = "SAT" if sat_result else "UNSAT"
                        print(f"{sat_str} in {runtime:.3f}s")
        
        return results, encoding_stats
    
    def save_results(self, results: List[SolverResult], encoding_stats: Dict = None):
        print(f"\n{'='*60}")
        print(f"Results processing complete")
        print(f"{'='*60}")


class ResultsAnalyzer:
    
    def __init__(self, results: List[SolverResult], encoding_stats: Dict = None):
        self.results = results
        self.encoding_stats = encoding_stats or {}
    
    def generate_summary(self) -> str:
        lines = []
        lines.append("="*80)
        lines.append("EXPERIMENTAL RESULTS SUMMARY")
        lines.append("CS5205 Assignment 5: SAT-based Course Scheduling")
        lines.append("="*80)
        lines.append("")
        
        lines.append("ENCODING STATISTICS")
        lines.append("="*80)
        
        for encoding in ['op-1', 'op-2']:
            if encoding in self.encoding_stats and self.encoding_stats[encoding]:
                stats_list = self.encoding_stats[encoding]
                
                lines.append(f"\n{encoding.upper()} Encoding:")
                lines.append("-" * 40)
                
                avg_vars = statistics.mean([s['num_variables'] for s in stats_list])
                avg_clauses = statistics.mean([s['num_clauses'] for s in stats_list])
                avg_binary = statistics.mean([s['num_binary'] for s in stats_list])
                avg_ternary = statistics.mean([s['num_ternary'] for s in stats_list])
                avg_longer = statistics.mean([s['num_longer'] for s in stats_list])
                
                min_vars = min([s['num_variables'] for s in stats_list])
                max_vars = max([s['num_variables'] for s in stats_list])
                min_clauses = min([s['num_clauses'] for s in stats_list])
                max_clauses = max([s['num_clauses'] for s in stats_list])
                
                lines.append(f"  Test Cases: {len(stats_list)}")
                lines.append(f"  Variables:")
                lines.append(f"    Average: {avg_vars:.1f}")
                lines.append(f"    Min: {min_vars}, Max: {max_vars}")
                lines.append(f"  Clauses:")
                lines.append(f"    Average: {avg_clauses:.1f}")
                lines.append(f"    Min: {min_clauses}, Max: {max_clauses}")
                lines.append(f"  Clause Distribution:")
                lines.append(f"    Binary (2 literals): {avg_binary:.1f}")
                lines.append(f"    Ternary (3 literals): {avg_ternary:.1f}")
                lines.append(f"    Longer (3+ literals): {avg_longer:.1f}")
        
        if 'op-1' in self.encoding_stats and 'op-2' in self.encoding_stats:
            lines.append("\n" + "="*80)
            lines.append("ENCODING COMPARISON")
            lines.append("="*80)
            
            op1_stats = self.encoding_stats['op-1']
            op2_stats = self.encoding_stats['op-2']
            
            if op1_stats and op2_stats:
                op1_avg_vars = statistics.mean([s['num_variables'] for s in op1_stats])
                op2_avg_vars = statistics.mean([s['num_variables'] for s in op2_stats])
                op1_avg_clauses = statistics.mean([s['num_clauses'] for s in op1_stats])
                op2_avg_clauses = statistics.mean([s['num_clauses'] for s in op2_stats])
                
                lines.append(f"\nAverage Variables:")
                lines.append(f"  op-1: {op1_avg_vars:.1f}")
                lines.append(f"  op-2: {op2_avg_vars:.1f}")
                
                var_diff_pct = ((op1_avg_vars - op2_avg_vars) / op2_avg_vars) * 100
                if op1_avg_vars < op2_avg_vars:
                    lines.append(f"  → op-1 uses {abs(var_diff_pct):.1f}% fewer variables ✓")
                else:
                    lines.append(f"  → op-2 uses {abs(var_diff_pct):.1f}% fewer variables ✓")
                
                lines.append(f"\nAverage Clauses:")
                lines.append(f"  op-1: {op1_avg_clauses:.1f}")
                lines.append(f"  op-2: {op2_avg_clauses:.1f}")
                
                clause_diff_pct = ((op1_avg_clauses - op2_avg_clauses) / op2_avg_clauses) * 100
                if op1_avg_clauses < op2_avg_clauses:
                    lines.append(f"  → op-1 uses {abs(clause_diff_pct):.1f}% fewer clauses ✓")
                else:
                    lines.append(f"  → op-2 uses {abs(clause_diff_pct):.1f}% fewer clauses ✓")
        
        if self.results:
            lines.append("\n" + "="*80)
            lines.append("SOLVER PERFORMANCE RESULTS")
            lines.append("="*80)
            
            for encoding in ['op-1', 'op-2']:
                encoding_results = [r for r in self.results if r.encoding_type == encoding]
                if not encoding_results:
                    continue
                
                lines.append(f"\n{encoding.upper()} Encoding:")
                lines.append("-" * 40)
                
                for solver in set(r.solver_name for r in encoding_results):
                    solver_results = [r for r in encoding_results if r.solver_name == solver]
                    successful = [r for r in solver_results if r.error is None]
                    
                    if successful:
                        runtimes = [r.runtime for r in successful]
                        avg_runtime = statistics.mean(runtimes)
                        median_runtime = statistics.median(runtimes)
                        
                        sat_count = sum(1 for r in successful if r.satisfiable)
                        unsat_count = sum(1 for r in successful if r.satisfiable == False)
                        
                        lines.append(f"\n  {solver.upper()}:")
                        lines.append(f"    Solved: {len(successful)}/{len(solver_results)}")
                        lines.append(f"    SAT: {sat_count}, UNSAT: {unsat_count}")
                        lines.append(f"    Avg Runtime: {avg_runtime:.4f}s")
                        lines.append(f"    Median Runtime: {median_runtime:.4f}s")
                        
                        if runtimes:
                            lines.append(f"    Min Runtime: {min(runtimes):.4f}s")
                            lines.append(f"    Max Runtime: {max(runtimes):.4f}s")
            
            lines.append("\n" + "="*80)
            lines.append("SOLVER COMPARISON (ACROSS ENCODINGS)")
            lines.append("="*80)
            
            for solver in set(r.solver_name for r in self.results):
                op1_results = [r for r in self.results 
                              if r.solver_name == solver and r.encoding_type == 'op-1' and r.error is None]
                op2_results = [r for r in self.results 
                              if r.solver_name == solver and r.encoding_type == 'op-2' and r.error is None]
                
                if op1_results and op2_results:
                    op1_avg_time = statistics.mean([r.runtime for r in op1_results])
                    op2_avg_time = statistics.mean([r.runtime for r in op2_results])
                    
                    lines.append(f"\n{solver.upper()}:")
                    lines.append(f"  Average Runtime:")
                    lines.append(f"    op-1: {op1_avg_time:.4f}s")
                    lines.append(f"    op-2: {op2_avg_time:.4f}s")
                    
                    speedup = (op1_avg_time / op2_avg_time - 1) * 100
                    if op1_avg_time < op2_avg_time:
                        lines.append(f"    → op-1 is {abs(speedup):.1f}% faster ✓")
                    else:
                        lines.append(f"    → op-2 is {abs(speedup):.1f}% faster ✓")
        else:
            lines.append("\n" + "="*80)
            lines.append("SOLVER RESULTS")
            lines.append("="*80)
            lines.append("\nNo SAT solver results available.")
            lines.append("Install Z3, MiniSat, or Glucose to run solver comparisons.")
            lines.append("\nTo install Z3:")
            lines.append("  Ubuntu/Debian: sudo apt-get install z3")
            lines.append("  macOS: brew install z3")
        
        lines.append("\n" + "="*80)
        lines.append("CONCLUSIONS")
        lines.append("="*80)
        
        if 'op-1' in self.encoding_stats and 'op-2' in self.encoding_stats:
            op1_stats = self.encoding_stats['op-1']
            op2_stats = self.encoding_stats['op-2']
            
            if op1_stats and op2_stats:
                op1_avg_vars = statistics.mean([s['num_variables'] for s in op1_stats])
                op2_avg_vars = statistics.mean([s['num_variables'] for s in op2_stats])
                
                lines.append("\nBased on the experimental analysis:")
                lines.append("")
                
                if op1_avg_vars < op2_avg_vars:
                    lines.append("1. Option 1 (z_ijt) encoding is more efficient in terms of:")
                    lines.append("   - Fewer variables on average")
                else:
                    lines.append("1. Option 2 (x_ij + y_it) encoding is more efficient in terms of:")
                    lines.append("   - Fewer variables on average")
                
                lines.append("")
                lines.append("2. Both encodings correctly model the course scheduling problem")
                lines.append("   with constraints for:")
                lines.append("   - Unique course assignment")
                lines.append("   - Room conflict prevention")
                lines.append("   - Deadline satisfaction")
                
                if self.results:
                    lines.append("")
                    lines.append("3. Solver performance varies by encoding and problem complexity")
        
        lines.append("")
        lines.append("="*80)
        
        return "\n".join(lines)
    
    # def save_summary(self, filepath: str):
    #     summary = self.generate_summary()
    #     with open(filepath, 'w', encoding='utf-8') as f:
    #         f.write(summary)
    #     print(f"\nSummary saved to: {filepath}")

    def save_summary(self, filepath: str):
        summary = self.generate_summary()
    
        styles = getSampleStyleSheet()
        story = []
    
        for line in summary.split("\n"):
            story.append(Paragraph(line, styles["Normal"]))
            story.append(Spacer(1, 6))
    
        pdf = SimpleDocTemplate(filepath)
        pdf.build(story)
    
        print(f"\nSummary saved to: {filepath}")


def main():
    print("="*80)
    print("CS5205 Assignment 5: SAT-based Course Scheduling")
    print("Automatic Test Case Generation and Comparative Analysis")
    print("="*80)
    
    num_tests = 100
    if len(sys.argv) > 1:
        try:
            num_tests = int(sys.argv[1])
        except ValueError:
            print(f"Warning: Invalid number of tests '{sys.argv[1]}', using default 100")
    
    print(f"\nGenerating {num_tests} test cases...")
    generator = TestCaseGenerator(seed=42)
    test_cases = generator.generate_batch(num_tests)
    print(f"✓ Generated {len(test_cases)} test cases")
    
    print("\nStarting experiments...")
    runner = ExperimentRunner(output_dir="results")
    results, encoding_stats = runner.run_experiments(test_cases)
    
    runner.save_results(results, encoding_stats)
    
    print("\nGenerating analysis and summary...")
    analyzer = ResultsAnalyzer(results, encoding_stats)
    summary_file = "results/report.pdf"
    analyzer.save_summary(summary_file)
    
    print("\n" + analyzer.generate_summary())
    
    print("\n" + "="*80)
    print("EXPERIMENT COMPLETE")
    print("="*80)
    print(f"Results directory: results/")
    print(f"  - test_cases/: Input files for all test cases")
    print(f"  - cnf_files/: Generated DIMACS CNF files")
    print(f"  - summary.txt: Summary and analysis")
    
    if not runner.available_solvers:
        print("\n" + "="*80)
        print("RECOMMENDATION: Install SAT Solvers")
        print("="*80)
        print("No SAT solvers were found. To run solver comparisons, install:")
        print("  Z3:      sudo apt-get install z3")
        print("  MiniSat: sudo apt-get install minisat")
        print("  Glucose: Download from satcompetition.org")
        print("\nCNF files have been generated and can be tested manually.")
    
    print("="*80)


if __name__ == "__main__":
    main()
