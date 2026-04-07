# -*- coding: utf-8 -*-
"""
Reusable goal classes for all behaviour tree scenarios

Each goal is an async coroutine launched by a BT node via asyncio.create_task
and polled each tick Goals for Scenario Alone (MoveToFlower, ReturnToBase, UnloadFlowers),
Scenario Critters (CritterRoam), and Scenario Collect and Run (EvadeCritter, WalkToBase)
are grouped by section

CritterRoam accepts a passable parameter in the constructor so each
BT can declare exactly which tags to ignore during roaming, instead of relying on a
shared class-level constant
"""

import math
import random
import asyncio
import Sensors
from collections import Counter

def calculate_distance(point_a, point_b):
    """Euclidean distance between two {x, y, z} dicts"""
    distance = math.sqrt((point_b['x'] - point_a['x']) ** 2 +
                         (point_b['y'] - point_a['y']) ** 2 +
                         (point_b['z'] - point_a['z']) ** 2)
    return distance

class DoNothing:
    """Idles for 1 second then returns True"""

    def __init__(self, a_agent):
        self.a_agent = a_agent
        self.rc_sensor = a_agent.rc_sensor
        self.i_state = a_agent.i_state

    async def run(self):
        print("Doing nothing")
        await asyncio.sleep(1)
        return True

class ForwardStop:
    """Moves forward until any ray hits an obstacle, then stops"""

    STOPPED = 0
    MOVING = 1
    END = 2

    def __init__(self, a_agent):
        self.a_agent = a_agent
        self.rc_sensor = a_agent.rc_sensor
        self.i_state = a_agent.i_state
        self.state = self.STOPPED

    async def run(self):
        try:
            while True:
                if self.state == self.STOPPED:
                    await self.a_agent.send_message("action", "mf")
                    self.state = self.MOVING
                elif self.state == self.MOVING:
                    sensor_hits = self.rc_sensor.sensor_rays[Sensors.RayCastSensor.HIT]
                    if any(ray_hit == 1 for ray_hit in sensor_hits):
                        self.state = self.END
                        await self.a_agent.send_message("action", "stop")
                    else:
                        await asyncio.sleep(0)
                elif self.state == self.END:
                    break
                else:
                    print("Unknown state: " + str(self.state))
                    return False
        except asyncio.CancelledError:
            print("***** TASK Forward CANCELLED")
            await self.a_agent.send_message("action", "stop")
            self.state = self.STOPPED

class ForwardDist:
    """
    Moves forward a specified distance

    Params:
        a_agent: agent reference
        dist: target distance, -1 for random between d_min and d_max
        d_min: minimum random distance
        d_max: maximum random distance
    """

    STOPPED = 0
    MOVING = 1
    END = 2

    def __init__(self, a_agent, dist, d_min, d_max):
        self.a_agent = a_agent
        self.rc_sensor = a_agent.rc_sensor
        self.i_state = a_agent.i_state
        self.original_dist = dist
        self.target_dist = dist
        self.d_min = d_min
        self.d_max = d_max
        self.starting_pos = a_agent.i_state.position
        self.state = self.STOPPED

    async def run(self):
        try:
            previous_dist = 0.0
            while True:
                if self.state == self.STOPPED:
                    self.starting_pos = self.a_agent.i_state.position
                    if self.original_dist < 0:
                        self.target_dist = random.randint(self.d_min, self.d_max)
                    else:
                        self.target_dist = self.original_dist
                    await self.a_agent.send_message("action", "mf")
                    self.state = self.MOVING
                elif self.state == self.MOVING:
                    await asyncio.sleep(0.5)
                    current_dist = calculate_distance(self.starting_pos, self.i_state.position)
                    if current_dist >= self.target_dist:
                        await self.a_agent.send_message("action", "ntm")
                        self.state = self.STOPPED
                        return True
                    elif previous_dist == current_dist: # stuck against an obstacle
                        await self.a_agent.send_message("action", "ntm")
                        self.state = self.STOPPED
                        return False
                    previous_dist = current_dist
                else:
                    print("Unknown state: " + str(self.state))
                    return False
        except asyncio.CancelledError:
            print("***** TASK Forward CANCELLED")
            await self.a_agent.send_message("action", "ntm")
            self.state = self.STOPPED


class Turn:
    """Turns a random number of degrees in a random direction"""

    LEFT = -1
    RIGHT = 1

    SELECTING = 0
    TURNING = 1

    def __init__(self, a_agent):
        self.a_agent = a_agent
        self.rc_sensor = a_agent.rc_sensor
        self.i_state = a_agent.i_state
        self.current_heading = 0
        self.new_heading = 0
        self.state = self.SELECTING

    async def run(self):
        try:
            while True:
                if self.state == self.SELECTING:
                    rotation_direction = random.choice([-1, 1])
                    rotation_degrees = random.uniform(1, 180) * rotation_direction
                    current_heading = self.i_state.rotation["y"]
                    self.new_heading = (current_heading + rotation_degrees) % 360
                    if self.new_heading == 360:
                        self.new_heading = 0.0
                    if rotation_direction == self.RIGHT:
                        await self.a_agent.send_message("action", "tr")
                    else:
                        await self.a_agent.send_message("action", "tl")
                    self.state = self.TURNING
                elif self.state == self.TURNING:
                    current_heading = self.i_state.rotation["y"]
                    final_condition = abs(current_heading - self.new_heading)
                    if final_condition < 5:
                        await self.a_agent.send_message("action", "nt")
                        current_heading = self.i_state.rotation["y"]
                        self.state = self.SELECTING
                        return True
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            print("***** TASK Turn CANCELLED")
            await self.a_agent.send_message("action", "nt")


# --- SECTION: Scenario Alone goals ---

class MoveToFlower:
    """
    Steers toward the closest detected AlienFlower using the ray-cast sensor
    and walks forward until the flower disappears from sensors (collected)
    Returns True on collection, False otherwise
    """

    TURNING = 0
    MOVING = 1

    def __init__(self, a_agent):
        self.a_agent = a_agent
        self.rc_sensor = a_agent.rc_sensor
        self.i_state = a_agent.i_state
        self.state = self.TURNING

    def _find_flower_ray(self):
        """Returns index of the ray hitting a flower, or -1"""
        sensor_obj_info = self.rc_sensor.sensor_rays[Sensors.RayCastSensor.OBJECT_INFO]
        for index, value in enumerate(sensor_obj_info):
            if value and value.get("tag") == "AlienFlower":
                return index
        return -1

    def _ray_angle_offset(self, ray_index):
        """Angular offset from centre using the pre-computed sensor angles"""
        return self.rc_sensor.sensor_rays[Sensors.RayCastSensor.ANGLE][ray_index]

    async def run(self):
        try:
            while True:
                flower_ray = self._find_flower_ray()
                if flower_ray == -1: # flower no longer detected, likely collected
                    await self.a_agent.send_message("action", "ntm")
                    await self.a_agent.send_message("action", "nt")
                    return True

                offset = self._ray_angle_offset(flower_ray)

                if abs(offset) > 8: # not aligned, need to turn toward the flower
                    await self.a_agent.send_message("action", "ntm")
                    if offset > 0:
                        await self.a_agent.send_message("action", "tr")
                    else:
                        await self.a_agent.send_message("action", "tl")
                    await asyncio.sleep(0.1)
                    await self.a_agent.send_message("action", "nt")
                else: # facing the flower, walk toward it
                    await self.a_agent.send_message("action", "nt")
                    await self.a_agent.send_message("action", "mf")
                    await asyncio.sleep(0.3)

                await asyncio.sleep(0)

        except asyncio.CancelledError:
            print("***** TASK MoveToFlower CANCELLED")
            await self.a_agent.send_message("action", "ntm")
            await self.a_agent.send_message("action", "nt")


class ReturnToBase:
    """Teleports to BaseAlpha and waits until arrival is confirmed"""

    def __init__(self, a_agent, base_name="BaseAlpha"):
        self.a_agent = a_agent
        self.i_state = a_agent.i_state
        self.base_name = base_name

    async def run(self):
        try:
            await self.a_agent.send_message("action", f"teleport_to,{self.base_name}")
            while True:
                await asyncio.sleep(0.5)
                if self.i_state.currentNamedLoc == self.base_name:
                    return True
                if not self.i_state.onRoute and self.i_state.currentNamedLoc != self.base_name:
                    await self.a_agent.send_message("action", f"teleport_to,{self.base_name}") # retry if navigation ended without arriving
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            print("***** TASK ReturnToBase CANCELLED")
            await self.a_agent.send_message("action", "ntm")


class UnloadFlowers:
    """Drops all AlienFlowers from inventory at the base container"""

    def __init__(self, a_agent):
        self.a_agent = a_agent
        self.i_state = a_agent.i_state

    def _count_flowers(self):
        for item in self.i_state.myInventoryList:
            if item.get("name") == "AlienFlower":
                return item.get("amount", 0)
        return 0

    async def run(self):
        try:
            count = self._count_flowers()
            if count > 0:
                await self.a_agent.send_message("action", f"leave,AlienFlower,{count}")
                await asyncio.sleep(1.0) # wait for Unity to register the drop
            return True
        except asyncio.CancelledError:
            print("***** TASK UnloadFlowers CANCELLED")


# --- SECTION: Scenario Critters goals ---

class CritterRoam:
    """
    Wanders with sensor-guided obstacle avoidance
    Only reacts when the centre ray is blocked to prevent the V-shape trap
    where alternating side hits cause infinite turning, left/right counts
    decide which way to turn when the centre ray fires

    Accepts a passable parameter so each BT can declare
    exactly which tags to ignore during roaming

    Params:
        a_agent: agent reference
        passable: set of tags to walk through, defaults to {"Astronaut", "AlienFlower"}
    """

    DEFAULT_PASSABLE = {"Astronaut", "AlienFlower"}

    def __init__(self, a_agent, passable=None):
        self.a_agent = a_agent
        self.rc_sensor = a_agent.rc_sensor
        self.i_state = a_agent.i_state
        self.passable = passable if passable is not None else self.DEFAULT_PASSABLE

    def _scan(self):
        """Returns (centre_blocked, left_blocked, right_blocked) skipping passable tags"""
        hits = self.rc_sensor.sensor_rays[Sensors.RayCastSensor.HIT]
        obj_info = self.rc_sensor.sensor_rays[Sensors.RayCastSensor.OBJECT_INFO]
        angles = self.rc_sensor.sensor_rays[Sensors.RayCastSensor.ANGLE]
        distances = self.rc_sensor.sensor_rays[Sensors.RayCastSensor.DISTANCE]

        centre_blocked = False
        left_blocked = 0
        right_blocked = 0

        for i in range(len(hits)):
            if not hits[i]:
                continue
            
            tag = obj_info[i].get("tag") if obj_info[i] else None
            if tag in self.passable:
                continue

            angle = angles[i]
            dist = distances[i]

            if dist > 2.0: # ignore obstacles further than 2 meters for roaming
                continue

            # PREVENTION: centre ray blocked, or any forward-cone ray critically close
            if angle == 0 and dist < 1.0: # directly in front
                centre_blocked = True
            if abs(angle) <= 45 and dist < 0.7: # imminent diagonal collision counts as blocked
                centre_blocked = True

            if angle < 0 and abs(angle) <= 45: # obstacle on left within forward cone
                left_blocked += 1
            elif angle > 0 and abs(angle) <= 45: # obstacle on right within forward cone
                right_blocked += 1
                
        return centre_blocked, left_blocked, right_blocked

    async def run(self):
        """
        Moves forward continuously. Nudges away from side obstacles.
        Only stops and turns when the path is directly blocked.
        Detects if the agent is stuck (not changing position) and forces a turn
        """
        try:
            await self.a_agent.send_message("action", "mf")
            
            # For stuck detection
            prev_pos = self.i_state.position
            stuck_count = 0
            
            while True:
                centre_blocked, left_blocked, right_blocked = self._scan()

                # --- Stuck detection logic ---
                curr_pos = self.i_state.position
                dist_moved = calculate_distance(prev_pos, curr_pos)
                if dist_moved < 0.05: # moved less than 5cm in 0.1s
                    stuck_count += 1
                else:
                    stuck_count = 0
                prev_pos = curr_pos

                # If stuck for ~0.5 seconds while path looks clear or nudging
                if stuck_count > 5:
                    print(f"Agent stuck! Forcing emergency turn...")
                    centre_blocked = True # force the emergency stop branch
                    stuck_count = 0

                if not centre_blocked:
                    # PREVENTION (Nudge): steer away from side obstacles while moving
                    if left_blocked > right_blocked:
                        await self.a_agent.send_message("action", "tr") # steer right
                    elif right_blocked > left_blocked:
                        await self.a_agent.send_message("action", "tl") # steer left
                    else:
                        await self.a_agent.send_message("action", "nt") # path clear
                    await asyncio.sleep(0.1)
                    continue

                # --- EMERGENCY: sharp turn while still moving forward ---
                if left_blocked >= right_blocked:
                    direction = "tr"
                else:
                    direction = "tl"

                turn_secs = random.uniform(0.5, 1.0) # sweep away from the obstacle
                await self.a_agent.send_message("action", direction) # keep mf active, just rotate
                await asyncio.sleep(turn_secs)
                await self.a_agent.send_message("action", "nt")
                await self.a_agent.send_message("action", "mf")
                prev_pos = self.i_state.position # reset after turn

        except asyncio.CancelledError:
            print("***** CritterRoam CANCELLED")
            await self.a_agent.send_message("action", "ntm")
            await self.a_agent.send_message("action", "nt")


# --- SECTION: Scenario Collect and Run goals ---

class EvadeCritter:
    """
    Evasion manoeuvre: stop, turn roughly 180 degrees, sprint away
    Uses time-based turning to avoid heading wrap issues near 0/360
    Returns True when the sprint completes
    """

    SPRINT_DURATION = 6.0 # seconds to sprint after turning

    def __init__(self, a_agent):
        self.a_agent = a_agent
        self.i_state = a_agent.i_state

    async def run(self):
        try:
            await self.a_agent.send_message("action", "ntm") # halt current movement
            await self.a_agent.send_message("action", "nt")

            await self.a_agent.send_message("action", "tr") # time-based 180 turn
            await asyncio.sleep(1.0)
            await self.a_agent.send_message("action", "nt")

            # --- Sprint away ---
            start_pos = self.a_agent.i_state.position
            await self.a_agent.send_message("action", "mf")
            previous_dist = 0.0
            elapsed = 0.0
            while elapsed < self.SPRINT_DURATION:
                await asyncio.sleep(0.3)
                elapsed += 0.3
                current_dist = calculate_distance(start_pos, self.a_agent.i_state.position)
                if current_dist == previous_dist: # stuck against wall, stop early
                    break
                previous_dist = current_dist

            await self.a_agent.send_message("action", "ntm")
            return True

        except asyncio.CancelledError:
            print("***** EvadeCritter CANCELLED")
            await self.a_agent.send_message("action", "ntm")
            await self.a_agent.send_message("action", "nt")


class WalkToBase:
    """
    Navigates to BaseAlpha using walk_to (NavMesh) instead of teleport
    Required for Collect and Run so the evade branch can interrupt mid-navigation
    Returns True on arrival
    """

    def __init__(self, a_agent, base_name="BaseAlpha"):
        self.a_agent = a_agent
        self.i_state = a_agent.i_state
        self.base_name = base_name

    async def run(self):
        try:
            await self.a_agent.send_message("action", f"walk_to,{self.base_name}")
            while True:
                await asyncio.sleep(0.5)
                if self.i_state.currentNamedLoc == self.base_name:
                    return True
                if not self.i_state.onRoute and self.i_state.currentNamedLoc != self.base_name:
                    await self.a_agent.send_message("action", f"walk_to,{self.base_name}") # retry if navigation ended without arriving
        except asyncio.CancelledError:
            print("***** WalkToBase CANCELLED")
            await self.a_agent.send_message("action", "ntm")
