import numpy as np

# Simulate sparse detections
sampled_points = [(0, 100), (5, 100), (10, 200), (15, 200), (20, 100), (25, 100)]
total_frames = 26

# Interpolate
frame_indices = [p[0] for p in sampled_points]
face_xs = [p[1] for p in sampled_points]

all_frames = np.arange(total_frames)
interpolated_xs = np.interp(all_frames, frame_indices, face_xs)

# Smooth with a simple moving average for "pro operator" feel
window_size = 10
smoothed = np.convolve(interpolated_xs, np.ones(window_size)/window_size, mode='valid')

# Pad the edges to match length
pad_left = window_size // 2
pad_right = window_size - pad_left - 1
smoothed = np.pad(smoothed, (pad_left, pad_right), mode='edge')

print("Interpolated:")
print(np.round(interpolated_xs))
print("Smoothed:")
print(np.round(smoothed))
