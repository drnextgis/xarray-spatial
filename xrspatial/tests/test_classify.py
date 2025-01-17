import pytest

import xarray as xr
import numpy as np

import dask.array as da

from xrspatial.utils import doesnt_have_cuda, is_cupy_backed
from xrspatial import equal_interval
from xrspatial import natural_breaks
from xrspatial import quantile
from xrspatial import reclassify

elevation = np.array([
    [1.,  2.,  3.,  4., np.nan],
    [5.,  6.,  7.,  8.,  9.],
    [10., 11., 12., 13., 14.],
    [15., 16., 17., 18., np.inf],
])

numpy_agg = xr.DataArray(elevation, attrs={'res': (10.0, 10.0)})
dask_numpy_agg = xr.DataArray(da.from_array(elevation, chunks=(3, 3)),
                              attrs={'res': (10.0, 10.0)})


def test_reclassify_cpu():
    bins = [10, 20]
    new_values = [1, 2]

    # numpy
    numpy_reclassify = reclassify(numpy_agg, bins=bins, new_values=new_values,
                                  name='numpy_reclassify')
    # ignore nans
    unique_elements = np.unique(
        numpy_reclassify.data[np.isfinite(numpy_reclassify.data)]
    )
    assert len(unique_elements) == 2

    # dask + numpy
    dask_reclassify = reclassify(dask_numpy_agg, bins=bins,
                                 new_values=new_values, name='dask_reclassify')
    assert isinstance(dask_reclassify.data, da.Array)

    dask_reclassify.data = dask_reclassify.data.compute()
    assert np.isclose(numpy_reclassify, dask_reclassify, equal_nan=True).all()


@pytest.mark.skipif(doesnt_have_cuda(), reason="CUDA Device not Available")
def test_reclassify_cpu_equals_gpu():

    import cupy

    bins = [10, 20, 30]
    new_values = [1, 2, 3]

    # vanilla numpy version
    cpu = reclassify(numpy_agg,
                     name='numpy_result',
                     bins=bins,
                     new_values=new_values)

    # cupy
    cupy_agg = xr.DataArray(cupy.asarray(elevation),
                            attrs={'res': (10.0, 10.0)})
    gpu = reclassify(cupy_agg,
                     name='cupy_result',
                     bins=bins,
                     new_values=new_values)
    assert isinstance(gpu.data, cupy.ndarray)
    assert np.isclose(cpu, gpu, equal_nan=True).all()

    # dask + cupy
    dask_cupy_agg = xr.DataArray(cupy.asarray(elevation),
                                 attrs={'res': (10.0, 10.0)})
    dask_cupy_agg.data = da.from_array(dask_cupy_agg.data, chunks=(3, 3))
    dask_gpu = reclassify(dask_cupy_agg, name='dask_cupy_result',
                          bins=bins, new_values=new_values)
    assert isinstance(dask_gpu.data, da.Array) and is_cupy_backed(dask_gpu)

    dask_gpu.data = dask_gpu.data.compute()
    assert np.isclose(cpu, dask_gpu, equal_nan=True).all()


def test_quantile_cpu():
    k = 5

    # numpy
    numpy_quantile = quantile(numpy_agg, k=k)
    unique_elements = np.unique(
        numpy_quantile.data[np.isfinite(numpy_quantile.data)]
    )
    assert isinstance(numpy_quantile.data, np.ndarray)
    assert len(unique_elements) == k

    # dask + numpy
    dask_quantile = quantile(dask_numpy_agg, k=k)
    assert isinstance(dask_quantile.data, da.Array)

    #     Note that dask's percentile algorithm is
    #     approximate, while numpy's is exact.
    #     This may cause some differences between
    #     results of vanilla numpy and
    #     dask version of the input agg.
    #     https://github.com/dask/dask/issues/3099
    #     This assertion may fail
    # dask_quantile = dask_quantile.compute()
    # assert np.isclose(numpy_quantile, dask_quantile, equal_nan=True).all()


@pytest.mark.skipif(doesnt_have_cuda(), reason="CUDA Device not Available")
def test_quantile_cpu_equals_gpu():

    import cupy

    k = 5

    # vanilla numpy version
    cpu = quantile(numpy_agg, k=k, name='numpy_result')

    # cupy
    cupy_agg = xr.DataArray(cupy.asarray(elevation),
                            attrs={'res': (10.0, 10.0)})
    gpu = quantile(cupy_agg, k=k, name='cupy_result')

    assert isinstance(gpu.data, cupy.ndarray)
    assert np.isclose(cpu, gpu, equal_nan=True).all()


def test_natural_breaks_cpu():
    k = 5

    # vanilla numpy
    numpy_natural_breaks = natural_breaks(numpy_agg, k=k)
    # shape and other attributes remain the same
    assert numpy_agg.shape == numpy_natural_breaks.shape
    assert numpy_agg.dims == numpy_natural_breaks.dims
    assert numpy_agg.attrs == numpy_natural_breaks.attrs
    for coord in numpy_agg.coords:
        assert np.all(numpy_agg[coord] == numpy_natural_breaks[coord])

    unique_elements = np.unique(
        numpy_natural_breaks.data[np.isfinite(numpy_natural_breaks.data)]
    )
    assert len(unique_elements) == k


def test_natural_breaks_cpu_deterministic():
    results = []
    elevation = np.arange(100).reshape(10, 10)
    agg = xr.DataArray(elevation, attrs={'res': (10.0, 10.0)})

    k = 5
    numIters = 3
    for i in range(numIters):
        # vanilla numpy
        numpy_natural_breaks = natural_breaks(agg, k=k)
        # shape and other attributes remain the same
        assert agg.shape == numpy_natural_breaks.shape
        assert agg.dims == numpy_natural_breaks.dims
        assert agg.attrs == numpy_natural_breaks.attrs
        for coord in agg.coords:
            assert np.all(agg[coord] == numpy_natural_breaks[coord])

        unique_elements = np.unique(
            numpy_natural_breaks.data[np.isfinite(numpy_natural_breaks.data)]
        )
        assert len(unique_elements) == k
        results.append(numpy_natural_breaks)
    # Check that the code is deterministic.
    # Multiple runs on same data should produce same results
    for i in range(numIters-1):
        assert(np.all(results[i].data == results[i+1].data))


@pytest.mark.skipif(doesnt_have_cuda(), reason="CUDA Device not Available")
def test_natural_breaks_cpu_equals_gpu():

    import cupy

    k = 5

    # vanilla numpy version
    cpu = natural_breaks(numpy_agg, k=k, name='numpy_result')

    # cupy
    cupy_agg = xr.DataArray(cupy.asarray(elevation),
                            attrs={'res': (10.0, 10.0)})
    gpu = natural_breaks(cupy_agg, k=k, name='cupy_result')

    assert isinstance(gpu.data, cupy.ndarray)
    assert np.isclose(cpu, gpu, equal_nan=True).all()


def test_equal_interval_cpu():
    k = 5
    # numpy
    numpy_ei = equal_interval(numpy_agg, k=5)

    unique_elements = np.unique(numpy_ei.data[da.isfinite(numpy_ei.data)])
    assert isinstance(numpy_ei.data, np.ndarray)
    assert len(unique_elements) == k

    # dask + numpy
    dask_ei = equal_interval(dask_numpy_agg, k=k, name='dask_reclassify')
    assert isinstance(dask_ei.data, da.Array)

    dask_ei.data = dask_ei.data.compute()
    assert np.isclose(numpy_ei, dask_ei, equal_nan=True).all()


@pytest.mark.skipif(doesnt_have_cuda(), reason="CUDA Device not Available")
def test_equal_interval_cpu_equals_gpu():

    import cupy

    k = 5

    # numpy
    cpu = equal_interval(numpy_agg, k=k)

    # cupy
    cupy_agg = xr.DataArray(cupy.asarray(elevation),
                            attrs={'res': (10.0, 10.0)})
    gpu = equal_interval(cupy_agg, k=k)
    assert isinstance(gpu.data, cupy.ndarray)

    assert np.isclose(cpu, gpu, equal_nan=True).all()
