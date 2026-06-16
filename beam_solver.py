class BeamLoad:
    def __init__(self, kind, magnitude, position=0.0, end_position=0.0):
        self.kind = kind
        self.magnitude = magnitude
        self.position = position
        self.end_position = end_position

    def label(self):
        if self.kind == "Point load":
            return f"Point load {self.magnitude:g} N at {self.position:g} m"
        if self.kind == "Point moment":
            return f"Point moment {self.magnitude:g} N.m at {self.position:g} m"
        return f"UDL {self.magnitude:g} N/m from {self.position:g} to {self.end_position:g} m"


def solve_linear_system(matrix, vector):
    n = len(vector)
    a = [row[:] + [vector[i]] for i, row in enumerate(matrix)]

    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 1e-14:
            raise ValueError("The support conditions leave the beam unstable.")
        a[col], a[pivot] = a[pivot], a[col]

        pivot_value = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= pivot_value

        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            for j in range(col, n + 1):
                a[row][j] -= factor * a[col][j]

    return [a[i][n] for i in range(n)]


class BeamSolver:
    def __init__(self, length, elastic_modulus, inertia, extreme_fiber, nodes, left_support, right_support, loads):
        self.length = length
        self.elastic_modulus = elastic_modulus
        self.inertia = inertia
        self.extreme_fiber = extreme_fiber
        self.nodes = nodes
        self.left_support = left_support
        self.right_support = right_support
        self.loads = loads
        self.x_nodes = [i * length / (nodes - 1) for i in range(nodes)]
        self.dofs = 2 * nodes

    def solve(self):
        stiffness = [[0.0 for _ in range(self.dofs)] for _ in range(self.dofs)]
        force = [0.0 for _ in range(self.dofs)]

        for element in range(self.nodes - 1):
            x0 = self.x_nodes[element]
            x1 = self.x_nodes[element + 1]
            span = x1 - x0
            self._assemble_stiffness(stiffness, element, span)
            self._assemble_distributed_load(force, element, x0, x1, span)

        for load in self.loads:
            if load.kind == "Point load":
                self._apply_point_load(force, load.position, load.magnitude)
            elif load.kind == "Point moment":
                self._apply_point_moment(force, load.position, load.magnitude)

        constrained = self._constrained_dofs()
        free = [i for i in range(self.dofs) if i not in constrained]
        reduced_k = [[stiffness[i][j] for j in free] for i in free]
        reduced_f = [force[i] for i in free]
        solved = solve_linear_system(reduced_k, reduced_f)

        displacement = [0.0 for _ in range(self.dofs)]
        for i, dof in enumerate(free):
            displacement[dof] = solved[i]

        reactions = [
            sum(stiffness[i][j] * displacement[j] for j in range(self.dofs)) - force[i]
            for i in range(self.dofs)
        ]

        return self._sample_results(displacement, reactions)

    def _assemble_stiffness(self, stiffness, element, span):
        ei = self.elastic_modulus * self.inertia
        factor = ei / (span ** 3)
        local = [
            [12, 6 * span, -12, 6 * span],
            [6 * span, 4 * span ** 2, -6 * span, 2 * span ** 2],
            [-12, -6 * span, 12, -6 * span],
            [6 * span, 2 * span ** 2, -6 * span, 4 * span ** 2],
        ]
        dofs = [2 * element, 2 * element + 1, 2 * element + 2, 2 * element + 3]
        for i in range(4):
            for j in range(4):
                stiffness[dofs[i]][dofs[j]] += factor * local[i][j]

    def _assemble_distributed_load(self, force, element, x0, x1, span):
        for load in self.loads:
            if load.kind != "UDL":
                continue
            overlap_start = max(x0, load.position)
            overlap_end = min(x1, load.end_position)
            if overlap_end <= overlap_start:
                continue

            sub_start = (overlap_start - x0) / span
            sub_end = (overlap_end - x0) / span
            gauss_points = [-0.9061798459, -0.5384693101, 0.0, 0.5384693101, 0.9061798459]
            weights = [0.2369268850, 0.4786286705, 0.5688888889, 0.4786286705, 0.2369268850]
            dofs = [2 * element, 2 * element + 1, 2 * element + 2, 2 * element + 3]
            jacobian = (sub_end - sub_start) / 2
            center = (sub_start + sub_end) / 2

            for point, weight in zip(gauss_points, weights):
                xi = center + jacobian * point
                n = self._shape_functions(xi, span)
                for i in range(4):
                    force[dofs[i]] += n[i] * load.magnitude * span * jacobian * weight

    def _apply_point_load(self, force, x, magnitude):
        element = min(max(int(x / self.length * (self.nodes - 1)), 0), self.nodes - 2)
        x0 = self.x_nodes[element]
        span = self.x_nodes[element + 1] - x0
        xi = min(max((x - x0) / span, 0.0), 1.0)
        n = self._shape_functions(xi, span)
        dofs = [2 * element, 2 * element + 1, 2 * element + 2, 2 * element + 3]
        for i in range(4):
            force[dofs[i]] += n[i] * magnitude

    def _apply_point_moment(self, force, x, magnitude):
        element = min(max(int(x / self.length * (self.nodes - 1)), 0), self.nodes - 2)
        x0 = self.x_nodes[element]
        span = self.x_nodes[element + 1] - x0
        xi = min(max((x - x0) / span, 0.0), 1.0)
        derivatives = self._shape_function_derivatives(xi, span)
        dofs = [2 * element, 2 * element + 1, 2 * element + 2, 2 * element + 3]
        for i in range(4):
            force[dofs[i]] += derivatives[i] * magnitude

    def _constrained_dofs(self):
        constrained = []
        constrained.extend(self._support_dofs(self.left_support, 0))
        constrained.extend(self._support_dofs(self.right_support, self.nodes - 1))
        return sorted(set(constrained))

    def _support_dofs(self, support, node):
        vertical = 2 * node
        rotation = vertical + 1
        if support == "Fixed":
            return [vertical, rotation]
        if support in ("Pinned", "Roller"):
            return [vertical]
        return []

    def _sample_results(self, displacement, reactions):
        samples = 401
        xs = [i * self.length / (samples - 1) for i in range(samples)]
        deflection = []

        for x in xs:
            element = min(max(int(x / self.length * (self.nodes - 1)), 0), self.nodes - 2)
            x0 = self.x_nodes[element]
            span = self.x_nodes[element + 1] - x0
            xi = min(max((x - x0) / span, 0.0), 1.0)
            n = self._shape_functions(xi, span)
            dofs = [2 * element, 2 * element + 1, 2 * element + 2, 2 * element + 3]
            deflection.append(sum(n[i] * displacement[dofs[i]] for i in range(4)))

        reaction_forces = []
        reaction_moments = []
        for node, x in enumerate(self.x_nodes):
            vertical = reactions[2 * node]
            moment = reactions[2 * node + 1]
            if abs(vertical) > 1e-6:
                reaction_forces.append((x, vertical))
            if abs(moment) > 1e-6:
                reaction_moments.append((x, moment))

        shear = []
        moment = []
        stress = []
        for x in xs:
            v = 0.0
            m = 0.0

            for xr, value in reaction_forces:
                if xr <= x + 1e-10:
                    v += value
                    m += value * (x - xr)
            for xm, value in reaction_moments:
                if xm <= x + 1e-10:
                    m -= value

            for load in self.loads:
                if load.kind == "Point load" and load.position <= x + 1e-10:
                    v += load.magnitude
                    m += load.magnitude * (x - load.position)
                elif load.kind == "Point moment" and load.position <= x + 1e-10:
                    m -= load.magnitude
                elif load.kind == "UDL":
                    active_length = min(x, load.end_position) - load.position
                    if active_length > 0:
                        active_length = min(active_length, load.end_position - load.position)
                        resultant = load.magnitude * active_length
                        centroid = load.position + active_length / 2
                        v += resultant
                        m += resultant * (x - centroid)

            shear.append(v)
            moment.append(m)
            stress.append(m * self.extreme_fiber / self.inertia if self.inertia else 0.0)

        return {
            "x": xs,
            "deflection": deflection,
            "shear": shear,
            "moment": moment,
            "stress": stress,
            "reactions": reactions,
            "nodes": self.x_nodes,
        }

    @staticmethod
    def _shape_functions(xi, span):
        return [
            1 - 3 * xi ** 2 + 2 * xi ** 3,
            span * (xi - 2 * xi ** 2 + xi ** 3),
            3 * xi ** 2 - 2 * xi ** 3,
            span * (-xi ** 2 + xi ** 3),
        ]

    @staticmethod
    def _shape_function_derivatives(xi, span):
        return [
            (-6 * xi + 6 * xi ** 2) / span,
            1 - 4 * xi + 3 * xi ** 2,
            (6 * xi - 6 * xi ** 2) / span,
            -2 * xi + 3 * xi ** 2,
        ]
