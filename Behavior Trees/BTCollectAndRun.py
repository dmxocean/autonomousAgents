# -*- coding: utf-8 -*-
"""
Astronaut behaviour tree for Scenario (Collect and Run)

Same core mission as BTAlone (wander, collect flowers, return to base, unload) 
but with active critter evasion and NavMesh walk_to for the return trip so critters can be dodged en route

Tree structure:
  Selector_root (memory=False)
  ├── Sequence_frozen   frozen -> do nothing (assignment requirement)
  ├── Sequence_evade    critter detected -> turn 180 and sprint
  ├── Sequence_unload   inventory full -> walk_to base -> unload
  ├── Sequence_collect  flower detected -> move to flower
  └── BN_AstroRoam      obstacle-aware wander

BN_AstroRoam passes passable={"AlienFlower", "CritterMantaRay"} to
CritterRoam so the astronaut ignores flowers (collect branch handles them) and
critters (evade branch handles them) during roaming
"""

import asyncio
import py_trees as pt
from py_trees import common
import Goals_BT_Basic
import Sensors


ASTRO_ROAM_PASSABLE = {"AlienFlower", "CritterMantaRay"} # PLAN 2: astronaut ignores flowers and critters during roaming


# --- SECTION: Condition nodes ---

class BN_DetectFrozen(pt.behaviour.Behaviour):
    """SUCCESS when isFrozen is active, FAILURE otherwise"""

    def __init__(self, aagent):
        self.my_goal = None
        super(BN_DetectFrozen, self).__init__("BN_DetectFrozen")
        self.my_agent = aagent
        self.i_state = aagent.i_state

    def initialise(self):
        pass

    def update(self):
        if self.i_state.isFrozen:
            return pt.common.Status.SUCCESS
        return pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        pass


class BN_DetectCritter(pt.behaviour.Behaviour):
    """SUCCESS if any sensor ray detects a CritterMantaRay"""

    CRITTER_TAG = "CritterMantaRay"

    def __init__(self, aagent):
        super(BN_DetectCritter, self).__init__("BN_DetectCritter")
        self.my_agent = aagent

    def initialise(self):
        pass

    def update(self):
        sensor_obj = self.my_agent.rc_sensor.sensor_rays[Sensors.RayCastSensor.OBJECT_INFO]
        for val in sensor_obj:
            if val and val.get("tag") == self.CRITTER_TAG:
                return pt.common.Status.SUCCESS
        return pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        pass


class BN_DetectInventoryFull(pt.behaviour.Behaviour):
    """SUCCESS when the astronaut carries MAX_FLOWERS or more"""

    MAX_FLOWERS = 2

    def __init__(self, aagent):
        super(BN_DetectInventoryFull, self).__init__("BN_DetectInventoryFull")
        self.my_agent = aagent
        self.i_state = aagent.i_state

    def initialise(self):
        pass

    def update(self):
        for item in self.i_state.myInventoryList:
            if item.get("name") == "AlienFlower" and item.get("amount", 0) >= self.MAX_FLOWERS:
                return pt.common.Status.SUCCESS
        return pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        pass


class BN_DetectFlower(pt.behaviour.Behaviour):
    """SUCCESS if any ray-cast hits an AlienFlower"""

    def __init__(self, aagent):
        super(BN_DetectFlower, self).__init__("BN_DetectFlower")
        self.my_agent = aagent

    def initialise(self):
        pass

    def update(self):
        sensor_obj = self.my_agent.rc_sensor.sensor_rays[Sensors.RayCastSensor.OBJECT_INFO]
        for val in sensor_obj:
            if val and val.get("tag") == "AlienFlower":
                return pt.common.Status.SUCCESS
        return pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        pass


# --- SECTION: Action nodes ---

class BN_DoNothing(pt.behaviour.Behaviour):
    """Idles for 1 second while frozen"""

    def __init__(self, aagent):
        self.my_agent = aagent
        self.my_goal = None
        super(BN_DoNothing, self).__init__("BN_DoNothing")

    def initialise(self):
        self.my_goal = asyncio.create_task(Goals_BT_Basic.DoNothing(self.my_agent).run())

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


class BN_EvadeCritter(pt.behaviour.Behaviour):
    """Turns away from the detected critter and sprints clear"""

    def __init__(self, aagent):
        super(BN_EvadeCritter, self).__init__("BN_EvadeCritter")
        self.my_agent = aagent
        self.my_goal = None

    def initialise(self):
        self.my_goal = asyncio.create_task(
            Goals_BT_Basic.EvadeCritter(self.my_agent).run()
        )

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


class BN_WalkToBase(pt.behaviour.Behaviour):
    """Navigates to BaseAlpha via walk_to (NavMesh) so evade can interrupt en route"""

    def __init__(self, aagent, base_name="BaseAlpha"):
        super(BN_WalkToBase, self).__init__("BN_WalkToBase")
        self.my_agent = aagent
        self.base_name = base_name
        self.my_goal = None

    def initialise(self):
        self.my_goal = asyncio.create_task(
            Goals_BT_Basic.WalkToBase(self.my_agent, self.base_name).run()
        )

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


class BN_UnloadFlowers(pt.behaviour.Behaviour):
    """Drops all AlienFlowers at the base container"""

    def __init__(self, aagent):
        super(BN_UnloadFlowers, self).__init__("BN_UnloadFlowers")
        self.my_agent = aagent
        self.my_goal = None

    def initialise(self):
        self.my_goal = asyncio.create_task(
            Goals_BT_Basic.UnloadFlowers(self.my_agent).run()
        )

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


class BN_MoveToFlower(pt.behaviour.Behaviour):
    """Steers toward the detected flower until collected"""

    def __init__(self, aagent):
        super(BN_MoveToFlower, self).__init__("BN_MoveToFlower")
        self.my_agent = aagent
        self.my_goal = None

    def initialise(self):
        self.my_goal = asyncio.create_task(
            Goals_BT_Basic.MoveToFlower(self.my_agent).run()
        )

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


class BN_AstroRoam(pt.behaviour.Behaviour):
    """Obstacle-aware continuous wander using CritterRoam goal"""

    def __init__(self, aagent):
        self.my_goal = None
        super(BN_AstroRoam, self).__init__("BN_AstroRoam")
        self.my_agent = aagent

    def initialise(self):
        self.my_goal = asyncio.create_task(
            Goals_BT_Basic.CritterRoam(self.my_agent, passable=ASTRO_ROAM_PASSABLE).run() # PLAN 2: explicit passable set for astronaut
        )

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


# --- SECTION: Main behaviour tree ---

class BTCollectAndRun:
    """
    Selector_root (memory=False)
    ├── Sequence_frozen   frozen -> do nothing
    ├── Sequence_evade    critter visible -> evade
    ├── Sequence_unload   full inventory -> walk_to base -> unload
    ├── Sequence_collect  flower visible -> move to flower
    └── BN_AstroRoam      obstacle-aware wander
    """

    def __init__(self, aagent):
        self.aagent = aagent

        frozen = pt.composites.Sequence(name="Sequence_frozen", memory=True) # mandatory per assignment spec
        frozen.add_children([
            BN_DetectFrozen(aagent),
            BN_DoNothing(aagent)
        ])

        evade = pt.composites.Sequence(name="Sequence_evade", memory=True) # memory=True so evade runs to completion once triggered
        evade.add_children([
            BN_DetectCritter(aagent),
            BN_EvadeCritter(aagent)
        ])

        unload = pt.composites.Sequence(name="Sequence_unload", memory=True) # uses walk_to so evade can interrupt en route
        unload.add_children([
            BN_DetectInventoryFull(aagent),
            BN_WalkToBase(aagent),
            BN_UnloadFlowers(aagent)
        ])

        collect = pt.composites.Sequence(name="Sequence_collect", memory=True)
        collect.add_children([
            BN_DetectFlower(aagent),
            BN_MoveToFlower(aagent)
        ])

        roam = BN_AstroRoam(aagent) # fallback when no flower or critter is visible

        self.root = pt.composites.Selector(name="Selector_root", memory=False) # re-evaluates every tick so higher branches preempt
        self.root.add_children([frozen, evade, unload, collect, roam])

        self.behaviour_tree = pt.trees.BehaviourTree(self.root)

    def stop_behaviour_tree(self):
        print("Stopping BTCollectAndRun")
        self.root.tick_once()
        for node in self.root.iterate():
            if node.status != pt.common.Status.INVALID:
                node.status = pt.common.Status.INVALID
                if hasattr(node, "terminate"):
                    node.terminate(pt.common.Status.INVALID)

    async def tick(self):
        self.behaviour_tree.tick()
        await asyncio.sleep(0)
