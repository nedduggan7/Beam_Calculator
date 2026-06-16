# Beam Calculator

A Python QtWidgets desktop app for beam analysis.

## Features

- Calculates deflection along a beam with Euler-Bernoulli finite elements.
- Shows deflection, shear force, bending moment, and bending stress diagrams.
- Supports fixed, pinned, roller, and free end constraints.
- Supports point loads, point moments, and uniform distributed loads.
- Includes a cross-section editor for straight-line closed shapes.
- Calculates cross-section area, horizontal neutral axis, `I_x`, and extreme fiber distance `c`.
- Saves named cross sections and lets the beam calculator use them instead of manual `I` and `c` entry.
- Reports reaction forces and fixed-end moments.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

## Build a macOS App

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install pyinstaller
chmod +x build_app.sh
./build_app.sh
```

The packaged app is created at `dist/Beam Calculator.app`, with a zipped copy at
`dist/Beam Calculator-macOS.zip`.

## Input Notes

- Use SI units throughout: meters, newtons, pascals, and m^4.
- Downward loads should be entered as negative values.
- Bending stress is calculated as `sigma = M c / I`, where `c` is the extreme fiber distance.
- Increase solver nodes for smoother deflection under distributed loading.
- Cross-section sketches are treated as closed solid polygons in metres, with the neutral axis assumed horizontal.
