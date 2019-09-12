from util import open_minian
from pathlib import Path
import os
from scipy.io import savemat
import numpy as np
import glob
import h5py
import pickle

class SpatialFootprints():
    def __init__(self, mouse_path):
        # Define paths.
        self.mouse_path = mouse_path
        self.session_paths = [folder.parent for folder in Path(self.mouse_path).rglob('minian')]
        self.session_numbers = [folder.parts[-2] for folder in self.session_paths]

    def make_mat(self, save_path=None):
        if save_path is None:
            save_path = os.path.join(self.mouse_path, 'SpatialFootprints')

        cellreg_path = os.path.join(save_path, 'CellRegResults')
        os.mkdir(save_path)
        os.mkdir(cellreg_path)

        for session, session_number in zip(self.session_paths,
                                           self.session_numbers):
            #File name.
            fname = os.path.join(save_path, session_number+'.mat')

            # Load data.
            data = open_minian(session)

            # Reshape matrix.
            footprints = np.asarray(data.A)
            footprints = np.rollaxis(footprints, 2)

            # Save.
            savemat(fname,
                    {'footprints': footprints})
            print(f'Saved {fname}')


class CellRegObj:
    def __init__(self, path):
        """
        Object for handling and saving outputs from CellReg Matlab package.

        :parameter
        ---
        path: str, full path to CellRegResults folder.

        """
        self.path = path
        self.data, self.file  = self.read_cellreg_output()
        self.compile_cellreg_data()

    def read_cellreg_output(self):
        """
        Reads the .mat file.
        :return:
        """
        cellreg_file = glob.glob(os.path.join(self.path,'cellRegistered*.mat'))
        assert len(cellreg_file) > 0, "No registration .mat detected."
        assert len(cellreg_file) is 1, "Multiple cell registration files!"
        cellreg_file = cellreg_file[0]

        # Load it.
        file = h5py.File(cellreg_file)
        data = file['cell_registered_struct']

        return data, file

    def process_registration_map(self):
        # Get the cell_to_index_map. Reading the file transposes the
        # matrix. Transpose it back.
        cell_to_index_map = self.data['cell_to_index_map'].value.T

        # Matlab indexes starting from 1. Correct this.
        match_map = cell_to_index_map - 1

        return match_map.astype(int)

    def process_spatial_footprints(self):
        # Get the spatial footprints after translations.
        footprints_reference = self.data['spatial_footprints_corrected'].value[0]

        footprints = []
        for idx in footprints_reference:
            # Float 32 takes less memory.
            session_footprints = np.float32(np.transpose(self.file[idx].value, (2, 0, 1)))
            footprints.append(session_footprints)

        return footprints

    def process_centroids(self):
        # Also get centroid positions after translations.
        centroids_reference = self.data['centroid_locations_corrected'].value[0]

        centroids = []
        for idx in centroids_reference:
            session_centroids = self.file[idx].value.T
            centroids.append(session_centroids)

        return centroids

    def compile_cellreg_data(self):
        # Gets registration information. So far, this consists of the
        # cell to index map, centroids, and spatial footprints.
        match_map = self.process_registration_map()
        centroids = self.process_centroids()
        footprints = self.process_spatial_footprints()

        filename =\
            os.path.join(self.path,'CellRegResults.pkl')
        filename_footprints = \
            os.path.join(self.path,'CellRegFootprints.pkl')
        filename_centroids = \
            os.path.join(self.path, 'CellRegCentroids.pkl')

        with open(filename, 'wb') as output:
            pickle.dump(match_map, output, protocol=4)
        with open(filename_footprints, 'wb') as output:
            pickle.dump(footprints, output, protocol=4)
        with open(filename_centroids, 'wb') as output:
            pickle.dump(centroids, output, protocol=4)

if __name__ == '__main__':
    path = r'D:\Projects\GTime\Data\G132\SpatialFootprints\CellRegResults'
    CellRegObj(path)