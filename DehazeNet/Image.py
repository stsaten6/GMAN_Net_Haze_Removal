#  ====================================================
#   Filename: Image.py
#   Function: This file defines a Image class
#  ====================================================
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import time


class Image(object):
    def __init__(self, path, key=None, image_tensor=None, image_index=None):
        self.path = path
        self.key = key
        self.image_tensor = image_tensor
        self.image_index = image_index


if __name__ == '__main__':
    for i in range(200):
        print(np.random.randint(1,3))
