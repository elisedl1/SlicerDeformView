---
title: 'DeformView: Quantitative Visualization of Non-Linear Deformation Fields'
tags:
  - Medical Imaging
  - Image Registration
  - Non-linear Deformation
  - Visualization
  - 3D Slicer
authors:
  - name: Isabel Frolick
    orcid: 0009-0001-5947-6973
    equal-contrib: true
    affiliation: 1, 2
  - name: Elise Donszelmann-Lund
    orcid: 0009-0000-4634-9118
    equal-contrib: true
    affiliation: 1, 2
  - name: Taj Choksi
    orcid: 0009-0004-2793-410X
    affiliation: 3
  - name: Étienne Léger
    orcid: 0000-0001-5452-9266
    affiliation: 2
  - name: Raphaël Christin
    orcid: 0009-0007-5769-9309
    affiliation: 1, 2
  - name: Kaleem Siddiqi
    orcid: 0000-0002-7347-9716
    affiliation: 1
  - name: D. Louis Collins
    orcid: 0000-0002-8432-7021
    affiliation: 1, 2
affiliations:
 - name: McGill University, Canada
   index: 1
 - name: Montreal Neurological Institute
   index: 2
 - name: Imperial College London
   index: 3

date: 17 March 2026
bibliography: paper.bib

---

# Summary

DeformView is a novel 3D Slicer module `[@fedorov2012:2012]` designed for dense, intuitive, and quantitative visualization of non-linear deformation fields for image registration. In addition to the local, sparse displacement vectors shown by the original Transform module, DeformView introduces two interactive, voxel-wise overlays: a displacement magnitude colour map (millimeters) and a Jacobian determinant colour map (percentage) encoding local volumetric expansion and compression. We additionally introduce real-time cursor interaction enables point-wise deformation value display directly on the image volume. Additionally, an Increment Transform feature supports visualization of the progressive deformation over discrete steps. DeformView is available from our GitHub repository: https://github.com/elisedl1/DeformView, using the 3D Slicer Extension Wizard.


# Statement of need

Non-linear image registration is a key task in medical imaging, where a spatially varying deformation field maps a source image onto a fixed target image. There is an extensive body of work on non-linear registration methods, reflecting its broad applicability across imaging modalities `[@sotiras2013:2013; @ferrante2017:2017]`. While the primary output of a registration pipeline is the deformed source image – warped into alignment with the target – the underlying deformation field itself encodes quantitative information about spatial correspondences and local tissue mechanics. 

Clinicians and surgeons must interpret these resulting deformation fields, either to guide clinical decision-making or to validate that a registration algorithm is performing correctly. However, existing deformation visualization software for non-linear image registration are largely sparse and qualitative, making it difficult to interpret and localize tissue deformation `[@brock2017]`. Correct interpretation of deformed anatomy is especially difficult for inexperienced surgeons or researchers.

For example, in image-guided neurosurgery (IGNS), patient-to-image registration is used to align preoperative scans with patient anatomy during surgery. ‘Brain shift’, or non-linear shifts in brain tissue, causes a mismatch between preoperative images and the patient’s current anatomy, necessitating the use of non-linear image registration to deform preoperative images into the intraoperative image space `[@abhari2014]`. Other use cases include longitudinal studies to monitor disease progression or interventional guidance to maximize therapeutic precision. As non-linear image registration is a general problem, these use cases extend across many anatomical systems and modalities.
 
DeformView is designed to address these challenges by providing an intuitive, user-friendly 3D Slicer module that enables efficient, dense, and quantitative visualization of deformation fields in medical imaging tasks where registration is applied.  


# State of the field

The primary existing tool for deformation visualization within 3D Slicer is the Transform module, which offers three sparse representations of the deformation field: glyphs (arrows), a uniform grid, and iso-contours `[@king2015:2015]`. The glyph visualization conveys the direction of local deformation, providing a qualitative sense of how the image has deformed from its initial state.

However, all three representations are sampled at a subset of voxel locations. As such, the deformation between sampled points is entirely invisible to the user and no numerical displacement information is displayed. In addition to providing only a sparse visualization, existing tools like the Transform module only show the final state deformation; the user is unable to visualize how the deformation is incrementally applied or how specific anatomical regions are compressed or expanded to accommodate the deformation. The absence of these features limits the ability of users to interpret deformation fields.


# Software design

DeformView is implemented as a Python extension for 3D Slicer, an open-source platform available on Linux, macOS, and Windows under a BSD-style license. Most Slicer basic infrastructure is implemented in C++ and made available in Python using PythonQt and VTK Python Wrapper `[@KAPUR2016176:2016]`. The DeformView module is developed using Python following community guidelines for Slicer extension development and built from the official Slicer extension template to ensure consistency and modularity with the Slicer ecosystem `[@fedorov2012:2012]`.

A key design principle of DeformView is compatibility, both with Slicer's data model and with existing modules. All input selectors expose only the data types relevant to each function: for example, the transformation input only accepts transform types available in Slicer (linear, BSpline, grid, thin-plate spline, and composite) `[@ Slicer_Transforms]`. As well, DeformView is designed to operate in conjunction with existing Slicer tools. For example, the DeformView colour maps can be displayed alongside the sparse overlays of the existing Transform module. As shown in \autoref{fig:glyph}, this combination of the displacement magnitude colour map and glyphs provides both a quantified, spatially localized interpretation and an intuitive representation of local direction change. 
 
![Integration of DeformView displacement magnitude and existing Transform glyph visualization.\label{fig:glyph}](figures/glyph_overlay.png)


# Research Impact Statement

DeformView has generated demonstrable interest from the medical imaging research community beyond its core development team. The module was presented at NA-MIC Project Week 43 and 44 `[@KAPUR2016176:2016; @NAMIC_PW43_2025:2025; @NAMIC_PW44_2026:2026]`, the biannual workshop hosted by the National Alliance for Medical Image Computing (NA-MIC), the organization responsible for the continued development of 3D Slicer. DeformView generated discussion among Slicer developers and requests for adoption from external research groups, including researchers at Texas A&M University College of Dentistry for applications in orofacial surgery and at the Instituto de Microelectrónica Aplicada, Universidad de Las Palmas de Gran Canaria, Spain. The DeformView module has also been used in ongoing research on groupwise ultrasound-CT image registration for spinal surgery `[@elise2024:2026]`.

This work was additionally presented as a peer-reviewed poster at the Imaging Network of Ontario (ImNO) 2026 symposium in the Image-Guided Intervention and Surgery category `[@imno]`. 

# Overview of DeformView Module

DeformView accepts a deformation field (transform node) and a reference image as inputs and produces two complementary, dense quantitative visualizations overlaid directly on the image, as shown in \autoref{fig:UI_overview}.

![Overview of DeformView 3D Slicer Module. Left: user interface for the proposed module Right: dense colour map (red is higher deformation) with cursor displaying point-wise deformation magnitude on hover.\label{fig:UI_overview}](figures/UI_overview.png)

### Displacement Magnitude Map
The first map renders the Euclidean magnitude of the displacement vector (the distance each voxel has moved from this point between its original and deformed position), in millimeters. Our module converts the transform into a dense vector field sampled across the entire reference image grid, and the length of each displacement vector is stored as a scalar value at each voxel location and displayed using one of eight scientifically derived colour maps, with options for colour-blind readability `[@crameri2024:2024]`.  An interactive voxel-wise cursor displays the numerical displacement magnitude at the pointer location in real time, as shown in \autoref{fig:four_plot}. This provides a dense spatial understanding of deformation quantity and position across the full 3D volume.


### Jacobian Determinant Magnitude Map
This map renders the magnitude of the Jacobian determinant of the deformation field at every voxel as a percentage of local volumetric change, indicating whether a region has expanded or contracted under the deformation `[@chung2001:2001]`. Tissue expansion (values > 1.0) is rendered in red, tissue compression (values < 1.0) in blue, and no change (values = 1.0) in white, as shown in \autoref{fig:four_plot}. This allows researchers to identify changes to anatomical regions or areas of physiologically implausible deformation that may indicate registration errors.

### Increment Transform:
Rather than only displaying the final deformation, as existing modules do, the transformation is incrementally applied to the moving image across 10 discrete steps (0.1x, 0.2x, … 1.0x of the full transform), allowing users to observe how the deformation accumulates spatially. This is particularly useful for training and for diagnosing registration behaviour at intermediate stages.

![DeformView visualizations (top row) versus existing Transform module visualizations (bottom row). Top left: DeformView displacement magnitude colour map. Top right: DeformView Jacobian colour map. Bottom left: Transform module glyph display. Bottom right: Transform module grid display.\label{fig:four_plot}](figures/labelled_4_plot.png)


# Preliminary Results

To evaluate whether DeformView has achieved its stated goals to improve user interpretability and confidence when visualizing deformed images, a user study was conducted. Participants were randomly shown one image pair from three cases of preoperative-intraoperative T2-FLAIR brain MRI volumes and tasked with interpreting the deformation using both DeformView and the Transform module. The test data comes from the ReMIND dataset `[@juvekar2024:2024]`.

Ten participants (technical researchers without clinical expertise, mean imaging research experience: 2.9 years) completed the study. Module functionality was assessed on four attributes: helpfulness in comprehension, interpretability, intuitiveness, and user confidence. The assessment was conducted using a 5-point Likert scale (1 = None, 5 = Great) and the System Usability Scale `[@vlachogianni2022:2022]`. Participants were given unlimited time to freely explore each module before providing responses. The image pairs were randomized and a counterbalanced design was employed to control for order effects. 

As shown in \autoref{fig:user}, DeformView achieved higher mean scores than the Transform module across all four attributes (mean: 4.1/5.0 vs. 3.2/5.0; standard deviation range: 4.0–4.3 vs. 3.0–3.5). Improvements in helpfulness and intuitiveness reached statistical significance (p = 0.008 and p = 0.027, respectively). Overall, 80% of the participants preferred DeformView over Transform and 80% indicated they would choose DeformView for similar applications in the future. On the System Usability Scale, DeformView achieved an adjusted mean score of 82.8/100 (std: 14.6), which falls in the "excellent" usability range per established SUS benchmarks (above 80/100) `[@Bangor2009DeterminingWI:2009]`. 

![User study (n=10) results comparing our DeformView module and existing Transform module on four attributes
(1–5 scale; green is better). DeformView significantly outperforms existing module on helpfulness (p=0.008) and intuition
(p=0.027), with higher mean scores across all metrics.\label{fig:user}](figures/user_study.png)

With the introduction of dense, quantitative colour maps for displacement magnitude and Jacobian determinant, DeformView provides an intuitive, Slicer compatible module that allows users to confidently interpret deformation fields in medical imaging tasks.



# AI usage disclosure

Generative AI tools (Claude Sonnet 4.6) were used in the development of this software, specifically for debugging purposes. Authors have reviewed and validated all AI-assisted code output and made all core design decisions. AI was not used for writing this manuscript, or the preparation of supporting materials.  

