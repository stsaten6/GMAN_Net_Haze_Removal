#  ====================================================
#   Filename: dehazenet_options.py
#   Function: This file is used to do several options using transmission.
#  ====================================================
import numpy as np
import queue
import os
import multiprocessing
import threading
from PIL import Image as Image
import dehazenet_optimize as do
import dehazenet_transmission as dt
import WRLock
import time
import matplotlib.pyplot as plt
import shutil
from enum import Enum
from abc import ABCMeta,abstractmethod
import dehazenet_darkchannel as dd
from ColorAttenuationPriorDehazing import runDehazing

TRANS_DIR = "./ClearImages/TransImages"
HAZY_DIR = "./HazeImages/TestImages"
STATISTICAL_DIR = "./StatisticalFigure"
START_CONDITION = threading.Condition()
RESULT_QUEUE = queue.Queue()
THRESHOLD = 0.005
LOWER_BOUNDARY = 0.7
STEP_SIZE = 0.01
TRANSMISSION_THRESHOLD = 0.001


class Options(Enum):
    GET_CLOSE_ZERO_TRANSMISSION_STATISTICS = 0
    GET_HISTOGRAM_WITH_CLOSE_RGB = 1
    GET_TRANSMISSION_HISTOGRAM = 2
    DEHAZE_WITH_TRANSMISSION_MAP = 3
    GET_PIXEL_NUMBER_CLOSE_FOR_LOW_TRANSMISSION = 4
    GET_ESTIMATE_ALPHA = 5


# TODO Modify options here
OPTION = Options.GET_ESTIMATE_ALPHA


class OptionFactory:
    @staticmethod
    def get_option_instance(option):
        if option == Options.GET_CLOSE_ZERO_TRANSMISSION_STATISTICS:
            return OptionDoCountCloseZero()
        elif option == Options.GET_HISTOGRAM_WITH_CLOSE_RGB:
            return OptionGetThreeChannelValueClose()
        elif option == Options.GET_TRANSMISSION_HISTOGRAM:
            return OptionGetTransmissionHistogram()
        elif option == Options.DEHAZE_WITH_TRANSMISSION_MAP:
            return OptionDehazeUsingTransmissionMap()
        elif option == Options.GET_PIXEL_NUMBER_CLOSE_FOR_LOW_TRANSMISSION:
            return OptionCheckDistancesWithSmallTransmission()
        elif option == Options.GET_ESTIMATE_ALPHA:
            return OptionGetEstimateAlpha()
        else:
            raise NotImplementedError("Method is not implemented!")

    @staticmethod
    def get_matplotlib_instance(option):
        if option == Options.GET_CLOSE_ZERO_TRANSMISSION_STATISTICS:
            return OptionDoCountCloseZero()
        elif option == Options.GET_HISTOGRAM_WITH_CLOSE_RGB:
            return OptionGetThreeChannelValueClose()
        elif option == Options.GET_TRANSMISSION_HISTOGRAM:
            return OptionGetTransmissionHistogram()
        elif option == Options.DEHAZE_WITH_TRANSMISSION_MAP:
            return OptionDehazeUsingTransmissionMap()
        elif option == Options.GET_PIXEL_NUMBER_CLOSE_FOR_LOW_TRANSMISSION:
            return OptionCheckDistancesWithSmallTransmission()
        elif option == Options.GET_ESTIMATE_ALPHA:
            return OptionGetEstimateAlpha()
        else:
            raise NotImplementedError("Method is not implemented!")


class IOption(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def do_option(self, transmission_array, tranmission_name, result_queue):
        pass


class IOptionPlot(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def print_visual_result(self):
        pass


class OptionDoCountCloseZero(IOption, IOptionPlot):
    # Get the number of transmissions under transmission threshold
    def do_option(self, transmission_array, transmission_array_name, result_queue):
        if OPTION != Options.GET_CLOSE_ZERO_TRANSMISSION_STATISTICS:
            return
        haze_arr = option_get_haze_array_with_transmission_name(transmission_array_name)
        pq = queue.Queue()
        shape = np.shape(transmission_array)
        H = shape[0]
        W = shape[1]
        size = H * W
        count = 0
        for h in range(H):
            for w in range(W):
                if transmission_array[h][w] < TRANSMISSION_THRESHOLD:
                    # single_result = (haze_arr[h][w][0] + haze_arr[h][w][1] + haze_arr[h][w][2]) / 3
                    print("(" + str(round(haze_arr[h][w][0], 3)) + "  " + str(round(haze_arr[h][w][1], 3)) + "  " + str(
                        round(haze_arr[h][w][2], 3)) + "), t: " + str(transmission_array[h][w]))
                    count += 1
        print("Total size: " + str(size) + " Close Zero: " + str(count))

    def print_visual_result(self):
        pass


# Calculate three channels value difference and get statistical calculation for all channels
# Put result into a queue and use matplotlib to generate the historgram
class OptionGetThreeChannelValueClose(IOption, IOptionPlot):
    def do_option(self, transmission_array, transmission_array_name, result_queue):
        if OPTION != Options.GET_HISTOGRAM_WITH_CLOSE_RGB:
            return
        haze_arr = option_get_haze_array_with_transmission_name(transmission_array_name)
        _, alpha, _ = dt.trans_get_alpha_beta(transmission_array_name)
        pq = queue.PriorityQueue()
        shape = np.shape(haze_arr)
        H = shape[0]
        W = shape[1]
        expected_number = 0
        for h in range(H):
            for w in range(W):
                if abs(haze_arr[h][w][0] - haze_arr[h][w][1]) <= THRESHOLD and abs(
                        haze_arr[h][w][1] - haze_arr[h][w][2]) <= THRESHOLD and abs(
                    haze_arr[h][w][0] - haze_arr[h][w][2]) \
                        <= THRESHOLD:
                    if haze_arr[h][w][0] >= LOWER_BOUNDARY:
                        # pq.put((haze_arr[h][w][0] + haze_arr[h][w][1] + haze_arr[h][w][2]) / 3)
                        pq.put(haze_arr[h][w][0])
                        if transmission_array[h][w] < TRANSMISSION_THRESHOLD:
                            expected_number += 1
        result_queue.put((alpha, pq, expected_number, transmission_array_name))

    def print_visual_result(self):
        if OPTION != Options.GET_HISTOGRAM_WITH_CLOSE_RGB:
            return
        while not RESULT_QUEUE.empty():
            s_queue = RESULT_QUEUE.get()
            alpha_gt = s_queue[0]
            plt.xlim(LOWER_BOUNDARY, 1)
            plt.xlabel('Hazy pixel value')
            my_x_ticks = np.arange(LOWER_BOUNDARY, 1, STEP_SIZE)
            plt.xticks(my_x_ticks)
            plt.ylabel('Number of points in this region')
            bar_list = []
            while not s_queue[1].empty():
                bar_list.append(round(s_queue[1].get(), 3))
            result_array = np.asarray(bar_list)
            size = np.size(result_array)
            plt.title("gt: " + str(alpha_gt) + "|threshold: " + str(THRESHOLD) + "|TransmissionThreshold: " +
                      str(TRANSMISSION_THRESHOLD) + "|fraction: " + str(s_queue[2]) + "/" + str(size))
            plt.hist(result_array, bins=30, width=0.006, normed=0, facecolor="blue", edgecolor="black", alpha=0.7)
            _, filename = os.path.split(s_queue[3])
            fname, _ = os.path.splitext(filename)
            fname_with_ext = fname + ".png"
            plt.savefig(os.path.join("./StatisticalFigure", fname_with_ext))
            plt.close()


class OptionGetTransmissionHistogram(IOption, IOptionPlot):
    # Get histogram of transmission map
    def do_option(self, transmission_array, transmission_array_name, result_queue):
        if OPTION != Options.GET_TRANSMISSION_HISTOGRAM:
            return
        _, alpha, _ = dt.trans_get_alpha_beta(transmission_array_name)
        shape = np.shape(transmission_array)
        H = shape[0]
        W = shape[1]
        expected_number = 0
        pq = queue.PriorityQueue()
        for h in range(H):
            for w in range(W):
                pq.put(transmission_array[h][w])
                if transmission_array[h][w] < TRANSMISSION_THRESHOLD:
                    expected_number += 1
        result_queue.put((alpha, pq, expected_number, transmission_array_name))

    def print_visual_result(self):
        if OPTION != Options.GET_TRANSMISSION_HISTOGRAM:
            return
        while not RESULT_QUEUE.empty():
            s_queue = RESULT_QUEUE.get()
            alpha_gt = s_queue[0]
            plt.xlim(0, 1)
            plt.xlabel('Hazy pixel value')
            my_x_ticks = np.arange(0, 1, STEP_SIZE)
            plt.xticks(my_x_ticks)
            plt.ylabel('Number of points in this region')
            bar_list = []
            while not s_queue[1].empty():
                bar_list.append(round(s_queue[1].get(), 3))
            result_array = np.asarray(bar_list)
            size = np.size(result_array)
            plt.title("gt: " + str(alpha_gt) + "|threshold: " + str(THRESHOLD) + "|TransmissionThreshold: " +
                      str(TRANSMISSION_THRESHOLD) + "|fraction: " + str(s_queue[2]) + "/" + str(size))
            plt.hist(result_array, bins=30, width=0.005, normed=0, facecolor="blue", edgecolor="black", alpha=0.7)
            _, filename = os.path.split(s_queue[3])
            fname, _ = os.path.splitext(filename)
            fname_with_ext = fname + ".png"
            plt.savefig(os.path.join("./StatisticalFigure", fname_with_ext))
            plt.close()


class OptionDehazeUsingTransmissionMap(IOption, IOptionPlot):
    # Dehaze hazy images using transmission map
    def do_option(self, transmission_array, transmission_name, result_queue):
        if OPTION != Options.DEHAZE_WITH_TRANSMISSION_MAP:
            return
        haze_arr = option_get_haze_array_with_transmission_name(transmission_name)
        # Get alpha from name
        _, alpha, _ = dt.trans_get_alpha_beta(transmission_name)
        do.opt_write_result_to_file(do.opt_dehaze_with_alpha_transmission(alpha, transmission_array, haze_arr))

    def print_visual_result(self):
        pass


class OptionCheckDistancesWithSmallTransmission(IOption, IOptionPlot):
    # Check if the t restriction is satisfied, and check how many pixels match the three channel values are close enough
    def do_option(self, transmission_array, transmission_name, result_queue):
        if OPTION != Options.GET_PIXEL_NUMBER_CLOSE_FOR_LOW_TRANSMISSION:
            return
        haze_arr = option_get_haze_array_with_transmission_name(transmission_name)
        shape = np.shape(transmission_array)
        H = shape[0]
        W = shape[1]
        number_counter = 0
        for h in range(H):
            for w in range(W):
                if transmission_array[h][w] < TRANSMISSION_THRESHOLD:
                    if abs(haze_arr[h][w][0] - haze_arr[h][w][1]) < THRESHOLD and \
                            abs(haze_arr[h][w][1] - haze_arr[h][w][2]) < THRESHOLD and \
                            abs(haze_arr[h][w][0] - haze_arr[h][w][2]) < THRESHOLD:
                        number_counter += 1
        print(number_counter)

    def print_visual_result(self):
        pass


class OptionGetEstimateAlpha(IOption, IOptionPlot):

    class Pixel(object):
        def __init__(self, transmission, h, w):
            self.transmission = transmission
            self.h = h
            self.w = w

        def __lt__(self, other):
            return self.transmission < other.transmission

    class ChannelDistance(object):
        def __init__(self, distance, h, w):
            self.distance = distance
            self.h = h
            self.w = w

        def __lt__(self, other):
            return self.distance < self.distance

    def do_option(self, transmission_array, transmission_name, result_queue):
        if OPTION != Options.GET_ESTIMATE_ALPHA:
            return
        _, alpha, _ = dt.trans_get_alpha_beta(transmission_name)
        haze_arr = option_get_haze_array_with_transmission_name(transmission_name)
        # dark_channel_map = OptionGetEstimateAlpha.__option_get_dark_channel_map(haze_arr)
        attenuation_depth_map = OptionGetEstimateAlpha.__option_get_depth_color_attenuation(haze_arr)
        OptionGetEstimateAlpha.__estimate_alpha_with_map(attenuation_depth_map, haze_arr, alpha, result_queue)

    def print_visual_result(self):
        if OPTION != Options.GET_ESTIMATE_ALPHA:
            return
        sum_error_rate = 0
        size = RESULT_QUEUE.qsize()
        while not RESULT_QUEUE.empty():
            sum_error_rate += RESULT_QUEUE.get()
        print(" Error rate: " + str(round(sum_error_rate / size, 5)) + "%")

    @staticmethod
    def __estimate_alpha_with_map(transmission, haze, alpha, result_queue):
        pq = queue.PriorityQueue()
        shape = np.shape(transmission)
        H = shape[0]
        W = shape[1]
        point_one_number = int(np.size(transmission) * 0.001)
        maximum_intensity = 0
        for h in range(H):
            for w in range(W):
                pq.put(OptionGetEstimateAlpha.Pixel(transmission[h][w], h, w))
        pq_for_minimum_distance = queue.PriorityQueue()
        while point_one_number > 0:
            point_one_number -= 1
            pixel = pq.get()
            # maximum_intensity = max(
            #     ((haze[pixel.h][pixel.w][0] + haze[pixel.h][pixel.w][1] + haze[pixel.h][pixel.w][2]) / 3),
            #     maximum_intensity)
            distance = (haze[pixel.h][pixel.w][0] - haze[pixel.h][pixel.w][1]) ** 2 + \
                       (haze[pixel.h][pixel.w][1] - haze[pixel.h][pixel.w][2]) ** 2 + \
                       (haze[pixel.h][pixel.w][0] - haze[pixel.h][pixel.w][2]) ** 2
            pq_for_minimum_distance.put(OptionGetEstimateAlpha.ChannelDistance(distance, pixel.h, pixel.w))
        solution_pixel = pq_for_minimum_distance.get()
        # estimate_alpha = (haze[solution_pixel.h][solution_pixel.w][0] + haze[solution_pixel.h][solution_pixel.w][1] +
        #                   haze[solution_pixel.h][solution_pixel.w][2]) / 3
        estimate_alpha = max(haze[solution_pixel.h][solution_pixel.w][0],  haze[solution_pixel.h][solution_pixel.w][1], haze[solution_pixel.h][solution_pixel.w][2])
        printed_estimate_alpha = abs(estimate_alpha - float(alpha)) / float(alpha)
        print("GT: %f Estimate Alpha: %.5f Error rate: " % (float(alpha), estimate_alpha) + '{:.3%}'.format(
            printed_estimate_alpha))
        result_queue.put(printed_estimate_alpha)

    @staticmethod
    def __option_get_dark_channel_map(haze_arr):
        u8_haze_arr = haze_arr.astype("uint8")
        u64_haze_arr = haze_arr.astype("float64")
        dark = dd.DarkChannel(u64_haze_arr, 15)
        alpha = dd.AtmLight(u64_haze_arr, dark)
        te = dd.TransmissionEstimate(u64_haze_arr, alpha, 15)
        return dd.TransmissionRefine(u8_haze_arr, te)

    @staticmethod
    def __option_get_depth_color_attenuation(haze_arr):
        dR, _ = runDehazing.calDepthMap((haze_arr * 255).astype('uint8'), 15)
        guided_filter = runDehazing.GuidedFilter(haze_arr, 60, 10 ** -3)
        refineDR = guided_filter.filter(dR)
        tR = np.exp(-1.0 * refineDR)
        return tR


# task[0]: Transmission array
# task[1]: Name of the transmission map
class OptionsProducer(threading.Thread):
    def __init__(self, input_queue, task_queue):
        threading.Thread.__init__(self)
        self.queue = input_queue
        self.task_queue = task_queue

    def run(self):
        while True:
            t = self.queue.get()
            if t is None:
                self.queue.put(None)
                self.task_queue.put(None)
                break
            # TODO open transmission from .npy file
            arr = np.load(t)
            # TODO open transmission from knight file
            # arr = np.array(Image.open(t)) / 255
            self.task_queue.put((arr, t))
            # if START_CONDITION.acquire():
            #     START_CONDITION.notify_all()
            # START_CONDITION.release()
        print('Producer finish')


class OptionsConsumer(threading.Thread):
    producer_end_number = 0

    def __init__(self, task_queue, lock, producer_num):
        threading.Thread.__init__(self)
        self.task_queue = task_queue
        self.lock = lock
        self.producer_num = producer_num

    def run(self):
        # if START_CONDITION.acquire():
        #     START_CONDITION.wait()
        # START_CONDITION.release()
        while True:
            task = self.task_queue.get()
            if task is None:
                self.lock.acquire_write()
                OptionsConsumer.producer_end_number += 1
                self.lock.demote()
                if OptionsConsumer.producer_end_number > self.producer_num:
                    self.lock.release()
                    break
                self.lock.release()
                self.task_queue.put(None)
            else:
                option_operator = OptionFactory.get_option_instance(OPTION)
                option_operator.do_option(task[0], task[1], RESULT_QUEUE)
        print('Consumer finish')


# Get normalize haze array
def option_get_haze_array_with_transmission_name(name):
    _, filename = os.path.split(name)
    fname, _ = os.path.splitext(filename)
    fname_with_ext = fname + ".jpg"
    full_name = os.path.join(HAZY_DIR, fname_with_ext)
    return np.array(Image.open(full_name)) / 255


def option_input(t_dir):
    t_file_list = os.listdir(t_dir)
    q = queue.Queue()
    for filename in t_file_list:
        q.put(os.path.join(t_dir, filename))
    q.put(None)
    return q


def main():
    if os.path.exists(STATISTICAL_DIR):
        shutil.rmtree(STATISTICAL_DIR)
        os.mkdir(STATISTICAL_DIR)
    q = option_input(TRANS_DIR)
    cpu_num = multiprocessing.cpu_count()
    task_queue = queue.Queue()
    thread_list = []
    flag_lock = WRLock.RWLock()
    for producer_id in range(cpu_num):
        producer = OptionsProducer(q, task_queue)
        producer.start()
        thread_list.append(producer)

    time.sleep(0.0001)
    for consumer_id in range(cpu_num):
        consumer = OptionsConsumer(task_queue, flag_lock, cpu_num)
        consumer.start()
        thread_list.append(consumer)
    for t in thread_list:
        t.join()

    plot_instance = OptionFactory.get_matplotlib_instance(OPTION)
    if plot_instance is not None:
        plot_instance.print_visual_result()


if __name__ == '__main__':
    main()