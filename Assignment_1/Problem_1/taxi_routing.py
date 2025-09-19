from heapq import heappush, heappop
from collections import defaultdict
import math
import copy
import matplotlib.pyplot as plt
import pandas as pd


class TaxiRouter:
    def __init__(self, num_nodes, edges, trips, wait_penalty=30.0, speed_kmh=40.0):
        self.num_nodes = num_nodes
        self.edges = edges
        self.trips = trips
        self.wait_penalty = wait_penalty
        self.speed_kmh = speed_kmh
        self.minutes_per_km = 60.0 / speed_kmh

        self.graph = self._build_graph()
        self.all_times = self._compute_all_shortest_times()

    def _build_graph(self):
        graph = defaultdict(list)
        for a, b, km in self.edges:
            graph[a].append((b, km))
            graph[b].append((a, km))
        return graph

    def _single_source_times(self, src):
        dist_km = {n: math.inf for n in range(1, self.num_nodes + 1)}
        dist_km[src] = 0.0
        heap = [(0.0, src)]

        while heap:
            d, node = heappop(heap)
            if d > dist_km[node]:
                continue
            for nxt, km in self.graph[node]:
                nd = d + km
                if nd < dist_km[nxt]:
                    dist_km[nxt] = nd
                    heappush(heap, (nd, nxt))

        return {n: dist_km[n] * self.minutes_per_km for n in dist_km}

    def _compute_all_shortest_times(self):
        return {n: self._single_source_times(n) for n in range(1, self.num_nodes + 1)}

    def _admissible_sum_heuristic(self, taxi_list):
        total = 0.0
        for t in taxi_list:
            if t['done']:
                continue
            cur, dest = t['pos'], t['dest']
            total += self.all_times[cur].get(dest, math.inf)
        return total

    @staticmethod
    def _undirected_edge(u, v):
        return (u, v) if u <= v else (v, u)

    @staticmethod
    def _overlapping_count(schedule, edge_key, s_time, e_time):
        cnt = 0
        for rec in schedule:
            ek, st, en = rec['edge'], rec['start'], rec['end']
            if ek == edge_key and not (en <= s_time or st >= e_time):
                cnt += 1
        return cnt

    def _initialize_taxi_states(self):
        taxi_states_init = []
        for origin, dest in self.trips:
            taxi_states_init.append({
                'pos': origin,
                'available_at': 0.0,
                'done': origin == dest,
                'dest': dest,
                'route': [origin],
                'wait_events': []
            })
        return taxi_states_init

    def _serialize_states(self, taxi_states):
        return tuple(tuple(sorted(ts.items())) for ts in taxi_states)

    def _deserialize_states(self, ser_states):
        taxi_states = []
        for s in ser_states:
            d = dict(s)
            taxi_states.append({
                'pos': d['pos'],
                'available_at': d['available_at'],
                'done': d['done'],
                'dest': d['dest'],
                'route': list(d['route']),
                'wait_events': list(d['wait_events']),
            })
        return taxi_states

    def _deserialize_schedule(self, ser_schedule):
        schedule = []
        for e in ser_schedule:
            schedule.append({
                'edge': e[0][1] if isinstance(e[0], tuple) and e[0][0] == 'edge' else dict(e)['edge'],
                'start': float(dict(e)['start']),
                'end': float(dict(e)['end']),
                'taxi': int(dict(e).get('taxi', -1))
            })
        return schedule

    def _get_canonical_key(self, taxi_states):
        return tuple((t['pos'], int(round(t['available_at'])), t['done']) for t in taxi_states)

    def solve(self):
        taxi_states_init = self._initialize_taxi_states()
        open_heap, counter = [], 0
        g0, h0 = 0.0, self._admissible_sum_heuristic(taxi_states_init)

        heappush(open_heap, (g0 + h0, g0, counter, self._serialize_states(taxi_states_init), tuple()))
        counter += 1

        seen, solution = {}, None

        while open_heap:
            f, g, _, ser_states, ser_schedule = heappop(open_heap)
            taxi_states = self._deserialize_states(ser_states)
            schedule = self._deserialize_schedule(ser_schedule)

            if all(t['done'] for t in taxi_states):
                solution = (g, taxi_states, schedule)
                break

            key = self._get_canonical_key(taxi_states)
            if key in seen and seen[key] <= g:
                continue
            seen[key] = g

            for idx, t in enumerate(taxi_states):
                if t['done']:
                    continue

                current_pos, atime = t['pos'], t['available_at']
                for (nbr, km) in self.graph[current_pos]:
                    traversal = km * self.minutes_per_km
                    ek = self._undirected_edge(current_pos, nbr)

                    attempt_time, attempts = atime, 0
                    while True:
                        c = self._overlapping_count(schedule, ek, attempt_time, attempt_time + traversal)
                        if c <= 1:
                            break
                        attempt_time += self.wait_penalty
                        attempts += 1
                        if attempts > 200:
                            break

                    end_time = attempt_time + traversal
                    new_states, new_schedule = copy.deepcopy(taxi_states), list(schedule)
                    new_schedule.append({'edge': ek, 'start': attempt_time, 'end': end_time, 'taxi': idx})

                    new_states[idx]['pos'] = nbr
                    new_states[idx]['available_at'] = end_time
                    new_states[idx]['route'] = new_states[idx]['route'] + [nbr]

                    if attempt_time > atime:
                        new_states[idx]['wait_events'] = new_states[idx]['wait_events'] + [{
                            'node': current_pos, 'from': atime, 'to': attempt_time, 'reason': 'capacity'
                        }]

                    if nbr == new_states[idx]['dest']:
                        new_states[idx]['done'] = True

                    delta = new_states[idx]['available_at'] - atime
                    new_g = g + delta
                    new_h = self._admissible_sum_heuristic(new_states)

                    ser_new_states = self._serialize_states(new_states)
                    ser_new_sched = tuple(tuple(sorted(entry.items())) for entry in new_schedule)
                    heappush(open_heap, (new_g + new_h, new_g, counter, ser_new_states, ser_new_sched))
                    counter += 1

        return solution


class TaxiRouterVisualizer:
    def __init__(self, router):
        self.router = router

    def print_results(self, solution):
        if solution is None:
            print("No feasible plan found.")
            return

        total_cost, final_taxis, final_schedule = solution
        rows = []

        for i, t in enumerate(final_taxis):
            rows.append({
                'Taxi': i + 1,
                'Trip': f"{self.router.trips[i][0]} -> {self.router.trips[i][1]}",
                'Route': ' -> '.join(map(str, t['route'])),
                'Waits': t['wait_events'],
                'Completion_min': round(t['available_at'], 2)
            })

        df = pd.DataFrame(rows)
        print("Solving started")
        print(f"\nTotal objective (sum of completion times) = {round(total_cost, 2)} minutes")
        return rows

    def plot_gantt_chart(self, solution):
        if solution is None:
            return

        total_cost, final_taxis, final_schedule = solution
        plot_entries = [{'taxi': e['taxi'], 'edge': e['edge'], 'start': e['start'], 'end': e['end']} for e in final_schedule]

        if not plot_entries:
            return

        fig, ax = plt.subplots(figsize=(10, 3 + 0.7 * len(self.router.trips)))
        yticks, ylabels = [], []

        for i in range(len(self.router.trips)):
            yticks.append(i)
            ylabels.append(f"Taxi {i + 1}")

        ax.set_yticks(yticks)
        ax.set_yticklabels(ylabels)

        for pe in plot_entries:
            taxi = pe['taxi']
            if taxi < 0 or taxi >= len(self.router.trips):
                continue
            start, dur = pe['start'], pe['end'] - pe['start']
            ax.broken_barh([(start, dur)], (taxi - 0.3, 0.6))
            ax.text(start + dur/2, taxi, f"{pe['edge']}", va='center', ha='center', fontsize=8)

        ax.set_xlabel('Time (minutes)')
        ax.set_title('Taxi traversal timeline')
        ax.grid(True, axis='x', linestyle=':', linewidth=0.5)
        plt.tight_layout()
        plt.show()

    def print_detailed_breakdown(self, rows):
        print("Solving ended")
        for i, r in enumerate(rows):
            print(f"\nTaxi {r['Taxi']} ({r['Trip']}):")
            print("  Route:", r['Route'])
            print("  Completion time (min):", r['Completion_min'])
            if r['Waits']:
                print('  Wait events:')
                for w in r['Waits']:
                    print(f"   - Node {w['node']} from {w['from']} to {w['to']} (reason: {w['reason']})")


def run_taxi_routing(num_nodes, edges, trips, wait_penalty=30.0, speed_kmh=40.0):
    router = TaxiRouter(num_nodes, edges, trips, wait_penalty, speed_kmh)
    solution = router.solve()
    visualizer = TaxiRouterVisualizer(router)
    rows = visualizer.print_results(solution)

    if solution is not None:
        visualizer.plot_gantt_chart(solution)
        visualizer.print_detailed_breakdown(rows)


if __name__ == "__main__":
    NUM_NODES = 8
    EDGES = [
        (1, 2, 30),
        (2, 3, 50),
        (2, 4, 60),
        (3, 5, 40),
        (4, 6, 70),
        (5, 7, 20),
        (6, 7, 30),
        (7, 8, 50),
        (3, 6, 90),
    ]
    TRIPS = [(2, 7), (1, 8), (3, 4)]
    WAIT_PENALTY, SPEED_KMH = 30.0, 40.0
    run_taxi_routing(NUM_NODES, EDGES, TRIPS, WAIT_PENALTY, SPEED_KMH)