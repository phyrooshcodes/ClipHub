#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <numeric>
#include <stdexcept>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

namespace py = pybind11;

namespace {

using GrayArray = py::array_t<std::uint8_t, py::array::c_style | py::array::forcecast>;

double mean_absolute_difference(const GrayArray& previous, const GrayArray& current) {
    const auto previous_info = previous.request();
    const auto current_info = current.request();
    if (previous_info.ndim != 2 || current_info.ndim != 2) {
        throw py::value_error("previous and current must be two-dimensional grayscale uint8 arrays");
    }
    if (previous_info.shape != current_info.shape) {
        throw py::value_error("previous and current frames must have identical shapes");
    }

    const auto count = static_cast<std::size_t>(previous_info.shape[0] * previous_info.shape[1]);
    if (count == 0) {
        throw py::value_error("frames must not be empty");
    }
    const auto* previous_pixels = static_cast<const std::uint8_t*>(previous_info.ptr);
    const auto* current_pixels = static_cast<const std::uint8_t*>(current_info.ptr);
    std::uint64_t total = 0;
    for (std::size_t i = 0; i < count; ++i) {
        total += static_cast<std::uint64_t>(std::abs(
            static_cast<int>(previous_pixels[i]) - static_cast<int>(current_pixels[i])));
    }
    return static_cast<double>(total) / static_cast<double>(count);
}

int smooth_crop_x(const std::vector<double>& positions, int crop_width, int source_width,
                  int smoothing_window) {
    if (crop_width < 0 || source_width < 0 || smoothing_window <= 0) {
        throw py::value_error("crop_width and source_width must be non-negative and smoothing_window must be positive");
    }
    if (crop_width > source_width) {
        throw py::value_error("crop_width must not exceed source_width");
    }
    if (positions.empty()) {
        return std::max(0, (source_width - crop_width) / 2);
    }
    if (!std::all_of(positions.begin(), positions.end(),
                     [](double value) { return std::isfinite(value); })) {
        throw py::value_error("positions must contain only finite values");
    }

    double center = 0.0;
    if (static_cast<int>(positions.size()) > smoothing_window) {
        std::vector<double> smoothed;
        smoothed.reserve(positions.size() - static_cast<std::size_t>(smoothing_window) + 1U);
        double sum = std::accumulate(positions.begin(), positions.begin() + smoothing_window, 0.0);
        smoothed.push_back(sum / smoothing_window);
        for (std::size_t i = static_cast<std::size_t>(smoothing_window); i < positions.size(); ++i) {
            sum += positions[i] - positions[i - static_cast<std::size_t>(smoothing_window)];
            smoothed.push_back(sum / smoothing_window);
        }
        const auto middle = smoothed.begin() + static_cast<std::ptrdiff_t>(smoothed.size() / 2U);
        std::nth_element(smoothed.begin(), middle, smoothed.end());
        center = *middle;
        if (smoothed.size() % 2U == 0U) {
            const auto lower = std::max_element(smoothed.begin(), middle);
            center = (*lower + center) / 2.0;
        }
    } else {
        center = std::accumulate(positions.begin(), positions.end(), 0.0) /
                 static_cast<double>(positions.size());
    }

    const auto raw = static_cast<int>(center - static_cast<double>(crop_width) / 2.0);
    return std::clamp(raw, 0, source_width - crop_width);
}

}  // namespace

PYBIND11_MODULE(_obscura_native, module) {
    module.doc() = "Small, dependency-free C++ kernels for Obscura Clips hot paths.";
    module.def("mean_absolute_difference", &mean_absolute_difference,
               py::arg("previous"), py::arg("current"),
               "Return mean absolute pixel difference between two grayscale uint8 frames.");
    module.def("smooth_crop_x", &smooth_crop_x, py::arg("positions"), py::arg("crop_width"),
               py::arg("source_width"), py::arg("smoothing_window"),
               "Return the crop offset using the legacy rolling-mean/median algorithm.");
}
