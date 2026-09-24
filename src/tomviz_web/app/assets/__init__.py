from trame.assets.local import LocalFileManager

ASSETS = LocalFileManager(__file__)

# View
ASSETS.url("v_palette", "./view/Palette.svg")
ASSETS.url("PickCenter", "./view/PickCenter.svg")
ASSETS.url("ResetCamera", "./view/ResetCamera.svg")
ASSETS.url("ResetCenter", "./view/ResetCenter.svg")
ASSETS.url("RotateCameraCCW", "./view/RotateCameraCCW.svg")
ASSETS.url("RotateCameraCW", "./view/RotateCameraCW.svg")
ASSETS.url("ShowCenterAxes", "./view/ShowCenterAxes.svg")
ASSETS.url("ShowOrientationAxes", "./view/ShowOrientationAxes.svg")
ASSETS.url("XMinus", "./view/XMinus.svg")
ASSETS.url("XPlus", "./view/XPlus.svg")
ASSETS.url("YMinus", "./view/YMinus.svg")
ASSETS.url("YPlus", "./view/YPlus.svg")
ASSETS.url("ZMinus", "./view/ZMinus.svg")
ASSETS.url("ZPlus", "./view/ZPlus.svg")
