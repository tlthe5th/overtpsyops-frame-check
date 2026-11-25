Markdown

# Mathematical & Signal-Processing Methods

## 1. Repeat-Cadence Detection
Consecutive decoded frames $I_t$ and $I_{t-1}$ are compared via mean absolute pixel difference across all BGR channels:

$$d_t = \frac{1}{3HW} \sum_{y,x,c} |I_t(y,x,c) - I_{t-1}(y,x,c)|$$

Frames with $d_t < 0.05$ (`0–255` scale) are grouped as identical duplicates produced when a low-rate or variable-frame-rate (VFR) stream is stored in a constant-frame-rate container.

## 2. Linear Cross-Fade Model
To test whether target frame $I_0$ is a linear blend of prior frame $I_{-1}$ and subsequent frame $I_{+1}$:

$$\hat{I}_0 = \alpha I_{+1} + (1 - \alpha) I_{-1}$$

The least-squares mixing weight $\alpha$ is solved directly from pixel differences:

$$\alpha = \frac{\sum (I_0 - I_{-1})(I_{+1} - I_{-1})}{\sum (I_{+1} - I_{-1})^2}$$

Goodness-of-fit is reported using Mean Absolute Error ($\text{MAE} = \text{mean}(|I_0 - \hat{I}_0|)$) and the coefficient of determination ($R^2 = 1 - \frac{\sum (I_0 - \hat{I}_0)^2}{\sum (I_0 - \bar{I}_0)^2}$).

## 3. Subpixel Phase-Correlation Registration
Before computing difference profiles, grayscale frames $G_{-1}$ and $G_0$ are aligned using Fast Fourier Transform phase correlation (`cv2.phaseCorrelate`) to estimate translational shift $(\Delta x, \Delta y)$ and warp $G_0$ by $(-\Delta x, -\Delta y)$ using bilinear interpolation. This prevents sub-pixel codec motion rounding from inflating edge residuals.

## 4. Matched-Baseline Controls & Saturation Reporting
Because camera auto-exposure and gamma curves act non-linearly across dark, midtone, a
