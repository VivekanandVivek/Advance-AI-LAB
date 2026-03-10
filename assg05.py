import sys
from itertools import combinations
from typing import List, Tuple, Dict, Set


class Course:
    # Represents a single course with scheduling constraints
    
    def __init__(self, course_id: int, earliest_start: int, 
                 latest_finish: int, duration: int):
        self.course_id = course_id
        self.earliest_start = earliest_start
        self.latest_finish = latest_finish
        self.duration = duration
    
    def get_valid_start_range(self) -> range:
        # Returns the range of valid start days for this course
        return range(self.earliest_start, 
                    self.latest_finish - self.duration + 2)
    
    def occupies_day(self, start_day: int, target_day: int) -> bool:
        # Check if course occupies target_day given a start_day
        return start_day <= target_day < start_day + self.duration


class InputParser:
    # Handles parsing of input files
    
    @staticmethod
    def load_from_file(filepath: str) -> Tuple[int, int, List[Course]]:
        num_rooms = 0
        num_courses = 0
        course_list = []
        
        with open(filepath, 'r') as file:
            lines = iter(file)
            for line in lines:
                cleaned = line.strip()
                
                if not cleaned or cleaned.startswith('%'):
                    continue
                
                tokens = cleaned.split()
                
                if tokens[0] == 'M':
                    num_rooms = int(tokens[1])
                elif tokens[0] == 'N':
                    num_courses = int(next(lines).strip())
                elif tokens[0] == 'C':
                    course = Course(
                        course_id=int(tokens[1]),
                        earliest_start=int(tokens[2]),
                        latest_finish=int(tokens[3]),
                        duration=int(tokens[4])
                    )
                    course_list.append(course)
        
        return num_rooms, num_courses, course_list


class VariableEncoder:
    # Manages variable encoding for SAT formulas
    
    def __init__(self, num_courses: int, num_rooms: int, time_horizon: int):
        self.num_courses = num_courses
        self.num_rooms = num_rooms
        self.time_horizon = time_horizon
        self.next_var = 1
    
    def reserve_variables(self, count: int) -> int:
        # Reserve a block of variables and return the starting index
        start = self.next_var
        self.next_var += count
        return start
    
    def get_total_variables(self) -> int:
        # Return total number of variables used
        return self.next_var - 1


class ThreeDimensionalEncoding:
    # Option 1: Encoding using z_ijt variables (course-room-time)
    
    def __init__(self, courses: List[Course], num_rooms: int, time_horizon: int):
        self.courses = courses
        self.num_rooms = num_rooms
        self.time_horizon = time_horizon
        self.var_encoder = VariableEncoder(len(courses), num_rooms, time_horizon)
        self.variable_map = {}
        self._initialize_variables()
    
    def _initialize_variables(self):
        # Create mapping for z[course_idx][room][time] variables
        for course_idx in range(len(self.courses)):
            for room in range(self.num_rooms):
                for time in range(self.time_horizon + 1):
                    var_id = self.var_encoder.reserve_variables(1)
                    self.variable_map[(course_idx, room, time)] = var_id
    
    def get_variable(self, course_idx: int, room: int, time: int) -> int:
        # Retrieve variable ID for given course-room-time triple
        return self.variable_map.get((course_idx, room, time), 0)
    
    def generate_cnf_formula(self) -> List[List[int]]:
        # Generate complete CNF formula with all constraints
        constraint_set = []
        
        # Add course assignment constraints
        constraint_set.extend(self._build_assignment_constraints())
        
        # Add room conflict constraints
        constraint_set.extend(self._build_room_conflict_constraints())
        
        return constraint_set
    
    def _build_assignment_constraints(self) -> List[List[int]]:
        # Each course must be assigned exactly onc
        constraints = []
        
        for course_idx, course in enumerate(self.courses):
            assignment_vars = []
            
            # Collect all valid assignment variables
            for room in range(self.num_rooms):
                for start_time in course.get_valid_start_range():
                    var = self.get_variable(course_idx, room, start_time)
                    if var > 0:
                        assignment_vars.append(var)
            
            # At least one assignment
            constraints.append(assignment_vars)
            
            # At most one assignment
            for var1, var2 in combinations(assignment_vars, 2):
                constraints.append([-var1, -var2])
        
        return constraints
    
    def _build_room_conflict_constraints(self) -> List[List[int]]:
        # Prevent multiple courses in same room at same time
        constraints = []
        
        for room in range(self.num_rooms):
            for day in range(1, self.time_horizon + 1):
                overlapping_assignments = []
                
                for course_idx, course in enumerate(self.courses):
                    # Find all start times where course occupies this day
                    for start_time in course.get_valid_start_range():
                        if course.occupies_day(start_time, day):
                            var = self.get_variable(course_idx, room, start_time)
                            if var > 0:
                                overlapping_assignments.append(var)
                
                # No two courses can overlap
                for var1, var2 in combinations(overlapping_assignments, 2):
                    constraints.append([-var1, -var2])
        
        return constraints


class TwoDimensionalEncoding:
    # Option 2: Encoding using x_ij (room) and y_it (time) variables
    
    def __init__(self, courses: List[Course], num_rooms: int, time_horizon: int):
        self.courses = courses
        self.num_rooms = num_rooms
        self.time_horizon = time_horizon
        self.var_encoder = VariableEncoder(len(courses), num_rooms, time_horizon)
        self.room_assignment_map = {}
        self.time_assignment_map = {}
        self._initialize_variables()
    
    def _initialize_variables(self):
        # Room assignment variables: x[course_idx][room]
        for course_idx in range(len(self.courses)):
            for room in range(self.num_rooms):
                var_id = self.var_encoder.reserve_variables(1)
                self.room_assignment_map[(course_idx, room)] = var_id
        
        # Time assignment variables: y[course_idx][time]
        for course_idx in range(len(self.courses)):
            for time in range(self.time_horizon + 1):
                var_id = self.var_encoder.reserve_variables(1)
                self.time_assignment_map[(course_idx, time)] = var_id
    
    def get_room_variable(self, course_idx: int, room: int) -> int:
        return self.room_assignment_map.get((course_idx, room), 0)
    
    def get_time_variable(self, course_idx: int, time: int) -> int:
        return self.time_assignment_map.get((course_idx, time), 0)
    
    def generate_cnf_formula(self) -> List[List[int]]:
        # Generate complete CNF formula with all constraints
        constraint_set = []
        
        # Add room assignment constraints
        constraint_set.extend(self._build_room_assignment_constraints())
        
        # Add time assignment constraints
        constraint_set.extend(self._build_time_assignment_constraints())
        
        # Add conflict prevention constraints
        constraint_set.extend(self._build_conflict_prevention_constraints())
        
        return constraint_set
    
    def _build_room_assignment_constraints(self) -> List[List[int]]:
        # Each course assigned to exactly one room
        constraints = []
        
        for course_idx in range(len(self.courses)):
            room_vars = [self.get_room_variable(course_idx, room) 
                        for room in range(self.num_rooms)]
            
            # At least one room
            constraints.append(room_vars)
            
            # At most one room
            for var1, var2 in combinations(room_vars, 2):
                constraints.append([-var1, -var2])
        
        return constraints
    
    def _build_time_assignment_constraints(self) -> List[List[int]]:
        # Each course starts at exactly one valid time
        constraints = []
        
        for course_idx, course in enumerate(self.courses):
            time_vars = [self.get_time_variable(course_idx, time) 
                        for time in course.get_valid_start_range()]
            
            # At least one start time
            constraints.append(time_vars)
            
            # At most one start time
            for var1, var2 in combinations(time_vars, 2):
                constraints.append([-var1, -var2])
        
        return constraints
    
    def _build_conflict_prevention_constraints(self) -> List[List[int]]:
        # Prevent time conflicts for courses in same room
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
                            # Check if time intervals overlap
                            if self._intervals_overlap(time1, course1.duration, 
                                                       time2, course2.duration):
                                time_var1 = self.get_time_variable(course1_idx, time1)
                                time_var2 = self.get_time_variable(course2_idx, time2)
                                
                                # Cannot have both courses in same room with overlapping times
                                constraints.append([-room_var1, -room_var2, 
                                                   -time_var1, -time_var2])
        
        return constraints
    
    @staticmethod
    def _intervals_overlap(start1: int, duration1: int, 
                          start2: int, duration2: int) -> bool:
        # Check if two time intervals overlap
        end1 = start1 + duration1
        end2 = start2 + duration2
        return not (end1 <= start2 or end2 <= start1)


class DIMACSWriter:
    # Writes CNF formulas in DIMACS format
    
    @staticmethod
    def write_to_file(clauses: List[List[int]], filepath: str):
        """Export CNF formula to DIMACS file"""
        if not clauses:
            return
        
        # Calculate number of variables
        max_variable = max(abs(literal) 
                          for clause in clauses 
                          for literal in clause)
        
        with open(filepath, 'w') as output:
            # Write header
            output.write(f"p cnf {max_variable} {len(clauses)}\n")
            
            # Write clauses
            for clause in clauses:
                clause_str = " ".join(map(str, clause)) + " 0\n"
                output.write(clause_str)


class SchedulingSolver:
    # Main solver orchestrating the SAT encoding process
    
    def __init__(self, input_file: str):
        self.input_file = input_file
        self.num_rooms = 0
        self.num_courses = 0
        self.courses = []
        self.time_horizon = 30
        self._load_problem_instance()
    
    def _load_problem_instance(self):
        # Load and initialize problem from input file
        parser = InputParser()
        self.num_rooms, self.num_courses, self.courses = \
            parser.load_from_file(self.input_file)
        
        # Calculate time horizon from latest deadline
        if self.courses:
            self.time_horizon = max(course.latest_finish 
                                   for course in self.courses)
    
    def solve_with_encoding_1(self) -> List[List[int]]:
        # Generate CNF using three-dimensional encoding
        encoder = ThreeDimensionalEncoding(self.courses, self.num_rooms, 
                                          self.time_horizon)
        return encoder.generate_cnf_formula()
    
    def solve_with_encoding_2(self) -> List[List[int]]:
        # Generate CNF using two-dimensional encoding
        encoder = TwoDimensionalEncoding(self.courses, self.num_rooms, 
                                        self.time_horizon)
        return encoder.generate_cnf_formula()
    
    def export_solution(self, clauses: List[List[int]], output_file: str):
        # Export generated clauses to DIMACS file
        writer = DIMACSWriter()
        writer.write_to_file(clauses, output_file)
        print(f"Successfully generated: {output_file}")


def main():
    if len(sys.argv) < 3:
        print("Usage: python scheduling_solver.py <input_file> <encoding_type>")
        print("  encoding_type: op-1 (3D encoding) or op-2 (2D encoding)")
        sys.exit(1)
    
    input_filepath = sys.argv[1]
    encoding_type = sys.argv[2].lower()
    
    # Initialize solver
    solver = SchedulingSolver(input_filepath)
    
    # Generate CNF based on encoding type
    if encoding_type == "op-1":
        formula = solver.solve_with_encoding_1()
        output_filename = "formula_op-1.cnf"
    elif encoding_type == "op-2":
        formula = solver.solve_with_encoding_2()
        output_filename = "formula_op-2.cnf"
    else:
        print("Error: Invalid encoding type. Use 'op-1' or 'op-2'")
        sys.exit(1)
    
    # Export to file
    solver.export_solution(formula, output_filename)


if __name__ == "__main__":
    main()



# After generating the .cnf file just comment all the above part of the code and uncommnent 
# below code so run the z3 for the cnf file.


"""

from z3 import *

def solve_cnf(file):
    solver = Solver()

    with open(file, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith('c') or line.startswith('p'):
                continue

            nums = list(map(int, line.split()))
            clause = []

            for n in nums:
                if n == 0:
                    break
                var = Bool(f"x{abs(n)}")
                clause.append(var if n > 0 else Not(var))

            solver.add(Or(clause))

    if solver.check() == sat:
        print("SAT")
        print(solver.model())
    else:
        print("UNSAT")

solve_cnf("formula_op-1.cnf")


"""
