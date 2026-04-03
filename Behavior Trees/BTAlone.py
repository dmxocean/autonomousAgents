import asyncio
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
        if self.i_state.isFrozen:
            return pt.common.Status.SUCCESS
        return pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        pass



class BN_DetectInventoryFull(pt.behaviour.Behaviour):
    """Succeeds when the astronaut is carrying MAX_FLOWERS or more flowers."""
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


class BN_DetectAtBase(pt.behaviour.Behaviour):
    """Succeeds when the astronaut is currently at BaseAlpha."""

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
        self.my_goal = asyncio.create_task(Goals_BT_Basic.DoNothing(self.my_agent).run())

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


class BN_ReturnToBase(pt.behaviour.Behaviour):
    """Navigates back to BaseAlpha using teleport."""

    def __init__(self, aagent, base_name="BaseAlpha"):
        super(BN_ReturnToBase, self).__init__("BN_ReturnToBase")
        self.my_agent = aagent
        self.base_name = base_name
        self.my_goal = None

    def initialise(self):
        self.my_goal = asyncio.create_task(
            Goals_BT_Basic.ReturnToBase(self.my_agent, self.base_name).run()
        )

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS if self.my_goal.result() else pt.common.Status.FAILURE

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


class BN_UnloadFlowers(pt.behaviour.Behaviour):
    """Unloads flowers at the base container."""

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


class BN_DetectFlower(pt.behaviour.Behaviour):
    """Succeeds if any ray-cast hits an AlienFlower."""

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
    """Moves the astronaut toward the detected flower until it is collected."""

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
    """
    Roams using the same obstacle-aware CritterRoam goal —
    moves forward continuously, turning reactively when blocked.
    Runs until cancelled by a higher-priority branch.
    """

    def __init__(self, aagent):
        self.my_goal = None
        super(BN_AstroRoam, self).__init__("BN_AstroRoam")
        self.my_agent = aagent

    def initialise(self):
        self.my_goal = asyncio.create_task(
            Goals_BT_Basic.CritterRoam(self.my_agent).run()
        )

    def update(self):
        if not self.my_goal.done():
            return pt.common.Status.RUNNING
        return pt.common.Status.SUCCESS

    def terminate(self, new_status: common.Status):
        self.my_goal.cancel()


# ─────────────────────────────────────────────
#  BTAlone  —  main Behaviour Tree class
# ─────────────────────────────────────────────

class BTAlone:
    """
    Behaviour Tree for the "Alone" scenario.
    
    """

    def __init__(self, aagent):
        self.aagent = aagent

        # ── Frozen handler (mandatory per assignment) ──────────────────────
        frozen = pt.composites.Sequence(name="Sequence_frozen", memory=True)
        frozen.add_children([
            BN_DetectFrozen(aagent),
            BN_DoNothing(aagent)
        ])

        # ── Unload handler: inventory full → go to base → unload ──────────
        unload = pt.composites.Sequence(name="Sequence_unload", memory=True)
        unload.add_children([
            BN_DetectInventoryFull(aagent),
            BN_ReturnToBase(aagent),
            BN_UnloadFlowers(aagent)
        ])

        # ── Collect handler: flower visible → move to it ───────────────────
        collect = pt.composites.Sequence(name="Sequence_collect", memory=True)
        collect.add_children([
            BN_DetectFlower(aagent),
            BN_MoveToFlower(aagent)
        ])

        # ── Roaming: obstacle-aware continuous wander (same as critter) ───
        roam = BN_AstroRoam(aagent)

        # ── Root selector ──────────────────────────────────────────────────
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
