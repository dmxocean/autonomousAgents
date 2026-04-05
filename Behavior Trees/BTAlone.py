# -*- coding: utf-8 -*-
"""
Behaviour Tree for Scenario (Alone)

The astronaut wanders the environment collecting AlienFlowers 
and returning to BaseAlpha when the inventory reaches MAX_FLOWERS

Roaming uses reactive sensor steering: side obstacles nudge the
heading while a blocked centre ray forces a full stop and turn

The frozen sequence must remain the highest-priority branch to suppress all actions
during the 5-second paralysis window
"""

import asyncio
import random
import py_trees as pt
from py_trees import common
import Goals_BT_Basic
import Sensors


class BN_DetectFrozen(pt.behaviour.Behaviour):
    def __init__(self, aagent):
        self.my_goal = None
        super(BN_DetectFrozen, self).__init__("BN_DetectFrozen")
        self.my_agent = aagent
        self.i_state = aagent.i_state

    def initialise(self):
        pass

    def update(self):
        if self.i_state.isFrozen: # isFrozen is set by Unity for exactly 5s after a critter bite
            return pt.common.Status.SUCCESS
        return pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        pass


class BN_DetectInventoryFull(pt.behaviour.Behaviour):
    """Succeeds when the astronaut is carrying MAX_FLOWERS or more flowers"""
    MAX_FLOWERS = 2

    def __init__(self, aagent):
        super(BN_DetectInventoryFull, self).__init__("BN_DetectInventoryFull")
        self.my_agent = aagent
        self.i_state = aagent.i_state

    def initialise(self):
        pass

    def update(self):
        for item in self.i_state.myInventoryList:
            if item.get("name") == "AlienFlower" and item.get("amount", 0) >= self.MAX_FLOWERS: # >= allows for edge cases where Unity reports more than expected
                return pt.common.Status.SUCCESS
        return pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        pass


class BN_DetectAtBase(pt.behaviour.Behaviour):
    """Succeeds when the astronaut is currently at BaseAlpha"""

    def __init__(self, aagent, base_name="BaseAlpha"):
        super(BN_DetectAtBase, self).__init__("BN_DetectAtBase")
        self.my_agent = aagent
        self.i_state = aagent.i_state
        self.base_name = base_name

    def initialise(self):
        pass

    def update(self):
        if self.i_state.currentNamedLoc == self.base_name:
            return pt.common.Status.SUCCESS
        return pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        pass


class BN_DoNothing(pt.behaviour.Behaviour):
    def __init__(self, aagent):
        self.my_agent = aagent
        self.my_goal = None
        super(BN_DoNothing, self).__init__("BN_DoNothing")

    def initialise(self):
        self.my_goal = asyncio.create_task(Goals_BT_Basic.DoNothing(self.my_agent).run()) # holds the tree in RUNNING for 1s while Unity completes the freeze

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel() # cancelling the task prevents the idle sleep from blocking the event loop


class BN_ReturnToBase(pt.behaviour.Behaviour):
    """Navigates back to BaseAlpha using teleport"""

    def __init__(self, aagent, base_name="BaseAlpha"):
        super(BN_ReturnToBase, self).__init__("BN_ReturnToBase")
        self.my_agent = aagent
        self.base_name = base_name
        self.my_goal = None

    def initialise(self):
        self.my_goal = asyncio.create_task(
            Goals_BT_Basic.ReturnToBase(self.my_agent, self.base_name).run() # uses teleport_to, not NavMesh, so critters cannot intercept the trip
        )

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


class BN_UnloadFlowers(pt.behaviour.Behaviour):
    """Unloads flowers at the base container"""

    def __init__(self, aagent):
        super(BN_UnloadFlowers, self).__init__("BN_UnloadFlowers")
        self.my_agent = aagent
        self.my_goal = None

    def initialise(self):
        self.my_goal = asyncio.create_task(
            Goals_BT_Basic.UnloadFlowers(self.my_agent).run() # sends leave,AlienFlower,N and waits 1s for Unity to register the drop
        )

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


class BN_DetectFlower(pt.behaviour.Behaviour):
    """Succeeds if any ray-cast hits an AlienFlower"""

    def __init__(self, aagent):
        super(BN_DetectFlower, self).__init__("BN_DetectFlower")
        self.my_agent = aagent

    def initialise(self):
        pass

    def update(self):
        sensor_obj_info = self.my_agent.rc_sensor.sensor_rays[Sensors.RayCastSensor.OBJECT_INFO]
        for value in sensor_obj_info:
            if value and value.get("tag") == "AlienFlower":
                return pt.common.Status.SUCCESS
        return pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        pass


class BN_MoveToFlower(pt.behaviour.Behaviour):
    """Moves the astronaut toward the detected flower until it is collected"""

    def __init__(self, aagent):
        super(BN_MoveToFlower, self).__init__("BN_MoveToFlower")
        self.my_agent = aagent
        self.my_goal = None

    def initialise(self):
        self.my_goal = asyncio.create_task(
            Goals_BT_Basic.MoveToFlower(self.my_agent).run() # steers toward the flower ray and walks forward until the tag disappears from sensor
        )

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


class BN_AstroRoam(pt.behaviour.Behaviour):
    """
    Roams using turn + forward steps.
    Runs until cancelled by a higher-priority branch.
    """

    def __init__(self, aagent):
        self.my_goal = None
        super(BN_AstroRoam, self).__init__("BN_AstroRoam")
        self.my_agent = aagent

    def _scan(self):
        """Returns (centre_blocked, left_blocked, right_blocked) ignoring flowers"""
        hits = self.my_agent.rc_sensor.sensor_rays[Sensors.RayCastSensor.HIT]
        obj_info = self.my_agent.rc_sensor.sensor_rays[Sensors.RayCastSensor.OBJECT_INFO]
        angles = self.my_agent.rc_sensor.sensor_rays[Sensors.RayCastSensor.ANGLE]
        centre_blocked = False
        left_blocked = 0
        right_blocked = 0
        for i in range(len(hits)):
            if not hits[i]:
                continue
            tag = obj_info[i].get("tag") if obj_info[i] else None
            if tag == "AlienFlower": # flowers must not trigger avoidance or the agent turns away from its target
                continue
            angle = angles[i]
            if angle == 0: # centre ray
                centre_blocked = True
            elif angle < 0: # left side rays (negative angles)
                left_blocked += 1
            else: # right side rays (positive angles)
                right_blocked += 1
        return centre_blocked, left_blocked, right_blocked

    async def _smart_roam(self):
        """Async roam loop that steers using live ray-cast data each tick without blocking the event loop"""
        await self.my_agent.send_message("action", "mf") # start moving forward
        while True:
            centre_blocked, left_blocked, right_blocked = self._scan()

            if not centre_blocked:
                # Centre ray clear, keep moving and only steer if a side is blocked
                if left_blocked > 0 and right_blocked == 0:
                    await self.my_agent.send_message("action", "tr") # left wall -> nudge right toward centre
                elif right_blocked > 0 and left_blocked == 0:
                    await self.my_agent.send_message("action", "tl") # right wall -> nudge left toward centre
                else:
                    await self.my_agent.send_message("action", "nt") # both clear or both blocked -> go straight
                await asyncio.sleep(0.1)
                continue

            # Centre ray blocked, must stop and turn before resuming
            await self.my_agent.send_message("action", "ntm") # stop translation
            if left_blocked >= right_blocked:
                direction = "tr" # more obstacles on left -> turn right
            else:
                direction = "tl" # more obstacles on right -> turn left
            turn_secs = random.uniform(0.4, 1.2) # random turn duration to avoid looping
            await self.my_agent.send_message("action", direction)
            await asyncio.sleep(turn_secs)
            await self.my_agent.send_message("action", "nt") # stop turning
            await self.my_agent.send_message("action", "mf") # resume forward

    def initialise(self):
        self.my_goal = asyncio.create_task(self._smart_roam())

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS # _smart_roam loops indefinitely, so SUCCESS only occurs after an unexpected task exit

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel() # stops the roam loop so the event loop is not left with a dangling moving task


class BTAlone:
    """Behaviour Tree for the Alone scenario"""

    def __init__(self, aagent):
        self.aagent = aagent

        # -- Frozen branch: suppresses all actions while isFrozen is active --
        frozen = pt.composites.Sequence(name="Sequence_frozen", memory=True)
        frozen.add_children([
            BN_DetectFrozen(aagent),
            BN_DoNothing(aagent)
        ])

        # -- Unload branch: triggered when inventory hits MAX_FLOWERS --
        unload = pt.composites.Sequence(name="Sequence_unload", memory=True)
        unload.add_children([
            BN_DetectInventoryFull(aagent),
            BN_ReturnToBase(aagent),
            BN_UnloadFlowers(aagent)
        ])

        # -- Collect branch: steers toward the nearest visible flower --
        collect = pt.composites.Sequence(name="Sequence_collect", memory=True)
        collect.add_children([
            BN_DetectFlower(aagent),
            BN_MoveToFlower(aagent)
        ])

        roam = BN_AstroRoam(aagent) # fallback when no flower is visible

        # -- Root re-evaluates from top every tick so higher branches can preempt --
        self.root = pt.composites.Selector(name="Selector_root", memory=False)
        self.root.add_children([frozen, unload, collect, roam])

        self.behaviour_tree = pt.trees.BehaviourTree(self.root)

    def stop_behaviour_tree(self):
        print("Stopping BTAlone")
        self.root.tick_once()
        for node in self.root.iterate():
            if node.status != pt.common.Status.INVALID:
                node.status = pt.common.Status.INVALID
                if hasattr(node, "terminate"):
                    node.terminate(pt.common.Status.INVALID)

    async def tick(self):
        self.behaviour_tree.tick()
        await asyncio.sleep(0)
