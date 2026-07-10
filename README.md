# DeformView

## Overview
**DeformView** provides **intuitive, quantitative visualization of non-linear deformation fields** within the 3D Slicer platform.  
It enables users to interpret deformations using **dense, voxel-wise maps**, given a known transformation and corresponding image data.

DeformView provides two complementary visualization maps:
1. **Displacement Magnitude Map (mm)** – shows local tissue displacement.  
2. **Jacobian Determinant Map (%)** – shows local tissue expansion or compression.

A **real-time cursor display** allows users to hover over any voxel and directly view the corresponding **displacement or Jacobian value**.

![](exampleImages/main_UI.png)

---

## Use Cases
DeformView is useful for:
- **Understanding non-linear tissue deformation**
- **Evaluation of image registration algorithms**
- **Research in brain shift modeling**
- **Quantitative interpretation of deformation fields**
- **Comparing preoperative and intraoperative scans**

---

## Installation

### Prerequisites
Download and install **3D Slicer** from the official website: [https://www.slicer.org](https://www.slicer.org)

### Installing DeformView Extension

1. **Clone the repository**
   ```bash
   git clone https://github.com/elisedl1/SlicerDeformView
   ```

2. **Open 3D Slicer**

3. **Open the Extension Wizard**
   - Navigate to: `Module Search` → `Extension Wizard`

4. **Select the extension**
   - Click **"Select Extension"**
   - Choose the **`DeformView` folder inside the cloned repository** (i.e. `SlicerDeformView/DeformView`, the folder containing `DeformView.py`) — not the repository root

5. **Restart 3D Slicer**

6. **Open DeformView**
   - Use the modules dropdown search bar and type "DeformView"

---

## Panels and Their Use

### Input Selection
- **Moving Image**  
   Source before transformation and the transform maps it onto the fixed image.
- **Fixed Image**  
  Reference image.
- **Transformation**  
  Known transformation between the fixed and moving images.

---

### Compute Displacement Field Mapping
- Computes both:
  - **Dense displacement magnitude volume (mm)**
  - **Dense Jacobian determinant volume (%)**
- Automatically:
  - Loads the fixed volume into the scene
  - Applies **100% of the transformation**
  - Overlays the corresponding displacement volume

### Increment Slider
- Controls the **step size** of the applied transformation
- Allows visualization of **0–100% of the transformation**

![](exampleImages/increment.gif)

---

### Color Map / Loading Function
- Switch between:
  - **Displacement volume**
  - **Jacobian volume**
- Reload required to update the color map
- Includes a selection of **intuitive, perceptually meaningful color maps**
- Color maps are:
  - **Editable for the displacement volume**
  - **Fixed for the Jacobian volume** (cannot be changed)

---

## Notes
- A valid transformation must be provided to compute deformation maps.

---
## Contributing

If you'd like to contribute, please first refer to the Slicer developer documentation https://www.slicer.org/wiki/Documentation/Nightly/Developers

Please also see the CONTRIBUTING.md file for specific information.

---

## Testing

DeformView ships with an automated self-test (`DeformViewTest`) that verifies the module loads and that its two core computations run correctly. The test uses only synthetic, in-memory data — no downloads or external data files required. It checks that:

- The module loads and `DeformViewLogic` exposes its expected methods.
- **Displacement magnitude** and **Jacobian determinant** maps compute on a synthetic volume deformed by a known 2 mm translation, returning valid volumes with matching geometry, finite values, and the analytically expected results (≈2 mm displacement and ≈0% volume change everywhere).

**Run it in Slicer:** open the DeformView module and click **Reload and Test** (enable developer mode under *Edit → Application Settings → Developer* if the button is hidden).

**Run it from the Python console:**

```python
import DeformView
DeformView.DeformViewTest().runTest()
```

A successful run reports each test passing; any failure prints an assertion traceback identifying the problem.

---

## Contributors
- Elise Donszelmann-Lund (@elisedl1)
- Isabel Frolick (@isabelfrolick)
- Taj Choksi (@TC2423)
- Étienne Léger (@errollgarner)
- Raphaël Christin (@raph-rc)

---

To cite this work:

Frolick, I., Donszelmann-Lund, E., Choksi, T., Léger, É., Christin, R., Siddiqi, K., & Collins, D. L. (2026). *DeformView: Quantitative Visualization of Non-Linear Deformation Fields* (Version 1.1) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.21287630

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.19008733-blue.svg)](https://doi.org/10.5281/zenodo.19008733)
---
## License

DeformView is distributed under the MIT License. See [LICENSE.txt](LICENSE.txt) for details.

