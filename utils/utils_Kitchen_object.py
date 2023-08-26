import pybullet as p
import pybullet_data
import math
import time
import numpy as np
import networkx as nx
import matplotlib.pyplot as plt
import random

from utils.utils_PbVisualizer import PbVisualizer
from utils.utils_PbClient import PbClient
from utils.utils_PIDController import PIDController

"""
Add kitchen
"""

class Kitchen:
    def __init__(self, pb_client):
        self.pb_client = pb_client
        self.client_id = self.pb_client.get_client()
        
        # ----------------------------------------------------------------
        # This is Element A, where there are a oven, and a few drawers
        # ----------------------------------------------------------------
        self.elementA_id = p.loadURDF(
            "./Kitchen/models_yan/elementA/urdf/kitchen_part_right_gen_convex.urdf",
            basePosition=[4, 2, 1.477],
            baseOrientation=p.getQuaternionFromEuler([0, 0, math.pi])
        )
        self.elementA_drawer_to_joint_id = {
            1: 17,
            2: 21,
            3: 26,
            4: 30,
            5: 36,
            6: 39,
            7: 47,
            8: 52,
            9: 55,
            10: 57,
            11: 13,
        }
        self.elementA_drawer_to_joint_limits = {
            1: (0, 1.5),
            2: (0, -1.5),
            3: (0, -1.5),
            4: (0, 1.5),
            5: (0.0, 0.4),
            6: (0.0, 0.4),
            7: (0, 1.5),
            8: (0, -1.5),
            9: (0.0, 0.4),
            10: (0.0, 0.4),
            11: (0, 1.5),
        }
        print(
            "-" * 20
            + "\n"
            + "Element A's drawer id in kithen: {}".format(
                self.elementA_drawer_to_joint_id
            )
        )

        # ----------------------------------------------------------------
        # This is Element B, where there are a sink, and a few container
        # ----------------------------------------------------------------
        self.elementB_id = p.loadURDF(
            "./Kitchen/models_yan/elementB/urdf/kitchen_assembly.urdf",
            basePosition=[4.3, 5.95, 0],
            baseOrientation=p.getQuaternionFromEuler([0, 0, math.pi])
        )

        # ----------------------------------------------------------------
        #  This is Element C (i.e., a dishwasher)
        # ----------------------------------------------------------------
        self.elementC_id = p.loadURDF(
            "./Kitchen/models_yan/elementC/dishwasher.urdf",
            basePosition=[3.95, 3.08, 0.43],
            baseOrientation=p.getQuaternionFromEuler([0, 0, - math.pi / 2.0])
        )
        self.elementC_drawer_to_joint_id = {
            1: 1,
            2: 2,
            3: 3,
        }
        self.elementC_drawer_to_joint_limits = {
            1: (0, 1.5),
            2: (0, -0.3),
            3: (0, -0.3),
        }
        print(
            "-" * 20
            + "\n"
            + "Element C's drawer id in kithen: {}".format(
                self.elementC_drawer_to_joint_id
            )
        )

        # ----------------------------------------------------------------
        # This is Element D (i.e., a microwave)
        # ----------------------------------------------------------------
        self.elementD_id = p.loadURDF(
            "./Kitchen/models_yan/elementD/microwave.urdf",
            basePosition=[4.0, 2.9, 0.95],
            baseOrientation=p.getQuaternionFromEuler([0, 0, math.pi / 2.0]),
        )
        self.elementD_drawer_to_joint_id = {
            1: 1,
        }
        self.elementD_drawer_to_joint_limits = {
            1: (0, -1.5),
        }
        print(
            "-" * 20
            + "\n"
            + "Element D's drawer id in kithen: {}".format(
                self.elementD_drawer_to_joint_id
            )
        )

        # ----------------------------------------------------------------
        # This is Element E (i.e., a refrigerator)
        # ----------------------------------------------------------------
        self.elementE_id = p.loadURDF(
            "./Kitchen/models_yan/elementE/refrigerator.urdf",
            basePosition=[4.1, 6.42, 0.05],
            baseOrientation=p.getQuaternionFromEuler([0, 0, -math.pi / 2.0]),
        )
        self.elementE_drawer_to_joint_id = {
            1: 1,
            2: 2,
        }
        self.elementE_drawer_to_joint_limits = {
            1: (0, -1.5),
            2: (0, -1.5),
        }
        print(
            "-" * 20
            + "\n"
            + "Element E's drawer id in kithen: {}".format(
                self.elementE_drawer_to_joint_id
            )
        )

        # ----------------------------------------------------------------
        # Set element A B C D E colors
        # ----------------------------------------------------------------
        self.visualizer = PbVisualizer(pb_client)
        self.visualizer.set_elementA_visual_color(self.elementA_id)
        self.visualizer.set_elementB_visual_color(self.elementB_id)
        self.visualizer.set_elementC_visual_color(self.elementC_id)
        self.visualizer.set_elementD_visual_color(self.elementD_id)
        self.visualizer.set_elementE_visual_color(self.elementE_id)

    # ----------------------------------------------------------------
    # Open drawer
    # ----------------------------------------------------------------
    def open_drawer(self, elementName, drawer_id):
        if elementName == "elementA":
            joint_id = self.elementA_drawer_to_joint_id[drawer_id]
            open_angle = self.elementA_drawer_to_joint_limits[drawer_id][1]
            print('elementA: joint_id:{}, open_angle:{}'.format(joint_id, open_angle))
            p.setJointMotorControl2(
                bodyIndex=self.elementA_id,
                jointIndex=joint_id,
                controlMode=p.POSITION_CONTROL,
                targetPosition=open_angle,
                maxVelocity=0.5,
            )
        elif elementName == "elementC":
            joint_id = self.elementC_drawer_to_joint_id[drawer_id]
            open_angle = self.elementC_drawer_to_joint_limits[drawer_id][1]
            print('elementC: joint_id:{}, open_angle:{}'.format(joint_id, open_angle))
            p.setJointMotorControl2(
                bodyIndex=self.elementC_id,
                jointIndex=joint_id,
                controlMode=p.POSITION_CONTROL,
                targetPosition=open_angle,
                maxVelocity=0.5,
            )
        elif elementName == "elementD":
            joint_id = self.elementD_drawer_to_joint_id[drawer_id]
            open_angle = self.elementD_drawer_to_joint_limits[drawer_id][1]
            print('elementD (open): joint_id:{}, open_angle:{}'.format(joint_id, open_angle))
            p.setJointMotorControl2(
                bodyIndex=self.elementD_id,
                jointIndex=joint_id,
                controlMode=p.POSITION_CONTROL,
                targetPosition=open_angle,
                maxVelocity=0.5,
            )
        elif elementName == "elementE":
            joint_id = self.elementE_drawer_to_joint_id[drawer_id]
            open_angle = self.elementE_drawer_to_joint_limits[drawer_id][1]
            print('elementE: joint_id:{}, open_angle:{}'.format(joint_id, open_angle))
            p.setJointMotorControl2(
                bodyIndex=self.elementE_id,
                jointIndex=joint_id,
                controlMode=p.POSITION_CONTROL,
                targetPosition=open_angle,
                maxVelocity=0.5,
            )
        self.pb_client.run(240 * 5)

    # ----------------------------------------------------------------
    # Close drawer
    # ----------------------------------------------------------------
    def close_drawer(self, elementName, drawer_id):
        if elementName == "elementA":
            joint_id = self.elementA_drawer_to_joint_id[drawer_id]
            close_angle = self.elementA_drawer_to_joint_limits[drawer_id][0]
            p.setJointMotorControl2(
                bodyIndex=self.elementA_id,
                jointIndex=joint_id,
                controlMode=p.POSITION_CONTROL,
                targetPosition=close_angle,
                maxVelocity=0.5,
            )
        elif elementName == "elementC":
            joint_id = self.elementC_drawer_to_joint_id[drawer_id]
            close_angle = self.elementC_drawer_to_joint_limits[drawer_id][0]
            p.setJointMotorControl2(
                bodyIndex=self.elementC_id,
                jointIndex=joint_id,
                controlMode=p.POSITION_CONTROL,
                targetPosition=close_angle,
                maxVelocity=0.5,
            )
            self.pb_client.run(240 * 5)
            
        elif elementName == "elementD":
            joint_id = self.elementD_drawer_to_joint_id[drawer_id]
            close_angle = self.elementD_drawer_to_joint_limits[drawer_id][0]
            print('elementD (close): joint_id:{}, open_angle:{}'.format(joint_id, close_angle))
            p.setJointMotorControl2(
                bodyIndex=self.elementD_id,
                jointIndex=joint_id,
                controlMode=p.POSITION_CONTROL,
                targetPosition=close_angle,
                maxVelocity=0.5,
            )
        elif elementName == "elementE":
            joint_id = self.elementE_drawer_to_joint_id[drawer_id]
            close_angle = self.elementE_drawer_to_joint_limits[drawer_id][0]
            p.setJointMotorControl2(
                bodyIndex=self.elementE_id,
                jointIndex=joint_id,
                controlMode=p.POSITION_CONTROL,
                targetPosition=close_angle,
                maxVelocity=0.5,
            )
        self.pb_client.run(240 * 5)
