import numpy as np
import os
import dehazenet_input as di
import queue
import threading
import dehazenet_transmission as dt
from PIL import Image as Image
import sys
import multiprocessing

HAZE_DIR = "./HazeImages/TestImages"
RESULT_DIR = "./ClearResultImages"
CLEAR_IMAGE_DICTIONARY = {}

START_CONDITION = threading.Condition()
INITIAL_ALPHA = 0.7
STEP_SIZE = 0.01
FINAL_ALPHA = 1


class Task:
    def __init__(self, alpha, result, haze):
        self.alpha = alpha
        self.result = result
        self.haze = haze


def opt_get_alpha(image_index):
    hazy_image_fullname = CLEAR_IMAGE_DICTIONARY[image_index]
    _, image_alpha, _ = dt.trans_get_alpha_beta(hazy_image_fullname)
    return hazy_image_fullname, image_alpha


def opt_input(haze_dir, result_dir):
    haze_file_list = os.listdir(haze_dir)
    result_file_list = os.listdir(result_dir)

    q = queue.Queue()
    # Put result full image path into the queue
    for result_image in result_file_list:
        file_path = os.path.join(result_dir, result_image)
        q.put(file_path)
    q.put(None)

    for haze_image in haze_file_list:
        _, filename = os.path.split(haze_image)
        CLEAR_IMAGE_DICTIONARY[filename[0:di.IMAGE_INDEX_BIT]] = os.path.join(haze_dir, haze_image)
    return q


def opt_get_loss_for_alpha_transmission(alpha, result, haze):
    shape = np.shape(result)
    H = shape[0]
    W = shape[1]
    alpha_matrix = np.ones((shape[0], shape[1])) * alpha
    transmission = []
    for i in range(3):
        t = (haze[:, :, i] - alpha_matrix) / (result[:, :, i] - alpha_matrix)
        where_are_inf = np.isinf(t)
        t[where_are_inf] = 1
        where_are_nan = np.isnan(t)
        t[where_are_nan] = 0
        transmission.append(t)
    avg_trans = (transmission[0] + transmission[1] + transmission[2]) / 3
    result_loss = 0
    for h in range(H):
        for w in range(W):
            result_loss += (transmission[0][h][w] - avg_trans[h][w]) ** 2 + \
                           (transmission[1][h][w] - avg_trans[h][w]) ** 2 + \
                           (transmission[2][h][w] - avg_trans[h][w]) ** 2
    return result_loss


def opt_find_best_alpha(result, haze, alpha):
    min_loss = sys.float_info.max
    best_alpha = None
    a = INITIAL_ALPHA
    while a <= FINAL_ALPHA:
        loss = opt_get_loss_for_alpha_transmission(a, result, haze)
        print("a: " + str(round(a, 3)) + " GT: " + alpha + " loss: " + str(loss))
        if loss < min_loss:
            min_loss = loss
            best_alpha = a
        a += STEP_SIZE
        a = round(a, 3)
    return best_alpha


class OptProducer(threading.Thread):
    def __init__(self, q, task_q):
        threading.Thread.__init__(self)
        self.queue = q
        self.task_queue = task_q

    def run(self):
        while True:
            single_image = self.queue.get()
            if single_image is None:
                self.queue.put(None)
                self.task_queue.put(None)
                break
            result_array = np.array(Image.open(single_image)) / 255
            _, filename = os.path.split(single_image)
            image_index = filename[0:di.IMAGE_INDEX_BIT]
            hazy_image_path, alpha = opt_get_alpha(image_index)
            hazy_array = np.array(Image.open(hazy_image_path)) / 255
            self.task_queue.put(Task(alpha, result_array, hazy_array))
            if START_CONDITION.acquire():
                START_CONDITION.notify_all()
            START_CONDITION.release()
        print('Producer finish')


class OptConsumer(threading.Thread):
    producer_end_number = 0

    def __init__(self, task_queue, lock, producer_num, result_queue):
        threading.Thread.__init__(self)
        self.task_queue = task_queue
        self.lock = lock
        self.producer_num = producer_num
        self.result_queue = result_queue

    def run(self):
        if START_CONDITION.acquire():
            START_CONDITION.wait()
        START_CONDITION.release()
        while True:
            task = self.task_queue.get()
            if task is None:
                self.lock.acquire()
                OptConsumer.producer_end_number += 1
                if OptConsumer.producer_end_number >= self.producer_num:
                    self.lock.release()
                    break
                self.lock.release()
                self.task_queue.put(None)
            else:
                alpha = opt_find_best_alpha(task.result, task.haze, task.alpha)
                self.result_queue.put((alpha, task.alpha))
        print('Consumer finish')


def main():
    q = opt_input(HAZE_DIR, RESULT_DIR)
    cpu_num = multiprocessing.cpu_count()
    task_queue = queue.Queue()
    result_queue = queue.Queue()
    flag_lock = threading.Lock()
    thread_list = []

    for producer_id in range(cpu_num):
        producer = OptProducer(q, task_queue)
        producer.start()
        thread_list.append(producer)

    for consumer_id in range(cpu_num):
        consumer = OptConsumer(task_queue, flag_lock, cpu_num, result_queue)
        consumer.start()
        thread_list.append(consumer)
    for t in thread_list:
        t.join()
    while not result_queue.empty():
        result_tuple = result_queue.get()
        print("Estimate alpha: " + str(result_tuple[0]) + " Groundtruth: " + str(result_tuple[1]))


if __name__ == '__main__':
    main()