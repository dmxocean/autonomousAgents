import math
import random
import asyncio
import Sensors
from collections import Counter

def calculate_distance(point_a, point_b):
    distance = math.sqrt((point_b['x'] - point_a['x']) ** 2 +
                         (point_b['y'] - point_a['y']) ** 2 +
                         (point_b['z'] - point_a['z']) ** 2)
    return distance

class DoNothing:
    """
    Does nothing
    """
    def __init__(self, a_agent):
        self.a_agent = a_agent
        self.rc_sensor = a_agent.rc_sensor
        self.i_state = a_agent.i_state

    async def run(self):
        print("Doing nothing")
        await asyncio.sleep(1)
        return True

class ForwardStop:
    """
        Moves forward till it finds an obstacle. Then stops.
    """
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
                    # Start moving
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
        Moves forward a certain distance specified in the parameter "dist".
        If "dist" is -1, selects a random distance between the initial
        parameters of the class "d_min" and "d_max"
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
            previous_dist = 0.0  # Used to detect if we are stuck
            while True:
                if self.state == self.STOPPED:
                    # starting position before moving
                    self.starting_pos = self.a_agent.i_state.position
                    # Before start moving, calculate the distance we want to move
                    if self.original_dist < 0:
                        self.target_dist = random.randint(self.d_min, self.d_max)
                    else:
                        self.target_dist = self.original_dist
                    # Start moving
                    await self.a_agent.send_message("action", "mf")
                    self.state = self.MOVING
                    # print("TARGET DISTANCE: " + str(self.target_dist))
                elif self.state == self.MOVING:
                    # If we are moving
                    await asyncio.sleep(0.5)  # Wait for a little movement
                    current_dist = calculate_distance(self.starting_pos, self.i_state.position)
                    # print(f"Current distance: {current_dist}")
                    if current_dist >= self.target_dist:  # Check if we already have covered the required distance
                        await self.a_agent.send_message("action", "ntm")
                        self.state = self.STOPPED
                        return True
                    elif previous_dist == current_dist:  # We are not moving
                        # print(f"previous dist: {previous_dist}, current dist: {current_dist}")
                        # print("NOT MOVING")
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
    """
    Repeats the action of turning a random number of degrees in a random
    direction (right or left)
    """
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
                    # print("SELECTING NEW TURN")
                    rotation_direction = random.choice([-1, 1])
                    # print(f"Rotation direction: {rotation_direction}")
                    rotation_degrees = random.uniform(1, 180) * rotation_direction
                    # print("Degrees: " + str(rotation_degrees))
                    current_heading = self.i_state.rotation["y"]
                    # print(f"Current heading: {current_heading}")
                    self.new_heading = (current_heading + rotation_degrees) % 360
                    if self.new_heading == 360:
                        self.new_heading = 0.0
                    # print(f"New heading: {self.new_heading}")
                    if rotation_direction == self.RIGHT:
                        await self.a_agent.send_message("action", "tr")
                    else:
                        await self.a_agent.send_message("action", "tl")
                    self.state = self.TURNING
                elif self.state == self.TURNING:
                    # check if we have finished the rotation
                    current_heading = self.i_state.rotation["y"]
                    final_condition = abs(current_heading - self.new_heading)
                    if final_condition < 5:
                        await self.a_agent.send_message("action", "nt")
                        current_heading = self.i_state.rotation["y"]
                        # print(f"Current heading: {current_heading}")
                        # print("TURNING DONE.")
                        self.state = self.SELECTING
                        return True
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            print("***** TASK Turn CANCELLED")
            await self.a_agent.send_message("action", "nt")


# ==================== CUSTOM GOALS FOR SCENARIO ALONE ====================
# (Critter goals are further below)

class MoveToFlower:
    """
    Moves the astronaut toward the closest detected AlienFlower using the
    ray-cast sensor. Faces the flower then walks forward until the flower
    disappears from sensors (collected) or we get too close.
    Returns True when the flower is collected (no longer detected), False otherwise.
    """
    TURNING = 0
    MOVING = 1

    def __init__(self, a_agent):
        self.a_agent = a_agent
        self.rc_sensor = a_agent.rc_sensor
        self.i_state = a_agent.i_state
        self.state = self.TURNING

    def _find_flower_ray(self):
        """Returns index of the ray hitting a flower, or -1."""
        sensor_obj_info = self.rc_sensor.sensor_rays[Sensors.RayCastSensor.OBJECT_INFO]
        for index, value in enumerate(sensor_obj_info):
            if value and value.get("tag") == "AlienFlower":
                return index
        return -1

    def _ray_angle_offset(self, ray_index):
        """
        Compute the angular offset of a ray from center.
        Assumes rays are evenly spread. The center ray index is num_rays//2.
        """
        num_rays = len(self.rc_sensor.sensor_rays[Sensors.RayCastSensor.OBJECT_INFO])
        center = num_rays // 2
        # Each ray covers (fov / (num_rays - 1)) degrees
        # We use a reasonable default angular step of ~5 degrees
        angle_step = 5.0
        return (ray_index - center) * angle_step

    async def run(self):
        try:
            while True:
                flower_ray = self._find_flower_ray()
                if flower_ray == -1:
                    # Flower no longer detected — collected or lost
                    await self.a_agent.send_message("action", "ntm")
                    await self.a_agent.send_message("action", "nt")
                    return True

                offset = self._ray_angle_offset(flower_ray)

                if abs(offset) > 8:
                    # Need to turn toward the flower
                    await self.a_agent.send_message("action", "ntm")
                    if offset > 0:
                        await self.a_agent.send_message("action", "tr")
                    else:
                        await self.a_agent.send_message("action", "tl")
                    # Turn a little then recheck
                    await asyncio.sleep(0.1)
                    await self.a_agent.send_message("action", "nt")
                else:
                    # Facing the flower — move forward
                    await self.a_agent.send_message("action", "nt")
                    await self.a_agent.send_message("action", "mf")
                    await asyncio.sleep(0.3)

                await asyncio.sleep(0)

        except asyncio.CancelledError:
            print("***** TASK MoveToFlower CANCELLED")
            await self.a_agent.send_message("action", "ntm")
            await self.a_agent.send_message("action", "nt")


class ReturnToBase:
    """
    Uses the NavMesh walk_to action to navigate back to BaseAlpha.
    Returns True when the agent arrives (currentNamedLoc == 'BaseAlpha').
    """
    def __init__(self, a_agent, base_name="BaseAlpha"):
        self.a_agent = a_agent
        self.i_state = a_agent.i_state
        self.base_name = base_name

    async def run(self):
        try:
            await self.a_agent.send_message("action", f"teleport_to,{self.base_name}")
            # Wait until we arrive
            while True:
                await asyncio.sleep(0.5)
                if self.i_state.currentNamedLoc == self.base_name:
                    return True
                if not self.i_state.onRoute and self.i_state.currentNamedLoc != self.base_name:
                    # Navigation ended but we're not at base — retry once
                    await self.a_agent.send_message("action", f"teleport_to,{self.base_name}")
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            print("***** TASK ReturnToBase CANCELLED")
            await self.a_agent.send_message("action", "ntm")


class UnloadFlowers:
    """
    Unloads all AlienFlowers from the astronaut inventory at the base container.
    Sends the leave action with the flower name and amount.
    Returns True when done.
    """
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
                await asyncio.sleep(1.0)  # Give time for the action to complete
            return True
        except asyncio.CancelledError:
            print("***** TASK UnloadFlowers CANCELLED")



