# !/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
# @FileName       : pyBulletSimRecorder.py
# @Time           : 2024-08-03 15:09:24
# @Author         : yk
# @Email          : yangkui1127@gmail.com
# @Description:   : A recorder in pybullet sim and the result can be import into blender scene
"""

import os

# import PySimpleGUI as sg
import pickle
from os.path import abspath, basename, dirname, splitext

import numpy as np
import pybullet as p
from transforms3d.affines import decompose
from transforms3d.quaternions import mat2quat
from urdfpy import URDF


class PyBulletRecorder:
    """A class for recording PyBullet simulations."""

    class LinkTracker:
        """Tracks the state of a link in the simulation."""

        def __init__(
            self, type, name, body_id, link_id, link_origin, mesh_path, mesh_scale
        ):
            """
            Initializes the LinkTracker class.

            Args:
                type (str): The type of the link (e.g., 'mesh', 'box').
                name (str): The name of the link.
                body_id (int): The ID of the body to which the link belongs.
                link_id (int): The ID of the link.
                link_origin (np.ndarray): The origin transformation of the link.
                mesh_path (str): The path to the mesh file.
                mesh_scale (list): The scale of the mesh.
            """
            self.type = type
            self.name = name
            self.body_id = body_id
            self.link_id = link_id
            decomposed_origin = decompose(link_origin)
            orn = mat2quat(decomposed_origin[1])
            orn = [orn[1], orn[2], orn[3], orn[0]]
            self.link_pose = [decomposed_origin[0], orn]
            self.mesh_path = mesh_path
            self.mesh_scale = mesh_scale

        def transform(self, position, orientation):
            """
            Transforms a local pose to a global pose.

            Args:
                position (list): The position of the link.
                orientation (list): The orientation of the link.

            Returns:
                tuple: The transformed position and orientation.
            """
            return p.multiplyTransforms(
                position,
                orientation,
                self.link_pose[0],
                self.link_pose[1],
            )

        def get_keyframe(self):
            """
            Gets the global pose of the link.

            Returns:
                dict: The position and orientation of the link.
            """
            if self.link_id == -1:
                position, orientation = p.getBasePositionAndOrientation(self.body_id)
                position, orientation = self.transform(
                    position=position, orientation=orientation
                )
            else:
                link_state = p.getLinkState(
                    self.body_id, self.link_id, computeForwardKinematics=True
                )
                position, orientation = self.transform(
                    position=link_state[4], orientation=link_state[5]
                )

            return {"position": list(position), "orientation": list(orientation)}

    def __init__(self):
        """Initializes the PyBulletRecorder class."""
        self.frame_cnt = 0
        self.states = []
        self.links = []

    def register_object(self, body_id, urdf_path, global_scaling):
        """
        Registers an object in the simulation for tracking.

        Args:
            body_id (int): The ID of the body to be registered.
            urdf_path (str): The path to the URDF file of the object.
            global_scaling (float): The global scaling factor for the object.
        """
        link_id_map = dict()
        n = p.getNumJoints(body_id)
        link_id_map[p.getBodyInfo(body_id)[0].decode("gb2312")] = (
            -1
        )  # object base link id
        for link_id in range(0, n):
            link_id_map[
                p.getJointInfo(body_id, link_id)[12].decode(  # object other link id
                    "gb2312"
                )
            ] = link_id

        dir_path = dirname(abspath(urdf_path))
        file_name = splitext(basename(urdf_path))[0]
        robot = URDF.load(urdf_path)
        for link in robot.links:
            link_id = link_id_map[link.name]
            if len(link.visuals) > 0:
                for i, link_visual in enumerate(link.visuals):
                    if link_visual.geometry.mesh is not None:
                        mesh_scale = (
                            [global_scaling, global_scaling, global_scaling]
                            if link_visual.geometry.mesh.scale is None
                            else link_visual.geometry.mesh.scale * global_scaling
                        )

                        self.links.append(
                            PyBulletRecorder.LinkTracker(
                                type="mesh",
                                name=file_name + f"_{body_id}_{link.name}_{i}",
                                body_id=body_id,
                                link_id=link_id,
                                link_origin=  # If link_id == -1 then is base link,
                                # PyBullet will return
                                # inertial_origin @ visual_origin,
                                # so need to undo that transform
                                (
                                    np.linalg.inv(link.inertial.origin)
                                    if link_id == -1
                                    else np.identity(4)
                                )
                                @ link_visual.origin
                                * global_scaling,
                                mesh_path=os.path.join(
                                    dir_path, link_visual.geometry.mesh.filename
                                ),
                                # mesh_path=dir_path + '/' + link_visual.geometry.mesh.filename,
                                mesh_scale=mesh_scale,
                            )
                        )

                    elif link_visual.geometry.box is not None:
                        box_size = link_visual.geometry.box.size
                        assert (
                            len(box_size) == 3
                        ), "wrong box size, please check object urdf file!"
                        self.links.append(
                            PyBulletRecorder.LinkTracker(
                                type="box",  # Specify type as box
                                name=file_name + f"_{body_id}_{link.name}_{i}",
                                body_id=body_id,
                                link_id=link_id,
                                link_origin=  # If link_id == -1 then is base link,
                                # PyBullet will return
                                # inertial_origin @ visual_origin,
                                # so need to undo that transform
                                (
                                    np.linalg.inv(link.inertial.origin)
                                    if link_id == -1
                                    else np.identity(4)
                                )
                                @ link_visual.origin
                                * global_scaling,
                                mesh_path=None,  # No mesh path for boxes
                                mesh_scale=box_size,  # Use box size as scale
                            )
                        )

                    elif link_visual.geometry.cylinder is not None:
                        length = link_visual.geometry.cylinder.length
                        radius = link_visual.geometry.cylinder.radius
                        self.links.append(
                            PyBulletRecorder.LinkTracker(
                                type="cylinder",  # Specify type as box
                                name=file_name + f"_{body_id}_{link.name}_{i}",
                                body_id=body_id,
                                link_id=link_id,
                                link_origin=  # If link_id == -1 then is base link,
                                # PyBullet will return
                                # inertial_origin @ visual_origin,
                                # so need to undo that transform
                                (
                                    np.linalg.inv(link.inertial.origin)
                                    if link_id == -1
                                    else np.identity(4)
                                )
                                @ link_visual.origin
                                * global_scaling,
                                mesh_path=None,  # No mesh path for boxes
                                mesh_scale=[length, radius],  # Use box size as scale
                            )
                        )

    def add_keyframe(self):
        """Adds a keyframe of the current simulation state."""
        # Ideally, call every p.stepSimulation()
        current_state = {}
        for link in self.links:
            link_frame = link.get_keyframe()
            link_frame["frame"] = self.frame_cnt
            current_state[link.name] = link_frame
        self.states.append(current_state)
        self.frame_cnt += 1

    # def prompt_save(self):
    #     """Prompts the user to save the recorded simulation states."""
    #     layout = [[sg.Text('Do you want to save previous episode?')],
    #               [sg.Button('Yes'), sg.Button('No')]]
    #     window = sg.Window('PyBullet Recorder', layout)
    #     save = False
    #     while True:
    #         event, values = window.read()
    #         if event in (None, 'No'):
    #             break
    #         elif event == 'Yes':
    #             save = True
    #             break
    #     window.close()
    #     if save:
    #         layout = [[sg.Text('Where do you want to save it?')],
    #                   [sg.Text('Path'), sg.InputText(os.getcwd())],
    #                   [sg.Button('OK')]]
    #         window = sg.Window('PyBullet Recorder', layout)
    #         event, values = window.read()
    #         window.close()
    #         self.save(values[0])
    #     self.reset()

    def reset(self):
        """Resets the recorded simulation states."""
        self.states = []

    def get_formatted_output(self):
        """
        Gets the formatted output of the recorded simulation states.

        Returns:
            dict: Formatted output of the recorded simulation states.
        """
        retval = {}
        for link in self.links:
            retval[link.name] = {
                "type": link.type,
                "mesh_path": link.mesh_path,
                "mesh_scale": link.mesh_scale,
                "frames": [
                    state[link.name] for state in self.states if link.name in state
                ],
            }
        print("[Recorder] \033[34mInfo\033[0m: Frames num {}".format(len(self.states)))
        return retval

    def save(self, path):
        """
        Saves the recorded simulation states to a file.

        Args:
            path (str): The path to save the recorded simulation states.
        """
        if path is None:
            print("[Recorder] \033[33mwarning\033[0m: Path is None.. not saving")
        else:
            print("[Recorder] \033[34mInfo\033[0m: Saving state to {}".format(path))
            pickle.dump(self.get_formatted_output(), open(path, "wb"))
