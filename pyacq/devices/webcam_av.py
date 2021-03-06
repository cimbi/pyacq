# -*- coding: utf-8 -*-
# Copyright (c) 2016, French National Center for Scientific Research (CNRS)
# Distributed under the (new) BSD License. See LICENSE for more info.

"""
av is python binding to libav or ffmpeg and this is so great.
http://mikeboers.github.io/PyAV/index.html
"""
import time
import sys
import subprocess
import os
import re

import numpy as np

from ..core import Node, register_node_type
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.util.mutex import Mutex

try:
    import av
    HAVE_AV = True
except ImportError:
    HAVE_AV = False



class AVThread(QtCore.QThread):
    def __init__(self, out_stream, container, parent=None):
        QtCore.QThread.__init__(self)
        self.out_stream = out_stream
        self.container = container

        self.lock = Mutex()
        self.running = False
        
    def run(self):
        with self.lock:
            self.running = True
        n = 0
        stream = self.container.streams[0]

        for packet in self.container.demux(stream):
            with self.lock:
                if not self.running:
                    break
            for frame in packet.decode():
                arr = frame.to_rgb().to_nd_array()
                n += 1
                self.out_stream.send(arr, index=n)

    def stop(self):
        with self.lock:
            self.running = False


class WebCamAV(Node):
    """
    Simple webcam device using the `av` python module, which is a wrapper around
    ffmpeg or libav.
    
    See http://mikeboers.github.io/PyAV/index.html.
    """
    _output_specs = {'video': dict(streamtype='video',dtype='uint8',
                                                shape=(4800, 6400, 3), compression ='',
                                                sample_rate = 1.)
                                }
    def __init__(self, **kargs):
        Node.__init__(self, **kargs)
        assert HAVE_AV, "WebCamAV node depends on the `av` package, but it could not be imported."
    

    def _configure(self, camera_num=0, **options):
        self.camera_num = camera_num
        self.options = options
        
        # todo 'dshow' under windows
        if sys.platform.startswith('win'):
            self.format = 'dshow'
            dev_names = get_device_list_dshow()
            self.filepath = "video={}".format(dev_names[camera_num])
        else:
            self.filepath = '/dev/video{}'.format(self.camera_num)
            self.format = 'video4linux2'
            
            
        container = av.open(self.filepath, 'r', self.format , self.options)
        stream = next(s for s in container.streams if s.type == 'video')
        self.output.spec['shape'] = (stream.format.height, stream.format.width, 3)
        self.output.spec['sample_rate'] = float(stream.average_rate)
    
    def _initialize(self):
        pass

    
    def _start(self):
        self.container = av.open(self.filepath, 'r', self.format , self.options)
        self._thread = AVThread(self.output, self.container)
        self._thread.start()

    def _stop(self):
        self._thread.stop()
        self._thread.wait()
        self._running = False
        
        # this delete container (+thread) to close the device
        del(self.container)
        del(self._thread)

    def _close(self):
        pass

register_node_type(WebCamAV)


def get_device_list_dshow():
    """
    Some uggly code to get get device name list under windows directshow
    """
    cmd = "ffmpeg -list_devices true -f dshow -i dummy"
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    txt = proc.stdout.read().decode('ascii')
    txt = txt.split("DirectShow video devices")[1].split("DirectShow audio devices")[0]
    pattern = '"([^"]*)"'
    l = re.findall(pattern, txt, )
    l = [e for e in l if not e.startswith('@')]
    return l
