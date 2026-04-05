# -*- coding: utf-8 -*-
"""
Behaviour tree for Scenario (Critters)

The critter wanders the environment and attacks the astronaut on sight

After a successful bite it flees to allow the astronaut to recover, then resumes roaming

State transitions: roam -> chase (astronaut detected) -> flee (bite landed) -> roam

Root is a memory=False Selector so it re-evaluates from the top every tick:
  Selector (memory=False)
  ├── BN_FleeBehaviour    SUCCESS while fleeing, FAILURE otherwise
  ├── BN_ChaseBehaviour   detects + chases + bites
  └── BN_CritterRoam      wander with obstacle avoidance (Goals_BT_Basic.CritterRoam)

PASSABLE_TAGS_CRITTER includes "CritterMantaRay" and
BN_CritterRoam passes an explicit passable set to CritterRoam constructor
"""

import asyncio
import time
import py_trees as pt
from py_trees import common

import Sensors
import Goals_BT_Basic


# --- SECTION: Configuration ---

DETECT_TAG = "Astronaut" # Unity tag for the astronaut agent
FLEE_DURATION = 6.0 # seconds to move away after biting
BITE_DISTANCE = 0.57 # ray distance that counts as contact

STATE_ROAM = "roam"
STATE_CHASE = "chase"
STATE_FLEE = "flee"

PASSABLE_TAGS_CRITTER = {DETECT_TAG, "CritterMantaRay"} # critters don't dodge each other
FORWARD_CONE_DEG = 30 # only check rays within this cone for obstacles
OBSTACLE_DIST_THRESHOLD = 0.25 # ignore obstacles further than this
DODGE_ROTATE_TIME = 0.1 # seconds to rotate when dodging an obstacle

CRITTER_ROAM_PASSABLE = {"Astronaut", "CritterMantaRay"} # critters dodge flowers but ignore astronauts (chase handles them) and each other


# --- SECTION: Shared sensor helpers ---

def _critter_obstacle_direction(agent):
    """Scans forward facing rays for non-astronaut obstacles, returns 'tl', 'tr', or None"""
    rc = agent.rc_sensor.sensor_rays
    sensor_obj = rc[Sensors.RayCastSensor.OBJECT_INFO]
    sensor_dist = rc[Sensors.RayCastSensor.DISTANCE]
    sensor_hits = rc[Sensors.RayCastSensor.HIT]
    sensor_ang = rc[Sensors.RayCastSensor.ANGLE]

    left_blocked = False
    right_blocked = False

    for idx, hit in enumerate(sensor_hits):
        if not hit:
            continue
        obj_info = sensor_obj[idx]
        if obj_info and obj_info.get("tag") in PASSABLE_TAGS_CRITTER:
            continue
        angle = sensor_ang[idx]
        dist = sensor_dist[idx]
        if abs(angle) > FORWARD_CONE_DEG: # outside forward cone, ignore
            continue
        if dist > OBSTACLE_DIST_THRESHOLD: # far enough, not a threat
            continue
        if angle <= 0:
            left_blocked = True
        else:
            right_blocked = True

    if left_blocked or right_blocked:
        return "tr" if left_blocked else "tl" # turn away from the blocked side
    return None


def _detect_astronaut(agent):
    """Returns (ray_index, distance, angle) for the closest astronaut hit, or None"""
    sensor_obj = agent.rc_sensor.sensor_rays[Sensors.RayCastSensor.OBJECT_INFO]
    sensor_dist = agent.rc_sensor.sensor_rays[Sensors.RayCastSensor.DISTANCE]
    sensor_ang = agent.rc_sensor.sensor_rays[Sensors.RayCastSensor.ANGLE]
    best_i, best_d = None, float("inf")
    for i, val in enumerate(sensor_obj):
        if val and val.get("tag", "") == DETECT_TAG:
            d = sensor_dist[i] if sensor_dist[i] >= 0 else float("inf")
            if d < best_d:
                best_d, best_i = d, i
    if best_i is None:
        return None
    return best_i, best_d, sensor_ang[best_i]


# --- SECTION: Flee behaviour ---

class BN_FleeBehaviour(pt.behaviour.Behaviour):
    """
    Retreat after a bite for FLEE_DURATION seconds
    RUNNING/SUCCESS while _critter_state == STATE_FLEE, FAILURE otherwise
    """

    def __init__(self, aagent):
        super().__init__("BN_FleeBehaviour")
        self.my_agent = aagent
        self.my_goal = None

    def initialise(self):
        if getattr(self.my_agent, "_critter_state", STATE_ROAM) == STATE_FLEE:
            self.my_goal = asyncio.create_task(self._flee_loop())
        else:
            self.my_goal = None # not fleeing -> fall through to chase or roam

    async def _flee_loop(self):
        """
        Turns roughly 180 degrees then sprints away, dodging obstacles
        until FLEE_DURATION seconds have elapsed since the bite
        """
        try:
            await self.my_agent.send_message("action", "tr") # time based 180 turn avoids 0/360 wrap issues
            await asyncio.sleep(1.0)
            await self.my_agent.send_message("action", "nt")
            await self.my_agent.send_message("action", "mf") # sprint away from the bite location

            while True:
                bite_time = getattr(self.my_agent, "_bite_timestamp", None)
                if bite_time is None or (time.time() - bite_time) >= FLEE_DURATION:
                    self.my_agent._critter_state = STATE_ROAM # hand control back to roam
                    await self.my_agent.send_message("action", "stop")
                    return True

                dodge_dir = _critter_obstacle_direction(self.my_agent) # steer around obstacles while fleeing
                if dodge_dir:
                    await self.my_agent.send_message("action", "stop")
                    await self.my_agent.send_message("action", dodge_dir)
                    await asyncio.sleep(DODGE_ROTATE_TIME)
                    await self.my_agent.send_message("action", "nt")
                    await self.my_agent.send_message("action", "mf")

                await asyncio.sleep(0.2)

        except asyncio.CancelledError:
            await self.my_agent.send_message("action", "stop")

    def update(self):
        if getattr(self.my_agent, "_critter_state", STATE_ROAM) != STATE_FLEE:
            return pt.common.Status.FAILURE # not in flee state -> skip this branch
        if self.my_goal is None:
            return pt.common.Status.FAILURE
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS

    def terminate(self, new_status: common.Status):
        if self.my_goal and not self.my_goal.done():
            self.my_goal.cancel()


# --- SECTION: Chase behaviour ---

class BN_ChaseBehaviour(pt.behaviour.Behaviour):
    """
    Detects the astronaut, steers toward it, and bites on contact
    FAILURE when astronaut not visible so the Selector falls through to roam
    Sets _critter_state = STATE_FLEE after a successful bite
    """

    def __init__(self, aagent):
        super().__init__("BN_ChaseBehaviour")
        self.my_agent = aagent
        self.my_goal = None

    def initialise(self):
        result = _detect_astronaut(self.my_agent)
        if result is not None:
            self.my_agent._critter_state = STATE_CHASE
            self.my_goal = asyncio.create_task(self._chase_loop())
        else:
            self.my_goal = None # no astronaut visible, will return FAILURE

    async def _chase_loop(self):
        """
        Steers toward the detected astronaut each tick and triggers a bite
        when the ray distance drops below the contact threshold
        """
        try:
            while True:
                result = _detect_astronaut(self.my_agent)

                if result is None:
                    await self.my_agent.send_message("action", "stop")
                    self.my_agent._critter_state = STATE_ROAM # lost astronaut -> back to roam
                    return False

                ray_idx, dist, angle = result

                dodge_dir = _critter_obstacle_direction(self.my_agent) # avoid walls while chasing
                if dodge_dir:
                    await self.my_agent.send_message("action", "stop")
                    await self.my_agent.send_message("action", dodge_dir)
                    await asyncio.sleep(DODGE_ROTATE_TIME)
                    await self.my_agent.send_message("action", "nt")
                    await asyncio.sleep(0.1)
                    continue

                # --- Bite check ---
                if dist <= BITE_DISTANCE:
                    await self.my_agent.send_message("action", "stop")
                    await self.my_agent.send_message("action", "bite")
                    self.my_agent._bite_timestamp = time.time() # used by flee to track elapsed time
                    self.my_agent._critter_state = STATE_FLEE # flee branch takes over next tick
                    return True

                # --- Steer toward astronaut ---
                if angle < -10:
                    await self.my_agent.send_message("action", "tl") # astronaut on left -> turn left
                elif angle > 10:
                    await self.my_agent.send_message("action", "tr") # astronaut on right -> turn right
                else:
                    await self.my_agent.send_message("action", "nt") # roughly aligned -> go straight

                await self.my_agent.send_message("action", "mf") # move toward astronaut
                await asyncio.sleep(0.15)

        except asyncio.CancelledError:
            await self.my_agent.send_message("action", "stop")

    def update(self):
        if self.my_goal is None:
            return pt.common.Status.FAILURE
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        if self.my_goal and not self.my_goal.done():
            self.my_goal.cancel()


# --- SECTION: Roam behaviour ---

class BN_CritterRoam(pt.behaviour.Behaviour):
    """Default wandering using CritterRoam goal which avoids walls and rocks"""

    def __init__(self, aagent):
        super().__init__("BN_CritterRoam")
        self.my_agent = aagent
        self.my_goal = None

    def initialise(self):
        self.my_goal = asyncio.create_task(
            Goals_BT_Basic.CritterRoam(self.my_agent, passable=CRITTER_ROAM_PASSABLE).run() # PLAN 2: explicit passable set
        )

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS

    def terminate(self, new_status: common.Status):
        if self.my_goal and not self.my_goal.done():
            self.my_goal.cancel()


# --- SECTION: Main behaviour tree ---

class BTCritter:
    """Behaviour Tree for the Critter agent in Scenario 2"""

    def __init__(self, aagent):
        self.aagent = aagent
        aagent._critter_state = STATE_ROAM # initial state before any astronaut is detected
        aagent._bite_timestamp = None # set by chase on bite, read by flee for elapsed time

        flee = BN_FleeBehaviour(aagent) # retreat after a bite for FLEE_DURATION seconds
        chase = BN_ChaseBehaviour(aagent) # detect astronaut + steer + bite
        roam = BN_CritterRoam(aagent) # obstacle aware wandering as fallback

        self.root = pt.composites.Selector(name="Sel_Root", memory=False) # re-evaluates from top every tick so flee preempts chase
        self.root.add_children([flee, chase, roam])

        self.behaviour_tree = pt.trees.BehaviourTree(self.root)

    def stop_behaviour_tree(self):
        print("Stopping BTCritter")
        self.root.tick_once()
        for node in self.root.iterate():
            if node.status != pt.common.Status.INVALID:
                node.status = pt.common.Status.INVALID
                if hasattr(node, "terminate"):
                    node.terminate(pt.common.Status.INVALID)

    async def tick(self):
        self.behaviour_tree.tick()
        await asyncio.sleep(0)
