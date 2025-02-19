# !/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
# @FileName       : Bestman_sim.py
# @Time           : 2024-08-03 14:44:09
# @Author         : yk
# @Email          : yangkui1127@gmail.com
# @Description:   : A basic class for BestMan robot
"""

import math
import time
from collections import namedtuple
import numpy as np
import pybullet as p

from Controller import PIDController
from Visualization import Camera

from .Pose import Pose


class Bestman_sim:
    """A basic class for BestMan robot

    Attributes:
        client (object): The pybullet client object.
        client_id (int): The client id returned by the pybullet client.

        target_distance (float): The target distance for the PID controller.
        controller (object): The PID controller object.
        rotated (bool): A flag indicating whether the object has been rotated.

        init_pos (object): The initial position object.
        base_id (int): The base id of the URDF model.
        arm_id (int): The arm id of the URDF model.
        arm_joints_idx (list): A list of joint indexes.
        arm_height (float): The height of the arm.
        end_effector_index (int): The index of the end effector.
        tcp_link (int): The tcp link index.
        tcp_height (float): The height of the tcp link.

        visualizer (object): The visualizer object.
        gripper_id (None): The gripper id. Initialized to None.
    """

    def __init__(self, client, visualizer, cfg):
        """
        Initialize a new robot.

        Args:
            client (object): The pybullet client object.
            visualizer (object): The visualizer object.
            cfg (object): Configuration object containing parameters for the PID controller and robot setup.
        """

        self.client = client
        self.client_id = self.client.get_client_id()

        self.visualizer = visualizer
        self.enable_cache = (
            p.URDF_ENABLE_CACHED_GRAPHICS_SHAPES
        )  # Enable caching of graphic shapes when loading URDF files

        # Init PID controller
        controller_cfg = cfg.Controller
        self.target_distance = controller_cfg.target_distance
        self.distance_controller = PIDController(
            Kp=controller_cfg.Kp,
            Ki=controller_cfg.Ki,
            Kd=controller_cfg.Kd,
            setpoint=self.target_distance,
        )

        # robot cfg
        robot_cfg = cfg.Robot
        
        # init pose for base and arm
        init_pose = Pose(robot_cfg.init_pose[:3], robot_cfg.init_pose[3:])
        
        # Init base
        self.base_id = self.client.load_object(
            obj_name="base",
            model_path=robot_cfg.base_urdf_path,
            object_position=init_pose.get_position(),
            object_orientation=init_pose.get_orientation(),
            fixed_base=True,
        )
        self.base_rotated = False
        self.current_base_yaw = init_pose.get_orientation("euler")[2]

        # Init arm
        self.arm_id = self.client.load_object(
            obj_name="arm",
            model_path=robot_cfg.arm_urdf_path,
            object_position=init_pose.get_position(),
            object_orientation=init_pose.get_orientation(),
            fixed_base=True,
        )
        self.arm_joints_idx = robot_cfg.arm_joints_idx
        self.DOF = len(self.arm_joints_idx)
        self.arm_place_height = robot_cfg.base_height + 0.02
        self.end_effector_index = robot_cfg.end_effector_index
        self.tcp_link = robot_cfg.tcp_link
        self.tcp_height = robot_cfg.tcp_height
        self.arm_reset_jointValues = robot_cfg.arm_reset_jointValues  # arm reset joint values
        self.arm_jointInfo = self.sim_get_arm_all_jointInfo()
        self.arm_lower_limits = [info.lowerLimit for info in self.arm_jointInfo]
        self.arm_upper_limits = [info.upperLimit for info in self.arm_jointInfo]
        self.arm_joint_ranges = [info.upperLimit - info.lowerLimit for info in self.arm_jointInfo]

        # Add constraint between base and arm
        p.createConstraint(
            parentBodyUniqueId=self.base_id,
            parentLinkIndex=-1,
            childBodyUniqueId=self.arm_id,
            childLinkIndex=-1,
            jointType=p.JOINT_FIXED,
            jointAxis=[0, 0, 0],
            parentFramePosition=[0, 0, 0],
            childFramePosition=[0, 0, 0],
            physicsClientId=self.client_id,
        )

        # synchronize base and arm positions
        self.sim_sync_base_arm_pose()
        
        # Init arm joint angle
        self.sim_set_arm_to_joint_values(robot_cfg.arm_init_jointValues)
        
        # change robot color
        self.visualizer.change_robot_color(self.base_id, self.arm_id, False)

        # Init camera
        Camera_cfg = cfg.Camera
        self.camera = Camera(Camera_cfg, self.base_id, self.arm_place_height)
        
        # global parameters
        self.constraint_id = None  # grasp constraint id

    # ----------------------------------------------------------------
    # functions for base
    # ----------------------------------------------------------------

    def sim_get_base_id(self):
        """
        Retrieves the ID of the robot base.

        Returns:
            int: The ID of the robot base.
        """
        return self.base_id

    def sim_get_current_base_pose(self):
        """
        Retrieves the current position and orientation of the robot base.

        Returns:
            Pose: A Pose object representing the current pose of the base.
                  The pose contains the position as a list [x, y, z] and the orientation as a list [roll, pitch, yaw].
        """
        base_position, base_orientation = p.getBasePositionAndOrientation(
            self.base_id, physicsClientId=self.client_id
        )
        return Pose(base_position, base_orientation)

    def sim_stop_base(self):
        """
        Stops the movement of the robot base by setting its velocity to zero.

        Returns:
            bool: True if the base has been successfully stopped.
        """
        zero_velocity = [0, 0, 0]
        p.resetBaseVelocity(
            self.base_id, zero_velocity, zero_velocity, physicsClientId=self.client_id
        )
        return True

    def sim_rotate_base(self, target_yaw, gradual=True, step_size=0.02, delay_time=0.05):
        """
        Rotate base to a specified yaw angle. Can be done gradually or at once.

        Args:
            target_yaw (float): The target yaw angle (in radians) for the base.
            gradual (bool): If True, the rotation is done gradually. Otherwise, it's instant.
            step_size (float, optional): Angle increment for each step in radians. Only used if gradual=True.
            delay_time (float, optional): Delay in seconds after each step. Only used if gradual=True.
        """

        def angle_to_quaternion(yaw):
            return [0, 0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)]

        def shortest_angular_distance(from_angle, to_angle):
            return (to_angle - from_angle + math.pi) % (2 * math.pi) - math.pi

        if gradual:

            angle_diff = shortest_angular_distance(self.current_base_yaw, target_yaw)

            while abs(angle_diff) > step_size:

                if angle_diff > 0:
                    self.current_base_yaw += step_size
                else:
                    self.current_base_yaw -= step_size

                self.current_base_yaw = (self.current_base_yaw + math.pi) % (
                    2 * math.pi
                ) - math.pi
                angle_diff = shortest_angular_distance(self.current_base_yaw, target_yaw)
                orientation = angle_to_quaternion(self.current_base_yaw)
                position, _ = p.getBasePositionAndOrientation(
                    self.base_id, physicsClientId=self.client_id
                )
                p.resetBasePositionAndOrientation(
                    self.base_id, position, orientation, physicsClientId=self.client_id
                )
                self.sim_sync_base_arm_pose()
                self.client.run()

            # Ensure final orientation is set accurately
            orientation = angle_to_quaternion(target_yaw)
            position, _ = p.getBasePositionAndOrientation(
                self.base_id, physicsClientId=self.client_id
            )
            p.resetBasePositionAndOrientation(
                self.base_id, position, orientation, physicsClientId=self.client_id
            )
            self.sim_sync_base_arm_pose()
            self.current_base_yaw = target_yaw
            self.client.run()

        else:
            orientation = angle_to_quaternion(target_yaw)
            position, _ = p.getBasePositionAndOrientation(
                self.base_id, physicsClientId=self.client_id
            )
            p.resetBasePositionAndOrientation(
                self.base_id, position, orientation, physicsClientId=self.client_id
            )
            self.sim_sync_base_arm_pose()

            self.client.run(5)

    def sim_action(self, output):
        """
        Ajust base position using PID controller's output

        Args:
            output (float): The output of the PID controller, which is used to calculate the new position of the robot's base.
        """
        position, orientation = p.getBasePositionAndOrientation(
            self.base_id, physicsClientId=self.client_id
        )
        euler_angles = p.getEulerFromQuaternion(
            orientation, physicsClientId=self.client_id
        )
        p.resetBasePositionAndOrientation(
            self.base_id,
            [
                position[0] + output * math.cos(euler_angles[2]),
                position[1] + output * math.sin(euler_angles[2]),
                position[2],
            ],
            orientation,
            physicsClientId=self.client_id,
        )
        self.sim_sync_base_arm_pose()

    def sim_move_base_to_waypoint(self, waypoint, threshold=0.01):
        """
        Move base to waypoint
        The robot first rotates towards the target, and then moves towards it in a straight line.
        The movement is controlled by a controller (assumed to be a PID controller) that adjusts the velocity of the robot based on the distance to the target.

        Args:
            waypoint (Pose): The target pose (position and orientation) for the robot. This should be an instance of a Pose class, which is assumed to have 'x' and 'y' properties.
        """
        self.next_waypoint = waypoint
        self.target_distance = 0.0
        self.base_rotated = False
        cnt = 1

        while True:
            pose = self.sim_get_current_base_pose()
            target = self.next_waypoint
            x, y = pose.x, pose.y

            distance = math.sqrt((target.y - y) ** 2 + (target.x - x) ** 2)
            if distance < threshold:
                break

            self.distance_controller.set_goal(self.target_distance)
            output = self.distance_controller.calculate(distance)

            yaw = math.atan2(target.y - y, target.x - x)

            if not self.base_rotated:
                self.sim_rotate_base(yaw)
                self.base_rotated = True

            self.sim_action(-output)

            if cnt % 20 == 0:
                self.client.run()

            cnt += 1

        self.client.run()

    def sim_navigate_base(self, goal_base_pose, path, threshold=0.05, enable_plot=False):
        """
        Navigate a robot from its current position to a specified goal position

        Args:
            goal_base_pose (Pose): The target pose (position and orientation) for the robot.
        """
        # for i, waypoint in enumerate(path, start=1):
        for i in range(len(path)):

            next_point = [path[i][0], path[i][1], 0]
            # move to each waypoint
            self.sim_move_base_to_waypoint(
                Pose([path[i][0], path[i][1], 0], goal_base_pose.get_orientation())
            )

            # draw the trajectory
            if i != 0 and enable_plot:
                front_point = [path[i - 1][0], path[i - 1][1], 0]
                p.addUserDebugLine(
                    front_point,
                    next_point,
                    lineColorRGB=[1, 0, 0],
                    lineWidth=3,
                    physicsClientId=self.client_id,
                )

        self.sim_rotate_base(goal_base_pose.get_orientation("euler")[2])
        self.client.run(10)
        ik_error = self.sim_calculate_nav_error(goal_base_pose)
        if ik_error >= threshold:
            print(
                f"[BestMan_Sim][Base] \033[33mwarning\033[0m: The robot base don't reach the specified position! IK error: {ik_error}"
            )
        print("[BestMan_Sim][Base] \033[34mInfo\033[0m: Navigation is done!")

    def sim_calculate_nav_error(self, goal_pose):
        """Calculate the navigation error for performing pick-and-place manipulation of an object using a robot arm.

        Args:
            goal_position: The desired goal position for the target object.
            goal_orientation: The desired goal orientation for the target object.
        """
        current_base_pose = self.sim_get_current_base_pose()
        distance = np.linalg.norm(
            np.array(current_base_pose.get_position()) - np.array(goal_pose.get_position())
        )
        return distance

    # ----------------------------------------------------------------
    # functions for arm
    # ----------------------------------------------------------------

    def sim_get_arm_id(self):
        """
        Retrieves the ID of the robot arm.

        Returns:
            int: The ID of the robot arm.
        """
        return self.arm_id

    def sim_get_DOF(self):
        """
        Retrieves the degree of freedom (DOF) of the robot arm.

        Returns:
            int: The degree of freedom of the robot arm.
        """
        return self.DOF

    def sim_get_arm_joint_idx(self):
        """
        Retrieves the indices of the joints in the robot arm.

        Returns:
            list: A list of indices for the joints in the robot arm.
        """
        return self.arm_joints_idx

    def sim_get_arm_all_joint_idx(self):
        """
        Retrieves the indices of the joints in the robot arm.

        Returns:
            list: A list of indices for the joints in the robot arm.
        """
        return list(range(p.getNumJoints(self.arm_id, physicsClientId=self.client_id)))

    def sim_get_tcp_link(self):
        """
        Retrieves the TCP (Tool Center Point) link of the robot arm.

        Returns:
            str: The TCP link of the robot arm.
        """
        return self.tcp_link

    def sim_get_tcp_link_height(self):
        """
        Retrieves the TCP (Tool Center Point) link height of the robot arm.

        Returns:
            str: The TCP link of the robot arm.
        """
        return self.tcp_height

    def sim_get_end_effector_link(self):
        """
        Retrieves the end effector link id

        Returns:
            str: The end effector link id of the robot arm.
        """
        return self.end_effector_index
    
    def sim_get_arm_all_jointInfo(self):
        """
        get all arm joints info
        
        Returns:
            list: joint info list of all arm active joint
        """
        jointInfo = namedtuple('jointInfo', 
            ['id','name','type','damping','friction','lowerLimit','upperLimit','maxForce','maxVelocity'])
        arm_jointInfo = []
        for i in self.arm_joints_idx:
            info = p.getJointInfo(self.arm_id, i)
            jointID = info[0]
            jointName = info[1].decode("utf-8")
            jointType = info[2]  # JOINT_REVOLUTE, JOINT_PRISMATIC, JOINT_SPHERICAL, JOINT_PLANAR, JOINT_FIXED
            jointDamping = info[6]
            jointFriction = info[7]
            jointLowerLimit = info[8]
            jointUpperLimit = info[9]
            jointMaxForce = info[10]
            jointMaxVelocity = info[11]
            info = jointInfo(jointID,jointName,jointType,jointDamping,jointFriction,jointLowerLimit,
                            jointUpperLimit,jointMaxForce,jointMaxVelocity)
            arm_jointInfo.append(info)
        return arm_jointInfo
    
    def sim_get_joint_bounds(self):
        """
        Retrieves the joint bounds of the robot arm.

        By default, this function reads the joint bounds from pybullet.

        Returns:
            list: A list of tuples representing the joint bounds, where each tuple contains the minimum and maximum values for a joint.
        """
        joint_bounds = [[info.lowerLimit, info.upperLimit] for info in self.arm_jointInfo]
        return joint_bounds

    def sim_get_current_joint_values(self):
        """
        Retrieve arm's joint angle
        """
        current_joint_values = [
            p.getJointState(self.arm_id, i, physicsClientId=self.client_id)[0]
            for i in self.arm_joints_idx
        ]
        return current_joint_values

    def sim_get_current_end_effector_pose(self):
        """
        Retrieve arm's end effect information
        """
        end_effector_info = p.getLinkState(
            bodyUniqueId=self.arm_id,
            linkIndex=self.end_effector_index,
            physicsClientId=self.client_id,
        )
        return Pose(end_effector_info[0], end_effector_info[1])

    def sim_set_arm_to_joint_values(self, joint_values):
        """
        Set arm to move to a specific set of joint angles, witout considering physics

        Args:
            joint_values: A list of desired joint angles (in radians) for each joint of the arm.
        """
        for joint, value in zip(self.arm_joints_idx, joint_values):
            p.resetJointState(self.arm_id, joint, value, targetVelocity=0)
        self.client.run(10)

    def sim_debug_set_arm_to_joint_values(self):
        """
        Manually set each joint value of the arm for debugging purposes.
        """

        joint_values = self.sim_get_current_joint_values()
        print(
            "[BestMan_Sim][Arm] \033[34mInfo\033[0m: Current joint angles: {}".format(
                joint_values
            )
        )

        for i in self.arm_joints_idx:
            joint_value = input(
                "Enter value for joint {} (current value: {}) or 'q' to keep current value: ".format(
                    i, joint_values[i]
                )
            )
            if joint_value.lower() == "q":
                print(
                    "[BestMan_Sim][Arm] \033[34mInfo\033[0m: Skipping joint {}".format(
                        i
                    )
                )
                continue
            try:
                joint_values[i] = float(joint_value)
            except ValueError:
                print(
                    "[BestMan_Sim][Arm] \033[31merror\033[0m: Invalid input. Keeping current value for joint {}.".format(
                        i
                    )
                )

        self.sim_set_arm_to_joint_values(joint_values)
        print(
            "[BestMan_Sim][Arm] \033[34mInfo\033[0m: Updated joint angles: {}".format(
                joint_values
            )
        )

    def sim_move_arm_to_joint_values(self, joint_values, threshold=0.015, timeout=0.05):
        """
        Move arm to move to a specific set of joint angles, with considering physics

        Args:
            joint_values: A list of desired joint angles (in radians) for each joint of the arm.
        """

        p.setJointMotorControlArray(
            bodyIndex=self.arm_id,
            jointIndices=self.arm_joints_idx,
            controlMode=p.POSITION_CONTROL,
            targetPositions=joint_values,
            physicsClientId=self.client_id,
        )

        # start_time = time.time()  # avoid time anomaly

        # while True:
        #     self.client.run()
        #     joint_states = p.getJointStates(
        #         self.arm_id, self.arm_joints_idx, physicsClientId=self.client_id
        #     )
        #     current_angles = [state[0] for state in joint_states]
        #     diff_angles = [abs(a - b) for a, b in zip(joint_values, current_angles)]
        #     if all(diff < threshold for diff in diff_angles):
        #         break

        #     if time.time() - start_time > timeout:  # avoid time anomaly
        #         if p.getContactPoints(self.arm_id):
        #             assert (
        #                 0,
        #                 "[BestMan_Sim][Arm] \033[31merror\033[0m: The arm collides with other objects!",
        #             )
        #         # print("-" * 20 + "\n" + "Timeout before reaching target joint position.")
        #         break
        
        self.client.run(40)

    def sim_joints_to_cartesian(self, joint_values):
        """
        Transforms the robot arm's joint angles to its Cartesian coordinates.

        Args:
            joint_values (list): A list of joint angles for the robot arm.

        Returns:
            tuple: A tuple containing the Cartesian coordinates (position and orientation) of the robot arm.
        """

        self.sim_move_arm_to_joint_values(joint_values)

        end_effector_info = p.getLinkState(
            bodyUniqueId=self.arm_id,
            linkIndex=self.end_effector_index,
            physicsClientId=self.client_id,
        )
        orientation = p.getEulerFromQuaternion(
            end_effector_info[1], physicsClientId=self.client_id
        )
        position = end_effector_info[0]
        return Pose(position, orientation)

    def sim_cartesian_to_joints(self, pose, max_iterations=1000, threshold=1e-4):
        """
        Transforms the robot arm's Cartesian coordinates to its joint angles.

        Args:
            position (list): The Cartesian position of the robot arm.
            orientation (list): The Cartesian orientation of the robot arm.

        Returns:
            list: A list of joint angles corresponding to the given Cartesian coordinates.
        """
        joint_values = p.calculateInverseKinematics(
            bodyUniqueId=self.arm_id,
            endEffectorLinkIndex=self.end_effector_index,
            targetPosition=pose.get_position(),
            targetOrientation=pose.get_orientation(),
            lowerLimits=self.arm_lower_limits,
            upperLimits=self.arm_upper_limits,
            jointRanges=self.arm_joint_ranges,
            restPoses=self.arm_reset_jointValues,
            maxNumIterations=max_iterations,
            residualThreshold=threshold
        )[: self.DOF]
        return joint_values

    def sim_rotate_end_effector(self, angle):
        """
        Rotate the end effector of the robot arm by a specified angle.

        Args:
            angle (float): The desired rotation angle in radians.
        """

        # Change this to your actual joint indices
        joint_states = p.getJointStates(
            self.arm_id, self.arm_joints_idx, physicsClientId=self.client_id
        )

        # Create a new list of target joint angles
        target_joint_values = [joint_state[0] for joint_state in joint_states]

        # Add desired rotation to the last joint's current angle
        target_joint_values[-1] += angle

        # Set the target angles
        self.sim_move_arm_to_joint_values(target_joint_values)

        # Step the simulation until the joints reach their target angles
        while True:
            # Update the current joint states
            joint_states = p.getJointStates(
                self.arm_id, self.arm_joints_idx, physicsClientId=self.client_id
            )
            current_joint_values = [joint_state[0] for joint_state in joint_states]

            # Check if all joints have reached their target angles
            if all(
                abs(current_joint_values[i] - target_joint_values[i]) < 0.01
                for i in range(len(self.arm_joints_idx))
            ):
                break

            self.client.run()

        print("[BestMan_Sim][Arm] \033[34mInfo\033[0m: Rotate end effector completed!")

    def sim_move_end_effector_to_goal_pose(
        self, end_effector_goal_pose, steps=10, threshold=0.1
    ):
        """
        Move arm's end effector to a target position.
        
        Args:
            end_effector_goal_pose (Pose): The desired pose of the end effector (includes both position and orientation).
        """

        start_pose = self.sim_get_current_end_effector_pose()
        for t in np.linspace(0, 1, steps):
            interpolated_position = (1 - t) * np.array(
                start_pose.get_position()
            ) + t * np.array(end_effector_goal_pose.get_position())
            interpolated_orientation = p.getQuaternionSlerp(
                start_pose.get_orientation(),
                end_effector_goal_pose.get_orientation(),
                t
            )
            interpolated_pose = Pose(interpolated_position, interpolated_orientation)
            joint_values = self.sim_cartesian_to_joints(interpolated_pose)
            self.sim_move_arm_to_joint_values(joint_values)
            # if len(p.getContactPoints(self.arm_id)) > 0:
            #     print(
            #         "[BestMan_Sim][Arm] \033[31merror\033[0m: The arm collides with other objects!"
            #     )
            #     return
        ik_error = self.sim_calculate_IK_error(end_effector_goal_pose)
        if ik_error >= threshold:
            print(
                f"[BestMan_Sim][Arm] \033[33mwarning\033[0m: The robot arm don't reach the specified position! IK error: {ik_error}"
            )
            
        print("[BestMan_Sim][Arm] \033[34mInfo\033[0m: Move end effector to goal pose finished!")

    def sim_execute_trajectory(self, trajectory, threshold=0.1, enable_plot=False):
        """Execute the path planned by Planner

        Args:
            trajectory: List, each element is a list of angles, corresponding to a transformation
        """

        for i in range(len(trajectory)):
            self.sim_move_arm_to_joint_values(trajectory[i])

            # if i % 3 == 0:
            # self.visualizer.draw_link_pose(self.arm_id, self.end_effector_index)
            current_point = self.sim_get_current_end_effector_pose().get_position()

            # draw the trajectory
            if i != 0 and enable_plot:
                p.addUserDebugLine(
                    front_point,
                    current_point,
                    lineColorRGB=[1, 0, 0],
                    lineWidth=3,
                    physicsClientId=self.client_id,
                )

            front_point = current_point

        self.client.run(40)

        current_joint_values = self.sim_get_current_joint_values()
        diff_angles = [abs(a - b) for a, b in zip(current_joint_values, trajectory[-1])]
        greater_than_threshold = [diff for diff in diff_angles if diff > threshold]
        greater_num = len(greater_than_threshold)
        if greater_num > 0:
            print(
                f"[BestMan_Sim][Arm] \033[33mwarning\033[0m: The robot arm({greater_num} joints) don't reach the specified position!"
            )

        print("[BestMan_Sim][Arm] \033[34mInfo\033[0m: Excite trajectory finished!")

    def sim_calculate_IK_error(self, goal_pose):
        """Calculate the inverse kinematics (IK) error for performing pick-and-place manipulation of an object using a robot arm.

        Args:
            goal_position: The desired goal position for the target object.
            goal_orientation: The desired goal orientation for the target object.
        """

        end_effector_pose = self.sim_get_current_end_effector_pose()
        distance = np.linalg.norm(
            np.array(end_effector_pose.get_position()) - np.array(goal_pose.get_position())
        )
        return distance

    # ----------------------------------------------------------------
    # functions between base and arms
    # ----------------------------------------------------------------

    def sim_get_robot_size(self):
        """Retrieves the maximum size of the robot (arm and base) in meters.

        Returns:
            float: The maximum size of the robot in meters.
        """
        (
            min_x_base,
            min_y_base,
            _,
            max_x_base,
            max_y_base,
            _,
        ) = self.client.get_bounding_box(self.base_id)

        (
            min_x_arm,
            min_y_arm,
            _,
            max_x_arm,
            max_y_arm,
            _,
        ) = self.client.get_bounding_box(self.arm_id)

        robot_size = max(
            max_x_base - min_x_base,
            max_y_base - min_y_base,
            max_x_arm - min_x_arm,
            max_y_arm - min_y_arm,
        )

        return robot_size

    def sim_sync_base_arm_pose(self):
        """
        Synchronizes the pose of the robot arm with the base.

        This function ensures that the positions of the robot arm and base are aligned.
        """

        position, orientation = p.getBasePositionAndOrientation(
            self.base_id, physicsClientId=self.client_id
        )
        if self.arm_id is not None:
            p.resetBasePositionAndOrientation(
                self.arm_id,
                [position[0], position[1], self.arm_place_height],
                orientation,
                physicsClientId=self.client_id,
            )

    # ----------------------------------------------------------------
    # functions for camera
    # ----------------------------------------------------------------

    def sim_update_camera(self):
        self.camera.sim_update()

    def sim_get_camera_pose(self):
        return self.camera.sim_get_camera_pose()
        
    def sim_get_camera_rgb_image(self, enable_show=False, enable_save=False, filename=None):
        return self.camera.sim_get_rgb_image(enable_show, enable_save, filename)

    def sim_get_camera_depth_image(
        self, enable_show=False, enable_save=False, filename=None
    ):
        return self.camera.sim_get_depth_image(enable_show, enable_save, filename)

    def sim_get_camera_3d_points(self, enable_show=False):
        return self.camera.sim_get_3d_points(enable_show)

    def sim_visualize_camera_3d_points(self):
        self.camera.sim_visualize_3d_points()
    
    def sim_trans_camera_to_world(self, pose):
        return self.camera.sim_trans_to_world(pose)
