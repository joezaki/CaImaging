import os
import xarray as xr
from natsort import natsorted
import glob
import pandas as pd
import numpy as np
import cv2
import itertools

def open_minian(dpath, fname='minian', backend='zarr', chunks=None):
    """
    Opens minian outputs.

    Parameters
    ---
    dpath: str, path to folder containing the minian outputs folder.
    fname: str, name of the minian output folder.
    backend: str, 'zarr' or 'netcdf'. 'netcdf' seems outdated.
    chunks: ??
    """
    if backend is 'netcdf':
        fname = fname + '.nc'
        mpath = os.path.join(dpath, fname)
        with xr.open_dataset(mpath) as ds:
            dims = ds.dims
        chunks = dict([(d, 'auto') for d in dims])
        ds = xr.open_dataset(os.path.join(dpath, fname), chunks=chunks)

        return ds

    elif backend is 'zarr':
        mpath = os.path.join(dpath, fname)
        dslist = [xr.open_zarr(os.path.join(mpath, d))
                  for d in os.listdir(mpath)
                  if os.path.isdir(os.path.join(mpath, d))]
        ds = xr.merge(dslist)
        if chunks is 'auto':
            chunks = dict([(d, 'auto') for d in ds.dims])

        return ds.chunk(chunks)

    else:
        raise NotImplementedError("backend {} not supported".format(backend))


def concat_avis(path, pattern='behavCam*.avi',
                fname='Merged.avi', fps=30, isColor=True):
    """
    Concatenates behavioral avi files for ezTrack.

    Parameters
    ---
    path: str, path to folder containing avis. All avis will be merged.
    pattern: str, pattern of video clips.
    fname: str, file name of final merged clip.
    fps: int, sampling rate.
    isColor: bool, flag for writing color.

    Return
    ---
    final_clip_name: str, full file name of final clip.
    """
    # Get all files.
    files = natsorted(glob.glob(os.path.join(path, pattern)))

    # Get width and height.
    cap = cv2.VideoCapture(files[0])
    size = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), \
           int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Define writer.
    fourcc = 0
    final_clip_name = os.path.join(path, fname)
    writer = cv2.VideoWriter(final_clip_name, fourcc,
                             fps, size, isColor=isColor)

    for file in files:
        print(f'Processing {file}')
        cap = cv2.VideoCapture(file)
        cap.set(1,0)                # Go to frame 0.
        cap_max = int(cap.get(7))   #7 is the index for total frames.

        # Loop through all the frames.
        for frame_num in range(cap_max):
            ret, frame = cap.read()
            if ret:
                # Convert to grayscale if specified.
                if not isColor:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                writer.write(frame)
            else:
                break

        cap.release()

    writer.release()
    print(f'Writing {final_clip_name}')

    return final_clip_name


def read_eztrack(csv_fname, cm_per_pixel=1):
    """
    Reads ezTrack outputs.

    Parameters
    ---
    csv_fname: str, path to tracking .csv from ezTrack.
    cm_per_pixel: float, centimeters per pixel.

    Return
    ---
    position: dict, with keys x, y, frame, distance.
    """
    # Open file.
    df = pd.read_csv(csv_fname[0])

    # Consolidate into dict.
    position = {'x': np.asarray(df['X']) / cm_per_pixel,    # x position
                'y': np.asarray(df['Y']) / cm_per_pixel,    # y position
                'frame': np.asarray(df['Frame']),           # Frame number
                'distance': np.asarray(df['Distance']) / cm_per_pixel} # Distance traveled since last sample

    return position


def synchronize_time_series(position, neural, behav_fps=30, neural_fps=15):
    """
    Synchronizes behavior and neural time series by interpolating behavior.

    :parameters
    ---
    position: dict, output from read_ezTrack().
    neural: (neuron, t) array, any time series output from minian (e.g., C, S).
    behav_fps: float, sampling rate of behavior video.
    neural_fps: float, sampling rate of minian data.

    :return
    ---
    position: dict, interpolated data based on neural sampling rate.

    """
    # Get number of frames in each video.
    neural_nframes = neural.shape[1]
    behav_nframes = len(position['frame'])

    # Create time vectors.
    neural_t = np.arange(0, neural_nframes/neural_fps, 1/neural_fps)
    behav_t = np.arange(0, behav_nframes/behav_fps, 1/behav_fps)

    # Interpolate.
    position['x'] = np.interp(neural_t, behav_t, position['x'])
    position['y'] = np.interp(neural_t, behav_t, position['y'])
    position['frame'] = np.interp(neural_t, behav_t, position['frame'])

    # Normalize.
    position['x'] = position['x'] - min(position['x'])
    position['y'] = position['y'] - min(position['y'])

    # Compute distance at each consecutive point.
    pos_diff = np.diff(position['x']), np.diff(position['y'])
    position['distance'] = np.hypot(pos_diff[0], pos_diff[1])

    # Compute velocity by dividing by 1/fps.
    position['velocity'] = \
        np.concatenate(([0], position['distance']*min((neural_fps, behav_fps))))

    return position


def get_transient_timestamps(neural_data, std_thresh=3):
    """
    Converts an array of continuous time series (e.g., traces or S)
    into lists of timestamps where activity exceeds some threshold.

    :parameters
    ---
    neural_data: (neuron, time) array
        Neural time series, (e.g., C or S).

    std_thresh: float
        Number of standard deviations above the mean to define threshold.

    :returns
    ---
    event_times: list of length neuron
        Each entry in the list contains the timestamps of a neuron's
        activity.

    event_mags: list of length neuron
        Event magnitudes.

    """
    # Compute thresholds for each neuron.
    stds = np.std(neural_data, axis=1)
    means = np.mean(neural_data, axis=1)
    thresh = means + std_thresh*stds

    # Get event times and magnitudes.
    bool_arr = neural_data > np.tile(thresh,[neural_data.shape[1], 1]).T

    event_times = [np.where(neuron > t)[0] for neuron, t
                   in zip(neural_data, thresh)]

    event_mags = [neuron[neuron > t] for neuron, t
                  in zip(neural_data, thresh)]

    return event_times, event_mags, bool_arr


def distinct_colors(n):
    def MidSort(lst):
        if len(lst) <= 1:
            return lst
        i = int(len(lst) / 2)
        ret = [lst.pop(i)]
        left = MidSort(lst[0:i])
        right = MidSort(lst[i:])
        interleaved = [item for items in itertools.zip_longest(left, right)
                       for item in items if item != None]
        ret.extend(interleaved)
        return ret


    # Build list of points on a line (0 to 255) to use as color 'ticks'
    max_ = 255
    segs = int(n ** (1 / 3))
    step = int(max_ / segs)
    p = [(i * step) for i in np.arange(1, segs)]
    points = [0, max_]
    points.extend(MidSort(p))

    # Not efficient!!! Iterate over higher valued 'ticks' first (the points
    #   at the front of the list) to vary all colors and not focus on one channel.
    colors = ["#%02X%02X%02X" % (points[0], points[0], points[0])]
    r = 0
    total = 1
    while total < n and r < len(points):
        r += 1
        for c0 in range(r):
            for c1 in range(r):
                for c2 in range(r):
                    if total >= n:
                        break
                    c = "#%02X%02X%02X" % (points[c0], points[c1], points[c2])
                    if c not in colors and c != '#FFFFFF':
                        colors.append(c)
                        total += 1

    return colors


def ordered_unique(sequence):
    seen = set()
    seen_add = seen.add

    return [x for x in sequence if not (x in seen or seen_add(x))]






if __name__ == '__main__':
    import matplotlib.pyplot as plt
    path = r'D:\Projects\GTime\Data\G123\2\H14_M46_S20'
    #behav_path = os.path.join(path, 'Behavior', 'Merged_tracked.csv')

    minian = open_minian(path)
    S = np.asarray(minian.S)

    get_transient_timestamps(S)
