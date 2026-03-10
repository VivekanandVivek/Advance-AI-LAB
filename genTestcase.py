import random
from math import ceil

def generate_prices(K, rng):
    base = rng.randint(3, 10)
    prices = [base]
    for _ in range(K - 1):
        prices.append(prices[-1] + rng.randint(4, 12))
    return prices

def generate_vehicles(N, K, rng):
    TIME_HORIZON = 100
    vehicles = []

    for vid in range(1, N + 1):
        arrival = rng.randint(0, TIME_HORIZON - 5)
        charge = rng.randint(1, 20)

        min_window = ceil(charge / K)
        max_window = min(
            charge + rng.randint(5, 30),
            TIME_HORIZON - arrival
        )

        window = max(
            min_window,
            rng.randint(min_window, max(min_window, max_window))
        )

        departure = arrival + window
        vehicles.append((vid, arrival, departure, charge))

    return vehicles

def main():
    try:
        K = int(input("Enter number of ports: "))
        N = int(input("Enter number of vehicles: "))
    except ValueError:
        print("Invalid input.")
        return

    if K < 1 or N < 1:
        print("Both values must be >= 1.")
        return

    rng = random.Random()

    prices = generate_prices(K, rng)
    vehicles = generate_vehicles(N, K, rng)

    with open("testcase.txt", "w") as f:
        f.write("% number of ports - K\n")
        f.write(f"K {K}\n")
        f.write("% Price for ports per time unit\n")
        f.write(f"P {' '.join(map(str, prices))}\n")
        f.write("% vehicle requests: id arrival-time departure-time charge-time\n")

        for vid, a, d, c in vehicles:
            f.write(f"V {vid} {a} {d} {c}\n")

    print("\nGenerated 'testcase.txt' successfully.\n")

if __name__ == "__main__":
    main()
