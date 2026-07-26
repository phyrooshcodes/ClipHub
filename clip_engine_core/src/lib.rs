use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use numpy::{PyReadonlyArray2, PyArrayMethods};
use rayon::prelude::*;

#[pyfunction]
#[pyo3(signature = (previous, current))]
fn mean_absolute_difference(
    previous: PyReadonlyArray2<u8>,
    current: PyReadonlyArray2<u8>,
) -> PyResult<f64> {
    let prev = previous.as_array();
    let curr = current.as_array();
    
    if prev.shape() != curr.shape() {
        return Err(PyValueError::new_err("previous and current must be equally shaped 2-D grayscale frames"));
    }
    
    if prev.is_empty() {
        return Err(PyValueError::new_err("frames must not be empty"));
    }

    // Since we're iterating over potentially large images, we can parallelize with rayon
    // But since ndarray's direct parallel iterators aren't always easily available without ndarray-parallel,
    // we can use standard slices if memory is contiguous, or just iterate.
    let prev_slice = prev.as_slice_memory_order().unwrap();
    let curr_slice = curr.as_slice_memory_order().unwrap();

    let sum: i64 = prev_slice.par_iter().zip(curr_slice.par_iter())
        .map(|(&p, &c)| (p as i64 - c as i64).abs())
        .sum();

    Ok(sum as f64 / prev.len() as f64)
}

#[pyfunction]
#[pyo3(signature = (positions, crop_width, source_width, smoothing_window))]
fn smooth_crop_x(
    positions: Vec<f64>,
    crop_width: i32,
    source_width: i32,
    smoothing_window: i32,
) -> PyResult<i32> {
    if crop_width < 0 || source_width < 0 || crop_width > source_width {
        return Err(PyValueError::new_err("crop_width must be between zero and source_width"));
    }
    if smoothing_window <= 0 {
        return Err(PyValueError::new_err("smoothing_window must be positive"));
    }
    if positions.iter().any(|v| !v.is_finite()) {
        return Err(PyValueError::new_err("positions must contain only finite values"));
    }

    if positions.is_empty() {
        return Ok(std::cmp::max(0, (source_width - crop_width) / 2));
    }

    let center: f64;
    let window = smoothing_window as usize;
    if positions.len() > window {
        // Convolve with 1/window
        let valid_len = positions.len() - window + 1;
        let mut convolved = Vec::with_capacity(valid_len);
        for i in 0..valid_len {
            let slice = &positions[i..i+window];
            let sum: f64 = slice.iter().sum();
            convolved.push(sum / window as f64);
        }
        convolved.sort_by(|a, b| a.partial_cmp(b).unwrap());
        center = convolved[convolved.len() / 2];
    } else {
        let sum: f64 = positions.iter().sum();
        center = sum / positions.len() as f64;
    }

    let proposed_start = (center - crop_width as f64 / 2.0).round() as i32;
    Ok(std::cmp::max(0, std::cmp::min(proposed_start, source_width - crop_width)))
}

#[pymodule]
fn clip_engine_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(mean_absolute_difference, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_crop_x, m)?)?;
    Ok(())
}
