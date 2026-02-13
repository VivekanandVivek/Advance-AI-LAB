#!/usr/bin/env python3
"""
Academic Task Scheduling System
Optimizes completion of dependent tasks across multiple AI platforms
"""

import sys
from collections import deque, defaultdict
import heapq


class TaskSchedulingEngine:
    """
    Manages scheduling optimization for AI-assisted academic tasks
    with dependency constraints and resource limitations
    """
    
    def __init__(self, task_registry, chatgpt_cost, gemini_cost):
        self.task_registry = task_registry
        self.chatgpt_cost = chatgpt_cost
        self.gemini_cost = gemini_cost
        self._build_dependency_graph()
    
    def _build_dependency_graph(self):
        """Construct adjacency list for task dependencies"""
        self.graph = defaultdict(list)
        self.reverse_deps = defaultdict(set)
        
        for task_id, task_info in self.task_registry.items():
            for prerequisite in task_info['dependencies']:
                self.graph[prerequisite].append(task_id)
                self.reverse_deps[task_id].add(prerequisite)
    
    def validate_capacity_constraints(self, chatgpt_limit, gemini_limit):
        """
        Verify that individual task requirements don't exceed capacity
        Returns: Boolean indicating feasibility
        """
        for task_id, task_data in self.task_registry.items():
            platform = task_data['platform']
            prompts_needed = task_data['prompts']
            
            capacity = chatgpt_limit if platform == 0 else gemini_limit
            
            if prompts_needed > capacity:
                return False
        
        return True
    
    def find_optimal_completion_timeline(self, chatgpt_cap, gemini_cap, allow_parallel):
        """
        Determines minimum days and associated cost to complete all tasks
        
        Args:
            chatgpt_cap: Daily prompt limit for ChatGPT
            gemini_cap: Daily prompt limit for Gemini
            allow_parallel: Whether multiple tasks can run simultaneously per day
            
        Returns:
            Tuple of (days_needed, total_cost) or (None, None) if infeasible
        """
        
        if not self.validate_capacity_constraints(chatgpt_cap, gemini_cap):
            return None, None
        
        # BFS-style state exploration with priority queue
        initial_state = ScheduleState(
            day_number=1,
            accumulated_cost=0,
            completed_tasks=frozenset()
        )
        
        priority_queue = [initial_state]
        explored_states = {}
        
        total_task_count = len(self.task_registry)
        
        while priority_queue:
            current_state = heapq.heappop(priority_queue)
            
            # Goal state reached
            if len(current_state.completed_tasks) == total_task_count:
                return current_state.day_number - 1, current_state.accumulated_cost
            
            # Prune redundant states
            state_key = current_state.completed_tasks
            if state_key in explored_states:
                if explored_states[state_key] <= current_state.day_number:
                    continue
            
            explored_states[state_key] = current_state.day_number
            
            # Identify executable tasks (all prerequisites met)
            ready_tasks = self._get_ready_tasks(current_state.completed_tasks)
            
            # Generate valid task combinations for current day
            valid_combinations = self._generate_task_combinations(
                ready_tasks, 
                chatgpt_cap, 
                gemini_cap, 
                allow_parallel
            )
            
            # No tasks can be executed - advance to next day
            if not valid_combinations:
                next_state = ScheduleState(
                    day_number=current_state.day_number + 1,
                    accumulated_cost=current_state.accumulated_cost,
                    completed_tasks=current_state.completed_tasks
                )
                heapq.heappush(priority_queue, next_state)
            else:
                # Try each valid combination
                for task_batch in valid_combinations:
                    new_completed = current_state.completed_tasks | frozenset(task_batch)
                    batch_cost = self._calculate_batch_cost(task_batch)
                    
                    next_state = ScheduleState(
                        day_number=current_state.day_number + 1,
                        accumulated_cost=current_state.accumulated_cost + batch_cost,
                        completed_tasks=new_completed
                    )
                    heapq.heappush(priority_queue, next_state)
        
        return None, None
    
    def _get_ready_tasks(self, completed_set):
        """Find tasks with all dependencies satisfied"""
        ready = []
        
        for task_id, task_info in self.task_registry.items():
            if task_id in completed_set:
                continue
            
            prerequisites = task_info['dependencies']
            
            if all(dep in completed_set for dep in prerequisites):
                ready.append(task_id)
        
        return ready
    
    def _generate_task_combinations(self, available_tasks, cap_chatgpt, cap_gemini, parallel_mode):
        """
        Generate feasible task combinations respecting resource limits
        
        Returns: List of task combinations (each combination is a list of task IDs)
        """
        combinations = []
        
        if not parallel_mode:
            # Sequential mode: one task per day
            for task_id in available_tasks:
                task_info = self.task_registry[task_id]
                platform = task_info['platform']
                prompts = task_info['prompts']
                
                capacity = cap_chatgpt if platform == 0 else cap_gemini
                
                if prompts <= capacity:
                    combinations.append([task_id])
        else:
            # Parallel mode: fit multiple tasks in one day
            batch = []
            remaining_chatgpt = cap_chatgpt
            remaining_gemini = cap_gemini
            
            for task_id in available_tasks:
                task_info = self.task_registry[task_id]
                platform = task_info['platform']
                prompts = task_info['prompts']
                
                if platform == 0 and prompts <= remaining_chatgpt:
                    batch.append(task_id)
                    remaining_chatgpt -= prompts
                elif platform == 1 and prompts <= remaining_gemini:
                    batch.append(task_id)
                    remaining_gemini -= prompts
            
            if batch:
                combinations.append(batch)
        
        return combinations
    
    def _calculate_batch_cost(self, task_batch):
        """Calculate total cost for a batch of tasks"""
        total = 0
        
        for task_id in task_batch:
            task_info = self.task_registry[task_id]
            platform = task_info['platform']
            prompts = task_info['prompts']
            
            cost_per_prompt = self.chatgpt_cost if platform == 0 else self.gemini_cost
            total += cost_per_prompt * prompts
        
        return total
    
    def optimize_subscription_plan(self, deadline, parallel_mode):
        """
        Find minimum-cost subscription to meet deadline
        
        Args:
            deadline: Maximum days allowed
            parallel_mode: Whether parallel execution is allowed
            
        Returns:
            Tuple of (chatgpt_capacity, gemini_capacity, daily_cost) or None
        """
        optimal_plan = None
        minimum_cost = float('inf')
        
        # Search space for subscription capacities
        for chatgpt_prompts in range(1, 20):
            for gemini_prompts in range(1, 20):
                daily_subscription_cost = (chatgpt_prompts * self.chatgpt_cost + 
                                          gemini_prompts * self.gemini_cost)
                
                # Skip if already more expensive than current best
                if daily_subscription_cost >= minimum_cost:
                    continue
                
                days_required, _ = self.find_optimal_completion_timeline(
                    chatgpt_prompts, 
                    gemini_prompts, 
                    parallel_mode
                )
                
                if days_required is not None and days_required <= deadline:
                    minimum_cost = daily_subscription_cost
                    optimal_plan = (chatgpt_prompts, gemini_prompts, daily_subscription_cost)
        
        return optimal_plan


class ScheduleState:
    """Represents a state in the scheduling search space"""
    
    def __init__(self, day_number, accumulated_cost, completed_tasks):
        self.day_number = day_number
        self.accumulated_cost = accumulated_cost
        self.completed_tasks = completed_tasks
    
    def __lt__(self, other):
        """Priority comparison for heap queue"""
        # Prioritize by day, then by cost
        if self.day_number != other.day_number:
            return self.day_number < other.day_number
        return self.accumulated_cost < other.accumulated_cost


def load_task_data(filepath):
    """
    Parse input file and construct task registry
    
    Returns:
        Dictionary mapping task_id to task attributes
    """
    task_map = {}
    
    with open(filepath, 'r') as file:
        for line in file:
            line = line.strip()
            
            # Skip comments and metadata
            if not line or line[0] in ['%', 'N', 'K']:
                continue
            
            # Parse task specification
            line = line.replace('A', '')
            tokens = list(map(int, line.split()))
            
            if len(tokens) < 2:
                continue
            
            task_identifier = tokens[0]
            prompt_count = tokens[1]
            prerequisites = tokens[2:-1] if len(tokens) > 3 else []
            
            # Platform assignment: even IDs -> ChatGPT, odd IDs -> Gemini
            platform_type = 0 if task_identifier % 2 == 0 else 1
            
            task_map[task_identifier] = {
                'prompts': prompt_count,
                'dependencies': prerequisites,
                'platform': platform_type
            }
    
    return task_map


def main():
    """Main execution entry point"""
    
    if len(sys.argv) != 7:
        print("Usage: python assignment_scheduler.py <input_file> <c1> <c2> <cap1> <cap2> <deadline>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    cost_chatgpt = int(sys.argv[2])
    cost_gemini = int(sys.argv[3])
    capacity_chatgpt = int(sys.argv[4])
    capacity_gemini = int(sys.argv[5])
    max_days = int(sys.argv[6])
    
    # Load and initialize
    tasks = load_task_data(input_file)
    scheduler = TaskSchedulingEngine(tasks, cost_chatgpt, cost_gemini)
    
    # Analyze both execution modes
    execution_modes = [
        ("Sequential Mode (Case-A)", False),
        ("Parallel Mode (Case-B)", True)
    ]
    
    for mode_label, parallel_enabled in execution_modes:
        print(f"\n{'='*50}")
        print(f"{mode_label}")
        print('='*50)
        
        # Query 1: Minimum completion time
        days, cost = scheduler.find_optimal_completion_timeline(
            capacity_chatgpt, 
            capacity_gemini, 
            parallel_enabled
        )
        
        if days is not None:
            print(f"Minimum Completion Time: {days} days")
            print(f"Total Cost: ${cost}")
        else:
            print("Status: Infeasible with given constraints")
        
        # Query 2: Optimal subscription for deadline
        optimal = scheduler.optimize_subscription_plan(max_days, parallel_enabled)
        
        if optimal:
            chatgpt_cap, gemini_cap, daily_cost = optimal
            print(f"\nOptimal Subscription for {max_days}-day deadline:")
            print(f"  ChatGPT Capacity: {chatgpt_cap} prompts/day")
            print(f"  Gemini Capacity: {gemini_cap} prompts/day")
            print(f"  Daily Cost: ${daily_cost}")
        else:
            print(f"\nNo feasible subscription found for {max_days}-day deadline")


if __name__ == "__main__":
    main()
