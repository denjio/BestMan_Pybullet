# !/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
# @FileName       : load_panda.py
# @Time           : 2024-08-03 15:04:37
# @Author         : yk
# @Email          : yangkui1127@gmail.com
# @Description:   : A example load panda robot
"""


import os

from Env.Client import Client
from RoboticsToolBox.Bestman_sim_panda import Bestman_sim_panda
from config.load_config import load_config
from Visualization.Visualizer import Visualizer


def main(filename):

    # load config
    config_path = "../Config/load_panda.yaml"
    cfg = load_config(config_path)
    print(cfg)

    # Init client and visualizer
    client = Client(cfg.Client)
    visualizer = Visualizer(client, cfg.Visualizer)

    # Start record
    visualizer.start_record(filename)

    # Init robot
    panda = Bestman_sim_panda(client, visualizer, cfg)
    visualizer.change_robot_color(panda.sim_get_base_id(), panda.sim_get_arm_id(), False)

    for _ in range(5):
        panda.sim_open_gripper()
        client.wait(2)
        panda.sim_close_gripper()
        client.wait(2)

    # End record
    visualizer.end_record()

    # disconnect pybullet
    client.wait(5)
    client.disconnect()


if __name__ == "__main__":

    # set work dir to Examples
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # get current file name
    file_name = os.path.splitext(os.path.basename(__file__))[0]

    main(file_name)
