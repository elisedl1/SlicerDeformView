import logging
import os
from typing import Annotated, Optional
import numpy as np
import vtk
import ctk 
import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)
from slicer import vtkMRMLScalarVolumeNode
from slicer import vtkMRMLTransformNode
from slicer import vtkMRMLColorTableNode
from slicer import vtkMRMLVectorVolumeNode
import vtk.util.numpy_support
import qt
import re
import os 
import tempfile
import traceback
from vtk.util.numpy_support import vtk_to_numpy
import SimpleITK as sitk
import sitkUtils
import logging


#
# DeformView
#
def setCrosshairColor(colorRGB):
    print("In setCrosshair Colour")
    layoutManager = slicer.app.layoutManager()
    sliceViewNames = slicer.util.getSliceViewNames()  # ['Red', 'Yellow', 'Green']
    
    for viewName in sliceViewNames:
        sliceWidget = layoutManager.sliceWidget(viewName)
        dm = sliceWidget.sliceView().displayableManagerByClassName("vtkMRMLCrosshairDisplayableManager")
        if dm:
            # Update color: (R,G,B) in range 0.0-1.0
            dm.SetCrosshairColor(colorRGB)


class DeformView(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("DeformView")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Examples")]
        self.parent.dependencies = [] 
        self.parent.contributors = [" Isabel Frolick (McGill), Elise Donszelmann-Lund (McGill)"]  
        self.parent.helpText = _("""
            Dense deformation visualization module.
            See more information in <a href="https://github.com/organization/projectname#DeformView">module documentation</a>.
            """)
        self.parent.acknowledgementText = _(""" """)

#
# DeformViewParameterNode
#


@parameterNodeWrapper
class DeformViewParameterNode:
    """
    The parameters needed by module.


    referenceVolume - The pre-operative MRI volume
    transformationNode - The transformation applied (MRI to iUS)).
    displacementField - volume node to store 3D vector field
    displacementMagnitudeVolume - Output volume storing per-voxel displacement (magnitude) in mm.
    """

    referenceVolume: vtkMRMLScalarVolumeNode
    transformNode: vtkMRMLTransformNode
    displacementMagnitudeVolume: vtkMRMLScalarVolumeNode
    backgroundVolume: vtkMRMLScalarVolumeNode



#
# DeformViewWidgeto
#
    


class DeformViewWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None
        
        # NEW: Sequence attributes for incremental slider
        self.isUpdatingSequence = False


    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.

        # instructionsLabel = qt.QLabel("Welcome to DisplaceMMent, the intuitive visualization module for non-linear registration.  To get started, select your registered fixed image, moving image, and related transformation. ") 
        # instructionsLabel.setWordWrap(True)

        # === Add the instructions (collapsible, to the top)===

        
        instructionsCollapsibleButton = ctk.ctkCollapsibleButton()
        instructionsCollapsibleButton.text = "Instructions"
        instructionsCollapsibleButton.collapsed = True  # Start collapsed
        self.layout.insertWidget(1, instructionsCollapsibleButton)

        instructionsLayout = qt.QVBoxLayout(instructionsCollapsibleButton)
        
        #instructionsLabel = qt.QLabel("  To get started, select your registered fixed image, moving image, and related transformation. ") 
        #instructionsLabel.setWordWrap(True)
        instructionsLabel = qt.QLabel()
        instructionsLabel.setText("""
        <b>Instructions:</b><br><br>
        Welcome to DisplaceMMent, the intuitive visualization module for non-linear registration!<br><br>
        To get started, select your registered fixed image, moving image, and related transformation. 
        # 1. First step<br>
        # 2. Second step<br>
        # <i>Note: Important information</i>
        """)
        instructionsLabel.setWordWrap(True)
        self.layout.addWidget(instructionsLabel)
        #instructionsLayout.addWidget(instructionsLabel)
        instructionsLayout.addWidget(instructionsLabel)
        #self.layout.insertWidget(1, instructionsLabel)
        
        # === LOAD UI FILE ===

        uiWidget = slicer.util.loadUI(self.resourcePath("UI/DeformView.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        # Hide the uiWidget so it doesn't take up space
        uiWidget.hide()

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # === DEFINE UI!!!S ===
        self.UIinstance()
       

        #--- Define the connectivity ---

        # set the scene for each individual node widget
        self.ui.referenceVolume.setMRMLScene(slicer.mrmlScene)
        self.ui.referenceVolume.setToolTip(
            "Select deformed image.\n"
        )
        self.ui.transformNode.setMRMLScene(slicer.mrmlScene)
        self.ui.displacementMagnitudeVolume.setMRMLScene(slicer.mrmlScene)
        self.ui.backgroundVolume.setMRMLScene(slicer.mrmlScene)
        self.ui.backgroundVolume.setToolTip(
            "Select non-deformed image.\n"
        )
        #self.ui.ConvertTagFCSVNode.setMRMLScene(slicer.mrmlScene)

        self.ui.backgroundVolume.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.ui.backgroundVolume.addEnabled = False 
        self.ui.backgroundVolume.removeEnabled = False

        self.ui.referenceVolume.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.ui.referenceVolume.addEnabled = False
        self.ui.referenceVolume.removeEnabled = False

        # self.ui.displacementMagnitudeVolume.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        # self.ui.displacementMagnitudeVolume.addEnabled = True  # can create new output volume
        # self.ui.displacementMagnitudeVolume.removeEnabled = True

        self.ui.transformNode.nodeTypes = ["vtkMRMLTransformNode"]
        self.ui.transformNode.addEnabled = False
        self.ui.transformNode.removeEnabled = False 

        #self.ui.ConvertTagFCSVNode.nodeTypes = ["vtkMRMLTransformNode"]
        self.ui.transformNode.addEnabled = False
        self.ui.transformNode.removeEnabled = False 
        self.ui.transformNode.setToolTip(
            "Select known transformation between moving and fixed images.\n"
        )

        self.ui.loadedTransformVolume.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.ui.loadedTransformVolume.setMRMLScene(slicer.mrmlScene)


        # NEW: Add observer for sequence browser changes
        self.sequenceBrowserObserverTag = None

        self.ui.incrementalSlider.valueChanged.connect(
            lambda val: self.incrementalValueLabel.setText(f"{val}%")
        )


        # load jacobian button
        self.ui.loadJacobianButton.connect(
            "clicked(bool)", lambda: self.onLoadDisplacementVolume(flag=1)
        )
        self.ui.loadJacobianButton.setToolTip(
            "Load the determinant of the Jacobian volume.\n"
            "Used to visualize voxel-wise expansion and compression (%)."
        )
        #self.ui.loadJacobianButton.setIcon(self.createJacobianIcon())
        #self.ui.loadJacobianButton.setIconSize(qt.QSize(80, 50))
      

        self.enableVTKErrorTracking()

        self.cleanupDuplicateColorNodes("JacobianMap")
        self.removeAllNamedNode("JacobianMap")

        self.resetBuiltInColorNodes()
        self.selectColourMap()



        # mouse displayer
        self.crosshairNode = slicer.util.getNode("Crosshair")

        # self.labelMarkupNode = slicer.util.getModule("Data").mrmlScene().GetFirstNodeByName("DeformView_MouseValueLabel")
        #Need to dynamically set the labelMarkupNode, depending on which label is being loaded by loadDisplacementVolume
        #Set to None initially so it can be created dynamically?

        #On initialization, set to None 
        self.labelMarkupNode = None
        #self.getOrCreateLabelNodeForCurrentVolume() 
        #Functionality moved to self.getOrCreateLabelNodeForCurrentVolume
  
        self.crosshairObserverTag = None

        #Step 2: Has landmark in it to check if it's modified - but seems wrong
        self.ui.enableHoverDisplayCheckbox.setChecked(False)  # start disabled
        self.ui.enableHoverDisplayCheckbox.connect("toggled(bool)", self.onToggleHoverDisplay)
        self.ui.enableHoverDisplayCheckbox.setToolTip(
            "Toggle mm displacement or '%' expansion/compression values\n"
        )


        self.ui.enableDisplacementVisualizationCheckbox.setChecked(False)  # start disabled
        self.ui.enableDisplacementVisualizationCheckbox.connect("toggled(bool)", self.onToggleDisplacementVisualizationDisplay)
        self.ui.enableDisplacementVisualizationCheckbox.setToolTip(
            "Toggle overlay\n"
        )




        # connect backgroundVolume
        self.ui.backgroundVolume.setProperty("SlicerParameterName", "backgroundVolume")

        # connect US Border display checkbox
        # self.ui.enableUsBorderDisplay.toggled.connect(self.onToggleUsDisplay)
        

        
        # connect threshold slider
        self.ui.thresholdSlider.connect("valuesChanged(double,double)", self.onThresholdSliderChanged)
        
        #self.ui.windowLevelSlider.connect("valuesChanged(double,double)", self.onWindowLevelSliderChanged)
            # Connect window/level controls
        self.ui.windowLevelSlider.connect('valuesChanged(double,double)', self.onWindowLevelSliderChanged)
        self.ui.windowSpinBox.connect('valueChanged(double)', self.onWindowSpinBoxChanged)
        self.ui.levelSpinBox.connect('valueChanged(double)', self.onLevelSpinBoxChanged)
        
        # Flag to prevent recursive updates
        self.updatingWindowLevel = False

        # Store default window/level values
        self.defaultWindow = None
        self.defaultLevel = None
        
        # Connect reset button
        self.ui.resetWindowLevelButton.connect('clicked(bool)', self.onResetWindowLevel)

        
        # set spin box max and mins
        self.ui.thresholdMinSpinBox.connect("valueChanged(double)", self.onMinSpinBoxChanged)
        self.ui.thresholdMaxSpinBox.connect("valueChanged(double)", self.onMaxSpinBoxChanged)        


        # button to create fcsv from tag file
        self.ConvertTagFCSVButton = qt.QPushButton("Load Tag File")
        self.ConvertTagFCSVButton.toolTip = "Load a .tag file and create fiducial nodes"
       
        self.ui.ConvertTagFCSVButton.connect("clicked(bool)", self.onConvertTagFCSVButtonClicked)


        #Visualize the landmarks as desired (multi-slect)
        self.LandmarkSelectorComboBox = ctk.ctkCheckableComboBox()
        self.LandmarkSelectorComboBox.setToolTip("Select fiducial landmark nodes to display")
        
        # Populate list manually
        self.updateLandmarkSelectorComboBox()

        # Check which landmarks to display
        self.LandmarkSelectorComboBox.connect('checkedIndexesChanged()', self.onLandmarkSelectionChanged)

        self.LoadExpertLabelsButton = qt.QPushButton("Load Tag File")
        self.LoadExpertLabelsButton.toolTip = "Visualize landmarks"
        #self.layout.addWidget(self.LoadExpertLabelsButton)
        self.ui.LoadExpertLabelsButton.connect('clicked(bool)', self.onLoadExpertLabelsClicked)
        #self.ui.LoadExpertLabelsButton.pressed.connect(self.onLoadExpertLabelsClicked)
        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = DeformViewLogic()

        # Connections
        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
       
    
        #Add observer to the node event to track landmark files available
        self.addObserver(slicer.mrmlScene, slicer.vtkMRMLScene.NodeAddedEvent, self.onNodeChanged)
        self.addObserver(slicer.mrmlScene, slicer.vtkMRMLScene.NodeRemovedEvent, self.onNodeChanged)

        
        # Buttons
        self.ui.applyButton.setToolTip(
            "Compute a displacement magnitude (mm) volume or the determinant of the Jacobian volume.\n"
            "Displacement volume automatically loaded in"
        )
        self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)


        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()


        #self.ui.resetWindowLevelButton = qt.QPushButton("Reset Window/Level")

        # allow for user to adjust opacity
        self.ui.opacitySlider.valueChanged.connect(self.onOpacityChanged)
        self.onOpacityChanged(self.ui.opacitySlider.value)

        #track whether it's the first time for each flag type (first time with flag=0, first time with flag=1) for colour 
        self.firstTimeFlag0 = True  # First time loading a volume with flag=0
        self.firstTimeFlag1 = True  # First time loading a volume with flag=1
        self.lastLoadedFlag = None

        # incremental displacement slider
        self.ui.incrementalSlider.valueChanged.connect(self.onIncrementalChanged)
        self.ui.incrementalSlider.setMinimum(0)
        self.ui.incrementalSlider.setMaximum(100)
        self.ui.incrementalSlider.setSingleStep(10)
        self.ui.incrementalSlider.setPageStep(10)
        self.ui.incrementalSlider.setTickInterval(10)
        self.ui.incrementalSlider.setTickPosition(qt.QSlider.TicksBelow)
  
        # self.onIncrementalChanged(self.ui.incrementalSlider.value)

        #Euclidian
        self.watchActiveLabel()
        self.ui.selectedLandmarks.setReadOnly(True)
        self.ui.landmarkEuclidianDistance.setReadOnly(True)

        # Displacement button
        self.ui.loadDisplacementButton.connect(
            "clicked(bool)", lambda: self.onLoadDisplacementVolume(flag=0)
        )
        iconPath = self.resourcePath("Icons/displacement_icon.png")
        if os.path.exists(iconPath):
            self.ui.loadDisplacementButton.setIcon(qt.QIcon(iconPath))
            self.ui.loadDisplacementButton.setIconSize(qt.QSize(50, 35))
        self.ui.loadDisplacementButton.setText("  Load Displacement Magnitude\n  Color Map")
        self.ui.loadDisplacementButton.setStyleSheet("text-align: left; padding-left: 8px;")
        self.ui.loadDisplacementButton.setLayoutDirection(qt.Qt.LeftToRight)

        # Jacobian button
        iconPath = self.resourcePath("Icons/jacobian_icon.png")
        if os.path.exists(iconPath):
            self.ui.loadJacobianButton.setIcon(qt.QIcon(iconPath))
            self.ui.loadJacobianButton.setIconSize(qt.QSize(50, 35))

        self.ui.loadJacobianButton.connect(
            "clicked(bool)", lambda: self.onLoadDisplacementVolume(flag=1)
        )
        self.ui.loadJacobianButton.setText("Load Jacobian\n  Color Map")
        self.ui.loadJacobianButton.setStyleSheet("text-align: left; padding-left: 8px;")
        self.ui.loadJacobianButton.setLayoutDirection(qt.Qt.LeftToRight)

        # # connect displacement button WTIH ICON
        # self.ui.loadDisplacementButton.connect(
        #     "clicked(bool)", lambda: self.onLoadDisplacementVolume(flag=0)
        # )
        # # add icon
        # iconPath = self.resourcePath("Icons/displacement_icon.png")
        # if os.path.exists(iconPath):
        #     self.ui.loadDisplacementButton.setIcon(qt.QIcon(iconPath))
        #     self.ui.loadDisplacementButton.setIconSize(qt.QSize(60, 40))

        # self.ui.loadDisplacementButton.setText("Load Displacement Magnitude\nColor Map")


        # # connect jacobian button WTIH ICON
        # self.ui.loadJacobianButton.connect(
        #     "clicked(bool)", lambda: self.onLoadDisplacementVolume(flag=1)
        # )
        # # add icon
        # iconPath = self.resourcePath("Icons/jacobian_icon.png")
        # if os.path.exists(iconPath):
        #     self.ui.loadJacobianButton.setIcon(qt.QIcon(iconPath))
        #     self.ui.loadJacobianButton.setIconSize(qt.QSize(60, 40))

        # self.ui.loadJacobianButton.setText("Load\nJacobian\nColor Map")




    # ╔══════════════════════════════════════╗
    # ║      COLOUR MAP FUNCTIONALITY        ║
    # ╚══════════════════════════════════════╝

    def enableVTKErrorTracking(self):
        """Enable detailed VTK error tracking with stack traces"""
        
        # Create an error observer
        def errorCallback(obj, event):
            
            # print("\n" + "="*60)
            # print("VTK ERROR DETECTED:")
            # print("="*60)
            traceback.print_stack()
            # print("="*60 + "\n")
        
        # Add observer to VTK output window
        errorObserver = vtk.vtkFileOutputWindow()
        vtk.vtkOutputWindow.SetInstance(errorObserver)
        
        # You can also observe specific objects
        return errorCallback

    def resetBuiltInColorNodes(self):
        """Reset built-in color nodes to defaults while preserving existing volume color assignments"""
        
        # Save current color node assignments
        volumes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        colorNodeNames = {}
        for vol in volumes:
            dispNode = vol.GetDisplayNode()
            if dispNode:
                colorNode = dispNode.GetColorNode()
                if colorNode:
                    colorNodeNames[vol.GetID()] = colorNode.GetName()
        
        # Reset color nodes
        colorLogic = slicer.modules.colors.logic()
        colorLogic.RemoveDefaultColorNodes()
        colorLogic.AddDefaultColorNodes()
        
        # Restore color node assignments
        for volID, colorName in colorNodeNames.items():
            vol = slicer.mrmlScene.GetNodeByID(volID)
            if vol:
                dispNode = vol.GetDisplayNode()
                if dispNode:
                    colorNode = slicer.mrmlScene.GetFirstNodeByName(colorName)
                    if colorNode:
                        dispNode.SetAndObserveColorNodeID(colorNode.GetID())

    def selectColourMap(self):
        """
        Set up the color map selector with available colormaps.
        Only creates colormaps that don't already exist.
        """
        
        # Set the scene FIRST
        self.ui.colorMapSelector.setMRMLScene(slicer.mrmlScene)
       
        self.ui.colorMapSelector.nodeTypes = ["vtkMRMLProceduralColorNode", "vtkMRMLColorTableNode"]

        # Filter: only show vtkMRMLColorTableNode nodes that have "MyColorMaps" attribute
        self.ui.colorMapSelector.addAttribute("vtkMRMLProceduralColorNode", "MyColourMaps", "1")

        self.ui.colorMapSelector.addAttribute("vtkMRMLColorTableNode", "MyColourMaps", "1")
        self.ui.colorMapSelector.addAttribute("vtkMRMLProceduralColorNode", "MyColourMaps", "1")
        self.ui.colorMapSelector.addAttribute("vtkMRMLPETColorNode", "MyColourMaps", "1")
        self.ui.colorMapSelector.addAttribute("vtkMRMLColorTableNodeFile", "MyColourMaps", "1")

      
        # Create Jacobian color node
        jacobianColorNode = self.createJacobianColorNode()

        # List of colormaps to ensure exist
        nodes_to_add = [
            ("Hot-To-Cold Rainbow", "vtkMRMLColorTableNodeFileColdToHotRainbow.txt"),
            ("Diverging Blue/Red", "vtkMRMLColorTableNodeFileDivergingBlueRed.txt"),
            #("Full Rainbow", "vtkMRMLColorTableNodeFullRainbow"),
            #("Iron", "vtkMRMLColorTableNodeIron"),
            #("Grey", "vtkMRMLColorTableNodeGrey"),
            ("Plasma", "vtkMRMLColorTableNodeFilePlasma.txt"),
            #("Cividis", "vtkMRMLColorTableNodeFileCividis.txt"),
            #("Inferno", "vtkMRMLColorTableNodeFileInferno.txt"),
            ("Viridis", "vtkMRMLColorTableNodeFileViridis.txt"),
            ("Rainbow", "vtkMRMLColorTableNodeRainbow"),
            #("Ocean", "vtkMRMLColorTableNodeOcean"),
            #("InvertedGrey", "vtkMRMLColorTableNodeInvertedGrey"),
            #("fMRI", "vtkMRMLColorTableNodefMRI"),
            #("Yellow", "vtkMRMLColorTableNodeYellow"),
            #("Warm1", "vtkMRMLColorTableNodeWarm1"),
            #("Magma", "vtkMRMLColorTableNodeFileMagma.txt"),
            #("Isodose_ColorTable_Relative", "Isodose_ColorTable_Relative"),
        ]

    # Add display order attribute
        for index, (name_str, node_ID) in enumerate(nodes_to_add):
            node = self.create_colour_node(name_str, node_ID)
            if node:
                #node.SetAttribute("DisplayOrder", str(index))
                node.SetAttribute("SortOrder", f"{index:03d}")

        # else:
        proxyModel = self.ui.colorMapSelector.sortFilterProxyModel()


        #self.verify_colormap("Viridis")
          # Set default to Rainbow
        HotToColdRainbowNode = slicer.mrmlScene.GetNodeByID(f'vtkMRMLColorTableNodeFileColdToHotRainbow.txt')
        self.defaultColorNodeID = 'vtkMRMLColorTableNodeFileColdToHotRainbow.txt'
        # print(self.defaultColorNodeID)
        #ColdToHotRainbowNode = slicer.mrmlScene.GetFirstNodeByName("HotToColdRainbow")
        if HotToColdRainbowNode:
            self.ui.colorMapSelector.setCurrentNode(HotToColdRainbowNode)
            
    def verify_colormap(self, colorNodeName):
        """
        Verify a colormap has a valid lookup table
        """
        colorNode = slicer.mrmlScene.GetFirstNodeByName(colorNodeName)
        if not colorNode:
            print(f"Color node '{colorNodeName}' not found")
            return False
        
        # print(f"\n=== Verifying {colorNodeName} ===")
        # print(f"Type: {colorNode.GetClassName()}")
        # print(f"Number of colors: {colorNode.GetNumberOfColors()}")
        
        # Check if it has a lookup table
        if hasattr(colorNode, 'GetLookupTable'):
            lut = colorNode.GetLookupTable()
            if lut:
                # print(f"Lookup table: {lut.GetNumberOfTableValues()} values")
                # print(f"Range: {lut.GetRange()}")
                print("Valid lookup table")
                return True
            else:
                print("No lookup table!")
                return False
        else:
            print("No GetLookupTable method")
            return False

    def create_colour_node(self, name_str, node_ID=None, use_table=False):
        """
        Unified function to create color nodes.
        
        Args:
            name_str: Name for the color node
            type_str: Type of colormap
            use_table: If True, creates ColorTableNode instead of ProceduralColorNode
        """
        # Remove existing node
        #node = slicer.mrmlScene.GetFirstNodeByName(name_str)
        #existing_node = slicer.mrmlScene.GetFirstNodeByName(name_str)
        existing_node = slicer.mrmlScene.GetNodeByID(f'{node_ID}')
        if existing_node:
            existing_node.SetName(name_str)
            # CRITICAL FIX: Set the attribute even on existing nodes
            existing_node.SetAttribute("MyColourMaps", "1")
            #existing_node.SetName(f"{name_str}")
            #existing_node.SetName(name_str)
            #existing_node.SetSingletonTag(name_str)  # This prevents duplicates
    
           #print(f"Color node {name_str} already exists")
            return existing_node
        
        # if node:
        #     slicer.mrmlScene.RemoveNode(node)
        
        # Try built-in vtkMRMLColorTableNode types first
        try:
            node = slicer.mrmlScene.GetNodeByID(f'{node_ID}')
            #node = slicer.mrmlScene.GetNodeByID('FilePlasma.txt')
            # if name_str.endswith("_1"):
            #     name_str = name_str.replace("_1", "")
            node.SetName(name_str)
            #node.SetSingletonTag(name_str)
            #node.SetDisplayName(f"{name_str}")

            slicer.mrmlScene.AddNode(node)
            node.SetAttribute("MyColourMaps", "1")
            if node.GetName() != name_str:
                node.SetName(name_str)
            return node
        
        except AttributeError:
            print(f"Failed to make {name_str}!")
            pass  # Type doesn't exist, try matplotlib
        
        # # Matplotlib colormaps
        # matplotlib_maps = {
        #     'Viridis': 'viridis',
        #     'Plasma': 'plasma', 
        #     'Inferno': 'inferno',
        #     'Magma': 'magma',
        #     'Cividis': 'cividis',
        #     'Turbo': 'turbo',
        #     'RdBu': 'RdBu',
        #     'Spectral': 'Spectral',
        # }
        
        # if type_str in matplotlib_maps:
        #     print(f"Creating {type_str} from matplotlib")
        #     if use_table:
        #         return self.create_colour_table_from_matplotlib(name_str, matplotlib_maps[type_str])
        #     else:
        #         return self.create_colour_node_from_matplotlib(name_str, matplotlib_maps[type_str])
        
        # Access the ColdToHotRainbow color map
    #     node = slicer.util.getNode('ColdToHotRainbow')


       
        #print(f"Created built-in color table: Attmept")


     
        return node

    def cleanupDuplicateColorNodes(self, nodeName):
        """
        Remove all but the first instance of a color node
        """
        allNodes = slicer.mrmlScene.GetNodesByName(nodeName)
        allNodes.InitTraversal()
        
        nodes_to_remove = []
        first_node = None
        
        for i in range(allNodes.GetNumberOfItems()):
            node = allNodes.GetNextItemAsObject()
            if i == 0:
                first_node = node
                # print(f"Keeping {nodeName} (ID: {node.GetID()})")
            else:
                nodes_to_remove.append(node)
                # print(f"Will remove duplicate {nodeName} (ID: {node.GetID()})")
        
        # Remove duplicates
        for node in nodes_to_remove:
            slicer.mrmlScene.RemoveNode(node)
        
        return first_node
    
    def removeAllNamedNode(self, nodeName):
            
        """
        Remove all but the first instance of a color node
        """
        allNodes = slicer.mrmlScene.GetNodesByName(nodeName)
        
        # existingNode = slicer.mrmlScene.GetFirstNodeByName(nodeName)
        # if existingNode:
        #     slicer.mrmlScene.RemoveNode(existingNode)
        #     print("removed JacobianMap")

        allNodes.InitTraversal()
        
        nodes_to_remove = []
        first_node = None
        
        for i in range(allNodes.GetNumberOfItems()):
            node = allNodes.GetNextItemAsObject()
            nodes_to_remove.append(node)
            # print(f"Will remove duplicate {nodeName} (ID: {node.GetID()})")
        
        # Remove duplicates
        for node in nodes_to_remove:
            slicer.mrmlScene.RemoveNode(node)
        
        #return first_node

    def createJacobianColorNode(self):
        """
        Create Jacobian colormap - only once, reuse if exists
        """
        existingNode = slicer.mrmlScene.GetFirstNodeByName("JacobianMap")
        
        if existingNode:
            existingNode.SetAttribute("MyColourMaps", "1")
            return existingNode

        # print("Creating new JacobianMap")
        
        colorNode = slicer.vtkMRMLColorTableNode()
        colorNode.SetName("JacobianMap")
        colorNode.SetAttribute("DisplayName", "Jacobian (Compression/Expansion)")
        colorNode.SetAttribute("MyColourMaps", "1")
        colorNode.SetTypeToUser()
        colorNode.SetNumberOfColors(3)
        colorNode.SetNoName("")
        colorNode.SetSingletonTag("JacobianMap")

        
        # Set only two colors
        colorNode.SetColor(0, 0.0, 0.0, 1.0, 1.0)  # Blue for contracting, index 0
        colorNode.SetColorName(0, "Contracting")

        colorNode.SetColor(1, 1.0, 1.0, 1.0, 1.0)  # White for no change, index 1
        colorNode.SetColorName(1, "No Change")
        
        colorNode.SetColor(2, 1.0, 0.0, 0.0, 1.0)  # Red for expanding, index 2
        colorNode.SetColorName(2, "Expanding")
                
        slicer.mrmlScene.AddNode(colorNode)

        return colorNode




    # ╔══════════════════════════════════════╗
    # ║          UI                          ║
    # ╚══════════════════════════════════════╝

    def UIinstance(self):
        # === SECTION 1: IMAGES LOADING ===

        inputGroup = qt.QGroupBox("Input Images")
        inputGroup.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                margin-top: 15px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        self.layout.addWidget(inputGroup)

        inputLayout = qt.QFormLayout(inputGroup)
        inputLayout.setContentsMargins(20, 25, 20, 20)  # Increased margins
        inputLayout.setSpacing(12)  # Increased spacing between rows
        inputLayout.setVerticalSpacing(12)  # Vertical spacing between form rows
        inputLayout.setLabelAlignment(qt.Qt.AlignRight | qt.Qt.AlignVCenter)  # Right-align labels

        inputLayout.addRow("Moving Image:", self.ui.referenceVolume)
        inputLayout.addRow("Fixed Image:", self.ui.backgroundVolume)
        inputLayout.addRow("Transformation:", self.ui.transformNode)
        self.ui.referenceVolume.setToolTip(
            "The volume that is warped by the deformation field to match the fixed image."
        )
        self.ui.backgroundVolume.setToolTip(
            "The reference volume that the moving image is registered to. Does not warp."
        )
        self.ui.transformNode.setToolTip(
            "The transformation computed by registration, used to generate the displacement field."
        )
        self.ui.applyButton.setToolTip(
            "Apply the transformation to compute the displacement field and Jacobian map."
        )
        self.ui.colorMapSelector.setToolTip(
            "Choose the colour map used to display the displacement or Jacobian volume. After selecting the colour map, you must reload the volume."
        )
        self.ui.loadDisplacementButton.setToolTip(
            "Load and display the displacement magnitude map as a colour overlay."
        )
        self.ui.loadJacobianButton.setToolTip(
            "Load and display the Jacobian determinant map, showing local volume change."
        )
        self.ui.enableDisplacementVisualizationCheckbox.setToolTip(
            "Toggle the displacement field colour overlay on the slice views."
        )
        self.ui.enableHoverDisplayCheckbox.setToolTip(
            "Show displacement or Jacobian values at the cursor position when hovering."
        )
        self.ui.incrementalSlider.setToolTip(
            "Set the percentage increment used when stepping through the displacement field."
        )
        self.ui.opacitySlider.setToolTip(
            "Adjust the opacity of the displacement or Jacobian colour overlay."
        )
        self.ui.thresholdSlider.setToolTip(
            "Set the threshold range: values outside this range will not be displayed."
        )
        self.ui.windowLevelSlider.setToolTip(
            "Adjust the colour window and level for display contrast."
        )
        self.ui.resetWindowLevelButton.setToolTip(
            "Reset the window and level to their default values."
        )
        self.ui.markupTextSizeSlider.setToolTip(
            "Adjust the size of the text label shown at the cursor marker."
        )
        self.ui.markupSizeSlider.setToolTip(
            "Adjust the size of the cursor marker in the slice views."
        )

   
        # Add some space before the button
        inputLayout.addRow("", qt.QWidget())  # Empty spacer row
        inputLayout.addRow("", self.ui.applyButton)


        # === SECTION 2: PROCESSING ===

        for b in [self.ui.loadDisplacementButton, self.ui.loadJacobianButton]:
            b.setMinimumSize(180, 60)
            font = b.font
            font.setPointSize(11)
            font.setBold(True)
            b.setFont(font)

        processingGroup = qt.QGroupBox("Displacement Field Visualization")
        processingGroup.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                margin-top: 15px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        self.layout.addWidget(processingGroup)
        processingLayout = qt.QFormLayout(processingGroup)
        processingLayout.setContentsMargins(20, 25, 20, 20)
        processingLayout.setSpacing(12)
        processingLayout.setVerticalSpacing(12)
        processingLayout.setLabelAlignment(qt.Qt.AlignRight | qt.Qt.AlignVCenter)

        # Colour map row
        processingLayout.addRow("Colour Map:", self.ui.colorMapSelector)

        # Row 1: Load buttons (TOP)
        loadButtonsLayout = qt.QHBoxLayout()
        loadButtonsLayout.addStretch(1)
        loadButtonsLayout.addWidget(self.ui.loadDisplacementButton)
        loadButtonsLayout.addSpacing(14)
        loadButtonsLayout.addWidget(self.ui.loadJacobianButton)
        loadButtonsLayout.addStretch(1)
        
        # buttonWidth = max(self.ui.loadDisplacementButton.sizeHint.width(),
        #           self.ui.loadJacobianButton.sizeHint.width())
        # self.ui.loadDisplacementButton.setFixedWidth(int(buttonWidth * 0.9))
        # self.ui.loadJacobianButton.setFixedWidth(int(buttonWidth * 0.9))

        processingLayout.addRow(" ", loadButtonsLayout)

        # Row 2: Checkboxes
        checkboxLayout = qt.QHBoxLayout()
        checkboxLayout.addStretch(1)
        checkboxLayout.addWidget(self.ui.enableDisplacementVisualizationCheckbox)
        checkboxLayout.addWidget(self.ui.enableHoverDisplayCheckbox)
        checkboxLayout.addStretch(1)

        processingLayout.addRow(" ", checkboxLayout)

        # Row 3: Incremental slider
        incrementalLayout = qt.QHBoxLayout()
        incrementalLayout.addWidget(self.ui.incrementalSlider, 1)
        self.incrementalValueLabel = qt.QLabel(f"{self.ui.incrementalSlider.value}%")
        self.incrementalValueLabel.setFixedWidth(35)
        self.incrementalValueLabel.setAlignment(qt.Qt.AlignRight | qt.Qt.AlignVCenter)
        incrementalLayout.addWidget(self.incrementalValueLabel)
        processingLayout.addRow("Increment:", incrementalLayout)

        # === SECTION 4: VISUALIZATION SETTINGS ===

        vizGroup = qt.QGroupBox("Display Settings")
        vizGroup.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                margin-top: 15px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        self.layout.addWidget(vizGroup)

        vizLayout = qt.QFormLayout(vizGroup)
        vizLayout.setContentsMargins(20, 25, 20, 20)
        vizLayout.setSpacing(12)
        vizLayout.setVerticalSpacing(12)
        vizLayout.setLabelAlignment(qt.Qt.AlignRight | qt.Qt.AlignVCenter)

        # Opacity with better layout
        opacityLayout = qt.QHBoxLayout()
        opacityLayout.addWidget(self.ui.opacitySlider, 1)  # Stretch factor
        opacityLayout.addSpacing(10)
        opacityLayout.addWidget(self.ui.opacityValue)
        vizLayout.addRow("Opacity:", opacityLayout)

        # Threshold with labels
        thresLayout = qt.QVBoxLayout()
        thresLayout.setSpacing(5)

        sliderLayout = qt.QHBoxLayout()
        sliderLayout.addWidget(self.ui.thresholdSlider)
        thresLayout.addLayout(sliderLayout)

        spinBoxLayout = qt.QHBoxLayout()
        spinBoxLayout.addWidget(qt.QLabel("Min:"))
        spinBoxLayout.addWidget(self.ui.thresholdMinSpinBox)
        spinBoxLayout.addSpacing(10)
        spinBoxLayout.addWidget(qt.QLabel("Max:"))
        spinBoxLayout.addWidget(self.ui.thresholdMaxSpinBox)
        thresLayout.addLayout(spinBoxLayout)

        vizLayout.addRow("Threshold Range:", thresLayout)

        windowLayout = qt.QVBoxLayout()
        windowLayout.setSpacing(5)

        colourWindowSliderLayout = qt.QHBoxLayout()
        colourWindowSliderLayout.addWidget(self.ui.windowLevelSlider)
        windowLayout.addLayout(colourWindowSliderLayout)

        WLSpinBoxLayout = qt.QHBoxLayout()
        WLSpinBoxLayout.addWidget(qt.QLabel("W:"))
        WLSpinBoxLayout.addWidget(self.ui.windowSpinBox)
        WLSpinBoxLayout.addSpacing(10)
        WLSpinBoxLayout.addWidget(qt.QLabel("L:"))
        WLSpinBoxLayout.addWidget(self.ui.levelSpinBox)
        windowLayout.addLayout(WLSpinBoxLayout)
    
        vizLayout.addRow("Colour Window/Level", windowLayout)

        vizLayout.addRow(self.ui.resetWindowLevelButton)

        # MARKUP TEXT SIZE
        markupTextSizeLayout = qt.QVBoxLayout()
        markupTextSizeLayout.setSpacing(5)
        colourmarkupTextSizeSliderLayout = qt.QHBoxLayout()
        colourmarkupTextSizeSliderLayout.addWidget(self.ui.markupTextSizeSlider)
        markupTextSizeLayout.addLayout(colourmarkupTextSizeSliderLayout)
        vizLayout.addRow("Cursor text size:", markupTextSizeLayout)

        # MARKUP SIZE
        markupSizeLayout = qt.QVBoxLayout()
        markupSizeLayout.setSpacing(5)
        colourmarkupSizeSliderLayout = qt.QHBoxLayout()
        colourmarkupSizeSliderLayout.addWidget(self.ui.markupSizeSlider)
        markupSizeLayout.addLayout(colourmarkupSizeSliderLayout)
        vizLayout.addRow("Cursor marker size:", markupSizeLayout)

        # Add stretch at the end
        self.layout.addStretch(1)

        self.processingGroup = processingGroup
        self.vizGroup = vizGroup
    
    def createDisplacementIcon(self):
        '''
        Creates icon for displacement magnitude button
        Rainbow gradient with "mm" label and arrow
        '''
        pixmap = qt.QPixmap(120, 80)
        pixmap.fill(qt.QColor(240, 240, 240))
        
        painter = qt.QPainter(pixmap)
        painter.setRenderHint(qt.QPainter.Antialiasing)
        
        # Draw rainbow gradient bar (hot to cold: red->yellow->green->cyan->blue)
        gradient = qt.QLinearGradient(10, 30, 110, 30)
        gradient.setColorAt(0.0, qt.QColor(255, 0, 0))      # red
        gradient.setColorAt(0.25, qt.QColor(255, 255, 0))   # yellow
        gradient.setColorAt(0.5, qt.QColor(0, 255, 0))      # green
        gradient.setColorAt(0.75, qt.QColor(0, 255, 255))   # cyan
        gradient.setColorAt(1.0, qt.QColor(0, 0, 255))      # blue
        
        # Use QBrush with the gradient
        brush = qt.QBrush(gradient)
        painter.fillRect(10, 20, 100, 25, brush)
        painter.setPen(qt.QPen(qt.QColor(0, 0, 0), 2))
        painter.drawRect(10, 20, 100, 25)
        
        # Draw displacement arrow
        painter.setPen(qt.QPen(qt.QColor(0, 0, 0), 3))
        painter.drawLine(20, 55, 80, 55)  # arrow shaft
        # arrow head
        painter.drawLine(80, 55, 70, 50)
        painter.drawLine(80, 55, 70, 60)
        
        # Add "mm" text
        font = qt.QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(85, 65, "mm")
        
        painter.end()
        return qt.QIcon(pixmap)


    def createJacobianIcon(self):
        '''
        Creates icon for Jacobian button
        Blue/red split with compression/expansion arrows and "%"
        '''
        pixmap = qt.QPixmap(120, 80)
        pixmap.fill(qt.QColor(240, 240, 240))
        
        painter = qt.QPainter(pixmap)
        painter.setRenderHint(qt.QPainter.Antialiasing)
        
        # Left half: blue (compression)
        painter.fillRect(10, 20, 50, 35, qt.QColor(0, 100, 255))
        
        # Right half: red (expansion)
        painter.fillRect(60, 20, 50, 35, qt.QColor(255, 50, 50))
        
        # Border around both
        painter.setPen(qt.QPen(qt.QColor(0, 0, 0), 2))
        painter.drawRect(10, 20, 100, 35)
        painter.drawLine(60, 20, 60, 55)  # middle divider
        
        # Compression arrows (pointing inward) - left side
        painter.setPen(qt.QPen(qt.QColor(255, 255, 255), 3))
        painter.drawLine(15, 37, 25, 37)
        painter.drawLine(25, 37, 20, 32)
        painter.drawLine(25, 37, 20, 42)
        
        painter.drawLine(50, 37, 40, 37)
        painter.drawLine(40, 37, 45, 32)
        painter.drawLine(40, 37, 45, 42)
        
        # Expansion arrows (pointing outward) - right side
        painter.drawLine(65, 37, 75, 37)
        painter.drawLine(65, 37, 70, 32)
        painter.drawLine(65, 37, 70, 42)
        
        painter.drawLine(105, 37, 95, 37)
        painter.drawLine(105, 37, 100, 32)
        painter.drawLine(105, 37, 100, 42)
        
        # Add "%" text
        font = qt.QFont()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(qt.QColor(0, 0, 0))
        painter.drawText(50, 72, "%")
        
        painter.end()
        return qt.QIcon(pixmap)


    def updateButtonStyles(self):
        palette = qt.QPalette()
        isDarkMode = palette.window().color().lightness() < 128
        
        if isDarkMode:
            activeStyle = """
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.15);
                    border: 2px solid rgba(255, 255, 255, 0.6);
                    border-radius: 4px;
                    font-weight: bold;
                }
            """
            inactiveStyle = """
                QPushButton {
                    background-color: transparent;
                    border: 2px solid rgba(255, 255, 255, 0.2);
                    border-radius: 4px;
                    font-weight: normal;
                    color: rgba(255, 255, 255, 0.5);
                }
            """
        else:
            activeStyle = """
                QPushButton {
                    background-color: rgba(0, 0, 0, 0.08);
                    border: 2px solid rgba(0, 0, 0, 0.5);
                    border-radius: 4px;
                    font-weight: bold;
                }
            """
            inactiveStyle = """
                QPushButton {
                    background-color: transparent;
                    border: 2px solid rgba(0, 0, 0, 0.2);
                    border-radius: 4px;
                    font-weight: normal;
                    color: rgba(0, 0, 0, 0.45);
                }
            """
        
        if self.currentVisualizationFlag == 0:
            self.ui.loadDisplacementButton.setStyleSheet(activeStyle)
            self.ui.loadJacobianButton.setStyleSheet(inactiveStyle)
        else:
            self.ui.loadDisplacementButton.setStyleSheet(inactiveStyle)
            self.ui.loadJacobianButton.setStyleSheet(activeStyle)

    # def updateButtonStyles(self):
    #     '''
    #     Updates button appearance based on which visualization is active
    #     '''
    #     # Detect if we're in dark mode by checking the palette
    #     palette = qt.QPalette()
    #     isDarkMode = palette.window().color().lightness() < 128
        
    #     if isDarkMode:
    #         # Dark mode: lighten the active button
    #         activeStyle = """
    #             QPushButton {
    #                 background-color: rgba(255, 255, 255, 0.15);
    #                 border: 2px solid rgba(255, 255, 255, 0.3);
    #             }
    #         """
    #     else:
    #         # Light mode: darken the active button
    #         activeStyle = """
    #             QPushButton {
    #                 background-color: rgba(0, 0, 0, 0.08);
    #                 border: 2px solid rgba(0, 0, 0, 0.2);
    #             }
    #         """
        
    #     # Style for inactive button (same for both modes)
    #     inactiveStyle = """
    #         QPushButton {
    #             background-color: transparent;
    #             border: 2px solid transparent;
    #         }
    #     """
        
    #     if self.currentVisualizationFlag == 0:
    #         self.ui.loadDisplacementButton.setStyleSheet(activeStyle)
    #         self.ui.loadJacobianButton.setStyleSheet(inactiveStyle)
    #     else:
    #         self.ui.loadDisplacementButton.setStyleSheet(inactiveStyle)
    #         self.ui.loadJacobianButton.setStyleSheet(activeStyle)

        





    # ╔══════════════════════════════════════╗
    # ║          CALLERS:                    ║
    # ╚══════════════════════════════════════╝

    def onOpacityChanged(self, value) -> None:
        normalizedValue = value/100
        slicer.util.setSliceViewerLayers(foregroundOpacity=normalizedValue)
        self.ui.opacityValue.setText(f"{value:.0f}%")

    def onNodeChanged(self, caller, event) -> None:
        self.updateLandmarkSelectorComboBox()


    def onIncrementalChanged(self, value: int) -> None:
        """
        Called when incremental slider changes.
        Scales the transform displacement AND the displacement magnitude values.
        Only works for B-spline transforms that support SetDisplacementScale.
        """
        if self.isUpdatingSequence:
            return
        
        if not self._parameterNode or not self._parameterNode.transformNode:
            slicer.util.warningDisplay(
                "No transform is currently loaded.\n\n"
                "Please compute the displacement field first by clicking 'Compute Mapping'."
            )
            # Reset slider to 100%
            self.isUpdatingSequence = True
            self.ui.incrementalSlider.setValue(100)
            self.ui.incrementalSlider.setEnabled(False)
            self.isUpdatingSequence = False
            return
        
        # Convert slider value (0-100) to scale (0.0-1.0)
        scale = value / 100.0
        if scale == 0:
            scale = 0.0001
        
        # Get the transform
        transformNode = self._parameterNode.transformNode
        bsplineTransform = transformNode.GetTransformFromParent()
        
        if not bsplineTransform:
            slicer.util.warningDisplay(
                "Could not access the transform.\n\n"
                "Please ensure a valid transform has been computed."
            )
            # Reset slider and disable
            self.isUpdatingSequence = True
            self.ui.incrementalSlider.setValue(100)
            self.ui.incrementalSlider.setEnabled(False)
            self.isUpdatingSequence = False
            return
        
        # Check if it has SetDisplacementScale method
        if not hasattr(bsplineTransform, 'SetDisplacementScale'):
            transformType = bsplineTransform.GetClassName()
            
            slicer.util.warningDisplay(
                f"Incremental Scaling Not Supported\n\n"
                f"The current transform type ({transformType}) does not support incremental scaling.\n\n"
                f"Incremental scaling is only available for B-spline transforms.\n\n"
                f"The slider has been disabled."
            )
            
            # Disable the slider and reset to 100%
            self.isUpdatingSequence = True
            self.ui.incrementalSlider.setValue(100)
            self.ui.incrementalSlider.setEnabled(False)
            self.ui.incrementalSlider.setToolTip(
                f"Incremental scaling is not supported for {transformType} transforms.\n"
                "Only B-spline transforms support this feature."
            )
            self.isUpdatingSequence = False
            
            logging.warning(f"Incremental scaling not supported for transform type: {transformType}")
            return
        
        # Apply the scale to the transform (updates spatial positions)
        bsplineTransform.SetDisplacementScale(scale)
        transformNode.Modified()

        # Also scale the displacement magnitude values
        if hasattr(self, 'displacementMagnitudeVolume') and self.displacementMagnitudeVolume:
            self.scaleDisplacementMagnitudeValues(scale)
        
        # Also scale Jacobian if it's loaded
        if hasattr(self, 'jacobianVolume') and self.jacobianVolume:
            self.scaleJacobianValues(scale)

        if self.ui.enableHoverDisplayCheckbox.isChecked():
            self.ensureHoverDisplayActive()
        
        logging.info(f"Set transform displacement scale to {scale:.1%}")


    def onThresholdSliderChanged(self, minValue, maxValue):

        volumeNode = self.ui.loadedTransformVolume.currentNode()
        if not volumeNode:
            logging.warning("No displacement magnitude volume available for thresholding.")
            return
        
        # dynamically set min and max value
        displayNode = volumeNode.GetDisplayNode()


    def onColourWindowSliderChanged(self, minValue, maxValue):

        volumeNode = self.ui.loadedTransformVolume.currentNode()
        if not volumeNode:
            logging.warning("No displacement magnitude volume available for thresholding.")
            return
        
        # dynamically set min and max value
        displayNode = volumeNode.GetDisplayNode()

        displayNode.AutoWindowLevelOff()
        displayNode.SetThreshold(minValue, maxValue)
        displayNode.SetApplyThreshold(True)
        displayNode.Modified()
        logging.info(f"Colour window applied: min = {minValue}, max = {maxValue}")

        self.ui.colourWindowMinSpinBox.blockSignals(True)
        self.ui.colourWindowMaxSpinBox.blockSignals(True)
        self.ui.colourWindowMinSpinBox.setValue(minValue)
        self.ui.colourWindowMaxSpinBox.setValue(maxValue)
        self.ui.colourWindowMinSpinBox.blockSignals(False)
        self.ui.colourWindowMaxSpinBox.blockSignals(False)


    def onThresholdSliderChanged(self, minValue, maxValue):

        volumeNode = self.ui.loadedTransformVolume.currentNode()
        if not volumeNode:
            logging.warning("No displacement magnitude volume available for thresholding.")
            return
        
        # dynamically set min and max value
        displayNode = volumeNode.GetDisplayNode()

        displayNode.AutoWindowLevelOff()
        displayNode.SetThreshold(minValue, maxValue)
        displayNode.SetApplyThreshold(True)
        displayNode.Modified()
        logging.info(f"Threshold applied: min = {minValue}, max = {maxValue}")

        self.ui.thresholdMinSpinBox.blockSignals(True)
        self.ui.thresholdMaxSpinBox.blockSignals(True)
        self.ui.thresholdMinSpinBox.setValue(minValue)
        self.ui.thresholdMaxSpinBox.setValue(maxValue)
        self.ui.thresholdMinSpinBox.blockSignals(False)
        self.ui.thresholdMaxSpinBox.blockSignals(False)


    def onMinSpinBoxChanged(self, value):
        currentMax = self.ui.thresholdMaxSpinBox.value
        self.ui.thresholdSlider.setValues(value, currentMax)


    def onMaxSpinBoxChanged(self, value):
        currentMin = self.ui.thresholdMinSpinBox.value
        self.ui.thresholdSlider.setValues(currentMin, value)

    def onResetWindowLevel(self, volumeNode):
        '''
        Reset window/level to default values
        '''
        if self.defaultWindow is None or self.defaultLevel is None:
            # No defaults stored, try to reinitialize
            selectedVolume = self.ui.loadedTransformVolume.currentNode()
            if selectedVolume:
                self.initializeWindowLevelControls(selectedVolume)
            return
        
        displayNode = volumeNode.GetDisplayNode()

        colorNode = displayNode.GetColorNode()
        
        if colorNode and "JacobianMap" in colorNode.GetName():
            window = self.defaultWindow_Jacobian
            level = self.defaultLevel_Jacobian

        else:
            window = self.defaultWindow_DisplacementMag
            level = self.defaultLevel_DisplacementMag

        # Use stored defaults

        # Block signals to prevent multiple updates
        self.updatingWindowLevel = True
        
        # # Update all controls
        # self.ui.windowSpinBox.value = window
        # self.ui.levelSpinBox.value = level
        
        # minVal = level - window / 2.0
        # maxVal = level + window / 2.0
        # self.ui.windowLevelSlider.minimumValue = minVal
        # self.ui.windowLevelSlider.maximumValue = maxVal
        
        # Update display node
        self.updateVolumeWindowLevel(window, level)
        
        self.updatingWindowLevel = False
        
        print(f"Reset to default: window={window}, level={level}")



    def onWindowLevelSliderChanged(self, minVal, maxVal):
        '''
        Called when the double slider values change
        Updates window/level based on slider min/max
        '''
        if self.updatingWindowLevel:
            return
        
        self.updatingWindowLevel = True
        
        # Calculate window and level from slider min/max
        window = maxVal - minVal
        level = (maxVal + minVal) / 2.0
        
        # Update spin boxes
        self.ui.windowSpinBox.value = window
        self.ui.levelSpinBox.value = level
        
        # Update display node
        self.updateVolumeWindowLevel(window, level)
        
        self.updatingWindowLevel = False

        
    def onWindowSpinBoxChanged(self, window):
        '''
        Called when window spinbox changes
        Updates level spinbox and slider
        '''
        if self.updatingWindowLevel:
            return
        
        self.updatingWindowLevel = True
        
        # Get current level
        level = self.ui.levelSpinBox.value
        
        # Calculate min/max for slider
        minVal = level - window / 2.0
        maxVal = level + window / 2.0
        
        # Update slider
        self.ui.windowLevelSlider.minimumValue = minVal
        self.ui.windowLevelSlider.maximumValue = maxVal
        
        # Update display node
        self.updateVolumeWindowLevel(window, level)
        
        self.updatingWindowLevel = False


    def onLevelSpinBoxChanged(self, level):
        '''
        Called when level spinbox changes
        Updates window spinbox and slider
        '''
        if self.updatingWindowLevel:
            return
        
        self.updatingWindowLevel = True
        
        # Get current window
        window = self.ui.windowSpinBox.value
        
        # Calculate min/max for slider
        minVal = level - window / 2.0
        maxVal = level + window / 2.0
        
        # Update slider
        self.ui.windowLevelSlider.minimumValue = minVal
        self.ui.windowLevelSlider.maximumValue = maxVal
        
        # Update display node
        self.updateVolumeWindowLevel(window, level)
        
        self.updatingWindowLevel = False


    def onToggleHoverDisplay(self, enabled: bool) -> None:
        # print("on Toggle Hover Display")
        

        self.labelMarkupNode = self.getOrCreateLabelNodeForCurrentVolume()
        disp = self.labelMarkupNode.GetDisplayNode()

        # set it to be CrossDot2D
        if disp:
            # Set default node type
            disp.SetGlyphType(3)  # if you want to change go look at markups -> display -> advanced -> glyphtype and choose number in list
            disp.SetGlyphScale(8) 

        if enabled:
            # print("enabled")
            
            # make mouse cursor invisible
            for sliceName in slicer.app.layoutManager().sliceViewNames():
                sliceWidget = slicer.app.layoutManager().sliceWidget(sliceName)
                sliceView = sliceWidget.sliceView()
                sliceView.setViewCursor(qt.Qt.BlankCursor)

            # FORCE all relevant visibilities ON
            self.labelMarkupNode.SetDisplayVisibility(True)       # main visibility toggle
            disp.SetVisibility(True)                              # fallback
            disp.SetVisibility2D(True)
            disp.SetVisibility3D(False)                           # i want 2D only
            disp.SetPointLabelsVisibility(True)                   # show text
            disp.SetTextScale(4.5)                                # initial label size

            # connect marksup size toggle
            self.ui.markupSizeSlider.setMinimum(50)     
            self.ui.markupSizeSlider.setMaximum(200)   
            self.ui.markupSizeSlider.setValue(int(disp.GetGlyphScale() * 10))  
            self.ui.markupSizeSlider.setSingleStep(1)
            self.ui.markupSizeSlider.valueChanged.connect(self.onMarkupNodeSizeChanged)

            # setup slider to control text size
            self.ui.markupTextSizeSlider.setMinimum(10)  # corresponds to 1.0
            self.ui.markupTextSizeSlider.setMaximum(100) # corresponds to 10.0
            self.ui.markupTextSizeSlider.setValue(int(disp.GetTextScale() * 10))  # match current label size
            self.ui.markupTextSizeSlider.setSingleStep(1)
            self.ui.markupTextSizeSlider.valueChanged.connect(self.onMarkupTextChanged)

            if self.crosshairObserverTag is None:
                # print('self.crosshairObserver is None')
                self.crosshairObserverTag = self.crosshairNode.AddObserver(
                    slicer.vtkMRMLCrosshairNode.CursorPositionModifiedEvent,
                    self.onMouseMoved
            )

            # if self.crosshairObserverTag is None:
            #     self.crosshairObserverTag = self.crosshairNode.AddObserver(
            #         slicer.vtkMRMLCrosshairNode.CursorPositionModifiedEvent,
            #         self.onMouseMoved
            #     )

            

        else:
            # FORCE everything off
            self.labelMarkupNode.SetDisplayVisibility(False)
            disp.SetVisibility(False)
            disp.SetVisibility2D(False)
            disp.SetVisibility3D(False)
            disp.SetPointLabelsVisibility(False)

            if self.crosshairObserverTag is not None:
                self.crosshairNode.RemoveObserver(self.crosshairObserverTag)
                self.crosshairObserverTag = None

            # restore cursor to default
            for sliceName in slicer.app.layoutManager().sliceViewNames():
                sliceWidget = slicer.app.layoutManager().sliceWidget(sliceName)
                sliceView = sliceWidget.sliceView()
                sliceView.setViewCursor(qt.Qt.ArrowCursor)
    

    def onMarkupNodeSizeChanged(self, value):
        """Adjust the glyph size of the labelMarkupNode."""
        if hasattr(self, "labelMarkupNode") and self.labelMarkupNode:
            disp = self.labelMarkupNode.GetDisplayNode()
            if disp:
                disp.SetGlyphScale(value / 10.0)


    def onMarkupTextChanged(self, value):
        # Adjust the size of the markup labels based on slider value
        if hasattr(self, "labelMarkupNode") and self.labelMarkupNode:
            disp = self.labelMarkupNode.GetDisplayNode()
            if disp:
                # Scale slider value down by 10 to allow float sizes like 3.5
                disp.SetTextScale(value / 10.0)



    def onToggleDisplacementVisualizationDisplay(self, enabled: bool) -> None:
        # print("on Displacement Visualization Toggle")

        self.volumeNode = self.ui.loadedTransformVolume.currentNode()
        
        if not self.volumeNode:
            return
        
        displayNode = self.volumeNode.GetDisplayNode()

        if enabled:
            # print("enabled")
            
            # Show in slice views by setting foreground opacity
            normalizedValue = self.ui.opacitySlider.value / 100
            
            for sliceName in slicer.app.layoutManager().sliceViewNames():
                sliceComposite = slicer.app.layoutManager().sliceWidget(sliceName).mrmlSliceCompositeNode()
                sliceComposite.SetForegroundVolumeID(self.volumeNode.GetID())
                sliceComposite.SetForegroundOpacity(normalizedValue)
            
            # Optional: also enable 3D visibility if needed
            displayNode.SetVisibility3D(False)  # Keep 3D off if you only want 2D

        else:
            # print("disabled")
            
            # Hide from slice views by setting foreground to None or opacity to 0
            for sliceName in slicer.app.layoutManager().sliceViewNames():
                sliceComposite = slicer.app.layoutManager().sliceWidget(sliceName).mrmlSliceCompositeNode()
                # Option 1: Remove as foreground entirely
                sliceComposite.SetForegroundVolumeID(None)
                # Option 2: Or just set opacity to 0
                # sliceComposite.SetForegroundOpacity(0.0)



    def onMouseMoved(self, observer, eventid):
        # if markup node doesn't exist do nothing
        #print("self.ui.loadedTransformVolume.currentNode()", self.ui.loadedTransformVolume.currentNode())
        #print("elf.ui.loadedTransformVolume.currentNode().GetDisplayNode())", self.ui.loadedTransformVolume.currentNode().GetDisplayNode())
        
        if not self.ui.loadedTransformVolume.currentNode() or not self.ui.loadedTransformVolume.currentNode().GetDisplayNode():
            #print("no volume")
            return
        
        # Check if labelMarkupNode exists and has a display node
        if not hasattr(self, 'labelMarkupNode') or not self.labelMarkupNode:
            print("no markup node")
            return
        
        displayNode = self.labelMarkupNode.GetDisplayNode()
        if not displayNode:
            print("no display node")
            return
        
        if not displayNode.GetVisibility2D():
            return

        ras = [0.0, 0.0, 0.0] 
        self.crosshairNode.GetCursorPositionRAS(ras)
    
        # move label to current RAS position
        self.labelMarkupNode.SetNthControlPointPosition(0, ras)

        #print("in mouse moved")

        # sample displacement volume at that RAS location
        #displacementVolume = self.ui.existingDisplacementVolumeSelector.currentNode()
        displacementVolume = self.ui.loadedTransformVolume.currentNode()

        if not displacementVolume:
            self.labelMarkupNode.SetNthControlPointLabel(0, "No volume")
            return
        

        # convert RAS to IJK
        rasToIjk = vtk.vtkMatrix4x4()
        displacementVolume.GetRASToIJKMatrix(rasToIjk)
        ijk = [0.0, 0.0, 0.0, 1.0]
        ras_hom = list(ras) + [1.0]
        rasToIjk.MultiplyPoint(ras_hom, ijk)
        ijk = [int(round(i)) for i in ijk[:3]]

        dims = displacementVolume.GetImageData().GetDimensions()
        if any(i < 0 or i >= d for i, d in zip(ijk, dims)):
            # self.labelMarkupNode.SetNthControlPointLabel(0, "Out of bounds")
            self.labelMarkupNode.SetNthControlPointLabel(0, "")
            return

        value = displacementVolume.GetImageData().GetScalarComponentAsDouble(*ijk, 0)

        # get flag
        # flag = self.getBrainShiftFlag(displacementVolume)
        flag = getattr(self, "currentVisualizationFlag", 0)


        # apply flag logic
        if flag == 0:
            # displacement magnitude (mm)
            label = f"{value:.2f} mm"
        elif flag == 1:
            # display percent
            label = f"{value:+.1f}%"
        else:
            label = f"{value:.2f}"

        self.labelMarkupNode.SetNthControlPointLabel(0, label)


    
    
    
    
    # ╔══════════════════════════════════════╗
    # ║       INCREMENTAL TRANSFORM          ║
    # ╚══════════════════════════════════════╝


    def scaleDisplacementMagnitudeValues(self, scale: float):
        """
        Scale the actual displacement magnitude values in the volume.
        This updates the colormap overlay to show scaled displacement values.
        """
        if not hasattr(self, '_fullDisplacementArray') or self._fullDisplacementArray is None:
            logging.warning("Original displacement array not stored")
            return
        
        volumeNode = self.displacementMagnitudeVolume
        imageData = volumeNode.GetImageData()
        
        if not imageData:
            return
        
        # Scale the displacement values from the original full-scale array
        scaledArray = self._fullDisplacementArray * scale
        
        # Get the VTK array and update it
        vtk_array = imageData.GetPointData().GetScalars()
        
        # Use numpy to update efficiently
        vtk_array_np = vtk_to_numpy(vtk_array)
        vtk_array_np[:] = scaledArray
        
        # Mark as modified to trigger visualization update
        vtk_array.Modified()
        imageData.Modified()
        volumeNode.Modified()
        
        # Update display node
        displayNode = volumeNode.GetDisplayNode()
        if displayNode:
            displayNode.Modified()
        
        logging.debug(f"Scaled displacement values by {scale:.1%}")


    def scaleJacobianValues(self, scale: float):
        """
        Scale the Jacobian values based on displacement scale.
        Jacobian shows compression/expansion, which also scales with displacement.
        """
        if not hasattr(self, '_fullJacobianArray') or self._fullJacobianArray is None:
            logging.warning("Original Jacobian array not stored")
            return
        
        volumeNode = self.jacobianVolume
        imageData = volumeNode.GetImageData()
        
        if not imageData:
            return
        
        # For Jacobian: J_scaled = 1 + scale * (J_full - 1)
        # This ensures at scale=0, J=1 (no deformation)
        # At scale=1, J=J_full (full deformation)
        scaledArray = 1.0 + scale * (self._fullJacobianArray - 1.0)
        
        # Get the VTK array and update it
        vtk_array = imageData.GetPointData().GetScalars()
        vtk_array_np = vtk_to_numpy(vtk_array)
        vtk_array_np[:] = scaledArray
        
        # Mark as modified
        vtk_array.Modified()
        imageData.Modified()
        volumeNode.Modified()
        
        # Update display node
        displayNode = volumeNode.GetDisplayNode()
        if displayNode:
            displayNode.Modified()
        
        logging.debug(f"Scaled Jacobian values by {scale:.1%}")


    def createIncrementalSequence(self):
        """
        Create a sequence node containing 10 incrementally transformed volumes
        (10%, 20%, ..., 100% of the full transformation).
        """
        if not self._parameterNode.backgroundVolume or not self._parameterNode.transformNode:
            logging.warning("Missing background volume or transform for sequence creation.")
            return
        
        logging.info("Creating incremental transformation sequence...")
        
        # Clean up existing sequence if present
        if self.sequenceNode:
            slicer.mrmlScene.RemoveNode(self.sequenceNode)
            self.sequenceNode = None
        if self.sequenceBrowserNode:
            # Remove observer before deleting
            if self.sequenceBrowserObserverTag:
                self.sequenceBrowserNode.RemoveObserver(self.sequenceBrowserObserverTag)
                self.sequenceBrowserObserverTag = None
            slicer.mrmlScene.RemoveNode(self.sequenceBrowserNode)
            self.sequenceBrowserNode = None
        
        # Create new sequence node
        self.sequenceNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSequenceNode",
            f"{self._parameterNode.backgroundVolume.GetName()}_IncrementalSequence"
        )
        
        # Create sequence browser node
        self.sequenceBrowserNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSequenceBrowserNode",
            "IncrementalTransformBrowser"
        )
        
        # IMPORTANT: Add synchronized sequence BEFORE generating volumes
        self.sequenceBrowserNode.AddSynchronizedSequenceNode(self.sequenceNode)
        
        # Generate 10 incrementally transformed volumes
        for i in range(1, 11):
            scale = i * 0.1  # 0.1, 0.2, ..., 1.0
            percentage = int(scale * 100)
            
            logging.info(f"Generating {percentage}% transformed volume...")
            
            # Create transformed volume at this scale
            transformedVolume = self.logic.createIncrementalTransform(
                backgroundVolume=self._parameterNode.backgroundVolume,
                transformNode=self._parameterNode.transformNode,
                scale=scale,
                name=f"{self._parameterNode.backgroundVolume.GetName()}_{percentage}pct"
            )
            
            # Add to sequence with percentage as index value
            timeValue = str(percentage)
            self.sequenceNode.SetDataNodeAtValue(transformedVolume, timeValue)
            
            # Remove the individual node from scene (sequence keeps a copy)
            slicer.mrmlScene.RemoveNode(transformedVolume)
        
        # Set up sequence browser properties
        self.sequenceBrowserNode.SetPlaybackRateFps(10)
        self.sequenceBrowserNode.SetPlaybackActive(False)
        self.sequenceBrowserNode.SetRecording(self.sequenceNode, False)
        
        # CRITICAL: Set initial item to 100% (index 9) BEFORE getting proxy node
        self.sequenceBrowserNode.SetSelectedItemNumber(9)
        
        # CRITICAL: Get the proxy node - this is what gets displayed
        proxyNode = self.sequenceBrowserNode.GetProxyNode(self.sequenceNode)
        
        if not proxyNode:
            logging.error("Failed to get proxy node from sequence browser!")
            return
        
        # Store proxy node for later use
        self.sequenceProxyNode = proxyNode
        
        logging.info(f"Proxy node created: {proxyNode.GetName()}")
        
        # Set the proxy node as background in all slice views
        layoutManager = slicer.app.layoutManager()
        for sliceViewName in layoutManager.sliceViewNames():
            compositeNode = layoutManager.sliceWidget(sliceViewName).mrmlSliceCompositeNode()
            compositeNode.SetBackgroundVolumeID(proxyNode.GetID())
            logging.info(f"Set {sliceViewName} background to proxy node")
        
        # Add observer to sync slider when sequence changes
        self.sequenceBrowserObserverTag = self.sequenceBrowserNode.AddObserver(
            vtk.vtkCommand.ModifiedEvent,
            self.onSequenceBrowserIndexChanged
        )
        
        logging.info(f"Created sequence with {self.sequenceNode.GetNumberOfDataNodes()} volumes")


    def onSequenceBrowserIndexChanged(self, caller, event):
        """
        Called when sequence browser index changes (e.g., from toolbar controls).
        Updates the slider to match.
        """


        if self.isUpdatingSequence:
            return
        
        self.isUpdatingSequence = True
        
        try:
            itemIndex = self.sequenceBrowserNode.GetSelectedItemNumber()
            # Map index (0-9) to slider value (10-100)
            sliderValue = (itemIndex + 1) * 10
            
            self.ui.incrementalSlider.blockSignals(True)
            self.ui.incrementalSlider.setValue(sliderValue)
            self.ui.incrementalSlider.blockSignals(False)
            
            logging.info(f"Sequence changed to item {itemIndex} ({sliderValue}%)")
        finally:
            self.isUpdatingSequence = False

       


    # ╔══════════════════════════════════════╗
    # ║     Slicer Module Functions          ║
    # ╚══════════════════════════════════════╝

        
    def setupWithResourcePath(self):
        """Alternative approach using module resource path"""
        print("setupWithResourcePath")
        # Get icon path relative to module resources
        iconPath = os.path.join(
            os.path.dirname(self.resourcePath("")),
            "Resources",
            "Icons",
            "jacobian_icon.png"
        )
        
        
        if os.path.exists(iconPath):
            icon = qt.QIcon(iconPath)
            self.ui.loadDisplacementButton.setIcon(icon)
            self.ui.loadDisplacementButton.setIconSize(qt.QSize(80, 50))
            
            # Make the button larger to accommodate icon
            self.ui.loadDisplacementButton.setMinimumSize(180, 60)
        else:
            logging.warning(f"Icon file not found at: {iconPath}")


    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        self.removeObservers()
        for interactor, tag in getattr(self, "sliceObservers", []):
            interactor.RemoveObserver(tag)
            self.sliceObservers = []
        for dn, tag in getattr(self, "_activeWatchers", []):
            try:
                dn.RemoveObserver(tag)
            except:
                pass
        self._activeWatchers = []

        if hasattr(self, 'crosshairNode') and self.crosshairNode and hasattr(self, 'crosshairObserverTag'):
            if self.crosshairObserverTag is not None:
                self.crosshairNode.RemoveObserver(self.crosshairObserverTag)
                self.crosshairObserverTag = None

        crosshairNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLCrosshairNode')
        if crosshairNode:
            crosshairNode.RemoveAllObservers()
            # print("Removed all crosshair observers")

        if self.sequenceBrowserObserverTag and self.sequenceBrowserNode:
            self.sequenceBrowserNode.RemoveObserver(self.sequenceBrowserObserverTag)
            self.sequenceBrowserObserverTag = None


    def onSceneUpdated(self, caller, event):
        self.updateLandmarkSelectorComboBox()
    
    
    def enter(self) -> None:
        """Called each time the user opens this module."""
        # Make sure parameter node exists and observed

        
        self.initializeParameterNode()

        # re-acquire or create mouse label node
        #This breaks!!:
        #self.labelMarkupNode = self.getOrCreateLabelNodeForCurrentVolume()
        # sync checkbox to match visibility
        self.updateHoverCheckboxFromNode()

        # sync checkbox to match visibility 
        self.updateVisualizationCheckboxFromNode()


    def exit(self) -> None:
        """Called each time the user opens a different module."""
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()


    def initializeParameterNode(self) -> None:
        """Ensure parameter node exists and observed."""
        self.setParameterNode(self.logic.getParameterNode())
        
      
        # Reset the slice viewers to have no foreground initially on entering and reloading module - much cleaner - NO LONGER DOING THIS
        layoutManager = slicer.app.layoutManager()
        # for sliceViewName in layoutManager.sliceViewNames():
        #     compositeNode = layoutManager.sliceWidget(sliceViewName).mrmlSliceCompositeNode()
        #     compositeNode.SetForegroundVolumeID(None)
    
        backgroundVolumeID = self._parameterNode.backgroundVolume.GetID() if self._parameterNode.backgroundVolume else None
        
        if backgroundVolumeID and self._parameterNode.backgroundVolume.GetDisplayNode():
            displayNode = self._parameterNode.backgroundVolume.GetDisplayNode()
            displayNode.SetAndObserveColorNodeID("vtkMRMLColorTableNodeGrey")
            displayNode.AutoWindowLevelOn()

        referenceVolumeID = self._parameterNode.referenceVolume.GetID() if self._parameterNode.referenceVolume else None
        
        if referenceVolumeID and self._parameterNode.referenceVolume.GetDisplayNode():
            displayNode = self._parameterNode.referenceVolume.GetDisplayNode()
            displayNode.SetAndObserveColorNodeID("vtkMRMLColorTableNodeGrey")
            displayNode.AutoWindowLevelOn()

    def setParameterNode(self, inputParameterNode: Optional[DeformViewParameterNode]) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
        self._parameterNode = inputParameterNode
        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)

            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
            self._checkCanApply() 



    def _checkCanApply(self, caller=None, event=None) -> None:
        
        # make sure there's a reference MRI and transformation
        if (
            self._parameterNode
            and self._parameterNode.referenceVolume
            and self._parameterNode.transformNode
            and self._parameterNode.backgroundVolume
        ):
            self.ui.applyButton.toolTip = _("Compute voxel-wise displacement magnitude")
            self.ui.applyButton.enabled = True
        else:
            # self.ui.applyButton.toolTip = _("Select reference volume and transform")
            self.ui.applyButton.enabled = False





    # ╔══════════════════════════════════════╗
    # ║     CORE BUTTON FUNCTIONALITIES      ║
    # ╚══════════════════════════════════════╝


    def onApplyButton(self) -> None:
        """
        Run processing when user clicks 'Compute Mapping' button.
        """
        
        with slicer.util.tryWithErrorDisplay(_("Failed to compute voxel-wise displacement."), waitCursor=True):
            
            logging.info(f"Reference Volume: {self._parameterNode.referenceVolume}")
            logging.info(f"Background Volume: {self._parameterNode.backgroundVolume}")
            logging.info(f"Transform Node: {self._parameterNode.transformNode}")

            hoverWasEnabled = self.ui.enableHoverDisplayCheckbox.isChecked()
            
            #  NEW: Reset background volume to have no transform
            if self._parameterNode.backgroundVolume:
                self._parameterNode.backgroundVolume.SetAndObserveTransformNodeID(None)
                logging.info("Reset background volume transform to identity")
            
            # Create displacement field (for visualization)
            displacementVolume = self.logic.computeDisplacementMagnitude(
                referenceVolume=self._parameterNode.referenceVolume,
                transformNode=self._parameterNode.transformNode,
                defaultColourMap=self.defaultColorNodeID,
                scale=1.0
            )
            
            # Create Jacobian volume
            jacobianVolume = self.logic.computeJacobianMagnitude(
                referenceVolume=self._parameterNode.referenceVolume,
                transformNode=self._parameterNode.transformNode,
                defaultColourMap=self.defaultColorNodeID
            )
            
            # Store original arrays for scaling
            imageData = displacementVolume.GetImageData()
            scalars = imageData.GetPointData().GetScalars()
            self._fullDisplacementArray = vtk_to_numpy(scalars).copy()
            
            jacImageData = jacobianVolume.GetImageData()
            jacScalars = jacImageData.GetPointData().GetScalars()
            self._fullJacobianArray = vtk_to_numpy(jacScalars).copy()
            
            logging.info(f"Stored original arrays - Displacement range: [{self._fullDisplacementArray.min():.2f}, {self._fullDisplacementArray.max():.2f}]")
            
            # Apply transform to BOTH volumes so they update together spatially
            transformNode = self._parameterNode.transformNode
            
            # UPDATED: Apply transform to background volume (now starting from identity)
            self._parameterNode.backgroundVolume.SetAndObserveTransformNodeID(transformNode.GetID())
            
            # Apply transform to displacement magnitude volume
            displacementVolume.SetAndObserveTransformNodeID(transformNode.GetID())
            
            # NEW: Reset transform scale to 100% (important!)
            bsplineTransform = transformNode.GetTransformFromParent()
            if bsplineTransform and hasattr(bsplineTransform, 'SetDisplacementScale'):
                bsplineTransform.SetDisplacementScale(1.0)
                logging.info("Reset transform scale to 100%")
            
            # Setup displacement volume display
            dispDisplay = displacementVolume.GetDisplayNode()
            if not dispDisplay:
                displacementVolume.CreateDefaultDisplayNodes()
                dispDisplay = displacementVolume.GetDisplayNode()
            
            if dispDisplay:
                dispDisplay.AutoWindowLevelOn()
                dispDisplay.SetScalarVisibility(True)
            
            # Set default selections
            if hasattr(self.ui, "loadedTransformVolume") and displacementVolume:
                self.ui.loadedTransformVolume.setEnabled(True)
                self.ui.loadedTransformVolume.setCurrentNode(displacementVolume)
            
            # Set default color
            colorNode = self.ui.colorMapSelector.currentNode()
            if colorNode is None:
                colorNode = slicer.util.getFirstNodeByClassByName('vtkMRMLColorTableNode', 'fMRI')
            
            self.ui.colorMapSelector.setEnabled(True)
            self.ui.colorMapSelector.setCurrentNode(colorNode)
            
            # Set background volume in slice views
            slicer.util.setSliceViewerLayers(
                background=self._parameterNode.backgroundVolume,
                foreground=displacementVolume,
                foregroundOpacity=self.ui.opacitySlider.value / 100
            )
            
            # Load displacement visualization
            self.ui.loadedTransformVolume.setCurrentNode(displacementVolume)
            self.onLoadDisplacementVolume(flag=0)
            
            # UPDATED: Reset incremental slider to 100%
            if hasattr(self.ui, 'incrementalSlider'):
                self.isUpdatingSequence = True
                self.ui.incrementalSlider.setValue(100)
                self.ui.incrementalSlider.setEnabled(True)
                self.isUpdatingSequence = False
                logging.info("Reset incremental slider to 100%")
            
            # Store volumes for reference
            self.displacementMagnitudeVolume = displacementVolume
            self.jacobianVolume = jacobianVolume

            if hoverWasEnabled:
                # Small delay to ensure everything is set up
                qt.QTimer.singleShot(100, lambda: self.ensureHoverDisplayActive())
            
            logging.info("Transform applied to both background and displacement volumes")
            
    



    def onLoadDisplacementVolume(self, flag:int) -> None:

        '''
        Runs when user selects the Load Volume button
        
        '''


        self.currentVisualizationFlag = flag

        self.updateButtonStyles()

        # --- AUTO-SELECT THE VOLUME FROM SCENE ---
        selectedVolume = None
            
        if flag == 0:
            # Load displacement magnitude volume
            suffix = "_displacementMagnitude"
        else:
            # Load jacobian magnitude volume
            suffix = "_jacobianMagnitude"
        
        # Find the volume by suffix
        scene = slicer.mrmlScene
        for i in range(scene.GetNumberOfNodesByClass("vtkMRMLScalarVolumeNode")):
            node = scene.GetNthNodeByClass(i, "vtkMRMLScalarVolumeNode")
            if node.GetName() and suffix in node.GetName():
                selectedVolume = node
                break
        
        # Sync with UI
        if selectedVolume:
            self.ui.loadedTransformVolume.setCurrentNode(selectedVolume)
        

        #  nothing found? show error and return
        if not selectedVolume or not selectedVolume.GetDisplayNode():
            slicer.util.errorDisplay(
                "No displacement/Jacobian volume found in scene."
            )
            return


        if not selectedVolume or not selectedVolume.GetDisplayNode():
            slicer.util.errorDisplay("Please select a volume before loading.")
            return
        

        # reset incremental slider to 100% when loading visualization
        if hasattr(self.ui, 'incrementalSlider') and self.ui.incrementalSlider.isEnabled():
            self.isUpdatingSequence = True
            self.ui.incrementalSlider.setValue(100)
            self.isUpdatingSequence = False
            
            # Reset the transform scale to 1.0
            if self._parameterNode and self._parameterNode.transformNode:
                transformNode = self._parameterNode.transformNode
                bsplineTransform = transformNode.GetTransformFromParent()
                if bsplineTransform and hasattr(bsplineTransform, 'SetDisplacementScale'):
                    bsplineTransform.SetDisplacementScale(1.0)
                    transformNode.Modified()
                    logging.info("Reset transform displacement scale to 100%")

        # restore full arrays when switching between visualizations
        if flag == 0 and hasattr(self, '_fullDisplacementArray') and self._fullDisplacementArray is not None:
            # Restore full displacement array
            imageData = selectedVolume.GetImageData()
            if imageData:
                scalars = imageData.GetPointData().GetScalars()
                numpy_scalars = vtk_to_numpy(scalars)
                numpy_scalars[:] = self._fullDisplacementArray
                scalars.Modified()
                imageData.Modified()
                selectedVolume.Modified()
                logging.info("Restored full displacement magnitude array")
            
        elif flag == 1 and hasattr(self, '_fullJacobianArray') and self._fullJacobianArray is not None:
            # Restore full Jacobian array
            imageData = selectedVolume.GetImageData()
            if imageData:
                scalars = imageData.GetPointData().GetScalars()
                numpy_scalars = vtk_to_numpy(scalars)
                numpy_scalars[:] = self._fullJacobianArray
                scalars.Modified()
                imageData.Modified()
                selectedVolume.Modified()
                logging.info("Restored full Jacobian array")


        usVolume = self.ui.referenceVolume.currentNode()
    
        backgroundVolume = self._parameterNode.backgroundVolume
        
        state = self.ui.enableUsBorderDisplay.checkState()


        #DYNAMICLALY SET THE LABEL MARKUP
        self.labelMarkupNode = self.getOrCreateLabelNodeForCurrentVolume()


        
        #self.onLoadExpertLabelsClicked()

        #self.onToggleDisplacementVisualizationDisplay(True)
        
        persistentDisplayNode = selectedVolume.GetDisplayNode()

        internalDisplayNode = slicer.mrmlScene.AddNewNodeByClass(persistentDisplayNode.GetClassName())

        #internalDisplayNode.Copy(persistentDisplayNode)
        internalDisplayNode = persistentDisplayNode
        selectedVolume.AddAndObserveDisplayNodeID(internalDisplayNode.GetID())

        numDisplayNodes = selectedVolume.GetNumberOfDisplayNodes() 
        
        currentColorNode = internalDisplayNode.GetColorNode()

        self.initializeWindowLevelControls(selectedVolume)

        if self.lastLoadedFlag is None or self.lastLoadedFlag != flag:
            # print(f"Flag changed from {self.lastLoadedFlag} to {flag} - auto-setting color map")
            self.windowLevelFlagUpdate(flag, selectedVolume) #Updtae the colour and level if the flag has changed

            if flag == 0:
                colorNode = slicer.util.getNode(self.defaultColorNodeID)
                self.ui.colorMapSelector.setEnabled(True)
                self.ui.windowLevelSlider.setEnabled(True)
                #self.windowLevelFlagUpdate(flag, internalDisplayNode) #Updtae the colour and level if the flag has changed
                self.ui.windowSpinBox.setEnabled(True)
                self.ui.levelSpinBox.setEnabled(True)
                self.ui.resetWindowLevelButton.setEnabled(True)

            else:
                colorNode = slicer.util.getNode("JacobianMap")
                colorNode.SetNoName("")  # Empty string, or
                self.ui.colorMapSelector.setEnabled(False)               

                self.ui.windowLevelSlider.setEnabled(False)
                self.ui.windowSpinBox.setEnabled(False)
                self.ui.levelSpinBox.setEnabled(False)
                self.ui.resetWindowLevelButton.setEnabled(False)

                
            self.lastLoadedFlag = flag  # Update the last flag
        else:
            # Not first time for this flag type - use current selection
            # print(f"Already loaded this type before - using current selection")
            colorNode = self.ui.colorMapSelector.currentNode()
            colorNode.SetNoName("")  # Empty string, or
            #call windowLevelFlagUpdate even when the flag hasn't changed but the user changed the color map
            self.windowLevelFlagUpdate(flag, selectedVolume)

    
        if colorNode:
            self.ui.colorMapSelector.setCurrentNode(colorNode)

            internalDisplayNode.SetAndObserveColorNodeID(colorNode.GetID())
            internalDisplayNode.Modified()

          
        normalizedValue = self.ui.opacitySlider.value / 100
        internalDisplayNode.SetOpacity(normalizedValue)
        
        #slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(persistentDisplayNode)

        # Do NOT set it as foreground of another volume to avoid cropping
        for sliceName in slicer.app.layoutManager().sliceViewNames():
            sliceComposite = slicer.app.layoutManager().sliceWidget(sliceName).mrmlSliceCompositeNode()
            sliceComposite.SetBackgroundVolumeID(backgroundVolume.GetID())  # your US/reference
            sliceComposite.SetForegroundVolumeID(selectedVolume.GetID())    # displacement field
            sliceComposite.SetForegroundOpacity(normalizedValue)

        self.ui.enableDisplacementVisualizationCheckbox.setChecked(True)
        
        self.ui.enableHoverDisplayCheckbox.setChecked(True)

        
        # change legend to be color name instead of value if jacobian
        # Remove any existing color legend display nodes for this display node
        displayNode = selectedVolume.GetDisplayNode()
        if displayNode:
            # First, remove all existing legend nodes for this display
            colorLegendNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLColorLegendDisplayNode")
            nodes_to_remove = []
            for i in range(colorLegendNodes.GetNumberOfItems()):
                legendNode = colorLegendNodes.GetItemAsObject(i)
                if legendNode.GetNodeReferenceID("primaryDisplay") == displayNode.GetID():
                    nodes_to_remove.append(legendNode)
            
            for node in nodes_to_remove:
                slicer.mrmlScene.RemoveNode(node)
            
            # Now create a fresh legend node
            slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(displayNode)
            
            
            # for i in range(colorLegendNodes.GetNumberOfItems()):
            #     legendNode = colorLegendNodes.GetItemAsObject(i)
            #     if legendNode.GetNodeReferenceID("primaryDisplay") == displayNode.GetID():
            #         # Clear all settings first
            #         legendNode.SetVisibility(False)
            #         legendNode.SetTitleText(" ")

            colorLegendNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLColorLegendDisplayNode")
            for i in range(colorLegendNodes.GetNumberOfItems()):
                legendNode = colorLegendNodes.GetItemAsObject(i)
                if legendNode.GetNodeReferenceID("primaryDisplay") == displayNode.GetID():
                    # Clear all settings first
                    legendNode.SetVisibility(False)
                    legendNode.SetTitleText(" ")

                    if flag == 0:  # displacement
                        # Reset jacobian-specific settings
                        legendNode.SetNumberOfLabels(0)  # Reset to default (auto)
                        legendNode.SetMaxNumberOfColors(256)  # Reset to full range
                        legendNode.SetUseColorNamesForLabels(False)  # Show numeric values
                        legendNode.SetMaxNumberOfColors(256)  # Reset to full range
                        legendNode.SetNumberOfLabels(5)  # Show 5 labels with numeric values
                        
                        # Set displacement settings
                        legendNode.SetSize(0.15, 0.5)
                        legendNode.SetPosition(0.95, 0.25)
                        legendNode.SetVisibility(True)
    
           
                    elif flag == 1:  # jacobian
                        # Reset displacement settings and set jacobian-specific ones
                        colorNode = displayNode.GetColorNode()
                        if colorNode:
                            colorNode.Modified()  # Force update
                        
                        legendNode.SetUseColorNamesForLabels(True)
                        legendNode.SetNumberOfLabels(3)
                        legendNode.SetMaxNumberOfColors(3)
                        
                        #legendNode.SetTitleText("Jacobian Determinant")
                        legendNode.SetTitleText("")

                        legendNode.SetSize(0.2, 0.5)
                        legendNode.SetPosition(0.95, 0.25) #Normalized coordinates of position - first is (right, left) second param is up, down
                        
                        titleProperty = legendNode.GetTitleTextProperty()
                        titleProperty.SetFontSize(12)
                        
                        legendNode.SetVisibility(True)


                    else:  # other type of node
                        legendNode.SetUseColorNamesForLabels(False)
                        legendNode.SetVisibility(False)
        


        # set max and min of threshold slider
        imageData = selectedVolume.GetImageData()
        #print("Image Data", imageData)
        if imageData:
            minScalar, maxScalar = imageData.GetScalarRange()
            defaultMinValue = minScalar + 0.009 * (maxScalar - minScalar) #Default minimum set to 2%
            #defaultMinValue = 0.009
            self.scalarRange = (float(minScalar), float(maxScalar))  # store exact range
            #print(f"min: {minScalar}, max: {maxScalar}")
            #print(defaultMinValue)
            
            self.ui.thresholdSlider.setRange(minScalar, maxScalar)
            

            self.ui.thresholdMinSpinBox.setSpecialValueText("") #clear 'Minimum Threshold'
            self.ui.thresholdMaxSpinBox.setSpecialValueText("")  
            self.ui.thresholdMinSpinBox.setRange(minScalar, maxScalar)
            self.ui.thresholdMaxSpinBox.setRange(minScalar, maxScalar)
            self.ui.thresholdMinSpinBox.setDecimals(6) 
            self.ui.thresholdMaxSpinBox.setDecimals(6)

            step = (maxScalar - minScalar) / 1000   # 0.1% of range 
        
            self.ui.thresholdSlider.singleStep = step
            self.ui.thresholdMinSpinBox.singleStep = step
            self.ui.thresholdMaxSpinBox.singleStep = step



            #Always set the values after setting the mins/ maxs to avoid caching issues 
            self.ui.thresholdSlider.setValues(minScalar, maxScalar)
            self.ui.thresholdMinSpinBox.setValue(defaultMinValue)  
            self.ui.thresholdMaxSpinBox.setValue(maxScalar)



        if hasattr(self, "lastLoadedVolumeID") and hasattr(self, "lastLoadedFlag"):
            if self.lastLoadedVolumeID == selectedVolume.GetID() and self.lastLoadedFlag == flag:
                # print("Volume already fully loaded — skipping display setup")
                return

        # Store currently loaded volume ID and flag
        self.lastLoadedVolumeID = selectedVolume.GetID()
        self.lastLoadedFlag = flag




    
    # ╔══════════════════════════════════════╗
    # ║          MOUSE CURSOR                ║
    # ╚══════════════════════════════════════╝
    
    def ensureHoverDisplayActive(self):
        """
        Ensure the hover display is properly active.
        Call this after transform modifications that might disrupt the observer.
        """
        if not self.ui.enableHoverDisplayCheckbox.isChecked():
            return
        
        # Check if observer exists
        if self.crosshairObserverTag is None:
            logging.info("Hover display enabled but observer missing - re-establishing")
            
            # Ensure label node exists
            if not hasattr(self, 'labelMarkupNode') or not self.labelMarkupNode:
                self.labelMarkupNode = self.getOrCreateLabelNodeForCurrentVolume()
            
            # Re-add observer
            if self.crosshairNode:
                self.crosshairObserverTag = self.crosshairNode.AddObserver(
                    slicer.vtkMRMLCrosshairNode.CursorPositionModifiedEvent,
                    self.onMouseMoved
                )
                logging.info("Re-established crosshair observer")
        
        # Verify display node visibility
        if hasattr(self, 'labelMarkupNode') and self.labelMarkupNode:
            disp = self.labelMarkupNode.GetDisplayNode()
            if disp and not disp.GetVisibility2D():
                disp.SetVisibility2D(True)
                disp.SetPointLabelsVisibility(True)
                logging.info("Re-enabled label node visibility")


    #Creates the label node for the cursor
    def getOrCreateLabelNodeForCurrentVolume(self):
        """Get or create a label node specific to the currently loaded volume"""
        
        volumeNode = self.ui.loadedTransformVolume.currentNode()
        
        # Get or create the single shared label node
        labelNodeName = "DeformView_MouseValueLabel"
        node = slicer.mrmlScene.GetFirstNodeByName(labelNodeName)
        # node.GetDisplayNode().SetGlyphScale(8)
        #print("label exists")
        #if it doesn't exist or 
        if not node: #or not node.GetDisplayNode().GetVisibility2D():
            node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsFiducialNode",
                labelNodeName
            )
            node.AddControlPoint(0, 0, 0)
            node.SetLocked(True)
            node.SetMarkupLabelFormat("{label}")
            node.GetDisplayNode().SetVisibility2D(False)
            node.GetDisplayNode().SetVisibility3D(False)
            node.SetNthControlPointLabel(0, "")
            node.GetDisplayNode().SetColor([0.0, 0.0, 0.0])
            node.GetDisplayNode().SetSelectedColor([0.0, 0.0, 0.0])
            node.GetDisplayNode().GetTextProperty().SetColor(0.0, 0.0, 0.0)
        
        # Store reference on volume
        # volumeNode.SetAttribute("DeformView_LabelNodeID", node.GetID())
        
        return node
        



    
    # ╔══════════════════════════════════════╗
    # ║         INITIALIZE STATE             ║
    # ╚══════════════════════════════════════╝

    def initializeWindowLevelControls(self, volumeNode):
        '''
        Initialize window/level controls based on the volume's display node
        and appropriate threshold/visualization range
        '''
        # print("CALLED INITIALIZE WINDOW LEVEL CONTROLS")
        if not volumeNode:
            return
            
        displayNode = volumeNode.GetDisplayNode()
        if not displayNode:
            return
        
        # Get the scalar range of the volume
        imageData = volumeNode.GetImageData()
        if not imageData:
            return
            
        scalarRange = imageData.GetScalarRange()
        dataMin = scalarRange[0]
        dataMax = scalarRange[1]
        
        # Get the threshold range (if thresholding is enabled)
        if displayNode.GetApplyThreshold():
            thresholdMin = displayNode.GetLowerThreshold()
            thresholdMax = displayNode.GetUpperThreshold()
            
            # Use threshold range for window/level
            window = thresholdMax - thresholdMin
            level = (thresholdMax + thresholdMin) / 2.0

        else:
            # Check if there's a color node with a defined range
            colorNode = displayNode.GetColorNode()
            if colorNode:
                # Try to get window/level from display node first
                currentWindow = displayNode.GetWindow()
                currentLevel = displayNode.GetLevel()
                
                if currentWindow > 0:
                    # Use existing window/level if valid
                    window = currentWindow
                    level = currentLevel
                else:
                    # Fallback to full data range
                    window = dataMax - dataMin
                    level = (dataMax + dataMin) / 2.0
            else:
                # No color node, use full data range
                window = dataMax - dataMin
                level = (dataMax + dataMin) / 2.0
        # else:
        #     # Check if there's a color node with a defined range
        #     colorNode = displayNode.GetColorNode()
        #     if colorNode:
        #         # Get the color transfer function range
        #         colorRange = [0, 0]
        #         colorNode.GetRange(colorRange)
                
        #         if colorRange[0] != colorRange[1]:
        #             # Use color node range
        #             window = colorRange[1] - colorRange[0]
        #             level = (colorRange[1] + colorRange[0]) / 2.0
        #         else:
        #             # Fallback to full data range
        #             window = dataMax - dataMin
        #             level = (dataMax + dataMin) / 2.0
        #     else:
        #         # No color node, use full data range
        #         window = dataMax - dataMin
        #         level = (dataMax + dataMin) / 2.0
        
        # **DIVERGING COLORMAP ADJUSTMENT**
        # Check if using a diverging colormap (e.g., "Diverging Blue/Red")
        colorNode = displayNode.GetColorNode()
        #if colorNode and "JacobianMap" in colorNode.GetName():
        # For diverging colormaps, center at zero
        level_jacobian = 1.0
        # Window should span symmetrically around zero
        maxAbsValue = max(abs(dataMin), abs(dataMax))
        window_jacobian = 1.0 #2.0 * maxAbsValue  # Symmetric range: -maxAbsValue to +maxAbsValue
        self.defaultWindow_Jacobian = window_jacobian
        self.defaultLevel_Jacobian = level_jacobian
    

        disabledModify = displayNode.StartModify()
        displayNode.SetAutoWindowLevel(0)
        displayNode.SetWindowLevel(window, level)
        displayNode.EndModify(disabledModify)
        

        # Calculate min and max from window and level
        minValue = level - window / 2.0
        maxValue = level + window / 2.0
        
        # Set slider range based on data range (not threshold range)
        padding = (dataMax - dataMin) * 0.1
        self.ui.windowLevelSlider.minimum = dataMin - padding
        self.ui.windowLevelSlider.maximum = dataMax + padding
        
        # Set slider values to the threshold/visualization range
        self.ui.windowLevelSlider.minimumValue = minValue
        self.ui.windowLevelSlider.maximumValue = maxValue
        
        # Set spin box ranges
        self.ui.windowSpinBox.minimum = 0
        self.ui.windowSpinBox.maximum = (dataMax - dataMin) * 2
        self.ui.levelSpinBox.minimum = dataMin - padding
        self.ui.levelSpinBox.maximum = dataMax + padding
        
        # STORE DEFAULT VALUES
        self.defaultWindow_DisplacementMag = window
        self.defaultLevel_DisplacementMag = level

        #By default, set to displacement magnitude
        # self.setWindowLevel(volumeNode, self.defaultWindow_DisplacementMag, self.defaultLevel_DisplacementMag )
        # self.updateVolumeWindowLevel(self.defaultWindow_DisplacementMag, self.defaultLevel_DisplacementMag)


    def setWindowLevel(self, volumeNode, window, level):
        displayNode = volumeNode.GetDisplayNode()
        imageData = volumeNode.GetImageData()



        scalarRange = imageData.GetScalarRange()
        dataMin = scalarRange[0]
        dataMax = scalarRange[1]
        
        # Calculate min and max from window and level
        minValue = level - window / 2.0
        maxValue = level + window / 2.0
        
        # Set slider range based on data range (not threshold range)
        padding = (dataMax - dataMin) * 0.1
        self.ui.windowLevelSlider.minimum = dataMin - padding
        self.ui.windowLevelSlider.maximum = dataMax + padding
        
        # Set slider values to the threshold/visualization range
        self.ui.windowLevelSlider.minimumValue = minValue
        self.ui.windowLevelSlider.maximumValue = maxValue
        
        # Set spin box ranges
        self.ui.windowSpinBox.minimum = 0
        self.ui.windowSpinBox.maximum = (dataMax - dataMin) * 2
        self.ui.levelSpinBox.minimum = dataMin - padding
        self.ui.levelSpinBox.maximum = dataMax + padding
        
        # Set spin box values
        self.ui.windowSpinBox.value = window
        self.ui.levelSpinBox.value = level


        print(f"Default Window/Level: window={window}, level={level}")
        print(f"Threshold range: [{minValue}, {maxValue}]")


    def getBrainShiftFlag(self, volumeNode):
        """
        Returns the BrainShiftFlag value stored in FieldData or PointData.
        FieldData → global flag (1 value)
        PointData → per-voxel array (returns first value)
        """
        if not volumeNode:
            return None

        imageData = volumeNode.GetImageData()
        if not imageData:
            return None

        # --- 1) Try FieldData (global flag) ---
        fd = imageData.GetFieldData()
        if fd:
            arr = fd.GetArray("BrainShiftFlag")
            if arr and arr.GetNumberOfTuples() > 0:
                return int(arr.GetValue(0))

        # --- 2) Try PointData (voxel mask) ---
        pd = imageData.GetPointData()
        if pd:
            arr = pd.GetArray("BrainShiftFlag")
            if arr and arr.GetNumberOfTuples() > 0:
                return int(arr.GetValue(0))

        # --- Not found ---
        return None



    def getCurrentDisplacementVolumeNode(self):
        """Return the displacement volume node, creating it if necessary."""
        volumeNode = self.ui.loadedTransformVolume.currentNode()
        if not volumeNode:
            # Optionally, try to auto-find an existing volume in the scene
            for node in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
                if "Displacement" in node.GetName():
                    return node
            return None
        return volumeNode
    


    # ╔══════════════════════════════════════╗
    # ║             UPDATE STATE             ║
    # ╚══════════════════════════════════════╝
    
    def windowLevelFlagUpdate(self, flag, volumeNode):

        displayNode = volumeNode.GetDisplayNode()
        if flag == 0: #Displacement magnitude
            window = self.defaultWindow_DisplacementMag
            level = self.defaultLevel_DisplacementMag

            # print("window (DM): ", window, "level (DM): ", level)

        elif flag == 1: #Jacobian
            window = self.defaultLevel_Jacobian
            level = self.defaultLevel_Jacobian

            # print("window (Jacobian): ", window, "level (Jacobian): ", level)

        minValue = level - window / 2.0
        maxValue = level + window / 2.0

        imageData = volumeNode.GetImageData()
        if not imageData:
            return
            
        scalarRange = imageData.GetScalarRange()
        dataMin = scalarRange[0]
        dataMax = scalarRange[1]
        
        # Set slider range based on data range (not threshold range)
        padding = (dataMax - dataMin) * 0.1
        self.ui.windowLevelSlider.minimum = dataMin - padding
        self.ui.windowLevelSlider.maximum = dataMax + padding
        
        # Set slider values to the threshold/visualization range
        self.ui.windowLevelSlider.minimumValue = minValue
        self.ui.windowLevelSlider.maximumValue = maxValue
        
        # Set spin box ranges
        self.ui.windowSpinBox.minimum = 0
        self.ui.windowSpinBox.maximum = (dataMax - dataMin) * 2
        self.ui.levelSpinBox.minimum = dataMin - padding
        self.ui.levelSpinBox.maximum = dataMax + padding

        self.updateVolumeWindowLevel(window=window, level=level)
        # disabledModify = displayNode.StartModify()
        # displayNode.SetAutoWindowLevel(0)
        # displayNode.SetWindowLevel(window, level)
        # displayNode.EndModify(disabledModify)
    
           
    def updateVolumeWindowLevel(self, window, level):
        '''
        Apply window/level to the currently loaded volume's display node
        '''
        selectedVolume = self.ui.loadedTransformVolume.currentNode()
        if not selectedVolume:
            return
            
        displayNode = selectedVolume.GetDisplayNode()
        if not displayNode:
            return
        
        # Update the display node
        disabledModify = displayNode.StartModify()
        displayNode.SetAutoWindowLevel(0)
        displayNode.SetWindowLevel(window, level)
        displayNode.EndModify(disabledModify)

        
    def updateHoverCheckboxFromNode(self):
        # Syncs the hover display checkbox with the actual visibility of the mouse label node 
        self.labelMarkupNode = self.getOrCreateLabelNodeForCurrentVolume()
        disp = self.labelMarkupNode.GetDisplayNode()
        if disp:
            visible = disp.GetVisibility2D() and self.labelMarkupNode.GetDisplayVisibility()
            self.ui.enableHoverDisplayCheckbox.blockSignals(True)
            self.ui.enableHoverDisplayCheckbox.setChecked(visible)
            self.ui.enableHoverDisplayCheckbox.blockSignals(False)



    def updateVisualizationCheckboxFromNode(self):
        """Syncs the displacement display checkbox with the actual visibility of the volume."""
        volumeNode = self.getCurrentDisplacementVolumeNode()
        if not volumeNode:
            self.ui.enableDisplacementVisualizationCheckbox.blockSignals(True)
            self.ui.enableDisplacementVisualizationCheckbox.setChecked(False)
            self.ui.enableDisplacementVisualizationCheckbox.blockSignals(False)
            return

        displayNode = volumeNode.GetDisplayNode()
        if displayNode:
            visible = displayNode.GetVisibility2D() and volumeNode.GetDisplayVisibility()
            self.ui.enableDisplacementVisualizationCheckbox.blockSignals(True)
            self.ui.enableDisplacementVisualizationCheckbox.setChecked(visible)
            self.ui.enableDisplacementVisualizationCheckbox.blockSignals(False)

        




 


                



 

    ''' --------- UNUSED ADDITIONAL FUNCTIONALITY ---------------'''
    def getLandmarkLabel(self):
        parent = slicer.util.mainWindow()  # safe parent for dialogs in Slicer

        # First prompt
        text1 = qt.QInputDialog.getText(
            parent,
            "Please name the first landmark file (derived from the source volume)",
            "Name:",
            qt.QLineEdit.Normal,  # Echo mode required!
            ""                    # default text (optional)
        )

        if not text1:
            slicer.util.errorDisplay("No name provided for first landmark file.")
            return None, None

        # Second prompt
        text2 = qt.QInputDialog.getText(
            parent,
            "Please name the second landmark file (derived from the moving volume)",
            "Name:",
            qt.QLineEdit.Normal,
            ""
        )

        if not text2:
            slicer.util.errorDisplay("No name provided for second landmark file.")
            return None, None

        print("Renamed to:", text1, text2)
        return text1, text2

    def getActivePairInfo(self):

        activeNode = None
        activeIndex = None
        
        #find active landmark
        for n in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
            if n is getattr(self, "labelMarkupNode", None) or not n.GetDisplayNode():
                continue
            if n.GetDisplayNode().GetActiveComponentType() != slicer.vtkMRMLMarkupsDisplayNode.ComponentControlPoint:
                continue
            idx = n.GetDisplayNode().GetActiveComponentIndex()
            if idx is None or idx < 0:
                continue
            activeNode = n
            activeIndex = idx
            break

        if activeNode is None:
            return None
        
        #find pair landmark
        pairNode = None
        for lmrk in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
            if lmrk is not activeNode and lmrk is not getattr(self, "labelMarkupNode", None):
                pairNode = lmrk
                break
        if pairNode is None:
            return None

        pairIndex = -1
        if activeIndex < pairNode.GetNumberOfControlPoints():
            pairIndex = activeIndex
        if pairIndex < 0:
            return None
        
        #compute distance in IJK (mm)
        rasA = [0.0, 0.0, 0.0]
        rasB = [0.0, 0.0, 0.0]
        activeNode.GetNthControlPointPositionWorld(activeIndex, rasA)
        pairNode.GetNthControlPointPositionWorld(pairIndex, rasB)
        vol = self.ui.loadedTransformVolume.currentNode()
        ijkA = ijkB = None
        if vol:
            rasToIjk = vtk.vtkMatrix4x4()
            vol.GetRASToIJKMatrix(rasToIjk)

            ijkhA = [0.0, 0.0, 0.0, 1.0]
            ras_hA = [rasA[0], rasA[1], rasA[2], 1.0]
            rasToIjk.MultiplyPoint(ras_hA, ijkhA)
            ijkA = [float(ijkhA[0]), float(ijkhA[1]), float(ijkhA[2])]

            ijkhB = [0.0, 0.0, 0.0, 1.0]
            ras_hB = [rasB[0], rasB[1], rasB[2], 1.0]
            rasToIjk.MultiplyPoint(ras_hB, ijkhB)
            ijkB = [float(ijkhB[0]), float(ijkhB[1]), float(ijkhB[2])]

        dx = ijkA[0]-ijkB[0]
        dy = ijkA[1]-ijkB[1]
        dz = ijkA[2]-ijkB[2]
        activeLabel = activeNode.GetNthControlPointLabel(activeIndex) or f"{activeNode.GetName()}-{activeIndex+1}"
        pairLabel   = pairNode.GetNthControlPointLabel(pairIndex)   or f"{pairNode.GetName()}-{pairIndex+1}"
        #print(f"{activeLabel}: IJK = {(ijkA)}")
        #print(f"{pairLabel}: IJK = {(ijkB)}")
        self.updateSelectedLandmarksDisplay(activeLabel, pairLabel)
        return (dx*dx + dy*dy + dz*dz) ** 0.5 
    

    def updateLandmarkDistanceDisplay(self, dist: float) -> None:
    
        if dist is None:
            self.ui.landmarkEuclidianDistance.setText("N/A")
        else:
            self.ui.landmarkEuclidianDistance.setText(f"{dist:.3f} mm")
            self.ui.landmarkEuclidianDistance.setReadOnly(True)

    
    def updateSelectedLandmarksDisplay(self, activeLabel: str, pairLabel: str) -> None:
        if not hasattr(self.ui, 'selectedLandmarks') or self.ui.selectedLandmarks is None:
            return
        self.ui.selectedLandmarks.setReadOnly(True)
        self.ui.landmarkEuclidianDistance.setReadOnly(True)
        self.ui.selectedLandmarks.setText(f"{activeLabel}  ↔  {pairLabel}")


    def onLandmarkSelectionChanged(self):
        # Get all fiducial nodes
        #allFiducials = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
        fcsvFiducials = [
            node for node in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
            if node.GetStorageNode() and node.GetStorageNode().GetFileName().endswith('.fcsv')
        ]
        
        # Get selected names from the combo box
        selectedNames = []
        for i in range(self.LandmarkSelectorComboBox.count):
            if self.LandmarkSelectorComboBox.checkState(i) == qt.Qt.Checked :
                selectedNames.append(self.LandmarkSelectorComboBox.itemText(i))

        # Show only selected ones
        for node in fcsvFiducials:
            print("Gte nMae:",node.GetName())
            displayNode = node.GetDisplayNode()
            if not displayNode:
                continue
            if node.GetName() in selectedNames:
                displayNode.SetUsePointColors(True)         # Use global color, not per-point
                displayNode.SetVisibility(True)
                displayNode.SetVisibility2D()
                displayNode.SetTextScale(1.0)
                
                displayNode.SetActiveColor([1.0, 0.0, 1.0])   # Pink when active
                displayNode.SetColor(1.0, 0.0, 1.0)           # Pink when not active
                displayNode.SetSelectedColor(1.0, 0.0, 1.0)   # Pink when selected
                displayNode.SetUseSelectedColor()       
                
                displayNode.SetGlyphScale(2.0)
                displayNode.SetHandlesInteractive(False)
                displayNode.SetInteractionHandleScale(0.0)
            else:

                displayNode.SetVisibility(False)
                displayNode.SetVisibility2D(False)


    def watchActiveLabel(self):
        
        #observers for selected landmark
        for n, tag in getattr(self, "_activeWatchers", []):
            try: n.RemoveObserver(tag)
            except: pass
        self._activeWatchers = []
        self._lastDistancePrinted = None

        def onPointEnd(markupsNode, ev):
            dn = markupsNode.GetDisplayNode()
            if not dn:
                return
            if dn.GetActiveComponentType() != slicer.vtkMRMLMarkupsDisplayNode.ComponentControlPoint:
                return
            i = dn.GetActiveComponentIndex()
            if i is None or i < 0 or i >= markupsNode.GetNumberOfControlPoints():
                return

            dist = self.getActivePairInfo()
            if dist is None:
                return
            if self._lastDistancePrinted is not None and abs(dist - self._lastDistancePrinted) < 1e-6:
                return
            self._lastDistancePrinted = dist
            #print(f"distance = {dist:.3f} mm")
            self.updateLandmarkDistanceDisplay(dist)
            
        for n in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
            if n is getattr(self, "labelMarkupNode", None):
                continue
            tag = n.AddObserver(slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, onPointEnd)
            self._activeWatchers.append((n, tag))
            

    def onLoadExpertLabelsClicked(self):
        comboBox = self.ui.LandmarkSelectorComboBox
        model = comboBox.model()
        for i in range(comboBox.count):
            #print("i", i)
            index = model.index(i, 0)
            itemText = comboBox.itemText(i)
            try:
                node = slicer.util.getNode(itemText)
                displayNode = node.GetDisplayNode()
                displayNode.SetVisibility(False)
                displayNode.SetVisibility2D(False)
            except:
                print(f"Could not get node for: {itemText}")
                continue
            
            checked = model.data(index, qt.Qt.CheckStateRole) == qt.Qt.Checked
            displayNode = node.GetDisplayNode()

            if node.IsA("vtkMRMLMarkupsFiducialNode") and checked:
                if displayNode:
                    print("Show Node", node.GetName())
                    displayNode.SetVisibility(True)
                    displayNode.SetVisibility2D(True)
                    displayNode.SetGlyphScale(3.0)
                    displayNode.SetTextScale(3.0)
                    displayNode.SetActiveColor([1.0, 0.2, 0.5])
                    displayNode.SetSelectedColor(0.0, 0.0, 0.0)
                    displayNode.SetGlyphTypeFromString("CrossDot2D")
                    displayNode.SetSelected(checked)
                    displayNode.SetHandlesInteractive(False) #??
                    displayNode.SetInteractionHandleScale(0.0)

            else:
                # print("don't show node", node.GetName()) #stores typed in landmark name
                #displayNode = node.GetDisplayNode()
                displayNode.SetVisibility(False)
                displayNode.SetVisibility2D(False)
                displayNode.SetGlyphScale(3.0)


    def onToggleUsDisplay(self) -> None:
        usVolume = self.ui.referenceVolume.currentNode()
        state = self.ui.enableUsBorderDisplay.checkState() 
        self.logic.showNonZeroWireframe(foregroundVolume=usVolume, state=state)
    

        #Unused additional functionality
    
    
    def onConvertTagFCSVButtonClicked(self):
        filePath = qt.QFileDialog.getOpenFileName(
            None, "Open Tag File", "", "Tag files (*.tag)"
        )
        text1, text2 = self.getLandmarkLabel()
        print("Selected file:", filePath, text1, text2)
        if filePath:
            success = self.logic.loadTagFile(filePath, text1, text2)
            if not success:
                slicer.util.errorDisplay(f"Failed to load tag file: {filePath}")
            else:
                logging.info(f"Loaded tag file: {filePath}")
    


    #Unused functionality
    def updateLandmarkSelectorComboBox(self):
        '''
        Tracks which files to add to the selection box for the available landmarks
        '''
        self.ui.LandmarkSelectorComboBox.clear()

        #print("Landmark Selector Count", self.LandmarkSelectorComboBox.count)

        #print("Update... ")
        fiducialNodes = slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
        
        #print(f"fiducial Nodes", fiducialNodes)
        #print("fiducial Nodes available", len(fiducialNodes))

        for node in fiducialNodes:
            if node == self.labelMarkupNode:
                continue
            self.ui.LandmarkSelectorComboBox.addItem(node.GetName()) #stores node name (string)

        self.watchActiveLabel()
        
       










class DeformViewLogic(ScriptedLoadableModuleLogic):
    """Logic for computing voxel-wise displacement from transformation field"""

    def __init__(self) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)

    def getParameterNode(self):
        return DeformViewParameterNode(super().getParameterNode())
    
    def countUniqueValues(self, volumeNode: vtkMRMLScalarVolumeNode):

        

        imageData = volumeNode.GetImageData()
        if imageData is None:
            logging.warning("Volume has no image data.")
            return None

        vtk_array = imageData.GetPointData().GetScalars()
        np_array = vtk_to_numpy(vtk_array)

        unique_values = np.unique(np_array)
        logging.info(f"Number of unique values in displacement magnitude volume: {len(unique_values)}")
        return len(unique_values), unique_values




    def computeDisplacementMagnitude(self,
                                referenceVolume: vtkMRMLScalarVolumeNode,
                                transformNode:   vtkMRMLTransformNode,
                                defaultColourMap: vtkMRMLColorTableNode,
                                scale: float = 1.0
                                ) -> vtkMRMLScalarVolumeNode:
        """
        Compute voxel-wise displacement magnitude from a BSpline transform.
        Returns a scalar volume node.
        """

        if not referenceVolume:
            raise ValueError("Reference volume is invalid")
        if not transformNode:
            raise ValueError("Transform node is invalid")
        
        #volumesLogic = slicer.modules.volumes.logic()
        

        # Get reference image as SimpleITK image
        refImage = sitkUtils.PullVolumeFromSlicer(referenceVolume)

       #imageData = refImage.GetImageData()
        # print("outputVolume image data: ", refImage)
        
        if refImage is None:
            raise Exception("Reference volume has no image data")
            
        
        # Convert MRML BSpline transform to ITK transform
        # itkTx = sitk.ReadTransform(transformNode.GetStorageNode().GetFileName())

        # Write computed transform to temporary .h5 file
        with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
            tmpPath = tmp.name

        slicer.util.saveNode(transformNode, tmpPath)

        # Read into SimpleITK
        itkTx = sitk.ReadTransform(tmpPath)

        # Clean up
        os.remove(tmpPath)



        # Resample the transform into a displacement field on the reference grid
        dispField = sitk.TransformToDisplacementField(
            itkTx,
            sitk.sitkVectorFloat64,
            refImage.GetSize(),
            refImage.GetOrigin(),
            refImage.GetSpacing(),
            refImage.GetDirection()
        )

        if scale != 1.0:
            dispField = sitk.Multiply(dispField, scale)

        # Compute magnitude image
        dispMag = sitk.VectorMagnitude(dispField)

        # Push back to Slicer
        volumeName = referenceVolume.GetName() + "_displacementMagnitude"
        if scale != 1.0:
            volumeName = f"{referenceVolume.GetName()}_displacement_{int(scale*100)}pct"
            
        outputVolume = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode",
            volumeName
        )

        sitkUtils.PushVolumeToSlicer(dispMag, outputVolume)

        # add flag
        img = outputVolume.GetImageData()
        flagArray = vtk.vtkIntArray()
        flagArray.SetName("BrainShiftFlag")
        flagArray.SetNumberOfValues(1)
        flagArray.SetValue(0, 0)  # 0 = displacement
        img.GetFieldData().AddArray(flagArray)
        outputVolume.Modified()


        # Ensure display node exists
        if not outputVolume.GetDisplayNode():
            #slicer.modules.volumes.logic().CreateDefaultDisplayNodes(outputVolume)
            outputVolume.CreateDefaultDisplayNodes()


        displayNode = outputVolume.GetDisplayNode()

        # Disable auto WL/CL so it doesn’t reset every time
        displayNode.AutoWindowLevelOff()
        # displayNode.SetWindow(10.0)
        # displayNode.SetLevel(5.0)

        array = sitk.GetArrayFromImage(dispMag)
        minVal, maxVal = float(array.min()), float(array.max())
        displayNode.SetWindow(maxVal - minVal)
        displayNode.SetLevel((maxVal + minVal) / 3.0)

        # Apply threshold for visibility
        displayNode.SetThreshold(0.05, 10.0)
        displayNode.SetApplyThreshold(True)

        # Use specific color map if available
        #colorNode = slicer.util.getNode("Viridis")
        if defaultColourMap:
            colorNode = slicer.mrmlScene.GetNodeByID(defaultColourMap)

        if colorNode:
            displayNode.SetAndObserveColorNodeID(colorNode.GetID())
        return outputVolume



    def computeJacobianMagnitude(self,
                                referenceVolume: vtkMRMLScalarVolumeNode,
                                transformNode: vtkMRMLTransformNode,
                                defaultColourMap: vtkMRMLColorTableNode
                                ) -> vtkMRMLScalarVolumeNode:

        refImage = sitkUtils.PullVolumeFromSlicer(referenceVolume)

        # itkTx = sitk.ReadTransform(transformNode.GetStorageNode().GetFileName())

        with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
            tmpPath = tmp.name

        slicer.util.saveNode(transformNode, tmpPath)

        # Read into SimpleITK
        itkTx = sitk.ReadTransform(tmpPath)

        # Clean up
        os.remove(tmpPath)

        # Convert transform to displacement field in reference grid
        displacementField = sitk.TransformToDisplacementField(
            itkTx,
            sitk.sitkVectorFloat64,
            refImage.GetSize(),
            refImage.GetOrigin(),
            refImage.GetSpacing(),
            refImage.GetDirection()
        )

        # Step 4: Compute Jacobian determinant
        jacDet = sitk.DisplacementFieldJacobianDeterminant(displacementField)

        # Step 6: Convert to percent change from 1
        # (J - 1) * 100
        jacPercent = sitk.Multiply(sitk.Subtract(jacDet, 1.0), 100.0)

        # Step 5: Take magnitude (absolute value)
        #jacMagnitude = sitk.Abs(jacDet)

        # Step 6: Push result back into Slicer
        outputVolume = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode",
            referenceVolume.GetName() + "_jacobianMagnitude"
        )

       
        # sitkUtils.PushVolumeToSlicer(jacDet, targetNode=outputVolume)
        sitkUtils.PushVolumeToSlicer(jacPercent, targetNode=outputVolume)

        array = sitk.GetArrayFromImage(jacPercent)
        # print(f"Jacobian Percent Range: min={array.min():.2f}, max={array.max():.2f}")
        # print(f"Sample values: {array.flatten()[:10]}")  # First 10 values

        # add flag
        img = outputVolume.GetImageData()
        flagArray = vtk.vtkIntArray()
        flagArray.SetName("BrainShiftFlag")
        flagArray.SetNumberOfValues(1)
        flagArray.SetValue(0, 1)  # 1 = Jacoban
        img.GetFieldData().AddArray(flagArray)
        outputVolume.Modified()



         # Step 7: Display setup
        if not outputVolume.GetDisplayNode():
            outputVolume.CreateDefaultDisplayNodes()

        displayNode = outputVolume.GetDisplayNode()

        existingNode = slicer.mrmlScene.GetFirstNodeByName("JacobianMap")
        
        if existingNode:
            # print("Jacobian exists")
            colorNode = slicer.util.getNode("JacobianMap")
        #if colorNode:
            displayNode.SetAndObserveColorNodeID(colorNode.GetID())
        else:
            colorNode = slicer.mrmlScene.GetNodeByID(defaultColourMap)
            displayNode.SetAndObserveColorNodeID(colorNode.GetID())

        displayNode.AutoWindowLevelOff()




        #Set threshold at 0 to split contraction (negative) from expansion (positive)
        displayNode.SetThreshold(0.0, True)  # Enable threshold at 0
        displayNode.SetLowerThreshold(0.0)
        displayNode.SetUpperThreshold(0.0)

        # Adjust window/level so 0 is the dividing point
        # displayNode.SetWindowLevel(100, 0)

        # Set window/level for percentage range
        # For example, -50% to +50% range
        #displayNode.SetWindowLevel(100, 0)  # window=100 (range), level=0 (center)
        # Or adjust based on your expected range of deformation


        # displayNode.SetWindow(5.0)
        # displayNode.SetLevel(2.5)
        # array = sitk.GetArrayFromImage(jacDet)
        array = sitk.GetArrayFromImage(jacPercent)
        minVal = float(array.min())
        maxVal = float(array.max())

        window = maxVal - minVal
        level = (maxVal + minVal) / 2.0
        displayNode.SetWindowLevel(window, level)

        if colorNode:
            lookupTable = colorNode.GetLookupTable()
            if lookupTable:
                # Map color indices to data values
                lookupTable.SetRange(minVal, maxVal)
                lookupTable.Build()       


        # Step 8: Store in UI and parameter node
        #self.ui.jacobianMagnitudeVolume.setCurrentNode(outputVolume)
        #self._parameterNode().SetNodeReferenceID("jacobianMagnitudeVolume", outputVolume.GetID())

        # # Just before return:
        # testArray = slicer.util.arrayFromVolume(outputVolume)
        # print(f"✓ Volume '{outputVolume.GetName()}' data range: [{testArray.min():.2f}, {testArray.max():.2f}]")
        # if testArray.min() >= 0:
        #     print("⚠ WARNING: No negative values found! Data might not be percentages.")

        return outputVolume






    def createIncrementalTransform(self,
                                    backgroundVolume: vtkMRMLScalarVolumeNode,
                                    transformNode: vtkMRMLTransformNode,
                                    scale: float,
                                    name: str) -> vtkMRMLScalarVolumeNode:
            """
            Create a volume by applying a scaled version of the transform to the background volume.
            
            Args:
                backgroundVolume: The volume to transform
                transformNode: The transformation to apply
                scale: Scale factor (0.0 to 1.0) for the transformation
                name: Name for the output volume
            
            Returns:
                Transformed volume node
            """
            import tempfile
            import os
            
            # Get background image as SimpleITK
            bgImage = sitkUtils.PullVolumeFromSlicer(backgroundVolume)
            
            # Write transform to temporary file
            with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
                tmpPath = tmp.name
            
            slicer.util.saveNode(transformNode, tmpPath)
            
            # Read into SimpleITK
            itkTx = sitk.ReadTransform(tmpPath)
            os.remove(tmpPath)
            
            # Convert to displacement field
            dispField = sitk.TransformToDisplacementField(
                itkTx,
                sitk.sitkVectorFloat32,
                bgImage.GetSize(),
                bgImage.GetOrigin(),
                bgImage.GetSpacing(),
                bgImage.GetDirection()
            )
            
            # Scale the displacement field
            components = [
                sitk.VectorIndexSelectionCast(dispField, i)
                for i in range(dispField.GetNumberOfComponentsPerPixel())
            ]

            # Scale each component
            components = [sitk.Multiply(c, scale) for c in components]

            scaledDispField = sitk.Compose(components)
            scaledDispField.CopyInformation(dispField)

            scaledDispField = sitk.Cast(scaledDispField, sitk.sitkVectorFloat64)

            # Convert displacement field back to transform
            scaledTransform = sitk.DisplacementFieldTransform(scaledDispField)
            
            # Apply scaled transform to background volume
            resampler = sitk.ResampleImageFilter()
            resampler.SetReferenceImage(bgImage)
            resampler.SetTransform(scaledTransform)
            resampler.SetInterpolator(sitk.sitkLinear)
            resampler.SetDefaultPixelValue(0)
            
            transformedImage = resampler.Execute(bgImage)
            
            # Create output volume node
            outputVolume = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLScalarVolumeNode",
                name
            )
            
            # Push back to Slicer
            sitkUtils.PushVolumeToSlicer(transformedImage, outputVolume)
            
            # Copy display properties from background volume
            bgDisplay = backgroundVolume.GetDisplayNode()
            if bgDisplay:
                outputDisplay = outputVolume.GetDisplayNode()
                if not outputDisplay:
                    outputVolume.CreateDefaultDisplayNodes()
                    outputDisplay = outputVolume.GetDisplayNode()
                
                if outputDisplay:
                    outputDisplay.SetAndObserveColorNodeID(bgDisplay.GetColorNodeID())
                    outputDisplay.SetWindow(bgDisplay.GetWindow())
                    outputDisplay.SetLevel(bgDisplay.GetLevel())
            
            return outputVolume
        

    def showNonZeroWireframe(self, foregroundVolume, state, reload=False, modelName="NonZeroWireframe"):
        """
        Extracts the non-zero region of a volume and displays its surface wireframe
        as a non-destructive 3D overlay using a vtkModelNode.
        """

        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger(__name__)

        currentModelNode = slicer.mrmlScene.GetFirstNodeByName(modelName)
        if currentModelNode:
            currentDisplayNode = currentModelNode.GetDisplayNode()
            if not reload:
                if not state:
                    currentDisplayNode.SetVisibility2D(False)
                    return
                currentDisplayNode.SetVisibility2D(True)
                return

            slicer.mrmlScene.RemoveNode(currentDisplayNode)
            slicer.mrmlScene.RemoveNode(currentModelNode)

        #print("Starting showNonZeroWireframe...")
        # Step 1: Convert foreground image to binary mask
        #print("Step 1: Pulling volume from Slicer for node: %s", foregroundVolume.GetName())
        image_sitk = sitkUtils.PullVolumeFromSlicer(foregroundVolume)
        arr = sitk.GetArrayFromImage(image_sitk)
        nonzero_voxels = np.count_nonzero(arr)
        #print("Step 1b: Number of non-zero voxels: %d", nonzero_voxels)

        if nonzero_voxels == 0:
            logger.warning("WARNING: No non-zero voxels found in the image. Aborting wireframe display.")
            return

        mask_arr = (arr != 0).astype(np.uint8)
        mask_sitk = sitk.GetImageFromArray(mask_arr)
        mask_sitk.CopyInformation(image_sitk)
        #print("Step 1b: Converted to binary mask.")

        # Push to Slicer as labelmap
        labelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode", "TempBinaryMask")
        sitkUtils.PushVolumeToSlicer(mask_sitk, targetNode=labelNode)
        #print("Step 1 done: Binary mask pushed to Slicer label node: %s", labelNode.GetName())

        # Step 2: Extract surface using marching cubes
        imageData = labelNode.GetImageData()
        if imageData is None:
            print("WARNING: Image data is None. Check label node data.")
            return

        #print("Step 2: Starting marching cubes...")
        marching = vtk.vtkDiscreteMarchingCubes()
        marching.SetInputData(imageData)
        marching.SetValue(0, 1)
        marching.Update()
        surface = marching.GetOutput()
        if surface is None or surface.GetNumberOfPoints() == 0:
            print("WARNING: No surface generated by marching cubes.")
            return

        # Step 3: Extract wireframe edges from the surface mesh
        #print("Step 3: Extracting edges from surface...")
        edges = vtk.vtkExtractEdges()
        edges.SetInputConnection(marching.GetOutputPort())
        edges.Update()

        # Step 4: Create and show model node with only edges
        #print("Step 4: Preparing model node '%s'...", modelName)
        newModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", modelName)
       # print("STep 4 done: Created new model node.")
        newModelNode.SetAndObservePolyData(edges.GetOutput())

        # Match spatial transform
        #print("Step 5: Applying spatial transform (IJK to RAS)...")
        transform = vtk.vtkTransform()
        ijkToRAS = vtk.vtkMatrix4x4()
        labelNode.GetIJKToRASMatrix(ijkToRAS)
        transform.SetMatrix(ijkToRAS)
        transformFilter = vtk.vtkTransformPolyDataFilter()
        transformFilter.SetTransform(transform)
        transformFilter.SetInputData(edges.GetOutput())
        transformFilter.Update()
        newModelNode.SetAndObservePolyData(transformFilter.GetOutput())

        # Step 6: Set wireframe-only display
        #print("Step 6: Setting display properties for wireframe...")
        displayNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelDisplayNode")

        #slicer.mrmlScene.AddNode(displayNode)
        newModelNode.SetAndObserveDisplayNodeID(displayNode.GetID())
        #print("Done: Created and linked display node.")

        displayNode.SetRepresentation(0)  # Wireframe
        displayNode.SetColor(0, 0, 0)     # Green
        displayNode.SetEdgeVisibility(True)
        displayNode.SetPointSize(3.0)
        displayNode.SetSliceIntersectionThickness(2)

        displayNode.SetVisibility3D(False)
        displayNode.SetVisibility2D(True)

        # Optional: remove temp label node
        slicer.mrmlScene.RemoveNode(labelNode)
        #print("Temporary label node removed. Done!")

        return newModelNode
    
    
    
    def loadTagFile(self, filepath, text1, text2):
        print(f"Reading tag file: {filepath}")
        print("Label: ", text2)
        points1, points2 = self.read_tag_file(filepath)
        if points1 is None or points2 is None or len(points1) == 0 or len(points2) == 0:
            logging.error("No valid points found in tag file.")
            return False
        

        # create fiducial nodes in Slicer scene
        fiducialNode1 = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", f"{text1}") #the set of landmarks from the first volume registered
        fiducialNode2 = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", f"{text2}") #the set of landmarks from the second volume registered

        # add points from tag file to the fiducial nodes
        for pt in points1:
            fiducialNode1.AddControlPoint(pt)
        for pt in points2:
            fiducialNode2.AddControlPoint(pt)

        displayNode1 = fiducialNode1.GetDisplayNode()
        if displayNode1:
            displayNode1.SetVisibility(False)            # Hide in 3D
            displayNode1.SetVisibility2D(False)          # Hide in 2D slice views
            displayNode1.SetSelectedColor(0.5, 0.5, 0.5) # Optional: make it less prominent when turned on
            displayNode1.SetTextScale(5.0)               # Hide label text
            #displayNode1.SetGlyphTypeFromString("None")  # Hide glyph icon
            displayNode1.SetHandlesInteractive(False)    # Disable user interaction
            #displayNode1.SetOpacity(1.0)
            #displayNode1.SetGlyphScale(5.0)  
        print("Number of points1:", fiducialNode1.GetNumberOfControlPoints())

        displayNode2 = fiducialNode2.GetDisplayNode()
        if displayNode2:
            displayNode2.SetVisibility(False)            # Hide in 3D
            displayNode2.SetVisibility2D(False)          # Hide in 2D slice views
            displayNode2.SetSelectedColor(0.5, 0.5, 0.5) # Optional: make it less prominent when turned on
            displayNode2.SetTextScale(5.0)               # Hide label text
            displayNode2.SetOpacity(1.0)
            displayNode2.SetGlyphScale(5.0)  
            displayNode2.SetHandlesInteractive(False)    # Disable user interaction
        
        else:
            slicer.util.errorDisplay("Failed to load landmark file.")
        qt.QMessageBox.information(slicer.util.mainWindow(), "Success", "Success! \nLandmark files created and available in Data.")
        print("Number of points2:", fiducialNode1.GetNumberOfControlPoints())

        logging.info("Landmarks loaded and hidden.")
        
        logging.info(f"Created {len(points1)} landmarks in each set.")
        return True
    

    def read_tag_file(self, filepath):

        """Parse the tag file robustly and return two numpy arrays of points."""
        source_points = []
        target_points = []
        try:
            with open(filepath, 'r') as file:
                for line in file:
                    line = line.strip()
                    if line.startswith('%') or not line:
                        continue
                    try:
                        values = list(map(float, re.findall(r"[-+]?\d*\.\d+|\d+", line)))
                        if len(values) >= 6:
                            source_points.append(values[0:3])
                            target_points.append(values[3:6])
                    except ValueError:
                        # skip lines that cannot be parsed into floats
                        continue
        except Exception as e:
            logging.error(f"Failed to read tag file: {e}")
            return None, None
        return np.array(source_points), np.array(target_points)
    

class DeformViewTest(ScriptedLoadableModuleTest):
    """Self-test for DeformView.

    Uses only synthetic, in-memory
    data: a small random volume and a pure 2 mm translation, for which
    the expected results are known analytically (displacement == 2 mm
    everywhere; Jacobian volume change == 0 % everywhere). 
    
    Doesn't need any downloads or data - IJZF
    """

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_LogicApiPresent()
        self.setUp()
        self.test_DisplacementAndJacobian()

    def test_LogicApiPresent(self):
        """Smoke test: module loads and the logic API is intact."""
        self.delayDisplay("Starting: logic API presence")
        logic = DeformViewLogic()
        self.assertIsNotNone(logic)
        for name in ("computeDisplacementMagnitude", "computeJacobianMagnitude",
                     "createIncrementalTransform", "countUniqueValues"):
            self.assertTrue(callable(getattr(logic, name, None)),
                            f"DeformViewLogic is missing method: {name}")
        self.delayDisplay("Passed: logic API presence")

    def test_DisplacementAndJacobian(self):
        """Functional test: run both maps on a synthetic translation."""
        self.delayDisplay("Starting: displacement + Jacobian")

        # 1. Synthetic reference volume (array shape is k, j, i).
        voxels = (np.random.RandomState(0).rand(20, 24, 28) * 100.0).astype(np.float32)
        referenceVolume = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLScalarVolumeNode", "TestReference")
        slicer.util.updateVolumeFromArray(referenceVolume, voxels)
        referenceVolume.SetSpacing(1.0, 1.0, 1.0)
        referenceVolume.SetOrigin(0.0, 0.0, 0.0)

        # 2. Synthetic transform: a pure 2 mm translation.
        translationMm = 2.0
        with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as tmp:
            txPath = tmp.name
        sitk.WriteTransform(sitk.TranslationTransform(3, (translationMm, 0.0, 0.0)), txPath)
        transformNode = slicer.util.loadTransform(txPath)
        os.remove(txPath)
        self.assertIsNotNone(transformNode)

        # 3. A colour table node; the compute methods want its ID *string*.
        colorNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLColorTableNode")
        if colorNode is None:
            colorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLColorTableNode", "TestColors")
            colorNode.SetTypeToRainbow()
        colorId = colorNode.GetID()

        logic = DeformViewLogic()

        # 4. Displacement magnitude.
        dispVol = logic.computeDisplacementMagnitude(referenceVolume, transformNode, colorId, scale=1.0)
        self.assertIsNotNone(dispVol)
        disp = slicer.util.arrayFromVolume(dispVol)
        self.assertEqual(disp.shape, voxels.shape)        # geometry preserved
        self.assertTrue(np.all(np.isfinite(disp)))        # no NaN / inf
        self.assertTrue(np.all(disp >= 0.0))              # magnitude is non-negative
        self.assertAlmostEqual(float(np.median(disp)), translationMm, delta=0.5)  # tune if needed

        # 5. Jacobian determinant (percentage volume change).
        jacVol = logic.computeJacobianMagnitude(referenceVolume, transformNode, colorId)
        self.assertIsNotNone(jacVol)
        jac = slicer.util.arrayFromVolume(jacVol)
        self.assertEqual(jac.shape, voxels.shape)
        self.assertTrue(np.all(np.isfinite(jac)))
        self.assertLess(abs(float(np.median(jac))), 1.0)  # translation is volume-preserving; tune if needed

        self.delayDisplay("Passed: displacement + Jacobian")