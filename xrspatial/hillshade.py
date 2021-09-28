# std lib
from typing import Optional
from functools import partial
import math

# 3rd-party
try:
    import cupy
except ImportError:
    class cupy(object):
        ndarray = False

import dask.array as da

from numba import cuda

import numpy as np
import xarray as xr

# local modules
from xrspatial.utils import cuda_args
from xrspatial.utils import has_cuda
from xrspatial.utils import is_cupy_backed


def _run_numpy(data, azimuth=225, angle_altitude=25):
    azimuth = 360.0 - azimuth
    x, y = np.gradient(data)
    slope = np.pi/2. - np.arctan(np.sqrt(x*x + y*y))
    aspect = np.arctan2(-x, y)
    azimuthrad = azimuth*np.pi/180.
    altituderad = angle_altitude*np.pi/180.
    shaded = np.sin(altituderad) * np.sin(slope) + \
        np.cos(altituderad) * np.cos(slope) * \
        np.cos((azimuthrad - np.pi/2.) - aspect)
    result = (shaded + 1) / 2
    result[(0, -1), :] = np.nan
    result[:, (0, -1)] = np.nan
    return result


def _run_dask_numpy(data, azimuth, angle_altitude):
    _func = partial(_run_numpy, azimuth=azimuth, angle_altitude=angle_altitude)
    out = data.map_overlap(_func,
                           depth=(1, 1),
                           boundary=np.nan,
                           meta=np.array(()))
    return out


def _run_dask_cupy(data, azimuth, angle_altitude):
    msg = 'Not implemented.'
    raise NotImplementedError(msg)


@cuda.jit
def _gpu_calc_numba(
    data,
    output,
    sin_altituderad,
    cos_altituderad,
    azimuthrad
):

    i, j = cuda.grid(2)
    if i > 0 and i < data.shape[0]-1 and j > 0 and j < data.shape[1] - 1:
        x = (data[i+1, j]-data[i-1, j])/2
        y = (data[i, j+1]-data[i, j-1])/2

        len = math.sqrt(x*x + y*y)
        slope = 1.57079632679 - math.atan(len)
        aspect = (azimuthrad - 1.57079632679) - math.atan2(-x, y)

        sin_slope = math.sin(slope)
        sin_part = sin_altituderad * sin_slope

        cos_aspect = math.cos(aspect)
        cos_slope = math.cos(slope)
        cos_part = cos_altituderad * cos_slope * cos_aspect

        res = sin_part + cos_part
        output[i, j] = (res + 1) * 0.5


def _run_cupy(d_data, azimuth, angle_altitude):
    # Precompute constant values shared between all threads
    altituderad = angle_altitude * np.pi / 180.
    sin_altituderad = np.sin(altituderad)
    cos_altituderad = np.cos(altituderad)
    azimuthrad = (360.0 - azimuth) * np.pi / 180.

    # Allocate output buffer and launch kernel with appropriate dimensions
    output = cupy.empty(d_data.shape, np.float32)
    griddim, blockdim = cuda_args(d_data.shape)
    _gpu_calc_numba[griddim, blockdim](
        d_data, output, sin_altituderad, cos_altituderad, azimuthrad
    )

    # Fill borders with nans.
    output[0, :] = cupy.nan
    output[-1, :] = cupy.nan
    output[:,  0] = cupy.nan
    output[:, -1] = cupy.nan

    return output


def hillshade(agg: xr.DataArray,
              azimuth: int = 225,
              angle_altitude: int = 25,
              name: Optional[str] = 'hillshade') -> xr.DataArray:
    """
    Calculates, for all cells in the array, an illumination value of
    each cell based on illumination from a specific azimuth and
    altitude.

    Parameters
    ----------
    agg : xarray.DataArray
        2D NumPy, CuPy, NumPy-backed Dask, or Cupy-backed Dask array
        of elevation values.
    angle_altitude : int, default=25
        Altitude angle of the sun specified in degrees.
    azimuth : int, default=225
        The angle between the north vector and the perpendicular
        projection of the light source down onto the horizon
        specified in degrees.
    name : str, default='hillshade'
        Name of output DataArray.

    Returns
    -------
    hillshade_agg : xarray.DataArray, of same type as `agg`
        2D aggregate array of illumination values.

    References
    ----------
        - GeoExamples: http://geoexamples.blogspot.com/2014/03/shaded-relief-images-using-gdal-python.html # noqa

    Examples
    --------
    .. plot::
       :include-source:

        import datashader as ds
        import matplotlib.pyplot as plt
        from xrspatial import generate_terrain, hillshade

        # Create Canvas
        W = 500
        H = 300
        cvs = ds.Canvas(plot_width = W,
                        plot_height = H,
                        x_range = (-20e6, 20e6),
                        y_range = (-20e6, 20e6))

        # Generate Example Terrain
        terrain_agg = generate_terrain(canvas = cvs)

        # Edit Attributes
        terrain_agg = terrain_agg.assign_attrs(
            {
                'Description': 'Example Terrain',
                'units': 'km',
                'Max Elevation': '4000',
            }
        )
        
        terrain_agg = terrain_agg.rename({'x': 'lon', 'y': 'lat'})
        terrain_agg = terrain_agg.rename('Elevation')

        # Create Hillshade Aggregate Array
        hillshade_agg = hillshade(agg = terrain_agg, name = 'Illumination')

        # Edit Attributes
        hillshade_agg = hillshade_agg.assign_attrs({'Description': 'Example Hillshade',
                                                    'units': ''})

        # Plot Terrain
        terrain_agg.plot(cmap = 'terrain', aspect = 2, size = 4)
        plt.title("Terrain")
        plt.ylabel("latitude")
        plt.xlabel("longitude")

        # Plot Terrain
        hillshade_agg.plot(cmap = 'Greys', aspect = 2, size = 4)
        plt.title("Hillshade")
        plt.ylabel("latitude")
        plt.xlabel("longitude")

    .. sourcecode:: python

        >>> print(terrain_agg[200:203, 200:202])
        <xarray.DataArray 'Elevation' (lat: 3, lon: 2)>
        array([[1264.02249454, 1261.94748873],
               [1285.37061171, 1282.48046696],
               [1306.02305679, 1303.40657515]])
        Coordinates:
          * lon      (lon) float64 -3.96e+06 -3.88e+06
          * lat      (lat) float64 6.733e+06 6.867e+06 7e+06
        Attributes:
            res:            1
            Description:    Example Terrain
            units:          km
            Max Elevation:  4000

        >>> print(hillshade_agg[200:203, 200:202])
        <xarray.DataArray 'Illumination' (lat: 3, lon: 2)>
        array([[1264.02249454, 1261.94748873],
               [1285.37061171, 1282.48046696],
               [1306.02305679, 1303.40657515]])
        Coordinates:
          * lon      (lon) float64 -3.96e+06 -3.88e+06
          * lat      (lat) float64 6.733e+06 6.867e+06 7e+06
        Attributes:
            res:            1
            Description:    Example Hillshade
            units:
            Max Elevation:  4000
    """
    # numpy case
    if isinstance(agg.data, np.ndarray):
        out = _run_numpy(agg.data, azimuth, angle_altitude)

    # cupy/numba case
    elif has_cuda() and isinstance(agg.data, cupy.ndarray):
        out = _run_cupy(agg.data, azimuth, angle_altitude)

    # dask + cupy case
    elif has_cuda() and isinstance(agg.data, da.Array) and is_cupy_backed(agg):
        out = _run_dask_cupy(agg.data, azimuth, angle_altitude)

    # dask + numpy case
    elif isinstance(agg.data, da.Array):
        out = _run_dask_numpy(agg.data, azimuth, angle_altitude)

    else:
        raise TypeError('Unsupported Array Type: {}'.format(type(agg.data)))

    return xr.DataArray(out,
                        name=name,
                        coords=agg.coords,
                        dims=agg.dims,
                        attrs=agg.attrs)
