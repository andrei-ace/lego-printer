#!/usr/bin/env python3
import os
import logging
import json
import threading
import xml.etree.ElementTree as ET

from time import sleep
from math import cos, sin, pi, acos, asin, sqrt, atan
import xml.etree.ElementTree as ET
from sys import stderr, stdout
import traceback


from ev3dev2.motor import LargeMotor, MediumMotor, OUTPUT_A, OUTPUT_D, OUTPUT_B
from ev3dev2.sound import Sound
from ev3dev2.led import Leds

from agt import AlexaGadget

MAX_ROTATION_X = 16
MAX_ROTATION_Y = 16
MAX_SPEED_X = 80
MAX_SPEED_Y = 80
DEGREES_PEN = 21

# set logger to display on both EV3 Brick and console
logging.basicConfig(level=logging.INFO, stream=stdout,
                    format='%(message)s')
logging.getLogger().addHandler(logging.StreamHandler(stderr))
logger = logging.getLogger(__name__)


class Printer(object):

    def __init__(self):
        self.motor_x = LargeMotor(OUTPUT_A)
        self.motor_y = LargeMotor(OUTPUT_D)
        self.motor_pen = MediumMotor(OUTPUT_B)
        self._pen_down = False
        self.solver = Solver()

    def x(self):
        return -self.motor_x.position / (MAX_ROTATION_X * self.motor_x.count_per_rot)

    def y(self):
        return self.motor_y.position / (MAX_ROTATION_Y * self.motor_y.count_per_rot)

    def reset(self):
        self.motor_x.on_to_position(speed=80, position=0, block=False)
        self.motor_y.on_to_position(speed=80, position=0, block=False)
        self.motor_x.wait_until_not_moving()
        self.motor_y.wait_until_not_moving()
        self.pen_up()

    def move_wh(self, w, h, speed_x=MAX_SPEED_X, speed_y=MAX_SPEED_Y):
        self.motor_x.on_for_rotations(
            speed=speed_x, rotations=-w * MAX_ROTATION_X, block=False)
        self.motor_y.on_for_rotations(
            speed=speed_y, rotations=h * MAX_ROTATION_Y, block=False)
        self.motor_x.wait_until_not_moving()
        self.motor_y.wait_until_not_moving()

    def pen_down(self):
        if not self._pen_down:
            self.motor_pen.on_for_degrees(
                speed=5, degrees=DEGREES_PEN, brake=True)
        self._pen_down = True

    def pen_up(self):
        if self._pen_down:
            self.motor_pen.on_for_degrees(
                speed=5, degrees=-DEGREES_PEN, brake=True)
        self._pen_down = False

    def draw_arc(self, rad_x, rad_y, large, sweep, sx, sy, ex, ey):
        self.pen_down()
        h, k, start, end = self.solver.solve_ellipse(
            (sx, sy), (ex, ey), rad_x, rad_y, large, sweep)
        print('The solution is:', h, k, start*180/pi, "->", end*180/pi)

        if start < 0:
            start += 2*pi
        if start < 0:
            end += 2*pi
        angle = start
        angle_to_do = 0

        if sweep:
            cclock = 1
            angle_to_do = end - start
        else:
            cclock = -1
            angle_to_do = start-end

        if angle_to_do < 0:
            angle_to_do += 2*pi

        print('doing:', angle_to_do*180/pi)

        step = 0
        angle_done = 0
        integral_error_x = 0
        integral_error_y = 0
        integral_weight = 0.1
        while angle_done < angle_to_do:
            dx = -sin(angle) * rad_x * cclock - \
                integral_error_x * integral_weight
            dy = cos(angle) * rad_y * cclock - \
                integral_error_y * integral_weight
            magnitude = sqrt(dx**2 + dy**2)
            speed_x = (dx/magnitude) * MAX_SPEED_X
            speed_y = (dy/magnitude) * MAX_SPEED_Y
            self.motor_x.on(speed=-speed_x)
            self.motor_y.on(speed=speed_y)
            sleep(0.1)

            old_angle = angle
            angle = self.solver.solve_angle(
                cx=h, cy=k, a=rad_x, b=rad_y, px=self.x(), py=self.y())
            step_angle = abs(angle-old_angle)
            if(step_angle > pi):
                step_angle = 2*pi - step_angle
            angle_done += step_angle
            if angle < 0:
                angle += 2*pi

            x_sol = cos(angle) * rad_x + h
            y_sol = sin(angle) * rad_y + k
            integral_error_x += (self.x()-x_sol)
            integral_error_y += (self.y()-y_sol)

            step += 1
            if(step > 100):
                break

        self.motor_x.stop()
        self.motor_y.stop()
        self.pen_up()

    def draw_line(self, from_x, from_y, to_x, to_y):
        self.move_wh(from_x - self.x(), from_y - self.y())
        self.pen_down()
        if (to_x-self.x()) < 0.001 and (to_x-self.x()) > -0.001:
            self.move_wh(0, to_y-self.y())
        else:
            m = (to_y-self.y())/(to_x-self.x())
            speed_x = 1
            speed_y = m * speed_x
            magnitude = sqrt(speed_x**2 + speed_y**2)
            speed_x = (speed_x/magnitude) * MAX_SPEED_X
            speed_y = (speed_y/magnitude) * MAX_SPEED_Y

            self.move_wh(to_x-self.x(), to_y-self.y(),
                         speed_x=speed_x, speed_y=speed_y)
        self.pen_up()

    def draw_svg_path(self, path, width, height):
        path_list = path.split(" ")
        index = 0
        m_x = 0
        m_y = 0
        while index < len(path_list):
            current = path_list[index]
            if current == 'M':
                x = float(path_list[index+1]) / width
                y = float(path_list[index+2]) / height
                m_x = x
                m_y = y
                self.move_wh(x-self.x(), y-self.y())
                index += 3
            elif current == 'A':
                rad_x = float(path_list[index+1]) / width
                rad_y = float(path_list[index+2]) / height
                large = int(path_list[index+4])
                sweep = int(path_list[index+5])
                dx = float(path_list[index+6]) / width
                dy = float(path_list[index+7]) / width
                index += 8
                self.draw_arc(rad_x, rad_y, large, sweep, m_x, m_y, dx, dy)
            else:
                index += 1


class Solver(object):

    def solve_angle(self, cx, cy, a, b, px, py):
        if px-cx:
            theta = atan(((py-cy)*a)/((px-cx)*b))
            if px-cx < 0:
                # quadrand 2 and 3
                theta = theta + pi
        else:
            if py-cy < 0:
                theta = -pi/2
            else:
                theta = pi/2
        return theta

    def solve_ellipse(self, p1, p2, a, b, large, sweep):
        x1 = p1[0]
        y1 = p1[1]
        x2 = p2[0]
        y2 = p2[1]

        m = -2*(b**2)*x1 + 2*(b**2)*x2
        n = -2*(a**2)*y1 + 2*(a**2)*y2
        q = -(b**2)*x1**2 - (a**2)*(y1**2) + (b**2)*(x2**2) + (a**2)*(y2**2)

        if n != 0:
            aa = b**2 + (a**2)*(m**2)/(n**2)
            bb = -2*(b**2)*x1 - (2*q*(a**2)*m)/(n**2) + (2*(a**2)*y1*m)/n
            cc = ((a**2)*(q**2))/(n**2) - (2*(a**2)*y1*q)/n + \
                (b**2)*(x1**2) + (a**2)*(y1**2) - (a**2)*(b**2)

            if bb**2 - 4*aa*cc < -0.001 or bb**2 - 4*aa*cc > 0.001:
                h1 = (-bb + sqrt(bb**2 - 4*aa*cc))/(2*aa)
                h2 = (-bb - sqrt(bb**2 - 4*aa*cc))/(2*aa)
            else:
                h1 = h2 = (-bb)/(2*aa)

            k1 = (q - m * h1)/n
            k2 = (q - m * h2)/n
        else:
            aa = a**2
            bb = -2*a**2*y1
            cc = b**2*q**2/m**2 - 2*b**2*x1*q/m + b**2*x1**2 + a**2*y1**2 - a**2*b**2

            h1 = q/m
            h2 = q/m
            k1 = (-bb + sqrt(bb**2 - 4*aa*cc))/(2*aa)
            k2 = (-bb - sqrt(bb**2 - 4*aa*cc))/(2*aa)

        h = "h"
        k = "k"
        if h1 != h2 or k1 != k2:
            results = [
                {h: h1, k: k1},
                {h: h2, k: k2}
            ]
        else:
            results = [{h: h1, k: k1}]
        results_len = len(results)
        for result in results:
            theta1 = 0
            theta2 = 0
            if p1[0]-result[h]:
                theta1 = atan(((p1[1]-result[k])*a)/((p1[0]-result[h])*b))
                if p1[0]-result[h] < 0:
                    # quadrand 2 and 3
                    theta1 = theta1 + pi
            else:
                if p1[1]-result[k] < 0:
                    theta1 = -pi/2
                else:
                    theta1 = pi/2

            if p2[0]-result[h]:
                theta2 = atan(((p2[1]-result[k])*a)/((p2[0]-result[h])*b))
                if p2[0]-result[h] < 0:
                    # quadrand 2 and 3
                    theta2 = theta2 + pi
            else:
                if p2[1]-result[k] < 0:
                    theta2 = -pi/2
                else:
                    theta2 = pi/2

            if results_len == 1:
                return result[h], result[k], theta1, theta2

            angle = theta2 - theta1
            if angle < 0:
                angle += 2 * pi
            if angle >= 2*pi:
                angle -= 2 * pi

            if large == 0:
                if sweep:
                    if angle <= pi:
                        return result[h], result[k], theta1, theta2
                else:
                    if angle >= pi:
                        return result[h], result[k], theta1, theta2
            else:
                if sweep:
                    if angle >= pi:
                        return result[h], result[k], theta1, theta2
                else:
                    if angle <= pi:
                        return result[h], result[k], theta1, theta2

        return None


class MindstormsGadget(AlexaGadget):
    """
    An Mindstorms gadget that will react to the Alexa wake word.
    """

    def __init__(self):
        """
        Performs Alexa Gadget initialization routines and ev3dev resource allocation.
        """
        super().__init__()

        self.leds = Leds()
        self.sound = Sound()
        self._waiting_for_speech = False
        self.lock = threading.Lock()
        self.printer = Printer()

    def on_connected(self, device_addr):
        """
        Gadget connected to the paired Echo device.
        :param device_addr: the address of the device we connected to
        """
        self.leds.set_color("LEFT", "GREEN")
        self.leds.set_color("RIGHT", "GREEN")
        logger.info("{} connected to Echo device".format(self.friendly_name))

    def on_disconnected(self, device_addr):
        """
        Gadget disconnected from the paired Echo device.
        :param device_addr: the address of the device we disconnected from
        """
        self.leds.set_color("LEFT", "BLACK")
        self.leds.set_color("RIGHT", "BLACK")
        logger.info("{} disconnected from Echo device".format(
            self.friendly_name))

    def on_custom_mindstorms_gadget_learn(self, directive):
        """
        Handles the Custom.Mindstorms.Gadget control directive.
        :param directive: the custom directive with the matching namespace and name
        """
        try:
            payload = json.loads(directive.payload.decode("utf-8"))
            print("Payload: {}".format(payload), file=stderr)
            self._waiting_for_speech = True
            threading.Thread(target=self.learn, args=(
                payload["letter"],), daemon=True).start()
        except KeyError:
            print("Missing expected parameters: {}".format(
                directive), file=stderr)

    def on_alexa_gadget_speechdata_speechmarks(self, directive):
        """
        Alexa.Gadget.SpeechData Speechmarks directive received.
        For more info, visit:
            https://developer.amazon.com/docs/alexa-gadgets-toolkit/alexa-gadget-speechdata-interface.html#Speechmarks-directive
        :param directive: Protocol Buffer Message that was send by Echo device.
        """
        try:
            if self._waiting_for_speech:
                if directive.payload.speechmarksData[-1].value == 'sil':
                    # sleep until time
                    print('received silence', file=stderr)
                    self._waiting_for_speech = False

        except KeyError:
            print("Missing expected parameters: {}".format(
                directive), file=stderr)

    def learn(self, letter):
        print('drawing letter ', letter, file=stderr)
        while self._waiting_for_speech:
            sleep(0.1)
        print('done', file=stderr)
        file = "svg/B.svg"
        tree = ET.parse(file)
        root = tree.getroot()
        width = int(root.attrib["width"])
        height = int(root.attrib["height"])
        self.lock.acquire()
        try:
            for child in root:
                if child.tag == '{http://www.w3.org/2000/svg}path':
                    for pos_title in child:
                        if pos_title.tag == '{http://www.w3.org/2000/svg}title':
                            self._waiting_for_speech = True
                            self.send_custom_event(
                                'Custom.Mindstorms.Gadget', 'speak', {'txt': pos_title.text})
                            while self._waiting_for_speech:
                                sleep(0.1)
                            print('done', file=stderr)
                    self.printer.draw_svg_path(
                        child.attrib["d"], width, height)
                elif child.tag == '{http://www.w3.org/2000/svg}line':
                    for pos_title in child:
                        if pos_title.tag == '{http://www.w3.org/2000/svg}title':
                            self._waiting_for_speech = True
                            self.send_custom_event(
                                'Custom.Mindstorms.Gadget', 'speak', {'txt': pos_title.text})
                            while self._waiting_for_speech:
                                sleep(0.1)
                            print('done', file=stderr)
                    self.printer.draw_line(
                        float(child.attrib["x1"])/width,
                        float(child.attrib["y1"])/height,
                        float(child.attrib["x2"])/width,
                        float(child.attrib["y2"])/height)
        except Exception as e:
            print(e, file=stderr)
            traceback.print_exc(file=stderr)
        self.printer.reset()
        self.lock.release()
        self.send_custom_event(
            'Custom.Mindstorms.Gadget', 'done', {})


if __name__ == '__main__':

    gadget = MindstormsGadget()

    # Set LCD font and turn off blinking LEDs
    os.system('setfont Lat7-Terminus12x6')
    gadget.leds.set_color("LEFT", "BLACK")
    gadget.leds.set_color("RIGHT", "BLACK")

    # Startup sequence
    # gadget.sound.play_song((('C4', 'e'), ('D4', 'e'), ('E5', 'q')))
    gadget.leds.set_color("LEFT", "GREEN")
    gadget.leds.set_color("RIGHT", "GREEN")

    # Gadget main entry point
    gadget.main()

    # Shutdown sequence
    # gadget.sound.play_song((('E5', 'e'), ('C4', 'e')))
    gadget.leds.set_color("LEFT", "BLACK")
    gadget.leds.set_color("RIGHT", "BLACK")
