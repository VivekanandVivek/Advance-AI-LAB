import sys
from math import ceil

try:
    from z3 import (
        Optimize, Bool, Int, If, And, Or, Sum, Not,
        sat, IntVal, BoolVal
    )
except ImportError:
    print("[ERROR] z3-solver is not installed.")
    print("Run:  pip install z3-solver")
    sys.exit(1)

class ChargingPort:
    def __init__(self, port_id: int, price: int):
        self.port_id = port_id
        self.price = price

    def duration_for(self, base_charge: int) -> int:
        return ceil(base_charge/self.port_id)

    def cost_for(self, base_charge: int) -> int:
        return self.price*self.duration_for(base_charge)

    def __repr__(self):
        return f"ChargingPort(id={self.port_id}, price={self.price})"


class Vehicle:
    def __init__(self, vid: int, arrival: int, departure: int, charge_time: int):
        self.vid = vid
        self.arrival = arrival
        self.departure = departure
        self.charge_time = charge_time

    def __repr__(self):
        return (f"Vehicle(id={self.vid}, arrival={self.arrival}, "
                f"departure={self.departure}, charge={self.charge_time})")


class ScheduleResult:
    def __init__(self, vehicle: Vehicle, port: ChargingPort,
                 start: int, end: int, cost: int):
        self.vehicle = vehicle
        self.port = port
        self.start = start
        self.end  = end
        self.cost  = cost

    def is_scheduled(self) -> bool:
        return self.port is not None

    def __repr__(self):
        if not self.is_scheduled():
            return f"Vehicle {self.vehicle.vid}: UNSCHEDULED"
        return (f"Vehicle {self.vehicle.vid} -> Port {self.port.port_id} "
                f"[{self.start}, {self.end})  cost={self.cost}")

class Z3Scheduler:

    def __init__(self, ports: list, vehicles: list):
        self.ports    = ports
        self.vehicles = vehicles
        self.n        = len(vehicles)
        self.K        = len(ports)

        # Precompute integer duration and cost tables
        self.dur  = [[p.duration_for(v.charge_time) for p in ports]
                     for v in vehicles]
        self.cost = [[p.cost_for(v.charge_time) for p in ports]
                     for v in vehicles]

    def _build_model(self):
        opt = Optimize()

        n, K = self.n, self.K
        V, P = self.vehicles, self.ports

        # Decision variables 
        # b[i][k] : vehicle i assigned to port (k+1)
        b = [[Bool(f"b_{V[i].vid}_p{P[k].port_id}") for k in range(K)]
             for i in range(n)]

        # s[i] : start time for vehicle i
        s = [Int(f"s_{V[i].vid}") for i in range(n)]

        # Constraint A: exactly one port per vehicle
        for i in range(n):
            # At least one port selected
            opt.add(Or(b[i]))
            # At most one port selected
            for k1 in range(K):
                for k2 in range(k1 + 1, K):
                    opt.add(Or(Not(b[i][k1]), Not(b[i][k2])))

        # Constraint B: time window 
        for i in range(n):
            v = V[i]
            for k in range(K):
                dur_ik = self.dur[i][k]
                # If b[i][k] then arrival <= s[i] <= departure - duration
                opt.add(
                    Or(
                        Not(b[i][k]),
                        And(
                            s[i] >= v.arrival,
                            s[i] + dur_ik <= v.departure
                        )
                    )
                )

        # Constraint C: no overlap on same port 
        for k in range(K):
            for i in range(n):
                for j in range(i + 1, n):
                    dur_ik = self.dur[i][k]
                    dur_jk = self.dur[j][k]
                    # If both assigned to same port -> must not overlap
                    opt.add(
                        Or(
                            Not(b[i][k]),
                            Not(b[j][k]),
                            s[i] + dur_ik <= s[j],
                            s[j] + dur_jk <= s[i]
                        )
                    )

        # Objective: minimise total cost 
        total_cost = Sum([
            If(b[i][k], self.cost[i][k], 0)
            for i in range(n)
            for k in range(K)
        ])
        opt.minimize(total_cost)

        return opt, b, s

    def solve(self):
        opt, b, s = self._build_model()

        status = opt.check()

        if status != sat:
            print("[Z3] No feasible schedule found.")
            return [], None

        model = opt.model()

        results = []
        total   = 0

        for i, v in enumerate(self.vehicles):
            assigned_port  = None
            assigned_start = None
            assigned_cost  = None

            for k, p in enumerate(self.ports):
                if model.evaluate(b[i][k]):
                    start_val = model.evaluate(s[i]).as_long()
                    dur_val   = self.dur[i][k]
                    cost_val  = self.cost[i][k]

                    assigned_port  = p
                    assigned_start = start_val
                    assigned_cost  = cost_val
                    total         += cost_val
                    break

            results.append(
                ScheduleResult(
                    v,
                    assigned_port,
                    assigned_start,
                    assigned_start + self.dur[i][self.ports.index(assigned_port)]
                    if assigned_port else None,
                    assigned_cost
                )
            )

        return results, total

class ResultPrinter:
    @staticmethod
    def show(results: list, total_cost: int):
        header = f"{'VehicleID':>10}  {'Port':>5}  {'Start':>7}  {'End':>5}  {'Cost':>8}"
        sep  = "-" * 44
        print(f"\n{header}")
        print(sep)
        for r in sorted(results, key=lambda x: x.vehicle.vid):
            if r.is_scheduled():
                print(f"{r.vehicle.vid:>10}  {r.port.port_id:>5}  "
                      f"{r.start:>7}  {r.end:>5}  {r.cost:>8}")
            else:
                print(f"{r.vehicle.vid:>10}  {'UNSCHEDULED':>35}")
        print(sep)
        print(f"{'Minimum Total Cost':>35} : {total_cost}\n")

class InputParser:
    @staticmethod
    def from_file(filepath: str):
        with open(filepath) as f:
            lines = [ln.strip() for ln in f
                     if ln.strip() and not ln.strip().startswith('%')]

        K, prices, vehicles = None, [], []
        for line in lines:
            tokens = line.split()
            if tokens[0] == 'K':
                K = int(tokens[1])
            elif tokens[0] == 'P':
                prices = list(map(int, tokens[1:]))
            elif tokens[0] == 'V':
                vid, a, d, c = (int(tokens[1]), int(tokens[2]),
                                int(tokens[3]), int(tokens[4]))
                vehicles.append(Vehicle(vid, a, d, c))

        ports = [ChargingPort(k, prices[k - 1]) for k in range(1, K + 1)]
        return ports, vehicles

    @staticmethod
    def default():
        ports = [
            ChargingPort(1,  5),
            ChargingPort(2, 12),
            ChargingPort(3, 17),
            ChargingPort(4, 23),
            ChargingPort(5, 32),
        ]
        vehicles = [
            Vehicle(1, 10, 24, 12),
            Vehicle(2,  2, 22,  6),
        ]
        return ports, vehicles

def main():
    if len(sys.argv) >= 2:
        ports, vehicles = InputParser.from_file(sys.argv[1])
    else:
        ports, vehicles = InputParser.default()

    print(f"Charging Station  |  Ports: {len(ports)}  |  Vehicles: {len(vehicles)}")
    print(f"Port prices       : {[p.price for p in ports]}")
    print("Solving with Z3 Optimizer ...\n")

    scheduler = Z3Scheduler(ports, vehicles)
    results, total_cost = scheduler.solve()

    if results:
        ResultPrinter.show(results, total_cost)


if __name__ == '__main__':
    main()
