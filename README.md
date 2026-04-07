# AAPE - Autonomous Agents Practice Environment

Python control layer for the Unity-based AAPE simulation. The Unity scene exposes a WebSocket server; Python agents connect to it and drive behavior through py-trees behavior trees.

## Installation

Requires Python 3.9+.

```bash
pip install py-trees aiohttp
```

## Usage

Launch the Unity project and enter Play Mode on the `3-AAC` scene. Unity listens on `127.0.0.1:4649`.

### Single agent

Run `AAgent_BT.py` with a JSON config file from the `Behavior Trees` directory:

```bash
cd "Behavior Trees"
python AAgent_BT.py AAgent-Alpha.json
```

Each JSON file under `Behavior Trees/` defines one agent (type, name, team, spawn point, sensor parameters, and the `initial_task` that runs on connection, e.g. `bt:BTAlone`, `bt:BTCritter`, `bt:BTCollectAndRun`).

### Multiple agents and critters

Use `Spawner.py` with a pack JSON file. A pack file lists one or more agent configs and how many instances of each to start:

```bash
python Spawner.py APackAstroCritters.json
```

`APackAstroCritters.json` spawns one astronaut (`AAgent-Alpha.json`) and five critters (`AAgent-Critter.json`). Edit `num_agents` to spawn more instances of the same config, or add more entries to the `packs` list to mix agent types.

To spawn only critters:

```bash
python Spawner.py APackCritters.json
```

To spawn multiple astronauts, create a pack file referencing `AAgent-Alpha.json`, `AAgent-Beta.json`, `AAgent-Gamma.json`, `AAgent-Delta.json` (each has its own spawn point) and set `num_agents` per entry.

### Switching behavior at runtime

In the Unity "Send message" field:

- `bt:BTAlone` - flower collection scenario
- `bt:BTCritter` - critter roam/chase/flee
- `bt:BTCollectAndRun` - astronaut collecting while evading critters
- `goal:<GoalName>` - run a single goal from `Goals_BT_Basic.py`
- `action:<cmd>` - send a raw action to Unity (e.g. `action:walk_to,BaseAlpha`)

## File Tree

```
./
├── README.md
├── Information/
└── Behavior Trees/
    ├── AAgent_BT.py
    ├── Spawner.py
    ├── Sensors.py
    ├── Goals_BT_Basic.py
    ├── BTAlone.py
    ├── BTCritter.py
    ├── BTCollectAndRun.py
    ├── BTRoam.py
    ├── AAgent-1.json
    ├── AAgent-Alpha.json
    ├── AAgent-Beta.json
    ├── AAgent-Gamma.json
    ├── AAgent-Delta.json
    ├── AAgent-Critter.json
    ├── APackAstroCritters.json
    └── APackCritters.json
```

## Scripts and Files

**AAgent_BT.py**

Agent entry point. Loads a JSON config, opens the WebSocket connection to Unity, registers available behavior trees and goals, and dispatches `bt:`, `goal:`, and `action:` messages received from the simulation.

**Spawner.py**

Launches multiple agents concurrently from a pack JSON file. Creates one `AAgent` per entry and runs them together via `asyncio`.

**Sensors.py**

Parses the ray-cast sensor payload from Unity. Exposes `HIT`, `DISTANCE`, `ANGLE`, and `OBJECT_INFO` arrays used by every behavior for obstacle detection and target recognition.

**Goals_BT_Basic.py**

Library of reusable goals used as leaves by the behavior trees: `ForwardDist`, `Turn`, `DetectFlower`, `MoveToFlower`, `Avoid`, `DetectObstacle`, `DoNothing`, `DetectFrozen`, `UnloadFlowers`, `CritterRoam`, `EvadeCritter`, `WalkToBase`.

**BTAlone.py**

Behavior tree for Scenario 1 (Alone). The astronaut roams with obstacle avoidance, detects flowers, moves to them to collect, and returns to `BaseAlpha` to unload when the inventory is full.

**BTCritter.py**

Behavior tree for Scenario 2 (Critters). Critter roams by default, chases and bites the astronaut on sight, then flees for a few seconds before resuming roam.

**BTCollectAndRun.py**

Behavior tree for Scenario 3 (Collect and Run). Combines the astronaut collect/unload logic with an evade branch that triggers when a critter is detected nearby. Includes the mandatory frozen sequence for the post-bite paralysis period.

**BTRoam.py**

Simple roam tree used as the default `initial_task` in the sample agent configs. Useful as a starting point or fallback.

**AAgent-Alpha.json / Beta / Gamma / Delta.json**

Astronaut configurations. Each points to a different spawn point (`SpawnAlpha`, `SpawnBeta`, ...) so multiple astronauts can coexist in the same scene.

**AAgent-1.json**

Generic astronaut config without a fixed spawn point.

**AAgent-Critter.json**

Critter configuration (type `AAgentCritterMantaRay`). Spawns inside `SmallHarvestZone` and starts with `bt:BTCritter`.

**APackAstroCritters.json**

Pack definition for `Spawner.py`: one astronaut plus five critters.

**APackCritters.json**

Pack definition containing only critters.
